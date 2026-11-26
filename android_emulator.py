"""Official Android Emulator support; no iOS dependencies or device spoofing."""

import asyncio
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from app_settings import data_dir
from android_performance import GRAPHICS_MODES, graphics_failure, launch_resources
from external_process import external_popen, external_run
from session_control import interruptible_sleep, raise_if_stopped


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class GraphicsStartupError(RuntimeError):
    pass


def sdk_roots(sdk=None):
    roots = [sdk, os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")]
    if os.environ.get("LOCALAPPDATA"):
        roots.append(str(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk"))
    roots.extend((str(Path.home() / "Android" / "Sdk"), "D:/Android/Sdk"))
    return [Path(root).expanduser() for root in roots if root]


def find_tool(name, sdk=None):
    filename = name + (".exe" if os.name == "nt" else "")
    folder = "platform-tools" if name == "adb" else "emulator"
    for root in sdk_roots(sdk):
        candidate = root / folder / filename
        if candidate.is_file():
            return str(candidate)
    if not sdk:
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError(f"未找到 {name}。请安装 Android SDK 的 {folder} 组件，并选择 SDK 目录。")


def run_command(command, timeout=15):
    environment = os.environ.copy()
    if Path(command[0]).stem.lower() == "adb":
        # Some Windows installations have an unwritable adb.log in the shared temp folder.
        temporary = data_dir() / "android-temp"
        temporary.mkdir(parents=True, exist_ok=True)
        environment.update({name: str(temporary) for name in ("TMP", "TEMP", "TMPDIR")})
    try:
        result = external_run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout,
                                stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW,
                                env=environment, check=False)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Android 命令超时，请确认模拟器已启动。") from error
    if result.returncode:
        raise RuntimeError(result.stdout.strip() or "Android 命令执行失败。")
    return result.stdout.strip()


class AndroidEmulator:
    def __init__(self, sdk=None, serial=None):
        self.sdk = sdk
        self.adb = find_tool("adb", sdk)
        self.serial = serial or None

    def devices(self):
        output = run_command([self.adb, "devices"])
        devices = []
        for line in output.splitlines():
            fields = line.split()
            if len(fields) >= 2 and re.fullmatch(r"emulator-\d+", fields[0]):
                devices.append((fields[0], fields[1]))
        return devices

    def select(self):
        devices = self.devices()
        ready = [serial for serial, state in devices if state == "device"]
        if self.serial:
            if self.serial not in ready:
                raise RuntimeError(f"模拟器 {self.serial} 未就绪，请先启动并等待开机。")
        elif len(ready) == 1:
            self.serial = ready[0]
        elif len(ready) > 1:
            raise RuntimeError("检测到多个模拟器，请填写设备编号：" + "、".join(ready))
        else:
            raise RuntimeError("未检测到已启动的 Android Emulator。请先创建并启动虚拟设备。")
        return self.serial

    def command(self, *args, timeout=15):
        if not self.serial:
            self.select()
        return run_command([self.adb, "-s", self.serial, *args], timeout=timeout)

    def check(self):
        self.select()
        if self.command("shell", "getprop", "sys.boot_completed") != "1":
            raise RuntimeError("Android 模拟器正在开机，请稍后重试。")
        return self.serial

    def install_apk(self, apk):
        path = Path(apk).expanduser().resolve()
        if path.suffix.lower() != ".apk" or not path.is_file():
            raise ValueError("请选择存在的 .apk 安装文件。")
        self.check()
        output = self.command("install", "-r", str(path), timeout=180)
        if "Success" not in output.splitlines():
            raise RuntimeError(output or "APK 安装失败。")
        return output

    def avds(self):
        emulator = find_tool("emulator", self.sdk)
        return [line.strip() for line in run_command([emulator, "-list-avds"]).splitlines() if line.strip()]

    async def start(self, avd, headless=False, graphics="auto"):
        if not avd or avd not in await asyncio.to_thread(self.avds):
            raise ValueError("请先在 Android Device Manager 创建虚拟设备，再填写它的 AVD 名称。")
        if graphics not in GRAPHICS_MODES:
            raise ValueError("图形模式必须是 auto、host 或 swiftshader。")
        memory, cores = launch_resources()
        # SDK auto can keep a software backend for a headless/older AVD even
        # when a GPU is available. Our auto policy tries the GPU, then retries
        # an actual driver initialization failure using the portable backend.
        selected = "host" if graphics == "auto" else graphics
        try:
            return await self._start_once(avd, headless, selected, memory, cores)
        except GraphicsStartupError:
            if graphics == "swiftshader":
                raise
            print("显卡初始化失败，正在改用软件兼容模式重试…", flush=True)
            return await self._start_once(avd, headless, "swiftshader", memory, cores)

    async def _start_once(self, avd, headless, graphics, memory, cores):
        emulator = find_tool("emulator", self.sdk)
        command = [emulator, "-avd", avd, "-no-boot-anim", "-gpu", graphics,
                   "-memory", str(memory), "-cores", str(cores)]
        if self.serial:
            match = re.fullmatch(r"emulator-(\d+)", self.serial)
            if not match or not 5554 <= int(match[1]) <= 5584 or int(match[1]) % 2:
                raise ValueError("启动端口需为 emulator-5554 至 emulator-5584 的偶数编号。")
            command.extend(("-port", match[1]))
        if headless:
            command.extend(("-no-window", "-no-audio"))
        binary_dir = Path(emulator).resolve().parent
        environment = os.environ.copy()
        # The QEMU child needs both the emulator's root DLLs and its lib64 DLLs.
        environment["PATH"] = os.pathsep.join((str(binary_dir), str(binary_dir / "lib64"), environment.get("PATH", "")))
        temporary = data_dir() / "android-temp"
        discovery = data_dir() / "android-discovery"
        temporary.mkdir(parents=True, exist_ok=True)
        discovery.mkdir(parents=True, exist_ok=True)
        environment.update({name: str(temporary) for name in ("TMP", "TEMP", "TMPDIR")})
        environment.setdefault("ANDROID_EMULATOR_DISCOVERY_DIR", str(discovery))
        log_path = data_dir() / "emulator-start.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if log_path.exists() and log_path.stat().st_size > 2 * 1024 * 1024:
            try:
                log_path.replace(log_path.with_suffix(".previous.log"))
            except OSError:
                # SDK crash-report helpers can keep the old log open on Windows.
                pass
        with log_path.open("ab") as log:
            log_start = log.tell()
            process = external_popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       creationflags=CREATE_NO_WINDOW, cwd=binary_dir, env=environment)
        print(f"已启动虚拟设备 {avd}（图形：{graphics}，内存：{memory} MB，{cores} 核），正在等待 Android 开机...", flush=True)
        try:
            return await self._wait_for_startup(avd, process, log_path, log_start)
        except BaseException:
            if process.poll() is None:
                if os.name == "nt":
                    await asyncio.to_thread(subprocess.run, ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            creationflags=CREATE_NO_WINDOW, timeout=10, check=False)
                else:
                    process.terminate()
            raise

    async def _wait_for_startup(self, avd, process, log_path, log_start=0):
        deadline = asyncio.get_running_loop().time() + 180
        while asyncio.get_running_loop().time() < deadline:
            raise_if_stopped()
            if process.poll() is not None:
                with log_path.open("rb") as log:
                    log.seek(max(log_start, log_path.stat().st_size - 65536))
                    tail = log.read().decode("utf-8", errors="replace")
                error = GraphicsStartupError if graphics_failure(tail) else RuntimeError
                raise error(f"模拟器启动失败（{process.returncode}），日志：{log_path}")
            if log_path.stat().st_size - log_start > 16 * 1024 * 1024:
                raise RuntimeError(f"模拟器启动日志异常增长，请查看：{log_path}")
            for serial, state in await asyncio.to_thread(self.devices):
                if state != "device":
                    continue
                candidate = AndroidEmulator(self.sdk, serial)
                try:
                    name = await asyncio.to_thread(candidate.command, "emu", "avd", "name")
                    if not name or name.splitlines()[0] != avd:
                        continue
                    booted = await asyncio.to_thread(candidate.command, "shell", "getprop", "sys.boot_completed") == "1"
                except RuntimeError:
                    continue
                if booted:
                    self.serial = serial
                    return serial
            await interruptible_sleep(2)
        raise RuntimeError("模拟器未在 180 秒内开机，请检查虚拟化支持或查看模拟器窗口。")


class EmulatorLocation:
    """Reuse one authenticated console connection for the complete route."""

    def __init__(self, serial, token_path=None, clock=None):
        match = re.fullmatch(r"emulator-(\d+)", serial)
        if not match or not 5554 <= int(match[1]) <= 5584 or int(match[1]) % 2:
            raise ValueError("设备编号必须是官方模拟器的 emulator-5554 等控制台编号。")
        self.port = int(match[1])
        self.token_path = Path(token_path) if token_path else Path.home() / ".emulator_console_auth_token"
        self.reader = self.writer = None
        self.clock = clock or time.monotonic
        self.last_fix = None
        self.last_fix_time = None

    async def response(self):
        lines = []
        for _ in range(64):
            data = await asyncio.wait_for(self.reader.readline(), timeout=5)
            if not data:
                raise RuntimeError("模拟器定位连接已断开。")
            line = data.decode("utf-8", errors="replace").strip()
            if line == "OK":
                return "\n".join(lines)
            if line.startswith("KO"):
                raise RuntimeError("模拟器定位命令失败：" + line)
            lines.append(line)
        raise RuntimeError("模拟器返回了无法识别的响应。")

    async def command(self, text):
        self.writer.write((text + "\n").encode("ascii"))
        await self.writer.drain()
        return await self.response()

    async def __aenter__(self):
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self.port), timeout=5)
            greeting = await self.response()
            if "Authentication required" in greeting:
                try:
                    token = self.token_path.read_text(encoding="utf-8").strip()
                except OSError as error:
                    raise RuntimeError("无法读取 Android 模拟器的控制台认证文件。") from error
                if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", token):
                    raise RuntimeError("Android 控制台认证文件格式无效。")
                await self.command("auth " + token)
            return self
        except BaseException:
            await self.__aexit__(None, None, None)
            raise

    async def __aexit__(self, *_):
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except OSError:
                pass

    async def set(self, latitude, longitude, *, stationary=False):
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("定位坐标超出有效范围。")
        now = self.clock()
        speed = 0.0
        if not stationary and self.last_fix is not None and now > self.last_fix_time:
            old_latitude, old_longitude = self.last_fix
            lat1, lat2 = math.radians(old_latitude), math.radians(latitude)
            dlat = lat2 - lat1
            dlon = math.radians(longitude - old_longitude)
            haversine = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            distance = 6371008.8 * 2 * math.asin(min(1.0, math.sqrt(haversine)))
            speed = min(100.0, distance / (now - self.last_fix_time))
        # Android's console takes velocity in knots, not metres per second.
        await self.command(f"geo fix {longitude:.8f} {latitude:.8f} 0 8 {speed * 1.94384449:.6f}")
        self.last_fix, self.last_fix_time = (latitude, longitude), now

    async def stop(self):
        if self.last_fix is not None:
            await self.set(*self.last_fix)


async def run_android(loc, speed, minutes, variation, sdk=None, serial=None):
    from run import follow_route

    device = AndroidEmulator(sdk, serial)
    serial = await asyncio.to_thread(device.check)
    print(f"Android 模拟器已连接：{serial}", flush=True)
    async with EmulatorLocation(serial) as location:
        print("Android 路线模拟已开始。停止后不再发送坐标，模拟器会保留最后的位置。", flush=True)
        try:
            await follow_route(location, loc, speed, minutes * 60 if minutes else None, variation)
        finally:
            try:
                await location.stop()
            except (RuntimeError, OSError, asyncio.TimeoutError) as error:
                print(f"停止时速度归零失败：{error}", flush=True)
            print("Android 路线推送已停止。", flush=True)
