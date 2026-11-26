import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from android_emulator import EmulatorLocation
from fixed_location import hold_point, validate_point, write_point
from session_control import RunStopped


class FixedLocationTests(unittest.IsolatedAsyncioTestCase):
    async def test_static_session_applies_the_latest_revision_without_repeating_fixes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target.json"
            write_point(path, {"latitude": 48.85, "longitude": 2.35, "revision": 1})
            provider = AsyncMock()
            events = []
            polls = 0

            async def advance(_):
                nonlocal polls
                polls += 1
                if polls == 2:
                    write_point(path, {"latitude": 1.3, "longitude": 103.8, "revision": 2})
                    write_point(path, {"latitude": -33.87, "longitude": 151.21, "revision": 3})
                if polls == 4:
                    raise RunStopped()

            with patch("fixed_location.interruptible_sleep", side_effect=advance), \
                 patch("fixed_location.emit", side_effect=lambda _, **event: events.append(event)):
                with self.assertRaises(RunStopped):
                    await hold_point(provider, path)
            self.assertEqual([call.args for call in provider.await_args_list], [(48.85, 2.35), (-33.87, 151.21)])
            self.assertEqual([event["revision"] for event in events], [1, 3])
            self.assertEqual(json.loads(path.read_text())["revision"], 3)

    async def test_android_static_jump_has_zero_speed(self):
        engine = EmulatorLocation("emulator-5554", clock=iter((1, 2)).__next__)
        engine.command = AsyncMock()
        await engine.set(51.5, -0.1, stationary=True)
        await engine.set(35.68, 139.76, stationary=True)
        self.assertEqual(engine.command.await_args.args[0], "geo fix 139.76000000 35.68000000 0 8 0.000000")

    def test_invalid_points_are_rejected(self):
        for point in ((True, False), (90.1, 0), (0, 181), ("NaN", 1), (0, float("inf"))):
            with self.subTest(point=point), self.assertRaises(ValueError):
                validate_point(*point)
