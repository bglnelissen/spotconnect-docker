import time
import types
import unittest

from discovery import Discovery, NetworkDevice, device_from_info

NAME = "A0A0A0A0A0A1@Study._raop._tcp.local."
ADDED = types.SimpleNamespace(name="Added")
REMOVED = types.SimpleNamespace(name="Removed")


class FakeInfo:
    def __init__(self, addresses, properties, server):
        self._addresses = addresses
        self.properties = properties
        self.server = server

    def parsed_addresses(self):
        return self._addresses


class FakeZeroconf:
    def __init__(self, info):
        self.info = info

    def get_service_info(self, service_type, name, timeout=3000):
        return self.info


STUDY_INFO = FakeInfo(["fdc0::1", "192.168.1.23"], {b"am": b"AppleTV3,2", b"flag": None}, "Study.local.")


class DeviceFromInfoTest(unittest.TestCase):
    def test_full_answer(self):
        device = device_from_info(NAME, STUDY_INFO.parsed_addresses(), STUDY_INFO.properties,
                                  STUDY_INFO.server)
        self.assertEqual(device, NetworkDevice(
            udn="A0A0A0A0A0A1@Study._raop._tcp.local",
            airplay_name="Study",
            address="192.168.1.23",
            model="AppleTV3,2",
            host_name="Study",
        ))
        self.assertTrue(device.is_apple_tv)

    def test_sparse_answer(self):
        device = device_from_info("A1@Garage._raop._tcp.local.", ["fe80::1"], {}, None)
        self.assertEqual((device.address, device.model, device.host_name), ("fe80::1", "", ""))
        self.assertFalse(device.is_apple_tv)

    def test_host_name_is_cut_at_local(self):
        device = device_from_info(NAME, [], {}, "Game-Room-4.LOCAL.")
        self.assertEqual(device.host_name, "Game-Room-4")


class DiscoveryTest(unittest.TestCase):
    def change(self, discovery, info, state, name=NAME):
        discovery._on_change(zeroconf=FakeZeroconf(info), service_type="_raop._tcp.local.",
                             name=name, state_change=state)

    def test_added_then_removed(self):
        discovery = Discovery(settle_seconds=0)
        self.change(discovery, STUDY_INFO, ADDED)
        self.assertEqual([d.airplay_name for d in discovery.devices()], ["Study"])
        self.change(discovery, None, REMOVED)
        self.assertEqual(discovery.devices(), [])

    def test_missing_info_is_ignored(self):
        discovery = Discovery(settle_seconds=0)
        self.change(discovery, None, ADDED)
        self.assertEqual(discovery.devices(), [])

    def test_devices_are_sorted(self):
        discovery = Discovery(settle_seconds=0)
        self.change(discovery, STUDY_INFO, ADDED)
        self.change(discovery, FakeInfo(["192.168.1.9"], {}, "Garage.local."), ADDED,
                    name="A1@garage._raop._tcp.local.")
        self.assertEqual([d.airplay_name for d in discovery.devices()], ["garage", "Study"])

    def test_waits_for_the_first_round_after_start(self):
        discovery = Discovery(settle_seconds=0.3)
        discovery._started_at = time.monotonic()
        started = time.monotonic()
        discovery.devices()
        self.assertGreaterEqual(time.monotonic() - started, 0.25)

    def test_no_wait_when_asked(self):
        discovery = Discovery(settle_seconds=5)
        discovery._started_at = time.monotonic()
        started = time.monotonic()
        discovery.devices(wait=False)
        self.assertLess(time.monotonic() - started, 0.1)

    def test_not_running_before_start(self):
        discovery = Discovery()
        self.assertFalse(discovery.running)
        self.assertIsNone(discovery.error)


if __name__ == "__main__":
    unittest.main()
