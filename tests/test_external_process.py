import sys
import unittest
from unittest.mock import patch

import external_process


class ExternalProgramTests(unittest.TestCase):
    def test_frozen_dll_search_is_restored_when_launch_fails(self):
        events = []
        with patch.object(sys, "platform", "win32"), patch.object(sys, "frozen", True, create=True), patch("external_process._get_dll_directory", return_value="C:\\bundle\\_internal"), patch("external_process._set_dll_directory", side_effect=lambda value: events.append(value)), patch("external_process.subprocess.Popen", side_effect=OSError("launch failed")):
            with self.assertRaises(OSError):
                external_process.external_popen(["SDK.exe"])
        self.assertEqual(events, [None, "C:\\bundle\\_internal"])

    def test_bundled_dll_paths_are_removed_only_from_child_environment(self):
        environment = {"PATH": "C:\\bundle\\_internal;C:\\bundle\\_internal\\bin;C:\\SDK;C:\\Windows", "KEEP": "value"}
        with patch.object(sys, "platform", "win32"), patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", "C:\\bundle\\_internal", create=True):
            clean = external_process.clean_environment(environment)
        self.assertEqual(clean["PATH"], "C:\\SDK;C:\\Windows")
        self.assertEqual(clean["KEEP"], "value")
        self.assertIn("_internal", environment["PATH"])
