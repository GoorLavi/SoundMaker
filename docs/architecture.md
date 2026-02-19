# SoundMaker — System Architecture & Design

This document is the single source of truth for SoundMaker's architecture, design decisions, and implementation plan. It is structured for both human reading and AI-assisted development.

---

## 1. Project Overview

SoundMaker is a distributed home audio system built on Raspberry Pi hardware. A single **Master** device receives all audio and distributes it in perfect sync to multiple **Slave** speakers throughout the home. The system is controlled via a mobile-first Web UI and runs entirely headless.

### What SoundMaker Does

- Streams internet radio as the always-on default audio source
- Receives Spotify Connect and Bluetooth audio from phones/laptops
- Distributes synced audio to every room via Snapcast
- Provides a mobile-first Web UI for room control, volume, and source management
- Runs Pi-hole for network-wide DNS ad blocking
- Operates fully headless — no keyboard, mouse, or monitor required

### What SoundMaker Does NOT Do

- Video playback
- Per-room independent audio sources (all rooms play the same thing)
- AirPlay (replaced by Bluetooth + Spotify Connect)
- Complex DSP or room calibration
- Integration with proprietary ecosystems beyond Spotify Connect
- Any UI or logic on the Slave devices

---

## 2. Hardware

### Master — Raspberry Pi 5 (8GB)

| Component    | Details                              |
| ------------ | ------------------------------------ |
| Board        | Raspberry Pi 5, 8GB RAM             |
| Audio output | None — Master has no speaker         |
| Network      | WiFi (2.4GHz + 5GHz) and Ethernet   |
| Storage      | micro-SD card (64GB+)               |
| Power        | USB-C, 5V/5A official PSU           |

The Master is an orchestrator. It receives audio from all sources, mixes it through PulseAudio, and distributes it to Slaves via Snapcast. It never plays audio locally.

### Slave — Raspberry Pi Zero 2 W

| Component    | Details                              |
| ------------ | ------------------------------------ |
| Board        | Raspberry Pi Zero 2 W               |
| Audio output | USB DAC → AUX → powered speaker     |
| Network      | WiFi (2.4GHz only)                  |
| Storage      | micro-SD card (32GB+)               |
| Power        | micro-USB, 5V/2A+ stable supply     |

Each Slave is a dumb speaker endpoint. It runs only a Snapcast Client and outputs audio. Nothing else.

---

## 3. Audio Sources

The Master receives audio from three sources, with strict priority ordering.

### Priority Table

| Priority | Source           | Technology                | Trigger                                       |
| -------- | ---------------- | ------------------------- | --------------------------------------------- |
| 1 (high) | Spotify Connect  | `raspotify` (librespot)   | Phone selects Master as Spotify speaker        |
| 2        | Bluetooth        | BlueZ A2DP sink           | Paired phone connects and plays audio          |
| 3 (low)  | Internet Radio   | `mpv` via PulseAudio      | Always-on default when nothing else is active  |

### Source Switching Rules

- A higher-priority source **automatically stops** any lower-priority source.
- On disconnect, the system **cascades back down** the priority chain:
  - Spotify disconnects → resume Bluetooth if still connected, otherwise resume radio.
  - Bluetooth disconnects → resume radio.
- Radio is the baseline. It plays whenever no higher-priority source is active.
- When Spotify or Bluetooth is active, the Web UI play/stop buttons are **disabled**. The phone controls playback. Volume and room toggles remain functional.

### Source Detection

| Source          | Connect event                                   | Disconnect event                                |
| --------------- | ----------------------------------------------- | ----------------------------------------------- |
| Spotify Connect | `raspotify` fires `on_play` event               | `raspotify` fires `on_stop`/`on_disconnect`     |
| Bluetooth       | BlueZ D-Bus signal: A2DP transport active       | BlueZ D-Bus signal: A2DP transport removed      |
| Internet Radio  | `mpv` process started by the Master             | `mpv` process stopped by the Master             |

The Python backend on the Master monitors all three sources via event listeners and manages switching.

---

## 4. Audio Pipeline

All audio follows a single path regardless of source.

