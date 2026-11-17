import asyncio
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from android_emulator import AndroidEmulator, EmulatorLocation
from session_control import RunStopped


class DevicesTests(unittest.TestCase):
    def test_multiple_emulators_require_explicit_selection(self):
        with patch("android_emulator.find_tool", return_value="adb"), patch("android_emulator.run_command", return_value="List of devices attached\nemulator-5554\tdevice\nemulator-5556\tdevice\nphysical-phone\tdevice"):
            device = AndroidEmulator()
            with self.assertRaisesRegex(RuntimeError, "多个"):
                device.select()
            self.assertEqual(AndroidEmulator(serial="emulator-5556").select(), "emulator-5556")

    def test_physical_android_phones_are_not_selected(self):
        with patch("android_emulator.find_tool", return_value="adb"), patch("android_emulator.run_command", return_value="List of devices attached\nphysical-phone\tdevice\nemulator-5554\toffline"):
            with self.assertRaisesRegex(RuntimeError, "未检测到"):
                AndroidEmulator().select()


class ConsoleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.token = Path(self.temp.name) / "token"
        self.token.write_text("test-token", encoding="utf-8")
        self.commands = []
        self.fail_geo = False
        self.finished = asyncio.Event()
        for port in range(5554, 5585, 2):
            try:
                self.server = await asyncio.start_server(self.handle_client, "127.0.0.1", port)
                self.serial = f"emulator-{port}"
                break
            except OSError:
                continue
        else:
            self.skipTest("No free emulator console port for protocol fixture")

    async def asyncTearDown(self):
        if hasattr(self, "server"):
            self.server.close()
            await self.server.wait_closed()
        self.temp.cleanup()

    async def handle_client(self, reader, writer):
        try:
            writer.write(b"Android Console: Authentication required\r\nOK\r\n")
            await writer.drain()
            while line := await reader.readline():
                command = line.decode().strip()
                self.commands.append(command)
                if command.startswith("geo") and self.fail_geo:
                    writer.write(b"KO: bad fix\r\n")
                else:
                    writer.write(b"OK\r\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            self.finished.set()

    async def test_authenticated_connection_sends_longitude_first_and_closes(self):
        async with EmulatorLocation(self.serial, self.token) as loc:
            await loc.set(30.3, 120.1)
            await loc.set(30.4, 120.2)
        await asyncio.wait_for(self.finished.wait(), 2)
        self.assertEqual(self.commands[0], "auth test-token")
        self.assertTrue(self.commands[1].startswith("geo fix 120.10000000 30.30000000 0 8 "))
        self.assertTrue(self.commands[2].startswith("geo fix 120.20000000 30.40000000 0 8 "))

    async def test_reported_velocity_uses_knots(self):
        clock = Mock(side_effect=[100.0, 101.0])
        async with EmulatorLocation(self.serial, self.token, clock=clock) as loc:
            await loc.set(0, 0)
            await loc.set(0, 0.0000089932)  # Approximately one metre in one second.
        await asyncio.wait_for(self.finished.wait(), 2)
        self.assertEqual(float(self.commands[1].split()[-1]), 0)
        self.assertAlmostEqual(float(self.commands[2].split()[-1]), 1.94384, places=4)

    async def test_console_failure_propagates(self):
        self.fail_geo = True
        async with EmulatorLocation(self.serial, self.token) as loc:
            with self.assertRaisesRegex(RuntimeError, "bad fix"):
                await loc.set(30, 120)
        await asyncio.wait_for(self.finished.wait(), 2)

    async def test_invalid_coordinates_are_not_sent(self):
        async with EmulatorLocation(self.serial, self.token) as loc:
            with self.assertRaises(ValueError):
                await loc.set(float("nan"), 120)
        await asyncio.wait_for(self.finished.wait(), 2)
        self.assertEqual(self.commands, ["auth test-token"])

    async def test_stopping_reports_zero_velocity_at_the_last_coordinate(self):
        clock = Mock(side_effect=[100.0, 101.0, 102.0])
        async with EmulatorLocation(self.serial, self.token, clock=clock) as loc:
            await loc.set(0, 0)
            await loc.set(0, .0000089932)
            await loc.stop()
        await asyncio.wait_for(self.finished.wait(), 2)
        self.assertEqual(self.commands[-1].split()[2:4], self.commands[-2].split()[2:4])
        self.assertEqual(float(self.commands[-1].split()[-1]), 0)


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_start_cleans_up_its_process_and_supplies_runtime_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "sdk" / "emulator" / "emulator.exe"
            with patch("android_emulator.find_tool", return_value=str(binary)), patch("android_emulator.data_dir", return_value=Path(directory)), patch("android_emulator.subprocess.Popen") as popen, patch("android_emulator.subprocess.run") as terminate:
                process = popen.return_value
                process.pid = 12345
                process.poll.return_value = None
                device = AndroidEmulator()
                device.avds = Mock(return_value=["TestAVD"])
                device._wait_for_startup = AsyncMock(side_effect=RunStopped())
                with self.assertRaises(RunStopped):
                    await device.start("TestAVD", headless=True)
                self.assertEqual(popen.call_args.kwargs["cwd"], binary.parent.resolve())
                self.assertEqual(popen.call_args.kwargs["env"]["PATH"].split(os.pathsep)[:2],
                                 [str(binary.parent.resolve()), str(binary.parent.resolve() / "lib64")])
                if os.name == "nt":
                    self.assertEqual(terminate.call_args.args[0], ["taskkill", "/F", "/T", "/PID", "12345"])
                else:
                    process.terminate.assert_called_once()
