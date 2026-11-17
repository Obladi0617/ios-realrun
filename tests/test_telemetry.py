import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from telemetry import TrackingLocation
from run import build_pace_model
from worker import apply_profile


class TelemetryTests(unittest.IsolatedAsyncioTestCase):
    def test_explicit_ui_profile_overrides_default_config_percentages(self):
        original = {"profile": "recreational", "cvPercent": 6, "fatiguePercent": 3, "targetDistance": 6000}
        steady = build_pace_model(4.8, variation=apply_profile(original, "steady"))
        variable = build_pace_model(4.8, variation=apply_profile(original, "variable"))
        self.assertEqual(steady.cv, .03)
        self.assertEqual(variable.cv, .10)
        self.assertEqual(steady.target_distance, 6000)
        self.assertEqual(original["cvPercent"], 6)

    async def test_failed_device_write_does_not_create_a_trail_point(self):
        provider = Mock()
        provider.set = AsyncMock(side_effect=RuntimeError("device disconnected"))
        callback = Mock()
        tracker = TrackingLocation(provider, callback)
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            await tracker.set(30, 120)
        callback.assert_not_called()
        self.assertEqual(tracker.sequence, 0)

    async def test_distance_and_speed_follow_accepted_fixes(self):
        provider = Mock()
        provider.set = AsyncMock()
        callback = Mock()
        tracker = TrackingLocation(provider, callback, Mock(side_effect=[0, 1]))
        await tracker.set(0, 0)
        await tracker.set(0, .0000089932)
        event = callback.call_args.kwargs
        self.assertEqual(event["sequence"], 2)
        self.assertAlmostEqual(event["distance"], 1, places=2)
        self.assertAlmostEqual(event["speed"], 1, places=2)
        self.assertEqual(event["elapsed"], 1)

    async def test_non_finite_fix_is_rejected_before_device_write(self):
        provider = Mock()
        provider.set = AsyncMock()
        with self.assertRaises(ValueError):
            await TrackingLocation(provider).set(float("nan"), 120)
        provider.set.assert_not_called()
