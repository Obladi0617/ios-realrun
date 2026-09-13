import asyncio
import time

from pymobiledevice3.lockdown import create_using_usbmux, LockdownClient
from pymobiledevice3.services.amfi import AmfiService
from pymobiledevice3.exceptions import NoDeviceConnectedError


DEVICE_WAIT_SECONDS = 60
RETRY_INTERVAL_SECONDS = 2


async def _connect_with_retry(timeout: float = DEVICE_WAIT_SECONDS) -> LockdownClient:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return await create_using_usbmux()
        except NoDeviceConnectedError as error:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "未检测到 iOS 设备：请用数据线连接设备、解锁屏幕并点击“信任此电脑”。"
                ) from error
            print("未检测到 iOS 设备，正在重试...", flush=True)
            await asyncio.sleep(RETRY_INTERVAL_SECONDS)


async def get_usbmux_lockdownclient() -> LockdownClient:
    lockdown = await _connect_with_retry()
    deadline = time.monotonic() + DEVICE_WAIT_SECONDS
    while lockdown.all_values.get("PasswordProtected"):
        if time.monotonic() >= deadline:
            raise RuntimeError("设备处于锁定状态：请解锁设备后重新开始。")
        print("设备已锁定，等待解锁...", flush=True)
        await asyncio.sleep(RETRY_INTERVAL_SECONDS)
        lockdown = await _connect_with_retry(timeout=RETRY_INTERVAL_SECONDS * 5)
    return lockdown


def get_version(lockdown: LockdownClient):
    return lockdown.all_values.get("ProductVersion")


async def get_developer_mode_status(lockdown: LockdownClient):
    return await lockdown.get_developer_mode_status()


async def reveal_developer_mode(lockdown: LockdownClient):
    await AmfiService(lockdown).reveal_developer_mode_option_in_ui()


async def enable_developer_mode(lockdown: LockdownClient):
    await AmfiService(lockdown).enable_developer_mode()
