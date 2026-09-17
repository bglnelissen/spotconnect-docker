import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import server
import spotconfig
from discovery import NetworkDevice

STUDY_UDN = "A0A0A0A0A0A1@Study._raop._tcp.local"
GAME_UDN = "B0B0B0B0B0B2@Game Room (4)._raop._tcp.local"
GARAGE_UDN = "A1B2C3D4E5F6@Garage._raop._tcp.local"

STUDY = NetworkDevice(STUDY_UDN, "Study", "192.168.1.23", "AppleTV3,2", "Study")
GAME = NetworkDevice(GAME_UDN, "Game Room (4)", "192.168.1.47", "AppleTV14,1", "Game-Room-4")
GARAGE = NetworkDevice(GARAGE_UDN, "Garage", "192.168.1.50", "AudioAccessory5,1", "Garage")
TWIN = NetworkDevice("FFFF@Garage._raop._tcp.local", "Garage", "192.168.1.51", "", "Garage-2")
NETWORK = [GAME, GARAGE, STUDY]

CONFIG = [
    spotconfig.ConfigDevice(STUDY_UDN, "", "Study", True),
    spotconfig.ConfigDevice(GAME_UDN, "", "Game-Room-4", False),
]
SETTINGS = server.Settings(
    ssh_target="user@docker-host",
    remote_device="~/spotconnect/web/device",
    remote_config="~/spotconnect/config/config.xml",
)


def page(query="", udn="", config=CONFIG, config_error=None, network=NETWORK, discovery_error=None):
    return server.render_page(query=query, udn=udn, config_devices=config,
                              config_error=config_error, network=network,
                              discovery_error=discovery_error, settings=SETTINGS)


class SelectDeviceTest(unittest.TestCase):
    def test_nothing_asked(self):
        self.assertEqual(server.select_device("", "", NETWORK).kind, "none")

    def test_found_by_name(self):
        selection = server.select_device("GARAGE", "", NETWORK)
        self.assertEqual((selection.kind, selection.device), ("found", GARAGE))

    def test_found_by_udn_with_trailing_dot(self):
        selection = server.select_device("", GAME_UDN + ".", NETWORK)
        self.assertEqual((selection.kind, selection.device), ("found", GAME))

    def test_unknown_udn(self):
        self.assertEqual(server.select_device("", "X@Nope._raop._tcp.local", NETWORK).kind, "not_found")

    def test_choose_between_devices_with_the_same_name(self):
        selection = server.select_device("garage", "", NETWORK + [TWIN])
        self.assertEqual(selection.kind, "choose")
        self.assertEqual({d.udn for d in selection.choices}, {GARAGE_UDN, TWIN.udn})

    def test_not_found_with_suggestion(self):
        selection = server.select_device("garge", "", NETWORK)
        self.assertEqual((selection.kind, selection.choices), ("not_found", [GARAGE]))


class RenderPageTest(unittest.TestCase):
    def test_footer_credits_spotconnect(self):
        html = page()
        self.assertIn('<a href="https://github.com/philippe44/SpotConnect">SpotConnect</a>', html)
        self.assertIn("philippe44", html)

    def test_active_section_lists_enabled_devices_with_disable_command(self):
        html = page()
        self.assertIn("Active in Spotify", html)
        self.assertIn("Study+", html)
        self.assertIn("~/spotconnect/web/device disable A0A0A0A0A0A1@Study._raop._tcp.local", html)
        self.assertIn("on the network", html)
        self.assertNotIn("Game-Room-4+", html)

    def test_active_device_not_on_the_network(self):
        self.assertIn("not seen on the network", page(network=[]))

    def test_no_enabled_devices(self):
        self.assertIn("No devices are enabled.", page(config=[CONFIG[1]]))

    def test_found_new_device(self):
        html = page(query="garage")
        self.assertIn("Garage+", html)
        self.assertIn(
            "ssh user@docker-host &#x27;~/spotconnect/web/device enable "
            "A1B2C3D4E5F6@Garage._raop._tcp.local --host Garage&#x27;", html)
        self.assertIn("This block will be added to", html)
        self.assertIn("&lt;name&gt;Garage+&lt;/name&gt;", html)
        self.assertIn("Takes 10 to 30 seconds", html)
        self.assertNotIn("This is an Apple TV", html)

    def test_found_disabled_device_in_config(self):
        html = page(query="gameroom 4")
        self.assertIn("already in <code>~/spotconnect/config/config.xml</code> but disabled", html)
        self.assertIn("Game Room (4)+", html)
        self.assertIn("--host Game-Room-4", html)
        self.assertIn("This is an Apple TV", html)

    def test_already_enabled(self):
        self.assertIn("Already enabled", page(query="study"))

    def test_choose(self):
        html = page(query="garage", network=NETWORK + [TWIN])
        self.assertIn("Several devices match", html)
        self.assertIn('href="/?udn=FFFF%40Garage._raop._tcp.local"', html)

    def test_not_found_with_suggestion(self):
        html = page(query="Garge")
        self.assertIn('No AirPlay device called "Garge"', html)
        self.assertIn("Did you mean", html)
        self.assertIn('href="/?udn=A1B2C3D4E5F6%40Garage._raop._tcp.local"', html)

    def test_user_input_is_escaped(self):
        html = page(query="<script>alert(1)</script>")
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_errors_are_shown(self):
        html = page(config=[], config_error="cannot read /config/config.xml",
                    discovery_error="no network")
        self.assertIn("The config cannot be read: cannot read /config/config.xml", html)
        self.assertIn("Network discovery is not working: no network", html)


class FakeDiscovery:
    def __init__(self, devices, error=None):
        self._devices = devices
        self.error = error
        self.running = error is None

    def devices(self, wait=True):
        return list(self._devices)


class HttpTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.config_path = os.path.join(self.dir.name, "config.xml")
        with open(self.config_path, "w") as handle:
            handle.write(
                '<?xml version="1.0"?>\n<spotraop>\n<device>\n'
                "<udn>A0A0A0A0A0A1@Study._raop._tcp.local</udn>\n<name></name>\n"
                "<friendly_name>Study</friendly_name>\n<enabled>1</enabled>\n"
                "</device>\n</spotraop>\n")

    def start(self, discovery, config_path):
        handler = server.make_handler(discovery, config_path, SETTINGS, quiet=True)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    def test_page_and_search(self):
        base = self.start(FakeDiscovery(NETWORK), self.config_path)
        with urllib.request.urlopen(base + "/?name=garage") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers["Content-Type"])
            body = response.read().decode("utf-8")
        self.assertIn("Study+", body)
        self.assertIn("Garage+", body)

    def test_health_ok(self):
        base = self.start(FakeDiscovery(NETWORK), self.config_path)
        with urllib.request.urlopen(base + "/health") as response:
            status = json.loads(response.read())
        self.assertEqual(status, {"ok": True, "discovery": True, "discovery_error": None,
                                  "config_readable": True, "devices_seen": 3})

    def test_health_fails_without_config(self):
        base = self.start(FakeDiscovery(NETWORK), os.path.join(self.dir.name, "missing.xml"))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(base + "/health")
        self.assertEqual(caught.exception.code, 503)
        caught.exception.close()

    def test_unknown_path(self):
        base = self.start(FakeDiscovery(NETWORK), self.config_path)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(base + "/nope")
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()


if __name__ == "__main__":
    unittest.main()
