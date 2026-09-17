import os
import stat
import tempfile
import unittest

import spotconfig

SAMPLE = (
    '<?xml version="1.0"?>\r\n'
    "<spotraop>\r\n"
    "<common>\r\n<enabled>0</enabled>\r\n</common>\r\n"
    "<interface>192.168.1.10</interface>\r\n"
    "<device>\r\n"
    "<udn>A0A0A0A0A0A1@Study._raop._tcp.local</udn>\r\n"
    "<name></name>\r\n"
    "<friendly_name>Study</friendly_name>\r\n"
    "<credentials></credentials>\r\n"
    "<enabled>1</enabled>\r\n"
    "</device>\r\n"
    "<device>\r\n"
    "<udn>B0B0B0B0B0B2@Game Room (4)._raop._tcp.local</udn>\r\n"
    "<name></name>\r\n"
    "<friendly_name>Game-Room-4</friendly_name>\r\n"
    "<credentials></credentials>\r\n"
    "<enabled>0</enabled>\r\n"
    "</device>\r\n"
    "</spotraop>\r\n"
)

STUDY = "A0A0A0A0A0A1@Study._raop._tcp.local"
GAME = "B0B0B0B0B0B2@Game Room (4)._raop._tcp.local"
GARAGE = "A1B2C3D4E5F6@Garage._raop._tcp.local"


def write_sample(folder, content=SAMPLE):
    path = os.path.join(folder, "config.xml")
    with open(path, "w", newline="") as handle:
        handle.write(content)
    return path


class NamesTest(unittest.TestCase):
    def test_airplay_name_strips_id_and_suffix(self):
        self.assertEqual(spotconfig.airplay_name(GAME), "Game Room (4)")

    def test_airplay_name_accepts_trailing_dot(self):
        self.assertEqual(spotconfig.airplay_name(STUDY + "."), "Study")

    def test_spotify_name_for_adds_plus(self):
        self.assertEqual(spotconfig.spotify_name_for(GAME), "Game Room (4)+")

    def test_valid_udns(self):
        self.assertTrue(spotconfig.is_valid_udn(STUDY))
        self.assertTrue(spotconfig.is_valid_udn(GAME + "."))

    def test_invalid_udns(self):
        for bad in ["", "Study", "A0A0A0A0A0A1@Study", "@Study._raop._tcp.local",
                    "x y@Study._raop._tcp.local"]:
            with self.subTest(bad=bad):
                self.assertFalse(spotconfig.is_valid_udn(bad))

    def test_device_block_escapes_xml(self):
        self.assertEqual(
            spotconfig.device_block("A1@Tom & Jerry._raop._tcp.local", "Tom & Jerry+"),
            "<device>\n"
            "<udn>A1@Tom &amp; Jerry._raop._tcp.local</udn>\n"
            "<name>Tom &amp; Jerry+</name>\n"
            "<enabled>1</enabled>\n"
            "</device>",
        )


class ReadTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = write_sample(self.dir.name)

    def test_list_devices(self):
        devices = spotconfig.list_devices(spotconfig.load(self.path))
        self.assertEqual([d.udn for d in devices], [STUDY, GAME])
        self.assertEqual([d.enabled for d in devices], [True, False])

    def test_spotify_name_falls_back_to_friendly_name(self):
        study = spotconfig.find_device(spotconfig.load(self.path), STUDY)
        self.assertEqual(study.spotify_name, "Study+")
        self.assertEqual(study.airplay_name, "Study")

    def test_spotify_name_prefers_name(self):
        device = spotconfig.ConfigDevice(GAME, "Games+", "Game-Room-4", True)
        self.assertEqual(device.spotify_name, "Games+")

    def test_spotify_name_without_friendly_name(self):
        device = spotconfig.ConfigDevice(GARAGE, "", "", True)
        self.assertEqual(device.spotify_name, "Garage+")

    def test_find_device_missing(self):
        self.assertIsNone(spotconfig.find_device(spotconfig.load(self.path), GARAGE))

    def test_load_missing_file(self):
        with self.assertRaises(spotconfig.ConfigError):
            spotconfig.load(os.path.join(self.dir.name, "nope.xml"))

    def test_load_broken_file(self):
        path = write_sample(self.dir.name, "<spotraop><device>")
        with self.assertRaises(spotconfig.ConfigError):
            spotconfig.load(path)


class EditTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.tree = spotconfig.load(write_sample(self.dir.name))

    def test_enable_existing_block(self):
        self.assertTrue(spotconfig.enable(self.tree, GAME))
        game = spotconfig.find_device(self.tree, GAME)
        self.assertEqual(game, spotconfig.ConfigDevice(GAME, "Game Room (4)+", "Game-Room-4", True))

    def test_enable_twice_changes_nothing_the_second_time(self):
        spotconfig.enable(self.tree, GAME)
        self.assertFalse(spotconfig.enable(self.tree, GAME))
        self.assertEqual(len(spotconfig.list_devices(self.tree)), 2)

    def test_enable_fills_empty_name_of_enabled_device(self):
        self.assertTrue(spotconfig.enable(self.tree, STUDY))
        self.assertEqual(spotconfig.find_device(self.tree, STUDY).name, "Study+")

    def test_enable_keeps_existing_name(self):
        self.tree.getroot().findall("device")[1].find("name").text = "Games+"
        self.assertTrue(spotconfig.enable(self.tree, GAME))
        self.assertEqual(spotconfig.find_device(self.tree, GAME).name, "Games+")

    def test_enable_adds_missing_block(self):
        self.assertTrue(spotconfig.enable(self.tree, GARAGE + "."))
        self.assertEqual(spotconfig.find_device(self.tree, GARAGE),
                         spotconfig.ConfigDevice(GARAGE, "Garage+", "", True))
        self.assertEqual(len(spotconfig.list_devices(self.tree)), 3)
        self.assertFalse(spotconfig.enable(self.tree, GARAGE))
        self.assertEqual(len(spotconfig.list_devices(self.tree)), 3)

    def test_disable(self):
        self.assertTrue(spotconfig.disable(self.tree, STUDY))
        self.assertFalse(spotconfig.find_device(self.tree, STUDY).enabled)
        self.assertFalse(spotconfig.disable(self.tree, STUDY))

    def test_disable_missing_or_disabled(self):
        self.assertFalse(spotconfig.disable(self.tree, GAME))
        self.assertFalse(spotconfig.disable(self.tree, GARAGE))
        self.assertEqual(len(spotconfig.list_devices(self.tree)), 2)


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = write_sample(self.dir.name)

    def test_round_trip(self):
        tree = spotconfig.load(self.path)
        spotconfig.enable(tree, GARAGE)
        spotconfig.save(tree, self.path)
        reloaded = spotconfig.load(self.path)
        self.assertEqual([d.udn for d in spotconfig.list_devices(reloaded)], [STUDY, GAME, GARAGE])
        self.assertEqual(reloaded.getroot().findtext("interface"), "192.168.1.10")

    def test_written_file_format(self):
        tree = spotconfig.load(self.path)
        spotconfig.enable(tree, GARAGE)
        spotconfig.save(tree, self.path)
        with open(self.path, "rb") as handle:
            data = handle.read()
        self.assertTrue(data.startswith(b'<?xml version="1.0"?>\n<spotraop>'))
        self.assertNotIn(b"\r", data)
        self.assertIn(
            b"</device>\n<device>\n"
            b"<udn>A1B2C3D4E5F6@Garage._raop._tcp.local</udn>\n"
            b"<name>Garage+</name>\n"
            b"<enabled>1</enabled>\n"
            b"</device>\n</spotraop>\n",
            data,
        )
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o644)

    def test_no_temporary_files_left(self):
        spotconfig.save(spotconfig.load(self.path), self.path)
        self.assertEqual(os.listdir(self.dir.name), ["config.xml"])


if __name__ == "__main__":
    unittest.main()
