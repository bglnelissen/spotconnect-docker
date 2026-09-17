# AGENTS.md

Guide for coding agents working on this repository. Humans: start with [README.md](README.md),
which also covers setup and the known quirks in detail.

## What this is

A thin Docker packaging around **spotraop**, the AirPlay half of
[SpotConnect](https://github.com/philippe44/SpotConnect) by philippe44. spotraop does all the real
work: it is a Spotify Connect receiver towards Spotify and an AirPlay sender towards the speaker.
This repository adds:

- a `Dockerfile` that downloads a pinned SpotConnect release and keeps the static binary;
- a `compose.yml` with host networking and the right command line;
- `web/`, a small read-only web page that finds AirPlay devices and shows the command to enable or
  disable one, plus `web/device`, the helper that runs that command on the host.

We did not write spotraop and we do not patch it. See [Upstream](#upstream-spotconnect) below.

## Map

| Path | What |
|---|---|
| `Dockerfile` | Builds the `spotraop` image from the release zip. Version is a build argument. |
| `compose.yml` | Services `spotraop` and `web`. Host-specific values come from `.env`. |
| `.env.example` | `HOST_IP`, `SSH_TARGET`, `REMOTE_DIR`, `WEB_PORT`. Real `.env` is not tracked. |
| `config.xml.example` | Starting `config/config.xml` without devices. `config/` is not tracked (credentials). |
| `web/server.py` | The page and `GET /health`. `http.server`, no framework. |
| `web/discovery.py` | Browses `_raop._tcp` with python-zeroconf (imported lazily). |
| `web/matching.py` | Fuzzy name matching: case, spaces and punctuation are ignored. |
| `web/commands.py` | Builds `ssh <target> '<device> enable <udn> --host <host>'` with `shlex` quoting. |
| `web/spotconfig.py` | Reads and edits spotraop's `config.xml` with ElementTree, atomic save. |
| `web/device` | Host-side CLI: `list`, `enable <udn> [--host <host>]`, `disable <udn>`. |
| `web/test_*.py` | unittest suites, one per module. |

## Commands

```bash
cd web && python3 -m unittest -v            # all tests, standard library only, a few seconds
docker compose up -d --build                 # on the Docker host; the web build runs the tests too
docker compose ps                            # web should report (healthy)
curl -s http://192.168.1.10:8131/health     # your HOST_IP and WEB_PORT; {"ok": true, ...}
docker compose logs --since 10m spotraop     # spotraop log
web/device list                              # devices in config/config.xml
```

The containers only work on a Linux host (host networking for mDNS). On macOS you can run the
tests and read the code, not the services.

## How the pieces fit

1. `config/config.xml` decides which AirPlay devices spotraop offers to Spotify. `<common><enabled>`
   is 0, so only devices with their own `<enabled>1</enabled>` block are used.
2. The web container mounts `config/` read-only. It never changes anything; it renders commands.
3. The user pastes a command; it runs `web/device` on the host over ssh. `device` takes a lock,
   stops spotraop, writes the config (backup in `config/config.xml.prev`), starts spotraop and
   waits for `adding renderer (<host name>@` in the log.
4. The user pairs the device once in the Spotify app. spotraop stores the login in
   `config/credentials/`, so later restarts need no pairing.

## Conventions

- **English everywhere:** code, comments, output, docs, commit messages.
- **Plain punctuation:** no emoji, no em dash or en dash.
- **Python:** `web/device` and `web/spotconfig.py` run with the host's system Python and must stay
  compatible with Python 3.11 and the standard library. The web image may use newer Python;
  python-zeroconf is its only dependency and is pinned in `web/Dockerfile`.
- **Tests first:** add or change a test for every behaviour change and keep the whole suite green.
  The image build fails on a failing test.
- **No personal data in tracked files:** no real IP addresses, host names, user names, device ids
  (they are MAC addresses) or room names. Tests and examples use made-up values such as
  `A1B2C3D4E5F6@Garage._raop._tcp.local`, `user@docker-host` and `192.168.1.10`. Host-specific
  values belong in `.env`.
- **Pinned versions:** upgrading SpotConnect means changing `SPOTCONNECT_VERSION` and the `image:`
  tag in `compose.yml` and rebuilding. No scripts that fetch "latest".
- **License:** MIT. New dependencies must be compatible.
- **Local notes:** `CLAUDE.local.md`, `PROJECT_STATUS.md` and `docs/` are ignored by git. They
  may exist in a maintainer's checkout with notes about one specific home network; read them if
  present, never commit them.

## Working with spotraop

- **Config changes:** stop spotraop, edit, start. It has no reload and rewrites `config.xml` on
  every network scan, so edits to a running instance get lost. `web/device` does this for you.
- **Required flags:** `-Z` (otherwise an interactive prompt burns a CPU core) and `-k`. Leave `-c`
  out while on 0.20.7, where it is inverted; `<alac_encode>1</alac_encode>` in the config selects
  ALAC.
- **Useful log lines:** `adding renderer (<host>@<ip>)` means a device was picked up;
  `spotify VOLUME request <dB>` is a volume change; `setting volume as part of connect -30.00` is
  the quiet start of every session. Output of the Spotify library is buffered and may arrive late.
- **Harmless noise:** `exec_request ... request failed` at playback start, and
  `AppleTV with no authentication key` for an Apple TV that plays anyway.
- **Silent playback:** check the volume in the Spotify app before anything else.
- **Needs a person, stop and ask:** pairing a device in the Spotify app, and Apple TV pairing with
  `-l`, which asks for a PIN shown on the TV.
- **Restarting** the `spotraop` container only affects its own Connect devices.

## Upstream: SpotConnect

spotraop is written and maintained by [philippe44](https://github.com/philippe44) in
[SpotConnect](https://github.com/philippe44/SpotConnect) (MIT), on top of
[cspot](https://github.com/feelfreelinux/cspot), philippe44's
[libraop](https://github.com/philippe44/libraop), [pupnp](https://github.com/pupnp/pupnp) and
[Mbed TLS](https://github.com/Mbed-TLS/mbedtls). Treat it with respect:

- Do not patch, wrap or re-host the binary. The Dockerfile downloads the official release and
  copies SpotConnect's `LICENSE` into the image at `/usr/share/doc/spotconnect/LICENSE`.
- Keep the credit visible: the README and the footer of the web page name SpotConnect and link
  to it. Do not remove that.
- When spotraop misbehaves, first rule out this packaging (flags in `compose.yml`, the config,
  host networking). Then read the upstream
  [CHANGELOG](https://github.com/philippe44/SpotConnect/blob/master/CHANGELOG) and
  [issues](https://github.com/philippe44/SpotConnect/issues); the fix may already be released.
- Report real upstream bugs there, briefly and politely, with the SpotConnect version, the exact
  command line and a short log excerpt, and without personal data. SpotConnect is free software;
  be considerate of the maintainer's time.
  Example of a good report: [issue 75](https://github.com/philippe44/SpotConnect/issues/75).
- Reading the source helps: `spotraop/src/spotraop.c` (command line, device handling),
  `spotraop/src/config_raop.c` (config file), `spotraop/src/spotify.cpp` (Connect side), and
  `src/pairing.cpp` in libraop (Apple TV pairing). Read the tag that matches
  `SPOTCONNECT_VERSION`.

## Before you finish

1. `cd web && python3 -m unittest` passes.
2. `git diff` contains no personal data (see Conventions).
3. README and this file still match what the code does.
4. If you changed `compose.yml` or a Dockerfile and have the host at hand:
   `docker compose config` resolves, `docker compose up -d --build` succeeds, `/health` is ok.