```
┌─────────────────────────────────────────────────────┐
│                    MASTER (Pi 5)                     │
│                                                     │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐ │
│  │   mpv    │  │ raspotify │  │ BlueZ A2DP Sink  │ │
│  │ (radio)  │  │ (spotify) │  │   (bluetooth)    │ │
│  └────┬─────┘  └─────┬─────┘  └────────┬─────────┘ │
│       │               │                 │           │
│       └───────────────┼─────────────────┘           │
│                       ▼                             │
│              ┌────────────────┐                      │
│              │   PulseAudio   │                      │
│              │   (mixer)      │                      │
│              └───────┬────────┘                      │
│                      ▼                              │
│              ┌────────────────┐                      │
│              │  Pipe Sink     │                      │
│              │ /tmp/snapfifo  │                      │
│              └───────┬────────┘                      │
│                      ▼                              │
│              ┌────────────────┐                      │
│              │ Snapcast Server│                      │
│              └───────┬────────┘                      │
│                      │ TCP :1704                    │
└──────────────────────┼──────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
   ┌────────────┐ ┌────────────┐ ┌────────────┐
   │  Slave A   │ │  Slave B   │ │  Slave C   │
   │ Snapcast   │ │ Snapcast   │ │ Snapcast   │
   │  Client    │ │  Client    │ │  Client    │
   │     │      │ │     │      │ │     │      │
   │     ▼      │ │     ▼      │ │     ▼      │
   │  USB DAC   │ │  USB DAC   │ │  USB DAC   │
   │  Speaker   │ │  Speaker   │ │  Speaker   │
   └────────────┘ └────────────┘ └────────────┘
```

### Synchronization

Snapcast provides sub-millisecond audio sync across all Slaves:

1. Snapcast Server timestamps each audio chunk with the server clock.
2. Snapcast Clients buffer audio and play at the exact scheduled time.
3. Per-client latency compensation adjusts for network delay.
4. Default buffer is ~1 second, configurable per client.

### PulseAudio Pipe Sink Configuration

All PulseAudio output is routed to a named pipe that Snapcast reads from:

```
load-module module-pipe-sink file=/tmp/snapfifo sink_name=Snapcast format=s16le rate=48000
set-default-sink Snapcast
```

### Key Constraint

The Master does **not** run a Snapcast Client. It has no speaker. Only Slaves run Snapcast Clients.

---

## 5. Slave Architecture

### What a Slave Runs

- **Snapcast Client** — connects to Master's Snapcast Server on TCP :1704
- **System-level audio** — ALSA/PulseAudio outputting to USB DAC

That's it. No application code, no Python, no web server, no logic.

### Discovery

Slaves are discovered **automatically**. When a Slave boots, its Snapcast Client connects to the Master's Snapcast Server. The Master's backend detects the new client by polling Snapcast's `Server.GetStatus` JSON-RPC endpoint. New clients appear as "unnamed" in the Web UI. The user names them from the UI (e.g., "Kitchen", "Bedroom").

### Volume Control

Volume per Slave is controlled remotely from the Master via Snapcast's JSON-RPC API:

```json
{
  "jsonrpc": "2.0",
  "method": "Client.SetVolume",
  "params": {
    "id": "<snapcast-client-id>",
    "volume": { "percent": 75, "muted": false }
  }
}
```

### Toggling a Slave On/Off

Toggling a room on/off in the Web UI mutes/unmutes the corresponding Snapcast Client. The audio stream continues; the client just plays silence when muted.

### Slave Failure Behavior

- If a Slave loses WiFi or crashes, the Master and other Slaves are unaffected.
- The Snapcast Client auto-retries connection every 5 seconds.
- When reconnected, the Slave syncs and resumes playing immediately.
- No fallback behavior on the Slave. If the Master is unreachable, the Slave is silent.

---

## 6. Master Services

The Master runs the following services, all managed by systemd:

| Service               | Technology               | Purpose                                        |
| --------------------- | ------------------------ | ---------------------------------------------- |
| Snapcast Server       | `snapserver`             | Distributes synced audio to all Slaves          |
| Spotify Connect       | `raspotify`              | Receives Spotify audio from phones/laptops      |
| Bluetooth A2DP        | BlueZ + PulseAudio       | Receives Bluetooth audio from paired devices    |
| Internet Radio        | `mpv`                    | Plays default stream URL via PulseAudio         |
| Audio Mixer           | PulseAudio               | Merges all sources, outputs to Snapcast pipe    |
| Backend API           | Python + FastAPI          | REST API, source management, state, BT control  |
| Web UI                | React (static files)     | Mobile-first SPA served by FastAPI              |
| Pi-hole               | Pi-hole                  | DNS-level ad blocking for the whole network     |

