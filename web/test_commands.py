import subprocess
import unittest

from commands import device_command


def run_like_ssh(command):
    """Run a generated command with `ssh` replaced by a shell function that hands
    the remote command to a second shell, the way sshd does."""
    script = 'ssh() { shift; sh -c "$1"; }\n' + command
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=True).stdout


class DeviceCommandTest(unittest.TestCase):
    def test_simple_command_is_readable(self):
        self.assertEqual(
            device_command("enable", "A0A0A0A0A0A1@Study._raop._tcp.local", "Study",
                           "user@docker-host", "~/spotconnect/web/device"),
            "ssh user@docker-host '~/spotconnect/web/device enable "
            "A0A0A0A0A0A1@Study._raop._tcp.local --host Study'",
        )

    def test_without_host(self):
        self.assertEqual(
            device_command("disable", "A1@Garage._raop._tcp.local", None, "me@box", "/opt/device"),
            "ssh me@box '/opt/device disable A1@Garage._raop._tcp.local'",
        )

    def test_unknown_action(self):
        with self.assertRaises(ValueError):
            device_command("remove", "A1@Garage._raop._tcp.local", None, "me@box", "/opt/device")

    def test_awkward_names_survive_two_shells(self):
        names = ["Game Room (4)", "Sam's HomePod", 'Say "hi" $HOME `id` ; echo x', "Tom & Jerry"]
        for name in names:
            udn = f"A1B2@{name}._raop._tcp.local"
            with self.subTest(name=name):
                command = device_command("enable", udn, name, "me@box", "printf '%s|'")
                self.assertEqual(run_like_ssh(command), f"enable|{udn}|--host|{name}|")


if __name__ == "__main__":
    unittest.main()
