"""A stable Android home and AVD, shared by startup, app login and route jobs."""

import asyncio
import os
from pathlib import Path
import re
import time

from android_emulator import AndroidEmulator, find_tool, run_command
from android_performance import optimize_display
from desktop_tools import APPS
from external_process import external_run
from session_control import raise_if_stopped


def configure(settings):
    emulator = Path(find_tool("emulator", settings.get("sdk") or None)).resolve()
    sdk = emulator.parent.parent
    root = Path(settings.get("android_home") or sdk.parent / "RealRunTest").expanduser().resolve()
    if not str(root).isascii():
        raise ValueError("虚拟手机数据目录请使用英文路径，例如 D:\\Android\\RealRunTest。")
    for name in ("avd", "state", "discovery"):
        (root / name).mkdir(parents=True, exist_ok=True)
    values = {"ANDROID_HOME": str(sdk), "ANDROID_USER_HOME": str(root), "ANDROID_EMULATOR_HOME": str(root),
              "ANDROID_AVD_HOME": str(root / "avd"), "ANDROID_EMULATOR_DISCOVERY_DIR": str(root / "discovery")}
    os.environ.update(values)
    return sdk, root


def ensure_device(settings, message=lambda _: None):
    sdk, root = configure(settings)
    avd = settings.get("avd") or "RealRun_Android15"
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", avd):
        raise ValueError("AVD 名称只能包含英文字母、数字、下划线和连字符。")
    device = AndroidEmulator(str(sdk), settings.get("serial") or None)
    for serial, status in device.devices():
        if status != "device" or device.serial and serial != device.serial:
            continue
        candidate = AndroidEmulator(str(sdk), serial)
        try:
            name = candidate.command("emu", "avd", "name").splitlines()[0]
            if name != avd and not device.serial:
                continue
            candidate.check()
        except RuntimeError:
            continue
        optimize_display(candidate, message)
        return candidate
    raise_if_stopped()
    available = device.avds()
    if avd not in available:
        image = sdk / "system-images" / "android-35" / "google_apis" / "x86_64"
        manager = sdk / "cmdline-tools" / "latest" / "bin" / "avdmanager.bat"
        if not image.is_dir() or not manager.is_file():
            raise RuntimeError("请先安装 Android SDK 的 cmdline-tools 与 Android 15 Google APIs x86_64 镜像，然后在设置中选择 SDK。")
        message("正在创建固定虚拟手机…")
        result = external_run([str(manager), "create", "avd", "--name", avd, "--package", "system-images;android-35;google_apis;x86_64", "--device", "pixel_5"],
                              input="no\n", capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
                              creationflags=getattr(__import__('subprocess'), "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "创建虚拟手机失败，请检查 JDK。")
    message("正在启动虚拟手机，等待 Android 开机…")
    asyncio.run(device.start(avd, headless=True, graphics=settings.get("android_gpu") or "auto"))
    device.check()
    optimize_display(device, message)
    return device


def app_inventory(device):
    installed = set(device.command("shell", "pm", "list", "packages").splitlines())
    result = {}
    for key, app in APPS.items():
        exists = "package:" + app["package"] in installed
        version = ""
        if exists:
            package = device.command("shell", "dumpsys", "package", app["package"])
            match = re.search(r"\bversionName=([^\s]+)", package)
            version = match[1] if match else ""
        result[key] = {"name": app["name"], "package": app["package"], "installed": exists, "version": version}
    return result


def restart_device(settings, message=lambda _: None):
    device = ensure_device(settings, message)
    avd = device.command("emu", "avd", "name").splitlines()[0].strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", avd):
        raise RuntimeError("无法确认当前虚拟设备名称，已取消重启。")
    if not settings.get("serial") and avd != (settings.get("avd") or "RealRun_Android15"):
        raise RuntimeError("当前虚拟设备与所选设备不一致，已取消重启。")
    raise_if_stopped()
    message("正在关闭所选虚拟手机，保留应用数据…")
    device.command("emu", "kill")
    begin = time.monotonic()
    while time.monotonic() - begin < 45:
        raise_if_stopped()
        if device.serial not in dict(device.devices()) and time.monotonic() - begin >= 4:
            break
        time.sleep(.5)
    else:
        raise RuntimeError("虚拟手机未能及时退出，请稍后重试。")
    message("正在使用新的性能设置启动虚拟手机…")
    asyncio.run(device.start(avd, headless=True, graphics=settings.get("android_gpu") or "auto"))
    device.check()
    optimize_display(device, message)
    return device


def open_app(device, key):
    if key not in APPS:
        raise ValueError("未知应用。")
    app = APPS[key]
    result = device.command("shell", "am", "start", "-W", "-a", "android.intent.action.MAIN",
                            "-c", "android.intent.category.LAUNCHER", "-f", "0x10200000",
                            "-n", app["package"] + "/" + app["activity"], timeout=60)
    if "Error:" in result or "Status: timeout" in result:
        raise RuntimeError(result)
    return result