### Service Dependency Order

```
network-online
    │
    ├── pulseaudio
    ├── snapserver
    ├── bluetoothd (BlueZ)
    ├── raspotify
    └── pihole-FTL
            │
            ▼
    soundmaker-backend.service
        │
        ├── starts/stops mpv (radio) internally
        ├── monitors raspotify events
        ├── monitors BlueZ D-Bus signals
        └── serves React UI + REST API
```

---

## 7. Web UI

### Technology

Lightweight React 19 SPA with Vite, mobile-first dark theme. Built to static files on the dev machine (macOS) and committed to the repo as `master/frontend/dist/`. Served by the FastAPI backend. No SSR, no heavy framework, no Node.js on the Pi.

Dependencies: `react`, `react-dom`, `vite`, `@vitejs/plugin-react` — nothing else.

During development, `npm run dev` runs Vite's dev server with a proxy to the backend (`/api` → `localhost:8000`).

### Screens and Controls

#### Main Dashboard

- **Current source indicator** — shows "Radio", "Spotify", or "Bluetooth" with visual distinction
- **Play/stop button** — controls radio; **disabled** when Spotify or Bluetooth is active
- **Stream URL** — configurable default internet radio URL

#### Room Management

- **List of all Slaves** — each showing:
  - Room name (editable)
  - Online/offline status indicator
  - Volume slider (0–100%)
  - On/off toggle (mute/unmute)
- **Unnamed Slaves** appear at the bottom for naming after first connection

#### Bluetooth

- **"Pair New Device" button** — makes Master discoverable for 60 seconds, shows countdown
- **Paired devices list** — shows previously paired devices
- **One active Bluetooth audio connection at a time**

#### Pi-hole (implemented)

- **Status badge** — "active" (green) or "disabled" (red) based on blocking state
- **Stats row** — queries today, blocked count, blocked percentage
- **Toggle switch** — enables/disables blocking via `POST /api/pihole/enable` or `/disable`
- **Admin link** — opens Pi-hole admin UI at `http://<master>:8080/admin` in a new tab
- **Polling** — refreshes status every 10 seconds
- **Graceful degradation** — shows "unavailable" when Pi-hole or backend is unreachable

---

## 8. Communication Model

| Path                           | Protocol                 | Port  | Purpose                              |
| ------------------------------ | ------------------------ | ----- | ------------------------------------ |
| Master → Slaves (audio)       | Snapcast TCP stream      | 1704  | Synced PCM audio distribution        |
| Master ↔ Slaves (control)     | Snapcast JSON-RPC        | 1705  | Volume, mute, client status          |
| Browser → Master (UI)         | HTTP                     | 80    | React SPA + FastAPI REST API         |
| Remote device → Master (VPN)  | Tailscale (WireGuard)    | —     | Encrypted tunnel for remote access   |
| Phone → Master (Spotify)      | Spotify Connect (WiFi)   | —     | Handled by raspotify/librespot       |
| Phone → Master (Bluetooth)    | Bluetooth A2DP           | —     | Handled by BlueZ                     |
| Network → Master (DNS)        | DNS                      | 53    | Pi-hole ad-blocking                  |

---

## 9. Persistent State

The Master stores all state in JSON files. No database.

### `state/slaves.json`

```json
{
  "slaves": [
    {
      "snapcast_id": "aabbccdd-1234-...",
      "name": "Kitchen",
      "volume": 75,
      "muted": false,
      "first_seen": "2026-02-18T10:30:00Z"
    },
    {
      "snapcast_id": "eeffaabb-5678-...",
      "name": null,
      "volume": 100,
      "muted": false,
      "first_seen": "2026-02-18T14:15:00Z"
    }
  ]
}
```

### `state/config.json`

```json
{
  "default_stream_url": "https://uk3.internet-radio.com/proxy/1940sradio/stream",
  "default_volume": 100
}
```

### `state/bluetooth.json`

```json
{
  "paired_devices": [
    {
      "mac": "AA:BB:CC:DD:EE:FF",
      "name": "Avi's iPhone",
      "paired_at": "2026-02-18T10:00:00Z"
    }
  ]
}
```

### Where State Lives on Disk

All JSON files stored under `/opt/soundmaker/state/` on the Master. Backed up periodically (implementation detail).

---

## 10. Bluetooth Management

