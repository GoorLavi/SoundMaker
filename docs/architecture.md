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
- Includes Jellyfin media server for video streaming (independent service)
- Operates fully headless — no keyboard, mouse, or monitor required

### What SoundMaker Does NOT Do

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
| Caddy                 | Caddy v2                 | HTTPS reverse proxy (ports 80/443 → backend :8081) |
| Snapcast Server       | `snapserver`             | Distributes synced audio to all Slaves          |
| Spotify Connect       | `raspotify`              | Receives Spotify audio from phones/laptops      |
| Bluetooth A2DP        | BlueZ + PulseAudio       | Receives Bluetooth audio from paired devices    |
| Internet Radio        | `mpv`                    | Plays default stream URL via PulseAudio         |
| Audio Mixer           | PulseAudio               | Merges all sources, outputs to Snapcast pipe    |
| Backend API           | Python + FastAPI          | REST API on :8081, behind Caddy                 |
| Web UI                | React (static files)     | Mobile-first SPA served by FastAPI              |
| Pi-hole               | Pi-hole                  | DNS-level ad blocking for the whole network     |
| Jellyfin              | Jellyfin                 | Media server for video streaming (:8096)        |

### Service Dependency Order

```
network-online
    │
    ├── caddy (HTTPS :443, HTTP :80 → backend :8081)
    ├── pulseaudio
    ├── snapserver
    ├── bluetoothd (BlueZ)
    ├── raspotify
    ├── jellyfin (:8096)
    └── pihole-FTL
            │
            ▼
    soundmaker-backend.service (:8081)
        │
        ├── starts/stops mpv (radio) internally
        ├── monitors raspotify events
        ├── monitors BlueZ D-Bus signals
        ├── runs alarm scheduler
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

#### Navigation (implemented)

- **Top-level tabs** — **Dashboard** (Alarm, Jellyfin, Pi-hole) and **System** (System Health + Updates). Mobile-first tab bar below the header.

#### Alarm / Morning Wake-up (implemented)

- Shown on the **Dashboard** tab.
- **Time picker** — set alarm time (HH:MM)
- **Enable/disable toggle** — turns alarm on/off
- **Spotify connection** — OAuth flow to connect Spotify account; shows connection status
- **Playlist selector** — choose which Spotify playlist to play at alarm time
- **Next alarm summary** — displays when the next alarm will trigger

#### Jellyfin Media Server (implemented)

- Shown on the **Dashboard** tab.
- **Status badge** — "running" (green), "stopped" (red), or "not installed" (gray)
- **Description** — brief explanation of Jellyfin's purpose
- **Open Jellyfin button** — opens Jellyfin web UI at `http://master.local:8096` in a new tab
- **Warning message** — if service is stopped, shows command to restart it
- **Polling** — refreshes status every 30 seconds
- **Read-only** — SoundMaker does not control Jellyfin; it only reports service status

#### Pi-hole (implemented)

- Shown on the **Dashboard** tab.
- **Status badge** — "active" (green) or "disabled" (red) based on blocking state
- **Stats row** — queries today, blocked count, blocked percentage
- **Toggle switch** — enables/disables blocking via `POST /api/pihole/enable` or `/disable`
- **Admin link** — opens Pi-hole admin UI at `http://<master>:8080/admin` in a new tab
- **Polling** — refreshes status every 10 seconds
- **Graceful degradation** — shows "unavailable" when Pi-hole or backend is unreachable

#### System tab (implemented)

- **System** tab is a read-only Master device health overview (no audio state, no slave info, no control actions).
- **System Health** card — card-based sections with polling every 20 seconds:
  - **CPU** — model, current frequency, load (1m / 5m)
  - **Memory** — total, used, free (MB)
  - **Temperature** — CPU temperature; visual warning when above safe threshold (70 °C)
  - **Storage** — total, used, free (GB)
  - **Network** — active interface (Ethernet / Wi-Fi), IP address, Wi-Fi SSID and signal (if applicable), internet connectivity status (OK / Offline)
  - **System** — OS version, uptime, hostname
  - **Application** — SoundMaker version (commit or tag), last update time
