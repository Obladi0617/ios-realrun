"""The desktop controller can change a held GPS point without reopening the device."""

import asyncio
import json
import math
import os
from pathlib import Path
import tempfile
import time

from session_control import interruptible_sleep, raise_if_stopped
from telemetry import emit


def validate_point(latitude, longitude):
    try:
        if isinstance(latitude, bool) or isinstance(longitude, bool):
            raise ValueError()
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("请输入有效的纬度和经度。") from error
    if not (math.isfinite(latitude) and math.isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("纬度范围为 −90 到 90，经度范围为 −180 到 180。")
    return {"latitude": latitude, "longitude": longitude}


def write_point(path, target):
    fd, temporary = tempfile.mkstemp(prefix="point-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(target, handle, allow_nan=False)
        for attempt in range(3):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.02)
    finally:
        Path(temporary).unlink(missing_ok=True)


async def hold_point(set_location, path):
    revision = 0
    while True:
        raise_if_stopped()
        target = json.loads(path.read_text(encoding="utf-8"))
        if target["revision"] > revision:
            point = validate_point(target["latitude"], target["longitude"])
            await asyncio.wait_for(set_location(point["latitude"], point["longitude"]), timeout=10)
            revision = target["revision"]
            emit("point_set", revision=revision, **point)
        await interruptible_sleep(0.2)
