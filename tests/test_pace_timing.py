import math
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch

from run import MetricRoute, build_pace_model, run1
from telemetry import TrackingLocation, distance_metres
from util.route import load_route


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


def position(east, north=0):
    return {"lat": math.degrees(north / 6371008.8), "lng": math.degrees(east / 6371008.8)}


class PaceTimingTests(unittest.IsolatedAsyncioTestCase):
    async def test_west_track_follows_the_wgs84_loop_without_coordinate_offsets(self):
        route = load_route(Path(__file__).resolve().parents[1] / "ZJGWestTrack.geojson")
        self.assertEqual(route[0], route[-1])
        path = MetricRoute(route)
        self.assertAlmostEqual(path.length, 400, delta=1)

        provider = AsyncMock()
        clock = FakeClock()
        model = build_pace_model(4.8, variation={"profile": "constant", "targetDistance": 5})
        await run1(provider, route, model, clock=clock, sleep=clock.sleep)
        self.assertEqual(provider.set.await_args_list[0].args, (route[0]["lat"], route[0]["lng"]))
        self.assertAlmostEqual(distance_metres(path.sample(5), provider.set.await_args.args), 0, places=2)

    async def simulate(self, points, target, delays):
        clock = FakeClock()
        events = []
        model = build_pace_model(4.8, variation={"profile": "constant", "targetDistance": target})
        count = 0

        async def accepted(*_):
            nonlocal count
            clock.now += delays[count % len(delays)]
            count += 1

        provider = Mock()
        provider.set = AsyncMock(side_effect=accepted)
        tracker = TrackingLocation(provider, lambda _, **event: events.append(event), clock)
        with patch("run.randLoc", side_effect=lambda path, **_: path), patch("run.bd09Towgs84", side_effect=lambda p: p):
            for _ in range(10):
                if model.reached_target():
                    break
                await run1(tracker, points, model, clock=clock, sleep=clock.sleep)
            else:
                self.fail("The route never reached its target")
        return events, model

    async def test_uneven_collinear_segments_do_not_produce_speed_dips(self):
        events, _ = await self.simulate([position(0), position(15.7), position(31.35), position(200)], 70, [.01])
        for event in events[1:-1]:
            self.assertAlmostEqual(event["speed"], 4.8, places=3)
        self.assertAlmostEqual(events[-1]["distance"], 70, places=2)

    async def test_variable_and_slow_provider_latency_does_not_reduce_route_speed(self):
        events, _ = await self.simulate([position(0), position(200)], 70, [.01, .12, .035, .35, .07])
        for event in events[1:-1]:
            self.assertAlmostEqual(event["speed"], 4.8, places=3)
        self.assertAlmostEqual(events[0]["elapsed"], 0)
        measured = events[-2]["distance"] / events[-2]["elapsed"]
        self.assertAlmostEqual(measured, 4.8, places=2)

    async def test_lap_boundaries_carry_fractional_progress_without_duplicate_fixes(self):
        points = [position(100 * math.cos(i * math.tau / 50), 100 * math.sin(i * math.tau / 50)) for i in range(50)]
        events, model = await self.simulate(points, 1300, [.025])
        self.assertTrue(model.reached_target())
        self.assertGreater(events[-1]["distance"], 1298)
        self.assertGreater(min(event["speed"] for event in events[1:-1]), 4.78)

    async def test_telemetry_uses_sample_time_and_excludes_acknowledgement_delay(self):
        clock = FakeClock()
        clock.now = 100
        delays = iter((.1, .8))

        async def write(*_):
            clock.now += next(delays)

        provider = Mock()
        provider.set = AsyncMock(side_effect=write)
        callback = Mock()
        tracker = TrackingLocation(provider, callback, clock)
        await tracker.set(0, 0)
        clock.now = 101
        point = position(1)
        await tracker.set(point["lat"], point["lng"])
        self.assertEqual(callback.call_args.kwargs["elapsed"], 1)
        self.assertEqual(callback.call_args.kwargs["speed"], 1)

    def test_mean_and_variation_use_time_weights(self):
        model = build_pace_model(4, variation={"profile": "constant"})
        model.step(dt=1)
        model.base_speed = 6
        model.step(dt=3)
        self.assertEqual(model.mean_speed(), 5.5)
        self.assertEqual(model.distance, 22)
        self.assertEqual(model.elapsed, 4)

    def test_duplicate_route_vertices_are_removed_without_losing_distance(self):
        path = MetricRoute([position(0), position(0), position(15.7), position(31.35)])
        a, b = path.sample(15), path.sample(16)
        self.assertAlmostEqual(distance_metres(a, b), 1, places=5)
