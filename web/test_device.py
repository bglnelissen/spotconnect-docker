import fcntl
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DEVICE = os.path.join(HERE, "device")

CONFIG = (
    '<?xml version="1.0"?>\r\n<spotraop>\r\n'
    "<device>\r\n<udn>A0A0A0A0A0A1@Study._raop._tcp.local</udn>\r\n<name>Study+</name>\r\n"
    "<friendly_name>Study</friendly_name>\r\n<enabled>1</enabled>\r\n</device>\r\n"
    "<device>\r\n<udn>B0B0B0B0B0B2@Game Room (4)._raop._tcp.local</udn>\r\n<name></name>\r\n"
    "<friendly_name>Game-Room-4</friendly_name>\r\n<enabled>0</enabled>\r\n</device>\r\n"
    "</spotraop>\r\n"
)
STUDY = "A0A0A0A0A0A1@Study._raop._tcp.local"
GAME = "B0B0B0B0B0B2@Game Room (4)._raop._tcp.local"
GARAGE = "A1B2C3D4E5F6@Garage._raop._tcp.local"
STARTED = "spotraop  | [07:42:49.058] main:1248 Starting spotraop version: v0.20.7\n"

FAKE_DOCKER = """#!/bin/sh
echo "$*" >> "$FAKE_DIR/calls.log"
case "$*" in
  *" logs "*) cat "$FAKE_DIR/logs.txt" 2>/dev/null ;;
  *" stop "*) if [ -f "$FAKE_DIR/fail_stop" ]; then echo "cannot stop" >&2; exit 1; fi ;;
esac
exit 0
"""


class DeviceScriptTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = tmp.name
        os.mkdir(os.path.join(self.project, "config"))
        self.config = os.path.join(self.project, "config", "config.xml")
        with open(self.config, "w", newline="") as handle:
            handle.write(CONFIG)
        self.docker = os.path.join(self.project, "fake-docker")
        with open(self.docker, "w") as handle:
            handle.write(FAKE_DOCKER)
        os.chmod(self.docker, 0o755)

    def set_logs(self, text):
        with open(os.path.join(self.project, "logs.txt"), "w") as handle:
            handle.write(text)

    def run_device(self, *args):
        env = dict(os.environ, SPOTCONNECT_DIR=self.project, DEVICE_DOCKER=self.docker,
                   DEVICE_WAIT_SECONDS="2", FAKE_DIR=self.project)
        return subprocess.run([sys.executable, DEVICE, *args], capture_output=True, text=True,
                              env=env, timeout=30)

    def calls(self):
        path = os.path.join(self.project, "calls.log")
        if not os.path.exists(path):
            return []
        with open(path) as handle:
            return [line.split(" --since ")[0] for line in handle.read().splitlines()]

    def config_text(self):
        with open(self.config, newline="") as handle:
            return handle.read()

    def test_is_executable(self):
        self.assertTrue(os.access(DEVICE, os.X_OK))

    def test_list(self):
        result = self.run_device("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            f"on   {'Study+':<28} {STUDY}",
            f"off  {'Game-Room-4+':<28} {GAME}",
        ])
        self.assertEqual(self.calls(), [])

    def test_enable_existing_device_and_wait(self):
        self.set_logs(STARTED + "spotraop  | [07:42:49.138] AddRaopDevice:594 [0x1]: "
                      "adding renderer (Game-Room-4@192.168.1.47) with mac AAAA-1\n")
        result = self.run_device("enable", GAME, "--host", "Game-Room-4")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "Stopping spotraop... done",
            "Updating config (backup in config.xml.prev)... done",
            "Starting spotraop... done",
            "Waiting for Game Room (4)+ to appear (up to 2 s)",
            "Ready: Game Room (4)+ is now available in Spotify.",
        ])
        self.assertEqual(self.calls(), ["compose stop spotraop", "compose start spotraop",
                                        "compose logs --no-color"])
        self.assertIn("<name>Game Room (4)+</name>\n<friendly_name>Game-Room-4</friendly_name>\n"
                      "<enabled>1</enabled>\n</device>\n</spotraop>", self.config_text())
        with open(self.config + ".prev", newline="") as handle:
            self.assertEqual(handle.read(), CONFIG)

    def test_enable_new_device_times_out_when_it_does_not_appear(self):
        self.set_logs(STARTED)
        started = time.monotonic()
        result = self.run_device("enable", GARAGE, "--host", "Garage")
        self.assertEqual(result.returncode, 1)
        self.assertGreaterEqual(time.monotonic() - started, 2)
        self.assertIn("Waiting for Garage+ to appear (up to 2 s)..\n", result.stdout)
        self.assertIn("Garage+ did not show up in the log.", result.stdout)
        self.assertIn("Starting spotraop version", result.stdout)
        self.assertIn("<udn>A1B2C3D4E5F6@Garage._raop._tcp.local</udn>\n<name>Garage+</name>\n"
                      "<enabled>1</enabled>", self.config_text())

    def test_enable_without_host_does_not_wait(self):
        result = self.run_device("enable", GARAGE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Done: Garage+ is enabled.", result.stdout)
        self.assertEqual(self.calls(), ["compose stop spotraop", "compose start spotraop"])

    def test_enable_already_enabled(self):
        result = self.run_device("enable", STUDY + ".")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Study+ is already enabled. Nothing to do.\n")
        self.assertEqual(self.calls(), [])

    def test_enable_rejects_invalid_udn(self):
        result = self.run_device("enable", "Garage")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a valid device id", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_disable(self):
        self.set_logs(STARTED)
        result = self.run_device("disable", STUDY)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Waiting for spotraop to start (up to 2 s)\n", result.stdout)
        self.assertIn("Done: Study+ is disabled.", result.stdout)
        self.assertIn("<udn>A0A0A0A0A0A1@Study._raop._tcp.local</udn>\n<name>Study+</name>\n"
                      "<friendly_name>Study</friendly_name>\n<enabled>0</enabled>",
                      self.config_text())

    def test_disable_when_already_disabled_or_missing(self):
        self.assertEqual(self.run_device("disable", GAME).stdout,
                         "Game-Room-4+ is already disabled. Nothing to do.\n")
        self.assertEqual(self.run_device("disable", GARAGE).stdout,
                         "Garage is not in the config. Nothing to do.\n")
        self.assertEqual(self.calls(), [])

    def test_broken_config_stops_before_docker(self):
        with open(self.config, "w") as handle:
            handle.write("<spotraop><device>")
        result = self.run_device("enable", GAME)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: cannot read", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_failed_stop_changes_nothing(self):
        open(os.path.join(self.project, "fail_stop"), "w").close()
        result = self.run_device("enable", GAME)
        self.assertEqual(result.returncode, 1)
        self.assertIn("docker compose stop spotraop failed: cannot stop", result.stderr)
        self.assertEqual(self.calls(), ["compose stop spotraop"])
        self.assertEqual(self.config_text(), CONFIG)

    def test_failed_update_still_starts_spotraop(self):
        # A directory where the backup file should go makes the backup fail.
        os.makedirs(os.path.join(self.config + ".prev", "config.xml"))
        result = self.run_device("enable", GAME)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Updating config (backup in config.xml.prev)... failed", result.stdout)
        self.assertIn("Starting spotraop... done", result.stdout)
        self.assertIn("could not update the config", result.stderr)
        self.assertEqual(self.calls(), ["compose stop spotraop", "compose start spotraop"])
        self.assertEqual(self.config_text(), CONFIG)

    def test_second_command_is_refused_while_one_runs(self):
        with open(os.path.join(self.project, ".device.lock"), "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            result = self.run_device("enable", GAME)
        self.assertEqual(result.returncode, 1)
        self.assertIn("another device command is running", result.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
