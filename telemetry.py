"""Opt-in worker events, emitted only after a location provider accepts a fix."""

import json
import math
import os
import time


PREFIX = "@realrun:"


def emit(event_type, **values):
    if os.environ.get("IOSREALRUN_EVENTS") == "1":
        print(PREFIX + json.dumps({"type": event_type, **values}, ensure_ascii=False, allow_nan=False), flush=True)


def distance_metres(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2 - lat1, math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


class TrackingLocation:
    def __init__(self, provider, callback=emit, clock=time.monotonic):
        self.provider, self.callback, self.clock = provider, callback, clock
        self.started = None
        self.previous = None
        self.previous_time = None
        self.distance = 0.0
        self.sequence = 0

    async def set(self, latitude, longitude):
        if not all(math.isfinite(value) for value in (latitude, longitude)) or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("定位坐标无效。")
        # Timestamp the requested sample, then publish only after acceptance.
        # Provider acknowledgement time is transport latency, not travel time.
        now = self.clock()
        await self.provider.set(latitude, longitude)
        if self.started is None:
            self.started = now
        speed = 0.0
        if self.previous is not None:
            travelled = distance_metres(self.previous, (latitude, longitude))
            self.distance += travelled
            speed = travelled / max(0.001, now - self.previous_time)
        self.previous, self.previous_time = (latitude, longitude), now
        self.sequence += 1
        self.callback("location", sequence=self.sequence, latitude=latitude, longitude=longitude,
                      elapsed=round(now - self.started, 3), distance=round(self.distance, 3),
                      speed=round(speed, 3), timestamp=time.time())
