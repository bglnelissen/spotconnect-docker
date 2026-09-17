#!/usr/bin/env python3
"""Web page that shows which AirPlay devices spotraop offers to Spotify and
builds the commands to enable or disable one.

GET /                 the page
GET /?name=garage     search for an AirPlay device by name (fuzzy)
GET /?udn=<udn>       show one device
GET /health           JSON status, used by the Docker health check

The page only shows commands. It never changes the config itself.
"""

from __future__ import annotations

import html
import json
import os
import signal
import sys
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, quote, urlsplit

import spotconfig
from commands import device_command
from discovery import Discovery, NetworkDevice
from matching import match

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8131"))
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/config/config.xml")
INTERFACE = os.environ.get("INTERFACE", "")


@dataclass
class Settings:
    ssh_target: str = os.environ.get("SSH_TARGET", "user@docker-host")
    remote_device: str = os.environ.get("REMOTE_DEVICE", "~/spotconnect/web/device")
    remote_config: str = os.environ.get("REMOTE_CONFIG", "~/spotconnect/config/config.xml")


@dataclass
class Selection:
    kind: str
    device: Optional[NetworkDevice] = None
    choices: list = field(default_factory=list)


def select_device(query: str, udn: str, network: list) -> Selection:
    if udn:
        wanted = spotconfig.normalize_udn(udn)
        for device in network:
            if device.udn == wanted:
                return Selection("found", device)
        return Selection("not_found")
    if not query.strip():
        return Selection("none")

    def named(names):
        return [device for name in names for device in network if device.airplay_name == name]

    result = match(query, [device.airplay_name for device in network])
    if result.matches:
        found = named(result.matches)
        if len(found) == 1:
            return Selection("found", found[0])
        return Selection("choose", choices=found)
    return Selection("not_found", choices=named(result.suggestions))


def read_config(path: str):
    try:
        return spotconfig.list_devices(spotconfig.load(path)), None
    except spotconfig.ConfigError as exc:
        return [], str(exc)


def esc(value) -> str:
    return html.escape(str(value), quote=True)


class _Ids:
    def __init__(self):
        self.count = 0

    def next(self) -> str:
        self.count += 1
        return f"copy{self.count}"


def copy_block(ids: _Ids, text: str) -> str:
    block_id = ids.next()
    return (
        '<div class="copy">'
        f'<pre id="{block_id}">{esc(text)}</pre>'
        f'<button type="button" onclick="copyText(&#x27;{block_id}&#x27;, this)">Copy</button>'
        "</div>"
    )


def device_links(devices: list) -> str:
    items = "".join(
        f'<li><a href="/?udn={quote(device.udn, safe="")}">{esc(device.airplay_name)}</a> '
        f'<span class="meta">{esc(device.model)} {esc(device.address)}</span></li>'
        for device in devices
    )
    return f"<ul>{items}</ul>"


def render_active(config_devices: list, online: dict, settings: Settings, ids: _Ids) -> str:
    out = ["<section>", "<h2>Active in Spotify</h2>"]
    active = [device for device in config_devices if device.enabled]
    if not active:
        out.append("<p>No devices are enabled.</p>")
    for device in active:
        state = "on the network" if device.udn in online else "not seen on the network"
        command = device_command("disable", device.udn, None, settings.ssh_target,
                                 settings.remote_device)
        out.append(
            '<div class="card">'
            f"<h3>{esc(device.spotify_name)}</h3>"
            f'<p class="meta">AirPlay name {esc(device.airplay_name)}, {state}</p>'
            "<p>To disable it, run this in Terminal:</p>"
            f"{copy_block(ids, command)}"
            "</div>"
        )
    out.append("</section>")
    return "\n".join(out)


