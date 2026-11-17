import asyncio
import os
from pathlib import Path


STOP_FILE_ENV = "IOSREALRUN_STOP_FILE"


class RunStopped(Exception):
    """The user requested a graceful stop."""


def stop_requested():
    path = os.environ.get(STOP_FILE_ENV)
    return bool(path and Path(path).exists())


def raise_if_stopped():
    if stop_requested():
        raise RunStopped()


async def interruptible_sleep(seconds):
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        raise_if_stopped()
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return
        await asyncio.sleep(min(0.2, remaining))
