# spotconnect-docker

Play Spotify on your AirPlay speakers straight from the Spotify app. This repository runs
`spotraop` from [philippe44/SpotConnect](https://github.com/philippe44/SpotConnect) in Docker, so
each AirPlay device you enable shows up in Spotify as a Spotify Connect device. A small web page
finds the AirPlay devices on your network and gives you the command to enable or disable one.

> **All the hard work is done by [SpotConnect](https://github.com/philippe44/SpotConnect)**, written
> by [philippe44](https://github.com/philippe44). This repository only packages its `spotraop`
> binary and adds a helper page. If this is useful to you, give SpotConnect a star, and report
> playback bugs there once you have ruled out this packaging. See [Credits](#credits).

Working on this repository with a coding agent? Point it at [AGENTS.md](AGENTS.md).

## How it works

```
Spotify app  --(control)-->  spotraop on the Docker host  --(AirPlay)-->  speaker
                                        ^
              Spotify servers --(audio)--+
```

- Towards Spotify, spotraop is a Spotify Connect receiver. A speaker called `Kitchen` appears in
  the app as `Kitchen+`.
- Towards the speaker, it is an AirPlay sender. It fetches the audio from Spotify itself, encodes
  it as ALAC and streams it to the speaker. The phone is only a remote control, so playback goes
  on when it locks.
- There is one Connect device per AirPlay device that is enabled in `config/config.xml`. Nothing
  is enabled by default.

| Container | What |
|---|---|
| `spotraop` | spotraop, the static Linux x86_64 binary from the SpotConnect release. |
| `spotconnect-web` | The web page on port 8131. It reads the config and never writes it. |

## Requirements

- A Linux x86_64 host with Docker and Compose, on the same network as the speakers. Docker
  Desktop on macOS or Windows will not work: both containers need host networking to read and
  announce mDNS.
- Python 3.11 or newer on the host, for the `web/device` helper (standard library only).
- ssh access to the host from the computer you open the page on. The page shows commands to paste
  into a terminal there. You can also run them on the host itself, without the `ssh` part.

## Setup

On the Docker host:

1. Clone the repository, for example into `~/spotconnect`.
2. Create `.env` from the example and fill it in:

   ```bash
   cp .env.example .env
   ```

   `HOST_IP` is the host's LAN address, `SSH_TARGET` is how you reach the host with ssh (only
   used to build the commands on the page), and `REMOTE_DIR` is where the repository lives on the
   host.
3. Create the config folder:

   ```bash
   mkdir -p config/credentials
   cp config.xml.example config/config.xml
   ```

   Set `<interface>` in `config/config.xml` to the same address as `HOST_IP`.
4. Both containers run as uid and gid 1000 (`user:` in `compose.yml`). spotraop writes to
   `config/`, and so does `web/device`, which runs as your ssh user. Make sure those are the same
   user: if `id -u` and `id -g` do not both print 1000, change `user:` for both services.
5. Build and start:

   ```bash
   docker compose up -d --build
   ```

   The web image runs the unit tests while it builds.
6. Open `http://<HOST_IP>:8131`.

## Adding a speaker

1. On the page, type the AirPlay name under **Add a device**. Case, spaces and punctuation do not
   matter.
2. Copy the command it shows and run it in a terminal. It looks like this:

   ```bash
   ssh user@docker-host '~/spotconnect/web/device enable A1B2C3D4E5F6@Kitchen._raop._tcp.local --host Kitchen'
   ```

   `device` stops spotraop, updates the config (the previous version is kept as
   `config/config.xml.prev`), starts spotraop again and waits until it has picked up the device.
   That takes 10 to 30 seconds.
3. Pair once: open Spotify on a phone or computer on the same network and pick `Kitchen+` from the
   device list. spotraop stores the login in `config/credentials`, so the device comes back after
   a restart without pairing again. Spotify dropped username and password login for this, so
   pairing through the app is the way to go.

To disable a speaker, use the command under **Active in Spotify** on the page. On the host,
`web/device list` shows what is in the config.

## Good to know

- **Connected but silent? Check the volume in Spotify first.** spotraop starts every AirPlay
  session at -30 dB, the lowest level above mute, and a Spotify volume of 0% keeps it there. Volume
  changes show up in the log as `spotify VOLUME request <dB>`.
- **Editing `config.xml` by hand:** stop spotraop first (`docker compose stop spotraop`), edit,
  then `docker compose start spotraop`. spotraop rewrites the file on every network scan and has
  no reload.
- **New devices are not added to the config by themselves**, because `<common><enabled>` is 0.
  The minimum device block is a `<udn>` and `<enabled>1</enabled>`.
- **The udn** is the full mDNS name, `<id>@<AirPlay name>._raop._tcp.local`. The id cannot be
  derived from the name. The page looks it up for you; on the host, `avahi-browse -rpt _raop._tcp`
  shows it too.
- **The Spotify name.** Without a `<name>`, spotraop uses the device's mDNS host name plus `+`,
  which can differ from the AirPlay name (`Game Room (4)` may have the host name `Game-Room-4`).
  `device enable` therefore always writes `<name>` as the AirPlay name plus `+`.
- **A paired device stops announcing itself over mDNS.** Once it has credentials it logs in to
  Spotify directly and appears in the app through your account. Browsing
  `_spotify-connect._tcp` is therefore no way to tell whether a paired device works. Check the app
  or the log.
- **The Spotify library buffers its log output.** Lines such as `Authorization successful` can
  reach `docker compose logs` late, with odd timestamps.
- **`-c` is inverted in SpotConnect 0.20.7** (`-c alac` gives PCM, and the flag overrides the
  config file). `compose.yml` leaves it out and `config.xml` sets `<alac_encode>1</alac_encode>`
  instead. [Fixed in 0.20.8](https://github.com/philippe44/SpotConnect/issues/75).
- **`-Z` is required.** Without it spotraop runs its interactive prompt and keeps a CPU core busy.
  `-k` lets `docker compose stop` finish right away.
- **Apple TV.** The log line `AppleTV with no authentication key, create one using '-l' option`
  is informational, and an Apple TV 3 played fine without a key. If yours does need one, stop
  spotraop and run the pairing mode interactively:

  ```bash
  docker compose run --rm -it --no-deps spotraop -b <HOST_IP> -x /config/config.xml -l
  ```

  It asks for the Apple TV's IP address and the PIN it shows, then prints `secret is <hex>`. Type
  `exit` to leave. It does not store the key for a device that is already in the config: add
  `<raop_credentials><hex></raop_credentials>` to that device block yourself.
- **`exec_request ... request failed`** lines when playback starts are harmless.
- **Ports.** spotraop uses 38010 to 38073 (`-a 38010:64`) for the Connect endpoints, the page uses
  `WEB_PORT`. An Avahi daemon on the host is no problem: spotraop and python-zeroconf share udp
  port 5353 with it.

## Upgrading SpotConnect

The version is a build argument. Change `SPOTCONNECT_VERSION` and the `image:` tag in
`compose.yml`, then run `docker compose up -d --build spotraop`. The Dockerfile keeps only the
static x86_64 binary from the release zip.

## Files

| File | What |
|---|---|
| `AGENTS.md` | Guide for coding agents: map, commands, conventions, upstream etiquette. |
| `CLAUDE.md` | Imports `AGENTS.md` for Claude Code. |
| `Dockerfile` | Downloads the SpotConnect release and keeps `spotraop` and its license. |
| `compose.yml` | Both services, host networking, spotraop's command line. |
| `.env.example` | Host-specific values. Copy to `.env`. |
| `config.xml.example` | Starting point for `config/config.xml`, without devices. |
| `web/server.py` | The page and `/health`. Standard library HTTP server. |
| `web/discovery.py` | Tracks `_raop._tcp` devices with python-zeroconf. |
| `web/matching.py` | Fuzzy name matching. |
| `web/commands.py` | Builds the ssh command with safe quoting. |
| `web/spotconfig.py` | Reads and edits `config.xml`. Standard library only, Python 3.11 compatible. |
| `web/device` | Runs on the host: `list`, `enable <udn> [--host <host>]`, `disable <udn>`. |

Tests: `cd web && python3 -m unittest -v`. They need no packages beyond the standard library.

## For a coding agent

To change the code, read [AGENTS.md](AGENTS.md) first. To set the service up for a user, work in
this order, on the machine that will host it.

1. Check that the host runs Linux on x86_64 with Docker Compose and is on the same network as the
   speakers. Docker Desktop cannot do host networking the way this needs; stop and tell the user
   if that is all there is.
2. Ask the user for the host's LAN address and for the ssh login they use to reach it, and write
   `.env` from `.env.example`.
3. Create `config/credentials`, copy `config.xml.example` to `config/config.xml` and set
   `<interface>`. Match `user:` in `compose.yml` to the owner of the folder.
4. `docker compose up -d --build`, then check that `curl http://<HOST_IP>:<WEB_PORT>/health`
   answers with `"ok": true`.
5. Ask which speakers the user wants. Enable each with `web/device enable <udn> --host <host>`;
   the page shows both values for a device name.
6. **Stop here and hand back to the user.** Pairing has to be done by a person, once per speaker,
   by picking the device in the Spotify app on the same network.

Restarting the `spotraop` container only affects these Connect devices. `web/device` stops and
starts it by itself.

## Credits

- [SpotConnect](https://github.com/philippe44/SpotConnect) by
  [philippe44](https://github.com/philippe44) (MIT): `spotraop`, the bridge this whole repository
  exists to run. The image downloads the official release at build time and keeps SpotConnect's
  license at `/usr/share/doc/spotconnect/LICENSE`. The web page links back to it in its footer.
- SpotConnect in turn builds on [cspot](https://github.com/feelfreelinux/cspot),
  [libraop](https://github.com/philippe44/libraop), [pupnp](https://github.com/pupnp/pupnp) and
  [Mbed TLS](https://github.com/Mbed-TLS/mbedtls).
- [python-zeroconf](https://github.com/python-zeroconf/python-zeroconf) (LGPL 2.1 or later) finds
  the AirPlay devices for the web page; the web image installs it with pip.

This project is not affiliated with Spotify, Apple or the SpotConnect project. Spotify and AirPlay
are trademarks of their owners.

## License

MIT, see [LICENSE](LICENSE).
