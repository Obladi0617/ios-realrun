import argparse
import asyncio
import multiprocessing
import os
import sys
from pathlib import Path

from app_info import APP_VERSION
from app_settings import DEFAULTS, validate_run
from session_control import RunStopped, interruptible_sleep, raise_if_stopped


def apply_profile(variation, profile):
    result = dict(variation or {})
    if profile:
        for key in ("cvPercent", "correlationTime", "fatiguePercent", "lapPercent"):
            result.pop(key, None)
        result["profile"] = profile
    return result


async def check_device():
    from driver.connect import get_usbmux_lockdownclient

    device = await get_usbmux_lockdownclient()
    print(f"设备已连接：iOS {device.all_values.get('ProductVersion')} / {device.all_values.get('BuildVersion')}", flush=True)


async def mount_image():
    from driver.connect import get_usbmux_lockdownclient
    from pymobiledevice3.exceptions import AlreadyMountedError
    from pymobiledevice3.exceptions import MessageNotSupportedError
    from pymobiledevice3.services.mobile_image_mounter import (
        MobileImageMounterService,
        auto_mount,
    )

    device = await get_usbmux_lockdownclient()

    async def mounted_image_types():
        async with MobileImageMounterService(device) as mounter:
            try:
                devices = await mounter.copy_devices()
            except MessageNotSupportedError:
                devices = []

            mounted = [
                "DeveloperDiskImage"
                for entry in devices
                if entry.get("IsMounted")
                and entry.get("MountPath") == "/System/Developer"
            ]
            if mounted:
                return mounted

            mounted = []
            for image_type in ("Developer", "Personalized"):
                if await mounter.is_image_mounted(image_type):
                    mounted.append(image_type)
            return mounted

    mounted = await mounted_image_types()
    if mounted:
        print(f"开发者镜像已挂载（{', '.join(mounted)}），继续运行", flush=True)
        return

    try:
        await auto_mount(device)
    except AlreadyMountedError:
        print("开发者镜像已挂载，继续运行", flush=True)
    except Exception:
        # Mount can report a failure after the device has finished mounting.
        # Only treat that as success when the device confirms a mounted image.
        try:
            mounted = await mounted_image_types()
        except Exception:
            mounted = []
        if not mounted:
            raise
        print(f"开发者镜像已挂载（{', '.join(mounted)}），继续运行", flush=True)
    else:
        print("开发者镜像挂载成功", flush=True)


async def start_tunnel():
    from pymobiledevice3.cli.lockdown import async_cli_start_tunnel
    from pymobiledevice3.lockdown import create_using_usbmux

    await async_cli_start_tunnel(await create_using_usbmux(), script_mode=True)


def run_main(args):
    import config

    config.config.routeConfig = str((Path(__file__).resolve().parent / args.route).resolve())
    config.config.v = args.speed
    if args.profile:
        config.config.speedVariation = apply_profile(getattr(config.config, "speedVariation", None), args.profile)
    print("正在准备设备和开发者镜像...", flush=True)
    asyncio.run(mount_image())
    asyncio.run(interruptible_sleep(0.2))
    import main

    sys.argv = ["main.py"]
    if args.minutes > 0:
        sys.argv.extend(("--minutes", str(args.minutes)))
    asyncio.run(main.main())


async def android_action(args):
    from android_emulator import AndroidEmulator, run_android

    device = AndroidEmulator(args.sdk or None, args.serial or None)
    if args.list_android:
        devices = await asyncio.to_thread(device.devices)
        print("Android 模拟器：" + ("、".join(f"{serial} ({state})" for serial, state in devices) or "无"), flush=True)
        try:
            print("可用 AVD：" + ("、".join(await asyncio.to_thread(device.avds)) or "无，请先创建虚拟设备"), flush=True)
        except RuntimeError as error:
            print(str(error), flush=True)
    elif args.start_emulator:
        from android_performance import optimize_display
        print("Android 模拟器已就绪：" + await device.start(args.avd, headless=args.headless, graphics=args.gpu), flush=True)
        await asyncio.to_thread(optimize_display, device, lambda text: print(text, flush=True))
    elif args.install_apk:
        print(await asyncio.to_thread(device.install_apk, args.install_apk), flush=True)
        print("APK 安装完成。请在模拟器内打开应用并登录。", flush=True)
    elif args.check:
        print("Android 模拟器已就绪：" + await asyncio.to_thread(device.check), flush=True)
    elif args.run:
        import config
        from util.route import parse_route

        route_path = (Path(__file__).resolve().parent / args.route).resolve()
        loc = parse_route(route_path.read_text(encoding="utf-8"))
        variation = apply_profile(getattr(config.config, "speedVariation", {}), args.profile)
        await run_android(loc, args.speed, args.minutes, variation, args.sdk, args.serial)
    else:
        raise ValueError("Android 模式支持 --check、--run、--list-android、--start-emulator、--install-apk。")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=APP_VERSION)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--tunnel", action="store_true")
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--mount", action="store_true")
    actions.add_argument("--run", action="store_true")
    actions.add_argument("--list-android", action="store_true")
    actions.add_argument("--start-emulator", action="store_true")
    actions.add_argument("--install-apk", metavar="APK")
    parser.add_argument("--backend", choices=("ios", "android"), default="ios")
    parser.add_argument("--sdk", default="")
    parser.add_argument("--serial", default="")
    parser.add_argument("--avd", default="")
    parser.add_argument("--headless", action="store_true", help="启动 Android 模拟器时不显示窗口")
    parser.add_argument("--gpu", choices=("auto", "host", "swiftshader"), default="auto", help="Android 图形模式，默认自动选择显卡加速")
    parser.add_argument("--events", action="store_true", help="输出桌面工作台使用的结构化位置事件")
    parser.add_argument("--route", default="ZJGroute.txt")
    parser.add_argument("--speed", type=float, default=float(DEFAULTS["speed"]))
    parser.add_argument("--profile", default=None)
    parser.add_argument("--minutes", type=int, default=30)
    args = parser.parse_args()
    if args.events:
        os.environ["IOSREALRUN_EVENTS"] = "1"
    try:
        validate_run(args.speed, args.minutes)
        raise_if_stopped()
        if args.backend == "android":
            asyncio.run(android_action(args))
        elif args.list_android or args.start_emulator or args.install_apk:
            parser.error("Android 操作需要 --backend android")
        elif args.tunnel:
            asyncio.run(start_tunnel())
        elif args.check:
            asyncio.run(check_device())
        elif args.mount:
            asyncio.run(mount_image())
        elif args.run:
            run_main(args)
        else:
            parser.error("需要指定 --check、--mount 或 --run")
    except RunStopped:
        print("操作已停止", flush=True)
    except KeyboardInterrupt:
        print("操作已取消", flush=True)
        raise SystemExit(130)
    except Exception as error:
        print(f"错误：{error}", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