- **History (24h)** card — inline SVG line graphs (no chart library) of CPU temperature (with a dashed 70 °C threshold line), CPU load (1-minute average), and memory used, over the last 24 hours. Backed by a once-a-minute background sampler; helps catch a thermal or memory trend before it crashes the Pi.
- **Logs** card — recent systemd-journal entries for a whitelisted service (SoundMaker backend, Jellyfin, Pi-hole, Caddy, raspotify, Tailscale). Service dropdown, line-count selector, manual refresh and optional auto-refresh, entries colored by severity, newest kept in view. Read-only; no SSH needed.
- **Power** card — **Restart backend** and **Reboot Pi** buttons (each behind a confirm dialog), plus an optional **weekly reboot** schedule (day + time, on/off). Removes the "SSH in to restart after an update" step.
- **Updates** card — same as below; lives under the System tab.
- Designed to be extendable later (e.g. audio, slaves, system actions).

#### Updates (implemented, under System tab)

- **Current version** — git commit hash (short) and last update timestamp
- **Check for updates** — compares local repo with remote (GitHub); no system changes
- **Apply update** — runs only when an update is available; shows real-time log and final success/failure
- **No automatic polling** — all update actions are user-initiated

---

## 8. Communication Model

| Path                           | Protocol                 | Port  | Purpose                              |
| ------------------------------ | ------------------------ | ----- | ------------------------------------ |
| Master → Slaves (audio)       | Snapcast TCP stream      | 1704  | Synced PCM audio distribution        |
| Master ↔ Slaves (control)     | Snapcast JSON-RPC        | 1705  | Volume, mute, client status          |
| Browser → Master (UI)         | HTTPS via Caddy          | 443   | React SPA + FastAPI REST API         |
| Browser → Master (HTTP→HTTPS) | HTTP redirect            | 80    | Caddy redirects to HTTPS             |
| Caddy → Backend (internal)    | HTTP                     | 8081  | Reverse proxy to FastAPI             |
| Browser → Master (Jellyfin)   | HTTP                     | 8096  | Jellyfin web UI and media streaming  |
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

### `state/version.json`

Used by the self-update system. Not committed to Git.

```json
{
  "current": "a1b2c3d4e5f6",
  "last_updated_at": "2026-02-20T14:30:00Z"
}
```

### `state/applied_migrations.json`

Tracks which migrations have been run (one-time, in order). Not committed to Git.

```json
{
  "applied": ["001_initial.sh", "002_add_foo.sh"]
}
```

### `state/update.lock`

A lock file created during an update to prevent concurrent apply. Removed when the update finishes or fails.

### `state/sessions.json`

Web UI session tokens and expiry timestamps. Persisted so logins survive backend restarts. Not committed to Git.

```json
{
  "sessions": {
    "<token>": 1234567890.0
  }
}
```

### `state/alarm.json`

Used by the morning wake-up feature. Not committed to Git.

```json
{
  "enabled": true,
  "time": "07:00",
  "playlist_uri": "spotify:playlist:abc123..."
}
```

- **enabled** — whether the alarm is active
- **time** — local time in HH:MM (24-hour)
- **playlist_uri** — optional Spotify playlist URI; if unset, alarm still fires but playback uses user's default or last context

### `state/spotify.json`

Stores Spotify Web API OAuth refresh token so the backend can start playback at alarm time. Not committed to Git.

```json
{
  "refresh_token": "AQC..."
}
```

### `state/power.json`

Scheduled weekly-reboot config. Not committed to Git.

```json
{
  "auto_reboot": {
    "enabled": false,
    "day": "sun",
    "time": "04:30"
  }
}
```

- **enabled** — whether the weekly reboot is active
- **day** — three-letter weekday (`mon`…`sun`)
- **time** — local time HH:MM (24-hour)

### `state/metrics_history.json`

Rolling 24-hour history of Master vitals for the System-tab graph. Not committed to Git. Kept in memory and written to disk only every ~5 minutes (and on shutdown) to limit SD-card wear.

```json
{
  "points": [
    { "t": 1784663514, "temp_c": 52.1, "load": 0.34, "mem_pct": 41.2 }
  ]
}
```