### How It Works

The Master acts as a Bluetooth **A2DP sink** (audio receiver). BlueZ handles pairing, connection, and audio routing. The Python backend controls BlueZ programmatically via D-Bus.

### Pairing Flow

1. User taps "Pair New Device" in the Web UI.
2. Backend sets the Master's Bluetooth adapter to **discoverable** for 60 seconds.
3. User finds "SoundMaker" on their phone's Bluetooth settings and pairs.
4. Backend accepts the pairing request automatically.
5. Device is saved to `bluetooth.json`.
6. Discoverable mode turns off after 60 seconds (or after successful pairing).

### Audio Routing

When a paired phone connects and starts Bluetooth audio:

1. BlueZ establishes an A2DP transport.
2. PulseAudio automatically routes BT audio through the `bluez_source` module.
3. Backend detects the BT audio stream via D-Bus signal.
4. Source switching logic stops radio (if playing), promotes Bluetooth as active source.
5. Audio flows: BlueZ → PulseAudio → pipe sink → Snapcast → Slaves.

### Constraints

- One active Bluetooth audio connection at a time.
- Previously paired devices auto-connect without re-pairing.
- Backend monitors BlueZ D-Bus for connect/disconnect events.

---

## 11. Spotify Connect

### How It Works

The Master runs `raspotify`, a Debian package wrapping `librespot`. It advertises the Master as a Spotify Connect device on the local network. Phones with Spotify Premium see "SoundMaker" as an available speaker.

### Audio Routing

1. Phone selects "SoundMaker" in Spotify's device picker.
2. `raspotify` receives the audio stream over WiFi.
3. `raspotify` outputs to PulseAudio.
4. Audio flows: raspotify → PulseAudio → pipe sink → Snapcast → Slaves.

### Event Handling

`raspotify` supports event hooks. The backend monitors these to detect:

- **Playback started** — triggers source switch to Spotify, stops lower-priority sources.
- **Playback stopped / device disconnected** — triggers fallback to next available source.

### Requirements

- Spotify Premium account on the connecting device.
- Master and phone on the same local network.

---

## 12. Internet Radio

### How It Works

`mpv` plays a configurable stream URL, outputting to PulseAudio. The backend starts and stops `mpv` as needed.

### Behavior

- Radio is the **default source**. It plays automatically on system boot.
- When a higher-priority source connects, the backend stops `mpv`.
- When all higher-priority sources disconnect, the backend restarts `mpv`.
- The stream URL is configurable from the Web UI and persisted in `config.json`.

### Resilience

- If `mpv` crashes, the backend restarts it with exponential backoff.
- If the stream URL is unreachable, `mpv` retries internally.

---

## 13. Pi-hole

### Version

SoundMaker uses **Pi-hole v6**, which replaced the legacy `api.php` + lighttpd stack with a new REST API embedded directly in the `pihole-FTL` binary.

### Installation

The Master install script (`install_master.sh`) performs an **unattended** Pi-hole install:

1. Creates the `pihole` system user and group.
2. Places `master/pihole.toml` at `/etc/pihole/pihole.toml` before running the installer — this makes the installer treat it as an upgrade rather than a fresh install, skipping interactive prompts.
3. Runs `curl -sSL https://install.pi-hole.net | bash /dev/stdin --unattended`.
4. Updates gravity blocklists with `pihole -g`.
5. Sets the admin password via `pihole setpassword`.

### Configuration (`master/pihole.toml`)

Only settings that differ from Pi-hole defaults:

| Setting                  | Value                                      | Reason                                              |
| ------------------------ | ------------------------------------------ | --------------------------------------------------- |
| `dns.upstreams`          | Cloudflare (1.1.1.1, 1.0.0.1) + Google (8.8.8.8, 8.8.4.4) | Redundant upstream DNS               |
| `dns.blocking.active`    | `true`                                     | Blocking enabled by default                         |
| `webserver.port`         | `8080`                                     | Avoids conflict with SoundMaker backend on port 80  |

All devices on the network should point their DNS to the Master's IP.

### Pi-hole v6 REST API

Pi-hole v6 uses **session-based authentication**. The backend (`pihole_api.py`) authenticates by POSTing the password to `/api/auth`, receives a short-lived session ID (SID), and passes it via `X-FTL-SID` header on subsequent requests. Sessions auto-renew on expiry.

