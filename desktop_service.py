"""Desktop jobs and state. The web UI and CLI tests use the same controller."""

from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
import json
import ctypes
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

from app_info import APP_VERSION
from app_settings import DEFAULTS, ROUTES, data_dir, load_settings, save_settings, validate_run
from android_workspace import app_inventory, ensure_device, open_app, restart_device
from android_performance import GRAPHICS_MODES, MIRROR_VIDEO_OPTIONS
from desktop_tools import APPS, download_app, ensure_scrcpy
from external_process import external_popen, external_run
from session_control import RunStopped, STOP_FILE_ENV, raise_if_stopped
from telemetry import PREFIX


ROOT = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class DesktopService:
    def __init__(self, storage=None, headless=False):
        self.storage = Path(storage) if storage else data_dir()
        self.storage.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.storage / "settings.json"
        self.settings = load_settings(self.settings_path)
        if not self.settings_path.exists() and Path("D:/Android/Sdk/emulator/emulator.exe").is_file():
            self.settings.update(backend="android", sdk="D:/Android/Sdk")
        self.headless = headless
        self.lock = threading.RLock()
        self.thread = self.process = self.mirror = self.phone_thread = None
        self.stop_flag = None
        self.stopping = self.closing = False
        self.log_sequence = 0
        self.logs = deque(maxlen=400)
        self.points = []
        self.state = {
            "task": {"status": "idle", "label": "等待操作", "action": ""},
            "device": {"status": "unknown", "serial": "", "label": "设备尚未检查"},
            "apps": {key: {"name": app["name"], "installed": None, "version": ""} for key, app in APPS.items()},
            "phone": {"status": "closed"},
            "update": {"status": "idle"},
            "run": {"id": "", "status": "idle", "cursor": 0, "pointCount": 0, "distance": 0, "elapsed": 0, "speed": 0, "reason": ""},
        }
        self.pick_file = None
        self.request_close = None
        self.open_map_window = None
        self.elevate = None
        self.message("工作台已就绪。")

    def message(self, text):
        text = ANSI.sub("", str(text)).strip()[:6000]
        if not text:
            return
        with self.lock:
            self.log_sequence += 1
            entry = {"id": self.log_sequence, "text": text, "time": datetime.now().strftime("%H:%M:%S")}
            self.logs.append(entry)
            if self.state["task"]["status"] == "busy":
                self.state["task"]["label"] = text[:100]
        try:
            path = self.storage / "desktop.log"
            if path.exists() and path.stat().st_size > 2 * 1024 * 1024:
                path.replace(path.with_suffix(".previous.log"))
            with path.open("a", encoding="utf-8") as output:
                output.write(f"{entry['time']} {text}\n")
        except OSError:
            pass

    def snapshot(self, cursor=0, run_id="", log_cursor=0):
        with self.lock:
            result = json.loads(json.dumps(self.state))
            result.update(version=APP_VERSION, settings=dict(self.settings), busy=self.thread is not None and self.thread.is_alive(), stopping=self.stopping)
            result["capabilities"] = {"nativeWindows": not self.headless, "admin": self.is_admin()}
            reset = run_id != self.state["run"]["id"]
            result["run"]["reset"] = reset
            result["run"]["points"] = [dict(point) for point in self.points if reset or point["sequence"] > cursor]
            result["logs"] = [dict(line) for line in self.logs if line["id"] > log_cursor]
            result["logCursor"] = self.log_sequence
            for key in APPS:
                result["apps"][key]["confirmedAt"] = self.settings.get("login_" + key, "")
            if self.mirror is not None and self.mirror.poll() is not None:
                result["phone"] = self.state["phone"] = {"status": "closed"}
                self.mirror = None
            return result

    def save_preferences(self, values):
        if not isinstance(values, dict) or set(values) - set(DEFAULTS):
            raise ValueError("设置字段无效。")
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                raise ValueError("请先停止当前任务再修改设置。")
            settings = {**self.settings, **{key: str(value) for key, value in values.items()}}
            validate_run(settings["speed"], settings["minutes"])
            if settings["backend"] not in ("ios", "android") or settings["route"] not in ROUTES or settings["app"] not in APPS:
                raise ValueError("设备类型、应用或路线无效。")
            if settings["profile"] not in ("constant", "steady", "recreational", "variable"):
                raise ValueError("配速档位无效。")
            if settings["android_gpu"] not in GRAPHICS_MODES:
                raise ValueError("Android 图形模式无效。")
            if settings["serial"] and not re.fullmatch(r"emulator-\d+", settings["serial"]):
                raise ValueError("Android 设备编号必须是 emulator-5554 等模拟器编号。")
            if settings["android_home"] and not settings["android_home"].isascii():
                raise ValueError("虚拟手机目录请使用英文路径。")
            changed_device = any(settings[key] != self.settings[key] for key in ("sdk", "avd", "android_home", "serial"))
            if settings["backend"] != self.settings["backend"]:
                self.state["device"] = {"status": "unknown", "serial": "", "label": "设备尚未检查"}
            if changed_device:
                settings.update(login_tyys="", login_ding="")
                self.state["device"] = {"status": "unknown", "serial": "", "label": "设备尚未检查"}
            save_settings(settings, self.settings_path)
            self.settings = settings
        return {"ok": True, "settings": dict(settings)}

    def route(self, name):
        if name not in ROUTES:
            raise ValueError("未知路线。")
        from run import route_wgs84
        from util.route import load_route
        positions = route_wgs84(load_route(ROOT / name))
        return {"name": name, "coordinates": [[point["lat"], point["lng"]] for point in positions], "coordinateSystem": "WGS84"}

    def _consume_event(self, event):
        with self.lock:
            if event.get("type") == "location":
                try:
                    fields = {key: float(event[key]) for key in ("latitude", "longitude", "distance", "elapsed", "speed")}
                    sequence = int(event["sequence"])
                except (KeyError, TypeError, ValueError, OverflowError):
                    return
                if not all(math.isfinite(value) for value in fields.values()) or not (-90 <= fields["latitude"] <= 90 and -180 <= fields["longitude"] <= 180):
                    return
                if sequence <= self.state["run"]["cursor"] or min(fields["distance"], fields["elapsed"], fields["speed"]) < 0:
                    return
                point = {"sequence": sequence, **fields}
                self.points.append(point)
                if len(self.points) > 8192:
                    self.points = self.points[::2]
                    if self.points[-1]["sequence"] != sequence:
                        self.points.append(point)
                self.state["run"].update(status="running", cursor=sequence, pointCount=sequence,
                                         distance=fields["distance"], elapsed=fields["elapsed"], speed=fields["speed"],
                                         lastFixAt=time.time())
            elif event.get("type") == "run_state":
                self.state["run"].update(status=event.get("state", "unknown"), reason=event.get("reason", ""))
                if event.get("state") == "stopped":
                    self.state["run"]["speed"] = 0.0

    def _worker(self, arguments):
        command = [str(APP_DIR / "iOSRealRun-worker.exe")] if getattr(sys, "frozen", False) else [sys.executable, str(ROOT / "worker.py")]
        environment = dict(os.environ, PYTHONIOENCODING="utf-8", IOSREALRUN_EVENTS="1", IOSREALRUN_DATA_DIR=str(self.storage))
        environment[STOP_FILE_ENV] = str(self.stop_flag)
        process = subprocess.Popen([*command, *arguments, "--events"], cwd=ROOT, env=environment,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        with self.lock:
            self.process = process
        try:
            for line in process.stdout:
                if line.startswith(PREFIX):
                    try:
                        event = json.loads(line[len(PREFIX):])
                        if isinstance(event, dict):
                            self._consume_event(event)
                    except (ValueError, TypeError):
                        self.message("收到无法识别的位置事件。")
                else:
                    self.message(line)
            code = process.wait()
            if code:
                raise RuntimeError(f"任务退出码 {code}，请查看运行日志。")
            return code
        finally:
            process.stdout.close()
            with self.lock:
                self.process = None

    def _device(self):
        device = ensure_device(dict(self.settings), self.message)
        with self.lock:
            self.state["device"] = {"status": "ready", "serial": device.serial, "label": "Android 虚拟手机已就绪"}
        return device

    def _inventory(self, device):
        inventory = app_inventory(device)
        with self.lock:
            self.state["apps"] = inventory
        return inventory

    def _progress(self, label):
        last = [0.0]

        def update(done, total):
            raise_if_stopped()
            now = time.monotonic()
            if now - last[0] < 0.5 and done != total:
                return
            last[0] = now
            detail = f"{done * 100 // total}%" if total else f"{done // 1048576} MB"
            self.message(f"{label} {detail}")
        return update

    def _mirror(self, device):
        if self.headless:
            raise RuntimeError("命令行服务模式不启动可见手机窗口；可使用 prepare_phone 准备工具。")
        if self.mirror is not None and self.mirror.poll() is None:
            self.message("手机窗口已打开。")
            return
        self.message("正在准备手机窗口工具…")
        tool = ensure_scrcpy(self._progress("下载手机窗口工具"), self.settings.get("scrcpy", ""))
        raise_if_stopped()
        if self.closing:
            raise RunStopped()
        log_path = self.storage / "phone-window.log"
        if log_path.exists() and log_path.stat().st_size > 2 * 1024 * 1024:
            log_path.replace(log_path.with_suffix(".previous.log"))
        with log_path.open("ab") as log:
            self.mirror = external_popen([str(tool), "--serial", device.serial, "--no-audio", "--no-clipboard-autosync",
                                          "--window-title", "RealRun · 虚拟手机", *MIRROR_VIDEO_OPTIONS],
                                         cwd=tool.parent, env=dict(os.environ, ADB=device.adb),
                                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=NO_WINDOW)
        # A short wait catches missing DLLs or incompatible command-line options.
        time.sleep(0.6)
        if self.mirror.poll() is not None:
            self.mirror = None
            raise RuntimeError("手机窗口启动失败，请查看 phone-window.log。")
        with self.lock:
            self.state["phone"] = {"status": "open"}
        self.message("手机窗口已打开，请在官方 App 中完成登录。")

    def hide_phone(self):
        with self.lock:
            process, self.mirror = self.mirror, None
            self.state["phone"] = {"status": "closed"}
        if process is not None and process.poll() is None:
            process.terminate()
        return {"ok": True}

    def _perform(self, action, values):
        backend = self.settings["backend"]
        key = values.get("app", self.settings["app"])
        if action == "check":
            if backend == "android":
                self._inventory(self._device())
            else:
                self._worker(["--check"])
                raise_if_stopped()
                with self.lock:
                    self.state["device"] = {"status": "ready", "serial": "", "label": "iOS 设备已连接"}
        elif action == "mount":
            if backend != "ios":
                raise ValueError("Android 模拟器不需要挂载开发者镜像。")
            self._worker(["--mount"])
        elif action == "run":
            arguments = ["--run", "--route", self.settings["route"], "--speed", self.settings["speed"], "--minutes", self.settings["minutes"], "--profile", self.settings["profile"]]
            if backend == "android":
                device = self._device()
                arguments.extend(("--backend", "android", "--sdk", str(Path(device.adb).parent.parent), "--serial", device.serial))
            self._worker(arguments)
            with self.lock:
                self.state["run"]["status"] = "stopped"
        elif action in ("prepare_app", "open_app", "update_app", "install_apk"):
            if backend != "android":
                raise ValueError("应用与手机窗口功能请切换到 Android 模式。")
            if key not in APPS:
                raise ValueError("未知应用。")
            device = self._device()
            inventory = self._inventory(device)
            if action == "install_apk":
                path = values.get("path")
                if not path:
                    if not self.pick_file:
                        raise ValueError("命令行模式安装 APK 时需要提供 path。")
                    path = self.pick_file()
                if not path:
                    raise RunStopped()
                self.message(device.install_apk(path))
            elif not inventory[key]["installed"] or action == "update_app":
                self.message("正在获取" + APPS[key]["name"] + "官方 APK…")
                path = download_app(key, self._progress("下载 APK"))
                self.message("正在安装 APK…")
                self.message(device.install_apk(path))
            self._inventory(device)
            if action == "open_app":
                open_app(device, key)
                self._mirror(device)
            self.message(APPS[key]["name"] + "已准备，登录状态需在 App 中确认。")
        elif action == "restart_phone":
            if backend != "android":
                raise ValueError("重启虚拟手机请切换到 Android 模式。")
            self.hide_phone()
            with self.lock:
                self.state["device"] = {"status": "starting", "serial": "", "label": "虚拟手机正在重启"}
            device = restart_device(dict(self.settings), self.message)
            with self.lock:
                self.state["device"] = {"status": "ready", "serial": device.serial, "label": "Android 虚拟手机已就绪"}
            self._inventory(device)
            self.message("虚拟手机已重启；可重新打开手机窗口继续使用。")
        elif action in ("phone_show", "prepare_phone"):
            if backend != "android":
                raise ValueError("手机窗口功能请切换到 Android 模式。")
            if action == "prepare_phone":
                tool = ensure_scrcpy(self._progress("下载手机窗口工具"), self.settings.get("scrcpy", ""))
                self.message("手机窗口工具已就绪：" + str(tool))
            else:
                self._mirror(self._device())
        elif action == "check_update":
            from app_update import latest_update
            update = latest_update()
            with self.lock:
                self.state["update"] = {"status": "available", **asdict(update)} if update else {"status": "latest", "version": APP_VERSION}
        elif action == "download_update":
            from app_update import Update, download_update
            with self.lock:
                update = dict(self.state["update"])
            if update.get("status") != "available":
                raise ValueError("请先检查新版本。")
            path = download_update(Update(**{key: update[key] for key in ("version", "url", "size", "sha256")}), progress=self._progress("下载安装包"))
            with self.lock:
                self.state["update"].update(status="ready", path=str(path))
        elif action == "install_update":
            if self.headless:
                raise ValueError("命令行服务模式不启动安装向导。")
            path = self.state["update"].get("path")
            if self.state["update"].get("status") != "ready" or not path or not Path(path).is_file():
                raise ValueError("请先下载新版本。")
            self.hide_phone()
            external_popen([path, f"/DIR={APP_DIR}", "/NORESTART"], creationflags=NO_WINDOW)
            if self.request_close:
                threading.Timer(0.5, self.request_close).start()
        else:
            raise ValueError("未知操作。")

    def dispatch(self, action, values=None):
        values = values or {}
        if not isinstance(values, dict):
            raise ValueError("操作参数无效。")
        if action == "stop":
            return self.stop()
        if action == "phone_hide":
            return self.hide_phone()
        if action in ("map_window", "elevate"):
            callback = self.open_map_window if action == "map_window" else self.elevate
            if not callback:
                raise ValueError("当前命令行服务不创建可见窗口。")
            callback()
            return {"ok": True}
        if action == "phone_show" and self.state["task"].get("action") == "run" and self.thread is not None and self.thread.is_alive():
            if self.settings["backend"] != "android":
                raise ValueError("手机窗口功能请切换到 Android 模式。")
            if self.headless:
                raise ValueError("当前命令行服务不创建可见手机窗口。")
            if self.phone_thread is not None and self.phone_thread.is_alive():
                return {"ok": True}

            def phone_work():
                from android_emulator import AndroidEmulator
                try:
                    device = AndroidEmulator(self.settings["sdk"] or None, self.state["device"]["serial"])
                    device.check()
                    self._mirror(device)
                except Exception as error:
                    with self.lock:
                        self.state["phone"] = {"status": "error", "error": str(error)}
                    self.message(str(error))
            self.phone_thread = threading.Thread(target=phone_work, name="realrun-phone", daemon=True)
            self.phone_thread.start()
            return {"ok": True}
        if action == "confirm_login":
            key = values.get("app", self.settings["app"])
            if key not in APPS:
                raise ValueError("未知应用。")
            return self.save_preferences({"login_" + key: datetime.now(timezone.utc).isoformat() if values.get("confirmed", True) else ""})
        allowed = {"check", "mount", "run", "prepare_app", "open_app", "update_app", "install_apk", "phone_show", "prepare_phone", "restart_phone", "check_update", "download_update", "install_update"}
        if action not in allowed:
            raise ValueError("未知操作。")
        with self.lock:
            if self.closing or self.thread is not None and self.thread.is_alive():
                raise ValueError("已有任务正在进行，请先停止或等待完成。")
            self.stopping = False
            self.stop_flag = self.storage / ("stop-" + uuid.uuid4().hex + ".flag")
            self.state["task"] = {"status": "busy", "label": "正在准备…", "action": action}
            if action == "run":
                self.points = []
                self.state["run"] = {"id": uuid.uuid4().hex, "status": "starting", "cursor": 0, "pointCount": 0, "distance": 0, "elapsed": 0, "speed": 0, "reason": "", "route": self.settings["route"]}

            def work():
                previous = {key: os.environ.get(key) for key in (STOP_FILE_ENV, "IOSREALRUN_DATA_DIR")}
                os.environ.update({STOP_FILE_ENV: str(self.stop_flag), "IOSREALRUN_DATA_DIR": str(self.storage)})
                try:
                    self._perform(action, values)
                    with self.lock:
                        self.state["task"].update(status="stopped" if self.stopping else "success", label="已停止" if self.stopping else "操作完成")
                except RunStopped:
                    with self.lock:
                        self.state["task"].update(status="stopped", label="已停止")
                        if action == "run":
                            self.state["run"].update(status="stopped", reason="stopped", speed=0.0)
                except Exception as error:
                    self.message(str(error))
                    with self.lock:
                        self.state["task"].update(status="error", label=str(error))
                        if action == "run":
                            self.state["run"].update(status="error", reason=str(error), speed=0.0)
                        if action in ("check", "restart_phone"):
                            self.state["device"].update(status="error", label=str(error))
                finally:
                    self.stop_flag.unlink(missing_ok=True)
                    for key, value in previous.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value
                    with self.lock:
                        self.stopping = False

            self.thread = threading.Thread(target=work, name="realrun-job", daemon=True)
            self.thread.start()
        return {"ok": True}

    def stop(self):
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                return {"ok": True}
            self.stopping = True
            flag = self.stop_flag
            flag.write_text("stop", encoding="utf-8")
            self.state["task"]["label"] = "正在停止，请等待定位连接清理…"
            process = self.process
        if process is not None:
            def wait():
                try:
                    process.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    if process.poll() is None:
                        self.message("定位进程没有及时退出，正在强制结束。")
                        if os.name == "nt":
                            external_run(["taskkill", "/F", "/T", "/PID", str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW, check=False, timeout=10)
                        else:
                            process.kill()
            threading.Thread(target=wait, daemon=True).start()
        return {"ok": True}

    def close(self):
        self.closing = True
        self.stop()
        self.hide_phone()
        if self.thread is not None:
            self.thread.join(timeout=35)
        if self.phone_thread is not None:
            self.phone_thread.join(timeout=3)
        self.hide_phone()

    @staticmethod
    def is_admin():
        return bool(ctypes.windll.shell32.IsUserAnAdmin()) if os.name == "nt" else True