- **t** — Unix timestamp (seconds)
- **temp_c** — CPU temperature (°C), **load** — 1-minute load average, **mem_pct** — memory used (%)
- At most `24 × 60 = 1440` points (one per minute for 24h)

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
│   │   ├── auth.py              # Authentication, persistent sessions (state/sessions.json), rate limiting
│   │   ├── alarm_manager.py     # Morning wake-up: alarm config, scheduler, Spotify playback at alarm time
│   │   ├── spotify_auth.py      # Spotify Web API OAuth (auth URL, callback, token refresh) and playback API
│   │   ├── audio_manager.py     # Source switching, priority logic
│   │   ├── radio_player.py      # mpv process management
│   │   ├── spotify_monitor.py   # raspotify event monitoring
│   │   ├── bluetooth_manager.py # BlueZ D-Bus control
│   │   ├── snapcast_api.py      # Snapcast JSON-RPC client
│   │   ├── pihole_api.py        # Pi-hole v6 REST API client
│   │   ├── jellyfin_manager.py  # Jellyfin service status checker
│   │   ├── state_manager.py     # JSON state persistence
│   │   ├── system_info.py       # Master system info (CPU, memory, temp, storage, network, OS)
│   │   ├── metrics_history.py   # 24h vitals sampler (temp/load/memory) for the History graph
│   │   ├── system_logs.py       # Read journald logs for whitelisted services (log viewer)
│   │   ├── power_manager.py     # Restart backend / reboot Pi + weekly-reboot scheduler
│   │   ├── update_manager.py    # Self-update: version check, apply, migrations
│   │   └── requirements.txt     # Python dependencies
│   │
│   ├── frontend/                # React Web UI (Vite + React 19)
│   │   ├── src/
│   │   │   ├── main.jsx         # React entry point
│   │   │   ├── App.jsx          # Dashboard shell + auth state
│   │   │   ├── api.js           # Shared fetch wrapper (401 handling)
│   │   │   └── components/
│   │   │       ├── LoginScreen.jsx  # Login form
│   │   │       ├── AlarmCard.jsx    # Dashboard: morning wake-up (time, toggle, playlist, Spotify connect)
│   │   │       ├── JellyfinCard.jsx # Dashboard: Jellyfin media server status and link
│   │   │       ├── PiholeCard.jsx   # Dashboard: Pi-hole status, toggle, stats
│   │   │       ├── SystemHealthCard.jsx  # System tab: health dashboard
│   │   │       ├── MetricsHistoryCard.jsx # System tab: 24h vitals graph (SVG)
│   │   │       ├── LogsCard.jsx     # System tab: journal log viewer
│   │   │       ├── PowerCard.jsx    # System tab: restart / reboot / weekly reboot
│   │   │       └── UpdatesCard.jsx  # System tab: Updates
│   │   ├── index.html
│   │   ├── vite.config.js
│   │   ├── package.json
│   │   └── dist/                # Built static files (committed to repo)
│   │
│   ├── migrations/              # Versioned one-time scripts (run during Apply update)
│   │   ├── 001_initial.sh
│   │   ├── 002_caddy_spotify_alarm.sh  # Caddy HTTPS, alarm (prints re-run instructions)
│   │   ├── 003_raspotify.sh            # Install and enable raspotify (Spotify Connect device)
│   │   ├── 004_raspotify_config.sh     # Fix raspotify config (HDMI output)
│   │   ├── 005_jellyfin.sh             # Install Jellyfin media server
│   │   ├── 006_jellyfin_cpu_limit.sh   # Cap Jellyfin CPU (Pi 5 thermal protection)
│   │   ├── 007_disable_jellyfin.sh     # Disable Jellyfin by default
│   │   └── 008_power_controls_log_access.sh  # sudoers + journal group for power/logs
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
- `state/*.json` — runtime state files (slaves, config, bluetooth, version, applied_migrations, sessions, alarm, spotify)
- `state/update.lock` — created during update, removed when done
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

Subsequent updates (either approach):

- **From the Web UI:** Open **System** tab → **Updates**, click "Check for updates", then "Apply update". Restart the backend when done (`sudo systemctl restart soundmaker-backend`). See §16.
- **From SSH:** `git pull`, then optionally `sudo ./master/install_master.sh` (only if dependencies or services changed), then `sudo systemctl restart soundmaker-backend`.

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

## 16. Updates and Migrations