| Backend function        | Pi-hole endpoint            | Method | Purpose                          |
| ----------------------- | --------------------------- | ------ | -------------------------------- |
| `get_blocking_status()` | `/api/dns/blocking`         | GET    | Check if blocking is enabled     |
| `set_blocking()`        | `/api/dns/blocking`         | POST   | Enable/disable blocking          |
| `get_stats_summary()`   | `/api/stats/summary`        | GET    | Queries, blocked count, clients  |

**Note:** Pi-hole v6's GET `/api/dns/blocking` returns `"enabled"` / `"disabled"` as strings, not booleans. The `get_status()` function normalizes this to `true` / `false` before sending it to the frontend.

The Pi-hole password is stored in `/opt/soundmaker/.env` (chmod 600) and read via the `PIHOLE_PASSWORD` environment variable.

### SoundMaker API Endpoints

| Method | Endpoint              | Behavior                                                       |
| ------ | --------------------- | -------------------------------------------------------------- |
| GET    | `/api/pihole/status`  | Combined blocking state + stats; degrades gracefully if Pi-hole is down |
| POST   | `/api/pihole/enable`  | Enables ad blocking                                            |
| POST   | `/api/pihole/disable` | Disables blocking; optional `?timer=N` for temporary disable (seconds) |

### Web UI Integration

The SoundMaker Web UI exposes basic Pi-hole controls:

| Control               | Implementation                                           |
| --------------------- | -------------------------------------------------------- |
| Toggle blocking       | `POST /api/pihole/enable` or `POST /api/pihole/disable`  |
| Stats (queries/day)   | `GET /api/pihole/status`                                  |
| Link to admin UI      | Direct link to `http://<master>:8080/admin`               |

Pi-hole runs as an independent service (`pihole-FTL.service`). SoundMaker's backend talks to it over localhost via the v6 REST API.

---

## 14. Project Structure

### Git Repository

The entire project lives in a single Git repository. All Master code lives under `master/`. The repo is cloned to `/opt/soundmaker` on the Pi.

```
SoundMaker/
├── master/
│   ├── backend/                 # Python FastAPI backend
│   │   ├── main.py              # Entry point, FastAPI app
│   │   ├── auth.py              # Authentication, sessions, rate limiting
│   │   ├── audio_manager.py     # Source switching, priority logic
│   │   ├── radio_player.py      # mpv process management
│   │   ├── spotify_monitor.py   # raspotify event monitoring
│   │   ├── bluetooth_manager.py # BlueZ D-Bus control
│   │   ├── snapcast_api.py      # Snapcast JSON-RPC client
│   │   ├── pihole_api.py        # Pi-hole v6 REST API client
│   │   ├── state_manager.py     # JSON state persistence
│   │   └── requirements.txt     # Python dependencies
│   │
│   ├── frontend/                # React Web UI (Vite + React 19)
│   │   ├── src/
│   │   │   ├── main.jsx         # React entry point
│   │   │   ├── App.jsx          # Dashboard shell + auth state
│   │   │   ├── api.js           # Shared fetch wrapper (401 handling)
│   │   │   └── components/
│   │   │       ├── LoginScreen.jsx  # Login form
│   │   │       └── PiholeCard.jsx
│   │   ├── index.html
│   │   ├── vite.config.js
│   │   ├── package.json
│   │   └── dist/                # Built static files (committed to repo)
│   │
│   ├── pihole.toml              # Pi-hole v6 config template (placed at /etc/pihole/)
│   └── install_master.sh        # Master installation script
│
├── slave/
│   └── install_slave.sh         # Slave installation script
│
├── deploy.sh                    # Deployment helper (runs from dev machine)
│
├── .gitignore
│
├── docs/
│   └── architecture.md          # This document
│
└── README.md
```

### Why Slaves Have No Application Code

Slaves run only a Snapcast Client, which is an off-the-shelf binary installed by `install_slave.sh`. All control (volume, mute, naming) happens remotely from the Master via Snapcast's JSON-RPC API. There is no Python code, no web server, and no custom logic on a Slave.

### What Is NOT Committed to Git

Managed by `.gitignore`:

- `node_modules/` — installed locally for development, never on the Pi
- `__pycache__/` — Python bytecode
- `.venv/` — Python virtual environment (created on device by install script)
- `state/*.json` — runtime state files (slaves, config, bluetooth)
- `.env` — runtime environment config (Pi-hole password, paths)
- `.DS_Store` — macOS metadata

