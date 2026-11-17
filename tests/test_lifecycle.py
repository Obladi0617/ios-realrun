import asyncio
import json
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app_settings import load_settings, save_settings, validate_run
from launcher import RunnerApp
from run import follow_route


class SettingsTests(unittest.TestCase):
    def test_preferences_survive_restart_and_corruption_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "settings.json"
            save_settings({"backend": "android", "speed": "5", "route": "HNroute.txt"}, target)
            self.assertEqual(load_settings(target)["backend"], "android")
            self.assertEqual(load_settings(target)["speed"], "5")
            target.write_text("{bad json", encoding="utf-8")
            self.assertEqual(load_settings(target)["backend"], "ios")
            target.write_text(json.dumps({"speed": "nan"}), encoding="utf-8")
            self.assertEqual(round(1000 / float(load_settings(target)["speed"])), 300)

    def test_non_finite_or_invalid_speed_is_rejected(self):
        for speed in ("nan", "inf", "-inf", "0", "-1"):
            with self.subTest(speed=speed), self.assertRaises(ValueError):
                validate_run(speed, "30")


class LifecycleTests(unittest.TestCase):
    def test_stop_returns_without_waiting_on_the_ui_thread(self):
        app = RunnerApp.__new__(RunnerApp)
        process = Mock()
        released = threading.Event()
        process.wait.side_effect = lambda **_: released.wait(2)
        app.process, app.action_process = process, None
        app.stopping = False
        app.status = Mock()
        app.refresh_buttons = Mock()
        app.write_log = Mock()
        app.is_android = lambda: True
        started = time.monotonic()
        with patch("launcher.request_stop"):
            app.stop_run()
        elapsed = time.monotonic() - started
        released.set()
        self.assertLess(elapsed, 0.5)
        self.assertTrue(app.stopping)

    def test_failed_check_is_not_reported_as_ready(self):
        app = RunnerApp.__new__(RunnerApp)
        process = Mock()
        app.process, app.action_process = None, process
        app.output_queue = queue.Queue()
        app.output_queue.put(("done", process, 1))
        app.write_log = Mock()
        app.status = Mock()
        app.refresh_buttons = Mock()
        app.root = Mock()
        app.closing, app.stopping = False, False
        with patch("launcher.clear_stop_flag"):
            app.consume_output()
        self.assertIn("失败", app.status.set.call_args.args[0])
        self.assertIsNone(app.action_process)


class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_timeout_is_not_hidden_as_duration_completion(self):
        async def fail(*_, **__):
            raise TimeoutError("provider disconnected")
        with patch("run.run1", side_effect=fail):
            with self.assertRaisesRegex(TimeoutError, "provider disconnected"):
                await follow_route(Mock(), [{"lat": 30, "lng": 120}] * 2, 4.8, 10)

    async def test_duration_limit_cancels_route(self):
        async def hang(*_, **__):
            await asyncio.sleep(60)
        with patch("run.run1", side_effect=hang):
            await asyncio.wait_for(follow_route(Mock(), [{"lat": 30, "lng": 120}] * 2, 4.8, 0.02), 1)