The Master supports **manual self-update** from the Web UI. There is no automatic polling or background update check; the user explicitly checks for updates and applies them when desired.

### How Updates Work

1. **Check for updates** — Backend runs `git fetch origin` and compares local `HEAD` with the remote default branch (`origin/HEAD`, or `origin/main` / `origin/master`). No files are modified.
2. **Apply update** — When the user clicks "Apply update":
   - A lock is taken (`state/update.lock`) so only one update runs at a time.
   - `git pull --ff-only origin` updates the repo.
   - Python dependencies are installed with `pip install -r requirements.txt` (in the backend venv).
   - Pending **migrations** are run in order (see below).
   - The new version (commit hash) and timestamp are written to `state/version.json`.
   - Lock is released. The UI shows a log and final success or failure.
3. **Restart** — After a successful update, the user must restart the SoundMaker backend to run the new code (e.g. `sudo systemctl restart soundmaker-backend`). The UI reminds them; automatic restart is not performed.

### Web UI (System tab: Updates)

| Control              | Behavior                                                                 |
| -------------------- | ------------------------------------------------------------------------ |
| Current version      | Short git commit hash from `version.json` or live `git rev-parse HEAD`   |
| Last update         | Timestamp from `version.json`, or "—" if never updated via UI            |
| Check for updates   | POST to API; shows "up to date" or "update available"                     |
| Apply update        | Enabled only when an update is available; runs apply and streams log     |
| Progress / result   | Scrollable log during apply; green success or red failure message         |

### System info API (read-only)

| Method | Endpoint             | Purpose                                                       |
| ------ | -------------------- | ------------------------------------------------------------- |
| GET    | `/api/system/info`   | Master system info: CPU, memory, temperature, storage, network, OS, application (for System tab dashboard) |
| GET    | `/api/system/metrics-history` | Rolling 24h history of CPU temperature, load, and memory (History graph) |
| GET    | `/api/system/logs/services`   | List of services whose logs can be viewed                    |
| GET    | `/api/system/logs`   | Recent journal entries for a whitelisted `service` (query: `service`, `lines`) |
| POST   | `/api/system/restart-service` | Restart the SoundMaker backend (via `systemd-run`)          |
| POST   | `/api/system/reboot` | Reboot the whole Pi (via `systemd-run`)                       |
| GET    | `/api/system/auto-reboot`     | Current scheduled weekly-reboot config                       |
| PUT    | `/api/system/auto-reboot`     | Set scheduled weekly reboot (enabled, day, time)             |

### Updates API Endpoints (all protected by auth)

| Method | Endpoint                 | Purpose                                              |
| ------ | ------------------------ | ---------------------------------------------------- |
| GET    | `/api/updates/status`     | Current version and last_updated_at                  |
| POST   | `/api/updates/check`     | Compare with remote; returns update_available, etc. |
| POST   | `/api/updates/apply`     | Start update (background); 409 if already running    |
| GET    | `/api/updates/progress`  | Status, log lines, and result message                |

### Versioning

- **Version** is the short git commit hash (12 characters). It is stored in `state/version.json` after a successful apply.
- If `version.json` has no `current`, the UI shows the live commit from `git rev-parse HEAD`.

### Migrations

Migrations are **ordered, one-time scripts** that run during "Apply update". They handle structural or config changes that must run once per device.

- **Location:** `master/migrations/`. Only `*.sh` files are run, sorted by filename (e.g. `001_initial.sh`, `002_add_feature.sh`).
- **Applied list:** `state/applied_migrations.json` holds the list of migration filenames that have already run. Each migration runs only once.
- **Execution:** Each script is run with `bash` from the repo root. Environment variables set for the script:
  - `SOUNDMAKER_STATE_DIR` — path to `state/` (e.g. `/opt/soundmaker/state`)
  - `SOUNDMAKER_REPO` — path to repo root (e.g. `/opt/soundmaker`)
- **Success/failure:** If a migration exits non-zero or times out, the update stops, the lock is released, and the UI shows the error. No partial state is left behind; already-applied migrations remain recorded.
- **Migrations that install system packages** (e.g. `003_raspotify.sh`) run as the backend user and use `sudo` for apt/systemctl. The backend user should have **passwordless sudo** for those commands so the migration can complete when "Apply update" is run from the Web UI.