---

## 15. Deployment

Deployment is **Git-based**. Code is developed on macOS, pushed to the remote repo, and pulled on the Pi(s).

### React Frontend Build Strategy

The React frontend is built **on the dev machine** (macOS), and the `dist/` output is committed to the repo. This means:

- No Node.js needed on the Pi
- `git pull` on the Pi gives it ready-to-serve static files
- FastAPI serves the built files directly

Build workflow (on dev machine):

```bash
cd master/frontend
npm run build        # outputs to dist/
git add dist/
git commit
git push
```

### Master Deployment

First time:

```bash
ssh goorlavi@soundmaker-master.local
cd /opt
sudo git clone <repo-url> soundmaker
sudo chown -R goorlavi:goorlavi /opt/soundmaker
cd /opt/soundmaker/master
sudo PIHOLE_PW=yourpassword ./install_master.sh
```

The install script handles: system packages, Pi-hole (unattended), Python venv, backend dependencies, environment config (`/opt/soundmaker/.env`), and the `soundmaker-backend.service` systemd unit.

Subsequent updates:

```bash
ssh goorlavi@soundmaker-master.local
cd /opt/soundmaker
git pull
sudo ./master/install_master.sh    # only if dependencies/services changed
```

### Slave Deployment

First time:

```bash
ssh goorlavi@soundmaker-slave.local
cd /opt
sudo git clone <repo-url> soundmaker
sudo chown -R goorlavi:goorlavi /opt/soundmaker
cd /opt/soundmaker/slave
sudo ./install_slave.sh            # defaults to soundmaker-master.local
```

Subsequent updates (rarely needed — Slaves have minimal code):

```bash
ssh goorlavi@soundmaker-slave.local
cd /opt/soundmaker
git pull
sudo ./slave/install_slave.sh
```

### deploy.sh Helper

A convenience script in the repo root, run from the dev machine:

```bash
./deploy.sh master                          # git pull + install on Master
./deploy.sh slave soundmaker-kitchen.local  # git pull + install on a Slave
```

It SSHes into the target device, runs `git pull`, and optionally re-runs the install script.

### Adding a New Room

1. Flash Raspberry Pi OS Lite (32-bit) to a Pi Zero 2 W.
2. Boot, connect to WiFi, SSH in.
3. Clone the repo to `/opt/soundmaker`.
4. Run `install_slave.sh`.
5. The Slave auto-connects to the Master.
6. Open the Web UI — the new Slave appears as unnamed.
7. Name it (e.g., "Bathroom").
8. Done.

---

## 16. Failure Handling

| Failure                     | System behavior                                                  |
| --------------------------- | ---------------------------------------------------------------- |
| Slave loses WiFi            | Other Slaves unaffected. Slave retries every 5s, auto-resumes.  |
| Slave crashes/reboots       | Same as WiFi loss — auto-reconnects after boot.                  |
| Master loses WiFi           | All Slaves go silent. Resume when Master reconnects.             |
| Master crashes/reboots      | All Slaves go silent. systemd restarts services. Slaves resume.  |
| mpv crashes                 | Backend restarts mpv with exponential backoff.                    |
| raspotify crashes           | systemd restarts it. Spotify reconnects automatically.            |
| BlueZ hangs                 | Backend monitors via D-Bus. systemd restart as last resort.       |
| Snapcast Server crashes     | systemd restarts it. All Slaves auto-reconnect.                   |
| Stream URL unreachable      | mpv retries internally. Backend logs the failure.                 |
| Pi-hole crashes             | systemd restarts it. DNS resolves normally (fails open).          |

---

## 17. Network Requirements

| Requirement                    | Details                                          |
| ------------------------------ | ------------------------------------------------ |
| Same local network             | Master and all Slaves on the same WiFi/LAN       |
| 2.4GHz WiFi available          | Pi Zero 2 W only supports 2.4GHz                 |
| mDNS / Avahi                   | For `soundmaker-master.local` hostname resolution |
| Open TCP ports on Master       | 1704 (Snapcast audio), 1705 (Snapcast control), 80 (Web UI), 8080 (Pi-hole admin), 53 (Pi-hole DNS) |
| Stable internet on Master      | For radio streaming, Spotify, Pi-hole updates     |

---

## 18. Security

