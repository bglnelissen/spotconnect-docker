"""Read and edit spotraop's config.xml.

Standard library only, and compatible with Python 3.11: the `device` helper
imports this module on the Docker host, where the system Python is 3.11.
"""

from __future__ import annotations

import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape

UDN_SUFFIX = "._raop._tcp.local"
_UDN_RE = re.compile(r"^[^@\s]+@.+\._raop\._tcp\.local$")
_DECLARATION = b'<?xml version="1.0"?>\n'


class ConfigError(Exception):
    """The config file is missing or is not valid XML."""


@dataclass(frozen=True)
class ConfigDevice:
    udn: str
    name: str
    friendly_name: str
    enabled: bool

    @property
    def airplay_name(self) -> str:
        return airplay_name(self.udn)

    @property
    def spotify_name(self) -> str:
        """What spotraop shows in Spotify: <name>, or the host name plus '+'."""
        if self.name:
            return self.name
        return (self.friendly_name or self.airplay_name) + "+"


def normalize_udn(udn: str) -> str:
    """Strip whitespace and the trailing dot that zeroconf adds."""
    return udn.strip().rstrip(".")


def is_valid_udn(udn: str) -> bool:
    return bool(_UDN_RE.match(normalize_udn(udn)))


def airplay_name(udn: str) -> str:
    """'ABC@Game Room (4)._raop._tcp.local' becomes 'Game Room (4)'."""
    rest = normalize_udn(udn).split("@", 1)[-1]
    if rest.endswith(UDN_SUFFIX):
        rest = rest[: -len(UDN_SUFFIX)]
    return rest


def spotify_name_for(udn: str) -> str:
    """The Spotify name this project always uses: the AirPlay name plus '+'."""
    return airplay_name(udn) + "+"


def device_block(udn: str, name: str) -> str:
    """The minimal XML block for an enabled device, as the page shows it."""
    return (
        "<device>\n"
        f"<udn>{escape(udn)}</udn>\n"
        f"<name>{escape(name)}</name>\n"
        "<enabled>1</enabled>\n"
        "</device>"
    )


def load(path: str) -> ET.ElementTree:
    try:
        return ET.parse(path)
    except (OSError, ET.ParseError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc


def _text(element: ET.Element, tag: str) -> str:
    return (element.findtext(tag) or "").strip()


def _device_elements(tree: ET.ElementTree) -> list:
    return tree.getroot().findall("device")


def _find_element(tree: ET.ElementTree, udn: str) -> Optional[ET.Element]:
    wanted = normalize_udn(udn)
    for element in _device_elements(tree):
        if _text(element, "udn") == wanted:
            return element
    return None


def _to_device(element: ET.Element) -> ConfigDevice:
    return ConfigDevice(
        udn=_text(element, "udn"),
        name=_text(element, "name"),
        friendly_name=_text(element, "friendly_name"),
        enabled=_text(element, "enabled") == "1",
    )


def list_devices(tree: ET.ElementTree) -> list:
    return [_to_device(element) for element in _device_elements(tree)]


def find_device(tree: ET.ElementTree, udn: str) -> Optional[ConfigDevice]:
    element = _find_element(tree, udn)
    return None if element is None else _to_device(element)


def _set_child(parent: ET.Element, tag: str, value: str) -> None:
    child = parent.find(tag)
    if child is None:
        child = ET.SubElement(parent, tag)
        child.tail = "\n"
    child.text = value


def enable(tree: ET.ElementTree, udn: str) -> bool:
    """Enable a device, adding its block when missing. True if anything changed."""
    udn = normalize_udn(udn)
    element = _find_element(tree, udn)
    if element is None:
        element = ET.SubElement(tree.getroot(), "device")
        element.text = "\n"
        element.tail = "\n"
        _set_child(element, "udn", udn)
        _set_child(element, "name", spotify_name_for(udn))
        _set_child(element, "enabled", "1")
        return True
    changed = False
    if _text(element, "enabled") != "1":
        _set_child(element, "enabled", "1")
        changed = True
    if not _text(element, "name"):
        _set_child(element, "name", spotify_name_for(udn))
        changed = True
    return changed


def disable(tree: ET.ElementTree, udn: str) -> bool:
    """Disable a device. True if it was enabled."""
    element = _find_element(tree, udn)
    if element is None or _text(element, "enabled") != "1":
        return False
    _set_child(element, "enabled", "0")
    return True


def save(tree: ET.ElementTree, path: str) -> None:
    """Write atomically: temporary file next to the target, parse check, rename."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".xml", dir=folder)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_DECLARATION)
            tree.write(handle, encoding="utf-8", xml_declaration=False)
            handle.write(b"\n")
        ET.parse(tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