#### Adding a new migration

1. Create a new file in `master/migrations/` with a numeric prefix so it sorts after existing ones (e.g. `003_my_change.sh`).
2. Make it executable and idempotent where possible. Use `SOUNDMAKER_STATE_DIR` and `SOUNDMAKER_REPO` if the script needs paths.
3. Commit and push. On the next "Apply update" on the Pi, the migration will run once and be recorded in `applied_migrations.json`.

Example:

```bash
#!/usr/bin/env bash
# 003_add_new_config.sh
set -euo pipefail
CONFIG="$SOUNDMAKER_STATE_DIR/config.json"
# ... add or modify config keys; be idempotent
echo "Migration 003 done."
```

### Managing updates: Web UI vs SSH

| Method        | When to use                                                                 |
| ------------- | --------------------------------------------------------------------------- |
| **Web UI**    | Normal flow: Check for updates → Apply update → restart backend when done.  |
| **SSH**       | First-time deploy, or if the UI is unreachable: `git pull`, then optionally `sudo ./master/install_master.sh`, then `sudo systemctl restart soundmaker-backend`. |

Using the Web UI applies the same steps (git pull, pip install, migrations) without SSH. After applying from the UI, restart the backend from SSH or a future "Restart service" control.

### Safety and constraints

- No background polling or cron for updates.
- Only one update at a time (file lock).
- On failure, the system stays usable; the log is shown in the UI.
- Update is considered successful only when all steps (pull, deps, migrations) complete; then the new version is recorded.

---

## 17. Failure Handling

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

## 18. Network Requirements

