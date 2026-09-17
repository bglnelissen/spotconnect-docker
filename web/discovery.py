"""Keep track of AirPlay (RAOP) receivers on the network with python-zeroconf.

zeroconf is imported inside Discovery.start(), so this module and its tests
work without it installed.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from spotconfig import airplay_name, normalize_udn

RAOP_TYPE = "_raop._tcp.local."


@dataclass(frozen=True)
class NetworkDevice:
    udn: str
    airplay_name: str
    address: str
    model: str
    host_name: str

    @property
    def is_apple_tv(self) -> bool:
        return self.model.lower().startswith("appletv")


def _decode(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def device_from_info(name: str, addresses: list, properties: dict,
                     server: Optional[str]) -> NetworkDevice:
    props = {_decode(key): _decode(value) for key, value in properties.items()}
    ipv4 = [address for address in addresses if ":" not in address]
    address = (ipv4 or addresses or [""])[0]
    # spotraop uses the host name up to ".local" as the device's friendly name.
    host = (server or "").rstrip(".")
    cut = host.lower().find(".local")
    if cut >= 0:
        host = host[:cut]
    udn = normalize_udn(name)
    return NetworkDevice(udn=udn, airplay_name=airplay_name(udn), address=address,
                         model=props.get("am", ""), host_name=host)


class Discovery:
    """Background browser for _raop._tcp. devices() returns a snapshot."""

    def __init__(self, settle_seconds: float = 5.0):
        self._lock = threading.Lock()
        self._devices = {}
        self._settle = settle_seconds
        self._started_at: Optional[float] = None
        self._zeroconf = None
        self._browser = None
        self.error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._zeroconf is not None and self.error is None

    def start(self, interface: Optional[str] = None) -> None:
        try:
            from zeroconf import InterfaceChoice, ServiceBrowser, Zeroconf

            interfaces = [interface] if interface else InterfaceChoice.All
            self._zeroconf = Zeroconf(interfaces=interfaces)
            self._browser = ServiceBrowser(self._zeroconf, RAOP_TYPE, handlers=[self._on_change])
            self._started_at = time.monotonic()
        except Exception as exc:  # reported on the page and in /health
            self.error = f"discovery failed to start: {exc}"

    def _on_change(self, zeroconf, service_type, name, state_change) -> None:
        if getattr(state_change, "name", "") == "Removed":
            with self._lock:
                self._devices.pop(normalize_udn(name), None)
            return
        info = zeroconf.get_service_info(service_type, name, timeout=3000)
        if info is None:
            return
        device = device_from_info(name, info.parsed_addresses(), info.properties, info.server)
        with self._lock:
            self._devices[device.udn] = device

    def devices(self, wait: bool = True) -> list:
        if wait and self._started_at is not None:
            remaining = self._settle - (time.monotonic() - self._started_at)
            if remaining > 0:
                time.sleep(remaining)
        with self._lock:
            return sorted(self._devices.values(), key=lambda d: d.airplay_name.casefold())

    def close(self) -> None:
        if self._browser is not None:
            self._browser.cancel()
        if self._zeroconf is not None:
            self._zeroconf.close()
