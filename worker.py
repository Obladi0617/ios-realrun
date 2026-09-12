import argparse
import asyncio
import sys


async def check_device():
    from pymobiledevice3.lockdown import create_using_usbmux

    device = await create_using_usbmux()
    print(f"设备已连接：iOS {device.all_values.get('ProductVersion')} / {device.all_values.get('BuildVersion')}", flush=True)


async def mount_image():
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.exceptions import AlreadyMountedError
    from pymobiledevice3.services.mobile_image_mounter import auto_mount

    device = await create_using_usbmux()
    try:
        await auto_mount(device)
    except AlreadyMountedError:
        print("开发者镜像已挂载，继续运行", flush=True)
    else:
        print("开发者镜像挂载成功", flush=True)


def run_main(args):
    import config

    config.config.routeConfig = args.route
    config.config.v = args.speed
    print("正在准备设备和开发者镜像...", flush=True)
    asyncio.run(mount_image())
    import main

    sys.argv = ["main.py"]
    if args.minutes > 0:
        sys.argv.extend(("--minutes", str(args.minutes)))
    asyncio.run(main.main())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--mount", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--route", default="ZJGroute.txt")
    parser.add_argument("--speed", type=float, default=4.8)
    parser.add_argument("--minutes", type=int, default=30)
    args = parser.parse_args()
    if args.check:
        asyncio.run(check_device())
    elif args.mount:
        asyncio.run(mount_image())
    elif args.run:
        run_main(args)
    else:
        parser.error("需要指定 --check、--mount 或 --run")


if __name__ == "__main__":
    main()