import asyncio
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

from pymobiledevice3.exceptions import AlreadyMountedError

from ios_session import device_serial, device_tunnel, mount_connected, preparing, run_ios
from run import run_on_provider
from session_control import RunStopped


class IosSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_mount_uses_rsd_and_preserves_real_mount_errors(self):
        rsd = object()
        mount = AsyncMock(side_effect=RuntimeError("signing failed"))
        with patch("ios_session.developer_services_ready", return_value=False), \
             patch("pymobiledevice3.services.mobile_image_mounter.auto_mount", mount):
            with self.assertRaisesRegex(RuntimeError, "signing failed"):
                await mount_connected(rsd)
        mount.assert_awaited_once_with(rsd)

    async def test_usable_location_service_does_not_trigger_signing_or_mounting(self):
        mount = AsyncMock()
        with patch("ios_session.developer_services_ready", return_value=True), \
             patch("pymobiledevice3.services.mobile_image_mounter.auto_mount", mount):
            await mount_connected(object())
        mount.assert_not_awaited()

    async def test_already_mounted_is_success(self):
        with patch("ios_session.developer_services_ready", return_value=False), \
             patch("pymobiledevice3.services.mobile_image_mounter.auto_mount", side_effect=AlreadyMountedError):
            await mount_connected(object())

    async def test_cancelled_preparation_releases_the_library_task(self):
        started, closed = asyncio.Event(), asyncio.Event()

        async def opening():
            started.set()
            try:
                await asyncio.sleep(60)
            finally:
                closed.set()

        def stop_after_start():
            if started.is_set():
                raise RunStopped()

        with patch("ios_session.raise_if_stopped", side_effect=stop_after_start):
            with self.assertRaises(RunStopped):
                await preparing(opening())
        self.assertTrue(closed.is_set())

    async def test_new_service_discovery_after_mount_stays_on_the_same_device(self):
        events = []
        providers = iter((object(), object()))

        @asynccontextmanager
        async def tunnel(serial):
            self.assertEqual(serial, "selected-device")
            rsd = next(providers)
            events.append(("open", rsd))
            try:
                yield rsd
            finally:
                events.append(("close", rsd))

        async def mount(rsd):
            events.append(("mount", rsd))

        async def run(rsd, *_):
            events.append(("run", rsd))

        with patch("ios_session.device_serial", return_value="selected-device"), \
             patch("ios_session.device_tunnel", tunnel), \
             patch("ios_session.mount_connected", side_effect=mount), \
             patch("run.run_on_provider", side_effect=run):
            await run_ios([], 3.7)
        self.assertEqual([kind for kind, _ in events], ["open", "mount", "close", "open", "run", "close"])
        self.assertIs(events[0][1], events[1][1])
        self.assertIs(events[3][1], events[4][1])
        self.assertIsNot(events[1][1], events[4][1])

    async def test_failed_tunnel_open_always_closes_handle(self):
        handle = Mock(aopen=AsyncMock(side_effect=RuntimeError("disconnected")), aclose=AsyncMock())
        with patch("pymobiledevice3.remote.userspace_tunnel.UserspaceRsdTunnel", return_value=handle):
            with self.assertRaisesRegex(RuntimeError, "disconnected"):
                async with device_tunnel("selected-device"):
                    self.fail("A disconnected device must not be usable")
        handle.aclose.assert_awaited_once()

    async def test_device_client_closed_when_developer_mode_is_off(self):
        device = Mock(product_version="27.2.1", all_values={}, close=AsyncMock(),
                      get_developer_mode_status=AsyncMock(return_value=False))
        with patch("driver.connect.get_usbmux_lockdownclient", return_value=device):
            with self.assertRaisesRegex(RuntimeError, "开发者模式"):
                await device_serial()
        device.close.assert_awaited_once()

    async def test_stop_clears_location_before_closing_dtx(self):
        events = []

        @asynccontextmanager
        async def provider(_):
            try:
                yield object()
            finally:
                events.append("close-provider")

        @asynccontextmanager
        async def simulation(_):
            async def clear():
                events.append("clear")
            try:
                yield Mock(clear=AsyncMock(side_effect=clear))
            finally:
                events.append("close-channel")

        with patch("pymobiledevice3.services.dvt.instruments.dvt_provider.DvtProvider", provider), \
             patch("pymobiledevice3.services.dvt.instruments.location_simulation.LocationSimulation", simulation), \
             patch("run.follow_route", side_effect=RunStopped):
            with self.assertRaises(RunStopped):
                await run_on_provider(object(), [], 3.7)
        self.assertEqual(events, ["clear", "close-channel", "close-provider"])

    async def test_clear_failure_is_not_reported_as_a_successful_stop(self):
        @asynccontextmanager
        async def context(_):
            yield Mock(clear=AsyncMock(side_effect=RuntimeError("USB disconnected")))

        with patch("pymobiledevice3.services.dvt.instruments.dvt_provider.DvtProvider", context), \
             patch("pymobiledevice3.services.dvt.instruments.location_simulation.LocationSimulation", context), \
             patch("run.follow_route", new_callable=AsyncMock):
            with self.assertRaisesRegex(RuntimeError, "清除模拟定位失败"):
                await run_on_provider(object(), [], 3.7)
