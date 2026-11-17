import json
import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from desktop_server import DesktopServer
from desktop_service import DesktopService
from desktop_tools import _app_url, _github_url
from session_control import RunStopped


def fix(sequence, **values):
    return {"type": "location", "sequence": sequence, "latitude": 30.3, "longitude": 120.1,
            "distance": sequence, "elapsed": sequence / 5, "speed": 4.8, **values}


class DesktopStateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.service = DesktopService(Path(self.directory.name), headless=True)

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def test_point_cursor_resets_for_new_run_and_rejects_invalid_fixes(self):
        self.service.state["run"]["id"] = "new-run"
        self.service._consume_event(fix(1))
        self.service._consume_event(fix(2))
        self.service._consume_event(fix(2))
        self.service._consume_event(fix(3, latitude=float("nan")))
        changed = self.service.snapshot(99, "previous-run")
        self.assertTrue(changed["run"]["reset"])
        self.assertEqual(len(changed["run"]["points"]), 2)
        self.assertEqual([p["sequence"] for p in self.service.snapshot(1, "new-run")["run"]["points"]], [2])
        self.assertEqual(self.service.state["run"]["pointCount"], 2)

    def test_long_trail_is_bounded_without_losing_start_and_latest_point(self):
        for sequence in range(1, 8300):
            self.service._consume_event(fix(sequence))
        self.assertLess(len(self.service.points), 8193)
        self.assertEqual(self.service.points[0]["sequence"], 1)
        self.assertEqual(self.service.points[-1]["sequence"], 8299)

    def test_jobs_are_serialized_and_stop_does_not_wait_for_completion(self):
        started, released = threading.Event(), threading.Event()

        def hold(*_):
            started.set()
            released.wait(3)

        with patch.object(self.service, "_perform", side_effect=hold):
            self.service.dispatch("check")
            self.assertTrue(started.wait(1))
            with self.assertRaisesRegex(ValueError, "任务"):
                self.service.dispatch("run")
            before = time.monotonic()
            self.service.stop()
            self.assertLess(time.monotonic() - before, .2)
            self.assertTrue(self.service.stop_flag.exists())
            released.set()
            self.service.thread.join(2)
        self.assertEqual(self.service.state["task"]["status"], "stopped")

    def test_failure_does_not_mark_the_device_ready(self):
        with patch.object(self.service, "_perform", side_effect=RuntimeError("not connected")):
            self.service.dispatch("check")
            self.service.thread.join(2)
        self.assertEqual(self.service.state["device"]["status"], "error")
        self.assertEqual(self.service.state["task"]["status"], "error")

    def test_iphone_mount_and_run_are_allowed_without_administrator(self):
        self.service.settings["backend"] = "ios"
        with patch.object(self.service, "is_admin", return_value=False), \
             patch.object(self.service, "_worker") as worker:
            self.service._perform("mount", {})
            self.service._perform("run", {})
        self.assertEqual(worker.call_args_list[0].args[0], ["--mount"])
        self.assertIn("--run", worker.call_args_list[1].args[0])

    def test_worker_cleanup_failure_is_visible_even_after_stop_was_requested(self):
        self.service.stopping = True
        process = type("FailedWorker", (), {"stdout": io.StringIO(""), "wait": lambda _: 1})()
        with patch("desktop_service.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "退出码 1"):
                self.service._worker(["--run"])

    def test_login_confirmation_persists_but_changes_of_device_clear_it(self):
        self.service.save_preferences({"login_tyys": "confirmed", "speed": "5.2"})
        restored = DesktopService(Path(self.directory.name), headless=True)
        self.assertEqual(restored.settings["login_tyys"], "confirmed")
        restored.save_preferences({"avd": "Another_Device"})
        self.assertEqual(restored.settings["login_tyys"], "")
        self.assertEqual(restored.settings["speed"], "5.2")
        restored.close()

    def test_switching_backend_requires_a_new_device_check(self):
        self.service.settings["backend"] = "android"
        self.service.state["device"].update(status="ready", serial="emulator-5554")
        self.service.save_preferences({"backend": "ios"})
        self.assertEqual(self.service.state["device"]["status"], "unknown")
        self.assertEqual(self.service.state["device"]["serial"], "")

    def test_route_and_settings_do_not_accept_arbitrary_files_or_passwords(self):
        with self.assertRaises(ValueError):
            self.service.route("../settings.json")
        with self.assertRaises(ValueError):
            self.service.save_preferences({"password": "should not be stored"})

    def test_stop_zeros_instantaneous_speed_and_preserves_average_inputs(self):
        self.service._consume_event(fix(1, speed=4.8, distance=48, elapsed=10))
        self.service._consume_event({"type": "run_state", "state": "stopped"})
        result = self.service.snapshot()["run"]
        self.assertEqual(result["speed"], 0)
        self.assertEqual(result["distance"] / result["elapsed"], 4.8)

    def test_start_resets_old_metrics_before_device_preparation_finishes(self):
        self.service.state["run"]["id"] = "previous-run"
        self.service._consume_event(fix(1, speed=4.8, distance=48, elapsed=10))
        started, released = threading.Event(), threading.Event()

        def prepare(*_):
            started.set()
            released.wait(3)

        with patch.object(self.service, "_perform", side_effect=prepare):
            self.service.dispatch("run")
            try:
                self.assertTrue(started.wait(1))
                result = self.service.snapshot()["run"]
                self.assertNotEqual(result["id"], "previous-run")
                self.assertEqual(result["status"], "starting")
                self.assertEqual((result["speed"], result["distance"], result["elapsed"], result["pointCount"]), (0, 0, 0, 0))
            finally:
                released.set()
                self.service.thread.join(2)

    def test_cancelling_preparation_leaves_a_stopped_run(self):
        with patch.object(self.service, "_perform", side_effect=RunStopped()):
            self.service.dispatch("run")
            self.service.thread.join(2)
        self.assertEqual(self.service.state["run"]["status"], "stopped")
        self.assertEqual(self.service.state["run"]["speed"], 0)


class LocalApiTests(unittest.TestCase):
    def test_api_requires_token_and_rejects_cross_origin_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("test", encoding="utf-8")
            service = DesktopService(root / "state", headless=True)
            server = DesktopServer(service, root)
            server.start()
            try:
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(server.origin + "/api/state")
                self.assertEqual(rejected.exception.code, 403)
                request = urllib.request.Request(server.origin + "/api/state", headers={"Authorization": "Bearer " + server.token})
                with urllib.request.urlopen(request) as response:
                    self.assertIn("settings", json.load(response))
                request.add_header("Origin", "https://untrusted.example")
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(request)
                self.assertEqual(rejected.exception.code, 403)
            finally:
                server.close()
                service.close()


class DownloadOriginTests(unittest.TestCase):
    def test_official_app_and_tool_redirects_cannot_escape_allowed_origins(self):
        for key, url in (("tyys", "http://tyys.zju.edu.cn.attacker.test/cgapp-server/a.apk"),
                         ("tyys", "http://tyys.zju.edu.cn/not-the-download/a.apk"),
                         ("ding", "http://www.dingtalk.com/android/d/"),
                         ("ding", "https://user:pass@www.dingtalk.com/file.apk")):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _app_url(key, url)
        with self.assertRaises(ValueError):
            _github_url("https://github.com.attacker.test/a.zip")