def render_found(device: NetworkDevice, config_devices: list, settings: Settings,
                 ids: _Ids) -> str:
    in_config = next((d for d in config_devices if d.udn == device.udn), None)
    head = [
        '<div class="card">',
        f"<h3>{esc(device.airplay_name)}</h3>",
        f'<p class="meta">{esc(device.model or "unknown model")}, {esc(device.address)}</p>',
    ]
    if in_config is not None and in_config.enabled:
        command = device_command("disable", device.udn, None, settings.ssh_target,
                                 settings.remote_device)
        return "\n".join(head + [
            f"<p>Already enabled. It shows up in Spotify as "
            f"<strong>{esc(in_config.spotify_name)}</strong>.</p>",
            "<p>To disable it, run this in Terminal:</p>",
            copy_block(ids, command),
            "</div>",
        ])

    if in_config is not None and in_config.name:
        spotify_name = in_config.name
    else:
        spotify_name = spotconfig.spotify_name_for(device.udn)
    command = device_command("enable", device.udn, device.host_name or None,
                             settings.ssh_target, settings.remote_device)
    config_file = f"<code>{esc(settings.remote_config)}</code>"
    if in_config is not None:
        where = f"This device is already in {config_file} but disabled. Its block will look like this:"
    else:
        where = f"This block will be added to {config_file}:"
    body = [
        f"<p>It will show up in Spotify as <strong>{esc(spotify_name)}</strong>.</p>",
        "<p>To enable it, run this in Terminal:</p>",
        copy_block(ids, command),
        '<p class="meta">Takes 10 to 30 seconds, the command shows its progress.</p>',
    ]
    if device.is_apple_tv:
        body.append(
            '<p class="note">This is an Apple TV. Some models need pairing (spotraop option '
            "<code>-l</code>) before they play audio. If Spotify connects but stays silent, "
            "that is the likely cause.</p>"
        )
    body += [
        f"<p>{where}</p>",
        copy_block(ids, spotconfig.device_block(device.udn, spotify_name)),
        '<p class="meta">To edit the file by hand instead, stop spotraop first '
        "(<code>docker compose stop spotraop</code>), edit, then start it again.</p>",
        "</div>",
    ]
    return "\n".join(head + body)


def render_search(query: str, udn: str, config_devices: list, network: list,
                  settings: Settings, ids: _Ids) -> str:
    out = [
        "<section>",
        "<h2>Add a device</h2>",
        '<form method="get" action="/">',
        '<label for="name">AirPlay name</label>',
        '<div class="row">'
        f'<input id="name" name="name" value="{esc(query)}" placeholder="for example Garage" '
        'autocomplete="off" autofocus>'
        '<button type="submit">Find</button>'
        "</div>",
        "</form>",
    ]
    selection = select_device(query, udn, network)
    if selection.kind == "found":
        out.append(render_found(selection.device, config_devices, settings, ids))
    elif selection.kind == "choose":
        out.append("<p>Several devices match. Pick one:</p>")
        out.append(device_links(selection.choices))
    elif selection.kind == "not_found":
        label = query.strip() or udn
        out.append(f'<p>No AirPlay device called "{esc(label)}" is on the network right now.</p>')
        if selection.choices:
            out.append("<p>Did you mean:</p>")
            out.append(device_links(selection.choices))
        out.append(
            '<p class="meta">Check that the device is switched on and on the same network. '
            "Case, spaces and punctuation do not matter.</p>"
        )
    out.append("</section>")
    return "\n".join(out)


PAGE_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SpotConnect devices</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #f6f6f4; --fg: #1d1d1f; --muted: #6b6b70; --card: #ffffff; --line: #dcdcd8;
  --accent: #1f7a4d; --on-accent: #ffffff; --error: #b3261e; --note: #8a5a00;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161617; --fg: #ececec; --muted: #9a9aa0; --card: #222224; --line: #3a3a3d;
    --accent: #4cc38a; --on-accent: #0d1f16; --error: #ff8a80; --note: #e0b25c;
  }
}
body { margin: 0; background: var(--bg); color: var(--fg);
       font: 16px/1.5 -apple-system, system-ui, sans-serif; }
main { max-width: 760px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 32px 0 12px; }
h3 { font-size: 1.05rem; margin: 0 0 4px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
        padding: 16px; margin: 12px 0; }
.meta { color: var(--muted); font-size: .9rem; margin: 0 0 8px; }
.error { color: var(--error); }
.note { color: var(--note); }
.row { display: flex; gap: 8px; margin-top: 6px; }
input { flex: 1; min-width: 0; font: inherit; padding: 8px 10px; border: 1px solid var(--line);
        border-radius: 8px; background: var(--card); color: var(--fg); }
