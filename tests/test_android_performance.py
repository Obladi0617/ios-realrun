import unittest
from unittest.mock import AsyncMock, Mock, patch

from android_emulator import AndroidEmulator, GraphicsStartupError
from android_performance import graphics_failure, launch_resources, optimize_display
from android_workspace import restart_device
from session_control import RunStopped


class PerformanceTests(unittest.TestCase):
    def test_resources_adapt_to_available_host_memory_and_cores(self):
        for total, free, cpus, expected in (
            (32768, 10000, 14, (4096, 4)), (16384, 4500, 8, (3072, 4)),
            (8192, 3000, 4, (2560, 2)), (0, 0, None, (2560, 1)),
        ):
            with self.subTest(total=total, free=free, cpus=cpus), patch(
                "android_performance.host_memory_mb", return_value=(total, free)
            ), patch("android_performance.os.cpu_count", return_value=cpus):
                self.assertEqual(launch_resources(), expected)

    def test_only_graphics_failures_allow_a_software_retry(self):
        for text in ("Failed to initialize Vulkan", "OpenGLES emulation failed to initialize",
                     "VK_ERROR_INCOMPATIBLE_DRIVER", "Could not initialize emulated framebuffer"):
            self.assertTrue(graphics_failure(text), text)
        for text in ("Permission denied", "Not enough disk space", "AVD is already running",
                     "Checking hasSufficientHwGpu: OK; user data disk failed"):
            self.assertFalse(graphics_failure(text), text)

    def test_large_phone_display_reduces_pixels_and_preserves_layout_density(self):
        device = Mock()
        device.command.side_effect = ["Physical size: 1080x2340", "Physical density: 440", "", ""]
        optimize_display(device)
        self.assertEqual(device.command.call_args_list[-2].args, ("shell", "wm", "size", "720x1560"))
        self.assertEqual(device.command.call_args_list[-1].args, ("shell", "wm", "density", "293"))

    def test_user_display_overrides_are_preserved(self):
        device = Mock()
        device.command.side_effect = ["Physical size: 1080x2340\nOverride size: 900x1950", "Physical density: 440"]
        optimize_display(device)
        self.assertEqual(device.command.call_count, 2)

    def test_display_is_restored_if_density_change_fails(self):
        device = Mock()
        device.command.side_effect = ["Physical size: 1080x2340", "Physical density: 440",
                                      "", RuntimeError("density failure"), "", ""]
        with self.assertRaisesRegex(RuntimeError, "density failure"):
            optimize_display(device)
        self.assertEqual(device.command.call_args_list[-2].args, ("shell", "wm", "size", "reset"))
        self.assertEqual(device.command.call_args_list[-1].args, ("shell", "wm", "density", "reset"))

    def test_restart_never_kills_an_unselected_avd(self):
        device = Mock()
        device.command.return_value = "Unrelated_Device\nOK"
        with patch("android_workspace.ensure_device", return_value=device):
            with self.assertRaisesRegex(RuntimeError, "不一致"):
                restart_device({"avd": "Selected_Device", "serial": ""})
        self.assertEqual(device.command.call_count, 1)

    def test_cancellation_before_shutdown_does_not_restart_device(self):
        device = Mock()
        device.command.return_value = "Selected_Device\nOK"
        with patch("android_workspace.ensure_device", return_value=device), patch(
            "android_workspace.raise_if_stopped", side_effect=RunStopped()
        ):
            with self.assertRaises(RunStopped):
                restart_device({"avd": "Selected_Device", "serial": ""})
        self.assertEqual(device.command.call_count, 1)
        device.start.assert_not_called()


class GraphicsStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_tries_gpu_and_retries_one_driver_failure(self):
        with patch("android_emulator.find_tool", return_value="adb"):
            device = AndroidEmulator()
        device.avds = Mock(return_value=["TestAVD"])
        device._start_once = AsyncMock(side_effect=[GraphicsStartupError("driver"), "emulator-5554"])
        self.assertEqual(await device.start("TestAVD", headless=True), "emulator-5554")
        self.assertEqual([call.args[2] for call in device._start_once.call_args_list], ["host", "swiftshader"])

    async def test_cancellation_and_non_graphics_failures_do_not_restart_device(self):
        for error in (RunStopped(), RuntimeError("disk full")):
            with self.subTest(error=type(error).__name__), patch("android_emulator.find_tool", return_value="adb"):
                device = AndroidEmulator()
                device.avds = Mock(return_value=["TestAVD"])
                device._start_once = AsyncMock(side_effect=error)
                with self.assertRaises(type(error)):
                    await device.start("TestAVD", headless=True)
                self.assertEqual(device._start_once.await_count, 1)

    async def test_explicit_compatibility_mode_is_not_retried(self):
        with patch("android_emulator.find_tool", return_value="adb"):
            device = AndroidEmulator()
        device.avds = Mock(return_value=["TestAVD"])
        device._start_once = AsyncMock(side_effect=GraphicsStartupError("driver"))
        with self.assertRaises(GraphicsStartupError):
            await device.start("TestAVD", graphics="swiftshader")
        self.assertEqual(device._start_once.await_count, 1)