| Aspect                    | Approach                                                    |
| ------------------------- | ----------------------------------------------------------- |
| Web UI authentication     | Password-based login with bcrypt-hashed password, HTTP-only session cookies (7-day TTL) |
| Login rate limiting       | Max 5 attempts per minute per IP — prevents brute-force     |
| Remote access             | Tailscale VPN (WireGuard) — encrypted tunnel, no open ports |
| Snapcast traffic          | Unencrypted PCM on local network — acceptable for home use  |
| Bluetooth pairing         | Discoverable only when triggered from UI, 60s timeout       |
| Spotify Connect           | Secured by Spotify's own authentication                     |
| Pi-hole admin             | Pi-hole's built-in web password                             |
| SSH                       | Key-based SSH locally; Tailscale SSH for remote access      |
| Credentials storage       | Password hash and secrets in `/opt/soundmaker/.env` (chmod 600) |

The Web UI requires authentication. Remote access is provided via Tailscale VPN, which encrypts all traffic with WireGuard. No ports are exposed to the public internet.

---

## 19. Authentication

### How It Works

The SoundMaker Web UI and all API endpoints (except `/api/health`) require authentication. The backend uses a single shared password, hashed with bcrypt and stored in the `.env` file.

### Login Flow

1. User opens the Web UI and sees a login screen.
2. User enters the password. Frontend sends `POST /api/auth/login` with the password.
3. Backend verifies against `SOUNDMAKER_PASSWORD_HASH` (bcrypt).
4. On success, backend creates a session token and sets an HTTP-only `session` cookie (7-day TTL).
5. Subsequent API requests include the cookie. The `require_auth` dependency validates it.
6. On logout, `POST /api/auth/logout` revokes the session and clears the cookie.

### Session Storage

Sessions are stored in-memory on the backend. On service restart, all sessions are invalidated and users must log in again. This is acceptable for a single-user home system.

### Rate Limiting

The login endpoint limits to 5 attempts per minute per IP address. Excess attempts receive HTTP 429.

### Password Setup

The password is set during `install_master.sh` (via `SOUNDMAKER_PW` env var or interactive prompt). The script hashes it with bcrypt (12 rounds) and writes the hash to `/opt/soundmaker/.env`.

---

## 20. Remote Access (Tailscale VPN)

### Why Tailscale

Tailscale provides a zero-config WireGuard mesh VPN. It requires no port forwarding, no static IP, and no DDNS. It installs as a single package and runs as a systemd service.

### How It Works

1. `tailscaled` runs on the Master as a systemd service.
2. The Master joins a private Tailscale network (tailnet) and receives a stable `100.x.x.x` IP.
3. Client devices (phone, laptop) run the Tailscale app and join the same tailnet.
4. All traffic between devices is encrypted with WireGuard (peer-to-peer when possible, relayed otherwise).
5. The Web UI is accessible at `http://<tailscale-hostname>/` from anywhere.

### What's Accessible Remotely

| Service          | URL via Tailscale                                    | Notes                        |
| ---------------- | ---------------------------------------------------- | ---------------------------- |
| Web UI           | `http://soundmaker-master.tailnet-name.ts.net/`      | Requires login               |
| Pi-hole admin    | `http://soundmaker-master.tailnet-name.ts.net:8080/admin` | Pi-hole's own password  |
| SSH              | `ssh` via Tailscale (if `--ssh` flag used)           | No port forwarding needed    |
| Backend API      | `http://soundmaker-master.tailnet-name.ts.net/api/*` | Requires session cookie      |

### What Does NOT Work Remotely

- **Spotify Connect** — requires local network presence for device discovery
- **Bluetooth** — requires physical proximity

### Setup

Tailscale is installed by `install_master.sh`. After installation, authenticate once:

```bash
sudo tailscale up --ssh
```

Then install the Tailscale app on your phone/laptop and sign in with the same account.

---

## 21. Future Possibilities (Out of Scope Now)

These are not planned but the architecture supports them:

- **Grouped Slaves** — play different streams in different groups of rooms
- **Scheduled playback** — time-based rules (morning alarm, sleep timer)
- **Presence-based automation** — detect phones on network, auto-play
- **OTA updates** — Master pushes updates to Slaves
- **Home automation hooks** — trigger events based on audio state
- **Additional audio sources** — line-in, podcast feeds, TTS announcements
- **EQ/DSP per room** — Snapcast supports per-client audio processing