button { font: inherit; padding: 8px 14px; border: 0; border-radius: 8px;
         background: var(--accent); color: var(--on-accent); cursor: pointer; }
.copy { display: flex; gap: 8px; align-items: flex-start; margin: 6px 0 10px; }
.copy pre { flex: 1; min-width: 0; margin: 0; padding: 10px; background: var(--bg);
            border: 1px solid var(--line); border-radius: 8px; white-space: pre-wrap;
            word-break: break-all; font: 13px/1.45 ui-monospace, Menlo, monospace; }
code { font-family: ui-monospace, Menlo, monospace; font-size: .9em; }
a { color: var(--accent); }
</style>
<script>
function copyText(id, button) {
  var text = document.getElementById(id).textContent;
  function done() {
    button.textContent = "Copied";
    setTimeout(function () { button.textContent = "Copy"; }, 1500);
  }
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(done);
    return;
  }
  var area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try { document.execCommand("copy"); done(); } finally { document.body.removeChild(area); }
}
</script>
</head>
<body>
<main>
<h1>SpotConnect devices</h1>
<p class="meta">AirPlay devices that spotraop offers as Spotify Connect endpoints.</p>"""

PAGE_FOOT = """</main>
</body>
</html>
"""


def render_page(query: str, udn: str, config_devices: list, config_error: Optional[str],
                network: list, discovery_error: Optional[str], settings: Settings) -> str:
    ids = _Ids()
    online = {device.udn: device for device in network}
    parts = [PAGE_HEAD]
    if discovery_error:
        parts.append(f'<p class="error">Network discovery is not working: {esc(discovery_error)}</p>')
    if config_error:
        parts.append(f'<p class="error">The config cannot be read: {esc(config_error)}</p>')
    parts.append(render_active(config_devices, online, settings, ids))
    parts.append(render_search(query, udn, config_devices, network, settings, ids))
    parts.append(PAGE_FOOT)
    return "\n".join(parts)


def make_handler(discovery, config_path: str, settings: Settings, quiet: bool = False):
    class Handler(BaseHTTPRequestHandler):
        server_version = "spotconnect-web"

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/health":
                self._health()
            elif url.path == "/":
                params = parse_qs(url.query)
                config_devices, config_error = read_config(config_path)
                body = render_page(
                    query=params.get("name", [""])[0],
                    udn=params.get("udn", [""])[0],
                    config_devices=config_devices,
                    config_error=config_error,
                    network=discovery.devices(),
                    discovery_error=discovery.error,
                    settings=settings,
                )
                self._send(200, "text/html; charset=utf-8", body.encode("utf-8"))
            else:
                self._send(404, "text/plain; charset=utf-8", b"Not found\n")

        def _health(self):
            _, config_error = read_config(config_path)
            status = {
                "ok": bool(discovery.running and config_error is None),
                "discovery": bool(discovery.running),
                "discovery_error": discovery.error,
                "config_readable": config_error is None,
                "devices_seen": len(discovery.devices(wait=False)),
            }
            self._send(200 if status["ok"] else 503, "application/json",
                       json.dumps(status).encode("utf-8"))

        def _send(self, code: int, content_type: str, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            if not quiet and not self.path.startswith("/health"):
                super().log_message(format, *args)

    return Handler


def healthcheck() -> int:
    host = "127.0.0.1" if HOST in ("", "0.0.0.0") else HOST
    try:
        with urllib.request.urlopen(f"http://{host}:{PORT}/health", timeout=4) as response:
            return 0 if response.status == 200 else 1
    except Exception as exc:
        print(f"health check failed: {exc}", file=sys.stderr)
        return 1


def _stop(signum, frame):
    raise KeyboardInterrupt


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--healthcheck"]:
        return healthcheck()
    discovery = Discovery()
    discovery.start(INTERFACE or None)
    if discovery.error:
        print(discovery.error, file=sys.stderr, flush=True)
    httpd = ThreadingHTTPServer((HOST, PORT), make_handler(discovery, CONFIG_PATH, Settings()))
    signal.signal(signal.SIGTERM, _stop)
    print(f"Listening on http://{HOST}:{PORT}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        discovery.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
