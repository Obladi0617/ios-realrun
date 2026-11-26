"""Own the USB RSD tunnel for both developer-image mounting and GPS services."""

import asyncio
import sys
from contextlib import asynccontextmanager, suppress

from packaging.version import Version

from session_control import raise_if_stopped


def run_async(coroutine):
    # DTX's SSL-stripping handshake requires a selector loop on Windows.
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
    with asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(coroutine)


async def preparing(awaitable, timeout=None):
    """Allow cancellation while a library call is opening a tunnel or downloading a DDI."""
    task = asyncio.ensure_future(awaitable)
    try:
        async with asyncio.timeout(timeout):
            while not task.done():
                raise_if_stopped()
                await asyncio.wait((task,), timeout=0.1)
            result = await task
            raise_if_stopped()
            return result
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def device_serial():
    from driver.connect import get_usbmux_lockdownclient

    device = await get_usbmux_lockdownclient()
    try:
        version = device.product_version
        print(f"设备已连接：iOS {version} / {device.all_values.get('BuildVersion')}", flush=True)
        if Version(version) < Version("17.4"):
            raise RuntimeError("当前 USB 定位通道需要 iOS 17.4 或更新版本。")
        if not await device.get_developer_mode_status():
            raise RuntimeError("请先在 iPhone 的设置 → 隐私与安全性中开启开发者模式。")
        return device.udid
    finally:
        await device.close()


@asynccontextmanager
async def device_tunnel(serial):
    from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel

    tunnel = UserspaceRsdTunnel(serial=serial, remotepairing_fallback=False)
    try:
        rsd = await preparing(tunnel.aopen(), timeout=45)
        if rsd.udid != serial:
            raise RuntimeError("连接的设备发生变化，请重新检查设备。")
        print("USB RSD 隧道已连接（普通权限）", flush=True)
        yield rsd
    finally:
        await tunnel.aclose()


async def check_device():
    serial = await device_serial()
    async with device_tunnel(serial):
        print("iPhone 开发者通道已就绪", flush=True)


async def mount_connected(rsd):
    from pymobiledevice3.exceptions import AlreadyMountedError
    from pymobiledevice3.services.mobile_image_mounter import auto_mount

    if await preparing(developer_services_ready(rsd), timeout=10):
        print("定位开发者服务已就绪，无需重复挂载镜像", flush=True)
        return
    try:
        await preparing(auto_mount(rsd))
    except AlreadyMountedError:
        print("开发者镜像已挂载，继续运行", flush=True)
    else:
        print("开发者镜像挂载成功", flush=True)


async def developer_services_ready(rsd):
    from pymobiledevice3.exceptions import InvalidServiceError
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

    if DvtProvider.RSD_SERVICE_NAME not in rsd.peer_info.get("Services", {}):
        return False
    try:
        async with DvtProvider(rsd) as dvt:
            async with LocationSimulation(dvt):
                return True
    except InvalidServiceError:
        return False


async def mount_image():
    serial = await device_serial()
    async with device_tunnel(serial) as rsd:
        await mount_connected(rsd)


@asynccontextmanager
async def developer_provider():
    serial = await device_serial()
    print("正在准备设备和开发者镜像...", flush=True)
    async with device_tunnel(serial) as rsd:
        await mount_connected(rsd)
    # Discover services again after mounting: the first handshake may precede DVT startup.
    # The second tunnel stays alive until clear() and both DTX contexts have closed.
    async with device_tunnel(serial) as rsd:
        yield rsd


async def run_ios(loc, speed, duration_seconds=None, variation=None):
    from run import run_on_provider

    async with developer_provider() as rsd:
        await run_on_provider(rsd, loc, speed, duration_seconds, variation)


async def hold_ios(point_file):
    from fixed_location import hold_point
    from run import ios_location

    async with developer_provider() as rsd, ios_location(rsd) as location:
        await hold_point(location.set, point_file)