| Requirement                    | Details                                          |
| ------------------------------ | ------------------------------------------------ |
| Same local network             | Master and all Slaves on the same WiFi/LAN       |
| 2.4GHz WiFi available          | Pi Zero 2 W only supports 2.4GHz                 |
| mDNS / Avahi                   | For `soundmaker-master.local` hostname resolution |
| Open TCP ports on Master       | 443 (HTTPS via Caddy), 80 (HTTP→HTTPS redirect), 1704 (Snapcast audio), 1705 (Snapcast control), 8080 (Pi-hole admin), 53 (Pi-hole DNS) |
| Router port forwarding         | Ports 80 and 443 forwarded to the Pi for HTTPS (Let's Encrypt) and Spotify OAuth |
| Stable internet on Master      | For radio streaming, Spotify, Pi-hole updates     |

---

## 19. Security

| Aspect                    | Approach                                                    |
| ------------------------- | ----------------------------------------------------------- |
| Web UI authentication     | Password-based login with bcrypt-hashed password, HTTP-only session cookies (long-lived; persisted to state so logins survive restarts) |
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

## 20. Authentication

### How It Works

The SoundMaker Web UI and all API endpoints (except `/api/health`) require authentication. The backend uses a single shared password, hashed with bcrypt and stored in the `.env` file.

### Login Flow

1. User opens the Web UI and sees a login screen.
2. User enters the password. Frontend sends `POST /api/auth/login` with the password.
3. Backend verifies against `SOUNDMAKER_PASSWORD_HASH` (bcrypt).
4. On success, backend creates a session token and sets an HTTP-only `session` cookie with a long TTL (10 years), so the user stays logged in until they log out.
5. Subsequent API requests include the cookie. The `require_auth` dependency validates it.
6. On logout, `POST /api/auth/logout` revokes the session and clears the cookie.

### Session Storage

Sessions are stored in memory and persisted to `state/sessions.json`. On service restart, sessions are loaded from disk so users remain logged in. Expired sessions are pruned on load and when validating or creating sessions.

### Rate Limiting

The login endpoint limits to 5 attempts per minute per IP address. Excess attempts receive HTTP 429.

### Password Setup

The password is set during `install_master.sh` (via `SOUNDMAKER_PW` env var or interactive prompt). The script hashes it with bcrypt (12 rounds) and writes the hash to `/opt/soundmaker/.env`.

---

## 21. Remote Access (Tailscale VPN)

### Why Tailscale

Tailscale provides a zero-config WireGuard mesh VPN. It requires no port forwarding, no static IP, and no DDNS. It installs as a single package and runs as a systemd service.

### How It Works

1. `tailscaled` runs on the Master as a systemd service.
2. The Master joins a private Tailscale network (tailnet) and receives a stable `100.x.x.x` IP.
3. Client devices (phone, laptop) run the Tailscale app and join the same tailnet.
4. All traffic between devices is encrypted with WireGuard (peer-to-peer when possible, relayed otherwise).
5. The Web UI is accessible from anywhere via MagicDNS at `http://<hostname>.<tailnet>.ts.net/` (e.g. `http://master.tail3ac861.ts.net/`).

### Finding Your Tailscale URL

The Pi's hostname is `master` by default. Your tailnet suffix is shown by:

```bash
tailscale dns status
```

Look for `suffix = XXXXX.ts.net`. The Web UI URL is then `http://master.<suffix>/` (e.g. `http://master.tail3ac861.ts.net/`). You can also use the Tailscale IP directly: `http://100.x.x.x/`.

**Note:** Typing `http://master/` in a browser may be treated as a search query. Use the full `.ts.net` URL or the IP to avoid that.

### What's Accessible Remotely

| Service          | URL via Tailscale                                    | Notes                        |
| ---------------- | ---------------------------------------------------- | ---------------------------- |
| Web UI           | `http://master.<tailnet>.ts.net/`                    | Requires login               |
| Pi-hole admin    | `http://master.<tailnet>.ts.net:8080/admin`         | Pi-hole's own password      |
| SSH              | `ssh` via Tailscale (if `--ssh` flag used)          | No port forwarding needed   |
| Backend API      | `http://master.<tailnet>.ts.net/api/*`               | Requires session cookie     |

### What Does NOT Work Remotely

- **Spotify Connect** — requires local network presence for device discovery
- **Bluetooth** — requires physical proximity

### Setup

Tailscale is installed by `install_master.sh`. After installation, authenticate once:

```bash
sudo tailscale up --ssh
```

Open the URL Tailscale prints (or run `tailscale status` if nothing is printed) and log in with your Tailscale account. Then install the Tailscale app on your phone/laptop and sign in with the same account. Use `tailscale dns status` on the Pi to see your full hostname (e.g. `master.tail3ac861.ts.net`) and bookmark `http://master.<your-tailnet>.ts.net/` for quick access.

---

## 22. Morning Wake-up (Alarm)

The Master can act as a **morning alarm**: at a user-configured time it starts playing a Spotify playlist over **HDMI** (e.g. to a JBL soundbar 5.1). This feature does not depend on PulseAudio or Snapcast; it is designed so that future multi-room (Phases 3–8) remains compatible.

### Flow

1. User sets **alarm time** and optional **playlist URI** in the Web UI and enables the alarm.
2. User **connects Spotify** once via OAuth (button in UI → Spotify login → callback stores refresh token in `state/spotify.json`).
3. **Raspotify** runs on the Master so the Pi appears as a Spotify Connect device (e.g. "SoundMaker"). Default audio output is **HDMI** so playback goes to the connected soundbar (and can wake the soundbar/ARC when playback starts).
4. A **scheduler** in the backend checks every minute. When current local time matches the alarm time and the alarm is enabled, the backend uses the **Spotify Web API** (refresh token → access token) to: transfer playback to the Pi's device, then start the configured playlist (or user's last context if no playlist is set).
5. Music plays on the Pi's HDMI output → soundbar.

### State and API

- **state/alarm.json** — `enabled`, `time` (HH:MM), `playlist_uri` (optional).
- **state/spotify.json** — `refresh_token` (from OAuth callback).
- **API:** `GET /api/alarm`, `PUT /api/alarm`; `GET /api/spotify/auth-url`, `GET /api/spotify/callback`, `GET /api/spotify/status`.

### Configuration

- **Env:** `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` (from Spotify Developer Dashboard). Redirect URI must be set in the dashboard (e.g. `http://master.local/api/spotify/callback` and, for dev, `http://localhost:8000/api/spotify/callback`).
- **Raspotify** is installed by `install_master.sh`. Default audio output should be HDMI so that the JBL soundbar receives the stream; if the soundbar is connected via ARC, starting playback typically wakes it.

### Future compatibility

