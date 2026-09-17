"""Shell commands the page shows for enabling and disabling a device."""

from __future__ import annotations

import shlex
from typing import Optional


def device_command(action: str, udn: str, host: Optional[str], ssh_target: str,
                   remote_device: str) -> str:
    """Build `ssh <target> '<remote_device> <action> <udn> [--host <host>]'`.

    The udn and host are quoted for the remote shell, and the whole remote
    command is quoted again for the local shell, so any device name survives
    both. remote_device is left unquoted so that `~` expands on the remote side.
    """
    if action not in ("enable", "disable"):
        raise ValueError(f"unknown action: {action}")
    parts = [remote_device, action, shlex.quote(udn)]
    if host:
        parts += ["--host", shlex.quote(host)]
    return f"ssh {ssh_target} {shlex.quote(' '.join(parts))}"