When Phases 3–8 (PulseAudio, Snapcast, rooms, radio, source manager) are implemented, the alarm can remain **HDMI-only** (no need to route alarm audio through Snapcast), or the alarm-fire logic can be extended to also route to Snapcast if desired.

---

## 23. Jellyfin Media Server

SoundMaker includes **Jellyfin**, an open-source media server for streaming video content to smart TVs, phones, tablets, and web browsers.

### Architecture

Jellyfin runs as a **completely independent service** (`jellyfin.service`) on the Raspberry Pi 5 Master. It has no integration with SoundMaker's audio pipeline, state management, or control logic. The only connection is a **status widget** in the SoundMaker Dashboard that shows whether Jellyfin is running and provides a quick link to open Jellyfin's web interface.

**Disabled by default** — Jellyfin is installed but not started or enabled on boot, since media streaming is optional and competes with the Pi 5's limited CPU/thermal headroom. Enable it with `sudo systemctl enable --now jellyfin`; disable again with `sudo systemctl disable --now jellyfin`.

### Service Details

| Aspect             | Detail                                                   |
| ------------------ | -------------------------------------------------------- |
| Service            | `jellyfin.service` (systemd)                             |
| Default state      | Installed, disabled, stopped                             |
| Web UI             | `http://master.local:8096`                               |
| Installation       | Official Jellyfin Debian repository                      |
| Configuration      | Managed entirely through Jellyfin's own web interface    |
| Media libraries    | User configures in Jellyfin (e.g., USB drive with videos)|
| Database           | SQLite, managed by Jellyfin                              |
| Transcoding        | Handled by Jellyfin (CPU-intensive on Pi 5)              |
| CPU limit          | Capped to 2 of 4 cores via systemd drop-in (see below)  |

### Thermal Protection (CPU Limit)

Jellyfin transcodes video with `ffmpeg`, which is very CPU-intensive. On a Raspberry Pi 5 a transcode runs the CPU to ~84 °C (the board throttles to protect itself), and **stacked transcodes can peg all 4 cores and drive the SoC to its ~110 °C emergency-shutdown point — cutting power and causing an unclean reboot** (the next boot shows a filesystem journal recovery).

To prevent this, the install ships a systemd drop-in at `/etc/systemd/system/jellyfin.service.d/10-cpu-limit.conf`:

```ini
[Service]
CPUQuota=200%   # at most 2 of the 4 cores — blocks the multi-transcode runaway
CPUWeight=50    # yields to Pi-hole DNS and the SoundMaker UI under load
```

A single transcode still plays fine (it uses one core, under the cap). To keep the Pi cooler even for a single stream, lower `CPUQuota` below `100%` — at the cost of possible buffering during heavy scenes.

- **Fresh installs:** applied by `install_master.sh` (`install_jellyfin`).
- **Existing deployments:** applied by migration `006_jellyfin_cpu_limit.sh`.
- **Disabling by default:** fresh installs via `install_master.sh`; existing deployments via migration `007_disable_jellyfin.sh`.
- **The real fix is on the client side:** if viewers use the **Jellyfin app** on a phone or streaming box (Apple TV, Nvidia Shield, Fire TV, Google TV) instead of a web browser, the media **direct-plays** and the Pi never transcodes. Browsers and forced/burned-in subtitles are the main triggers for transcoding.

### SoundMaker Integration (Minimal)

SoundMaker's backend provides a **read-only status check**:

| Component               | Behavior                                                |
| ----------------------- | ------------------------------------------------------- |
| `jellyfin_manager.py`   | Runs `systemctl is-active jellyfin.service` to check status |
| `GET /api/jellyfin/status` | Returns `{"installed": bool, "running": bool, "url": str}` |
| `JellyfinCard.jsx`      | Dashboard widget: status badge, description, "Open Jellyfin" link |

SoundMaker **does not**:
- Control Jellyfin's service state (start/stop)
- Interact with Jellyfin's API
- Manage media libraries or user accounts
- Configure transcoding or playback settings

### Client Access

Users access Jellyfin **directly**:
- **Web browser**: `http://master.local:8096`
- **Smart TV apps**: Install Jellyfin app from Roku/Fire TV/Apple TV/Android TV app stores
- **Mobile apps**: Install Jellyfin app from iOS/Android app stores
- **Remote (via Tailscale VPN)**: `http://master.<tailnet>:8096`

### Media Storage

Users mount a USB drive (e.g., `/media/tv-shows/`) and point Jellyfin's library configuration to that directory. Jellyfin indexes the media, fetches metadata (posters, descriptions, episode info), and streams to clients.

### Transcoding Considerations

The Raspberry Pi 5 (8GB) can handle Jellyfin but transcoding is **CPU-intensive**. For best performance:
- Use video formats natively supported by client devices (H.264/H.265 in MP4/MKV containers)
- Enable **direct play** whenever possible (no transcoding)
- Avoid 4K transcoding (Pi 5 will struggle)

---

## 24. Future Possibilities (Out of Scope Now)

These are not planned but the architecture supports them:

- **Grouped Slaves** — play different streams in different groups of rooms
- **Sleep timer** — stop playback after a set duration
- **Presence-based automation** — detect phones on network, auto-play
- **OTA updates to Slaves** — Master pushes updates to Slaves (Master self-update via Web UI is implemented; see §16)
- **Home automation hooks** — trigger events based on audio state
- **Additional audio sources** — line-in, podcast feeds, TTS announcements
- **EQ/DSP per room** — Snapcast supports per-client audio processing

---

## 25. System Tab controls (power, logs, vitals history)

Three conveniences that make the headless Master manageable from the Web UI, without SSH.

### Vitals history (24h graph)

`metrics_history.py` runs a background task that samples CPU temperature, 1-minute load average, and memory-used percentage **once a minute**, reusing the read-only helpers in `system_info.py`. It keeps up to 1440 points (24h) in memory and returns them via `GET /api/system/metrics-history`. The `MetricsHistoryCard` draws them as inline SVG line charts — no chart library, keeping the frontend's dependency list at just React. The temperature chart draws a dashed line at the 70 °C warning threshold so a thermal creep is obvious.

To avoid wearing the SD card, history is persisted to `state/metrics_history.json` only every ~5 samples and once on shutdown — not on every tick.

### Log viewer

`system_logs.py` exposes recent journal entries for a **fixed whitelist** of services (SoundMaker backend, Jellyfin, Pi-hole, Caddy, raspotify, Tailscale). The UI passes a short key (e.g. `backend`); the key selects a known unit name and is **never** interpolated into a shell command, so it can't be used for injection. Logs are read as journald JSON (`journalctl -o json`), so each entry carries a real severity (`PRIORITY`) and a clean message; the UI colors warnings and errors.

The backend reads the journal as a member of the `systemd-journal` group (granted by the installer) — no sudo.

### Power controls

`power_manager.py` provides:

- **Restart backend** — `POST /api/system/restart-service`
- **Reboot Pi** — `POST /api/system/reboot`
- **Weekly reboot** — `GET`/`PUT /api/system/auto-reboot`, config in `state/power.json`, fired by a minute-resolution scheduler (same pattern as the alarm).

Both restart and reboot run via `sudo systemd-run --on-active=2 …`. Using `systemd-run` schedules the action as a **transient systemd timer** that runs *outside* the backend's own service group — so restarting the backend does not kill the command mid-flight, and the HTTP request returns before the action happens (a plain detached child would be killed when the service's control group is torn down).

### Permissions (installed in code)

Set up by `install_master.sh` → `install_power_permissions()` on fresh installs and migration `008_power_controls_log_access.sh` on existing ones:

| Grant | Purpose | How |
| ----- | ------- | --- |
| `systemd-journal` group membership | Log viewer reads the journal | `usermod -aG systemd-journal <user>` |
| Scoped passwordless sudo | Restart / reboot from the UI | `/etc/sudoers.d/soundmaker`, validated with `visudo -cf` |

The sudoers file grants **only** the two exact `systemd-run` invocations — nothing else — so the backend cannot run arbitrary commands as root:

```
<user> ALL=(root) NOPASSWD: /usr/bin/systemd-run --on-active=2 systemctl restart soundmaker-backend.service, /usr/bin/systemd-run --on-active=2 systemctl reboot
```

Journal group membership takes effect the next time the backend service starts; the installer restarts it, and after an "Apply update" the user restarts the backend anyway (now possible from the **Power** card itself).
