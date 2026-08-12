# SoundMaker

A distributed home audio system built on Raspberry Pi. One **Master** receives all audio and distributes it in perfect sync to multiple **Slave** speakers throughout your home.

## What It Does

- Streams internet radio as the always-on default audio source
- Receives **Spotify Connect** and **Bluetooth** audio from phones and laptops
- Distributes synced audio to every room via [Snapcast](https://github.com/badaix/snapcast)
- Provides a mobile-first **Web UI** for room control, volume, and source management
- Runs **Pi-hole** for network-wide DNS ad blocking
- Includes **Jellyfin** media server for streaming video content to smart TVs
- Serves a public **guest landing page** (`/guest`) with a scan-to-join Wi-Fi QR code
- Acts as a **Tailscale exit node** — route your phone's traffic through home while traveling (Pi-hole ad blocking everywhere)
- Operates fully headless — no keyboard, mouse, or monitor

## Hardware

| Device | Board | Role |
|--------|-------|------|
| Master | Raspberry Pi 5 (8GB) | Receives audio, runs all services, distributes to Slaves |
| Slave (per room) | Raspberry Pi Zero 2 W | Plays audio via USB DAC to a powered speaker |

## Audio Source Priority

| Priority | Source | Trigger |
|----------|--------|---------|
| 1 (high) | Spotify Connect | Phone selects SoundMaker as Spotify speaker |
| 2 | Bluetooth A2DP | Paired phone connects and plays audio |
| 3 (low) | Internet Radio | Always-on default when nothing else is active |

Higher-priority sources automatically override lower ones. On disconnect, the system cascades back down to the next available source.

## Project Structure

```
SoundMaker/
├── master/
│   ├── backend/              # Python FastAPI backend
│   │   ├── main.py           # Entry point, FastAPI app + REST API
│   │   ├── auth.py           # Authentication, sessions, rate limiting
│   │   ├── pihole_api.py     # Pi-hole v6 REST API client
│   │   ├── state_manager.py  # JSON state persistence
│   │   └── requirements.txt  # Python dependencies
│   ├── frontend/             # React Web UI (Vite + React 19)
│   │   ├── src/              # Source files (components, styles, auth)
│   │   ├── dist/             # Built static files (committed to repo)
│   │   ├── package.json
│   │   └── vite.config.js
│   ├── pihole.toml           # Pi-hole v6 config template
│   └── install_master.sh     # Master installation script
├── slave/
│   └── install_slave.sh      # Slave installation script
├── docs/
│   ├── architecture.md       # Full system architecture & design
│   └── plan.md               # Implementation plan & progress
└── README.md
```

## Quick Start

### Prerequisites

- Raspberry Pi 5 (8GB) with Raspberry Pi OS Lite (64-bit)
- One or more Raspberry Pi Zero 2 W with Raspberry Pi OS Lite (32-bit)
- USB DAC + powered speaker per Slave
- All devices on the same local network (2.4GHz WiFi required for Pi Zero 2 W)

### Master Setup

```bash
ssh goorlavi@master.local
cd /opt
sudo git clone <repo-url> soundmaker
sudo chown -R goorlavi:goorlavi /opt/soundmaker
cd /opt/soundmaker/master
sudo PIHOLE_PW=yourpassword SOUNDMAKER_PW=yourpassword ./install_master.sh
```

The install script handles everything: system packages, Tailscale VPN, Pi-hole (unattended), Python virtual environment, backend dependencies, Web UI password hashing, and the `soundmaker-backend` systemd service.

If you omit `SOUNDMAKER_PW`, the script will prompt you to set a password interactively.

### Slave Setup

```bash
ssh goorlavi@<slave-hostname>.local
cd /opt
sudo git clone <repo-url> soundmaker
sudo chown -R goorlavi:goorlavi /opt/soundmaker
cd /opt/soundmaker/slave
sudo ./install_slave.sh
```

The Slave auto-connects to the Master. Name it from the Web UI.

### Frontend Development (on macOS)

The React frontend is built on your dev machine and committed as static files — no Node.js on the Pi.

```bash
cd master/frontend
npm install          # first time only
npm run dev          # local dev server at localhost:5173 (proxies /api to backend)
npm run build        # build to dist/ for deployment
```

### Updating the Master

**From the Web UI (recommended):** Open **System → Updates**, click "Check for updates", then "Apply update". When it finishes, restart the backend: `ssh` in and run `sudo systemctl restart soundmaker-backend.service`.

**From SSH:** `cd /opt/soundmaker && git pull`, then `sudo systemctl restart soundmaker-backend.service`. Run `sudo ./master/install_master.sh` only if dependencies or system services changed.

Updates run versioned migrations automatically when applied from the UI. See [docs/architecture.md §16](docs/architecture.md) for how updates and migrations work and how to add new migrations.

## Services

After installation, the Master exposes:

| Service | URL | Purpose |
|---------|-----|---------|
| Web UI | `http://master.local/` | Mobile-first dashboard (Pi-hole, Jellyfin, System → Updates) |
| Backend API | `http://master.local/api/health` | REST API |
| Pi-hole Admin | `http://master.local:8080/admin` | Ad-blocking management |
| Jellyfin | `http://master.local:8096` | Media server for video streaming (disabled by default) |
| Pi-hole DNS | port 53 | Point your router's DHCP DNS to Master's IP |  

### Using the Web UI as a phone app

Install the Web UI on your phone's home screen (iOS Safari → Share → **Add to Home Screen**). It opens full-screen with no browser chrome, so the app provides its own refresh: **pull down from the top of the page** (pull-to-refresh), or tap the **↻ button** in the header. A refresh also picks up the new frontend after an "Apply update".

## System Tab

The Web UI's **System** tab is a read-only-plus-controls view of the Master itself:

- **System Health** — live CPU, memory, temperature, storage, and network.
- **History (24h)** — a graph of CPU temperature (with the 70 °C warning line), CPU load, and memory over the last day, so you can spot a thermal trend before it crashes the Pi. Sampled once a minute in the background.
- **Logs** — recent logs for any core service (SoundMaker, Jellyfin, Pi-hole, Caddy, Spotify, Tailscale) right in the browser, colored by severity — no SSH needed.
- **Power** — **Restart backend** (reloads just the app) and **Reboot Pi** buttons, plus an optional **weekly reboot** on a day/time you choose. This removes the usual "SSH in to restart after an update" step.
- **Updates** — check for and apply updates (see below).

Power controls need passwordless sudo scoped to exactly two commands and journal read access; both are set up automatically by the installer (and migration `008` for existing devices). See `docs/architecture.md` → *System Tab controls*.

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/health` | No | Backend health check |
| POST | `/api/auth/login` | No | Log in with password, sets session cookie |
| POST | `/api/auth/logout` | No | Clear session cookie |
| GET | `/api/auth/check` | No | Check if current session is valid |
| GET | `/api/config` | Yes | Current system config |
| GET | `/api/pihole/status` | Yes | Pi-hole blocking state + stats |
| POST | `/api/pihole/enable` | Yes | Enable ad blocking |
| POST | `/api/pihole/disable?timer=N` | Yes | Disable ad blocking (optional timer in seconds) |
| GET | `/api/updates/status` | Yes | Current version and last update time |
| POST | `/api/updates/check` | Yes | Check if a newer version exists on remote |
| POST | `/api/updates/apply` | Yes | Start update (git pull, deps, migrations) |
| GET | `/api/updates/progress` | Yes | Update progress log and result |
| GET | `/api/jellyfin/status` | Yes | Jellyfin service status and URL |
| GET | `/api/guest` | Yes | Guest page config (admin) |
| PUT | `/api/guest` | Yes | Update guest page config |
| GET | `/api/guest/page` | No | Guest-visible page data (empty while disabled) |
| GET | `/api/tailscale/status` | Yes | Tailscale connection + exit-node state |
| POST | `/api/tailscale/exit-node` | Yes | Advertise / stop advertising as exit node |
| GET | `/api/system/info` | Yes | Master health snapshot (CPU, memory, temp, storage, network, OS) |
| GET | `/api/system/metrics-history` | Yes | Rolling 24h history of CPU temp, load, memory (for the graph) |
| GET | `/api/system/logs/services` | Yes | Services whose logs can be viewed |
| GET | `/api/system/logs?service=&lines=` | Yes | Recent journal entries for a whitelisted service |
| POST | `/api/system/restart-service` | Yes | Restart the SoundMaker backend (no SSH) |
| POST | `/api/system/reboot` | Yes | Reboot the whole Raspberry Pi |
| GET | `/api/system/auto-reboot` | Yes | Scheduled weekly reboot config |
| PUT | `/api/system/auto-reboot` | Yes | Set scheduled weekly reboot (day, time, on/off) |

## Remote Access (Tailscale VPN)

SoundMaker includes [Tailscale](https://tailscale.com/) for secure remote access. Tailscale creates an encrypted WireGuard tunnel — no port forwarding or DDNS required.

### Setup

1. Tailscale is installed automatically by `install_master.sh`.
2. After installation, authenticate once:

```bash
sudo tailscale up --ssh --operator=goorlavi
```

3. Open the printed URL in a browser (or run `tailscale status` if nothing is printed) and log in with your Tailscale account.
4. Install the Tailscale app on your phone (iOS/Android) and sign in with the same account.
5. Find your Web UI URL: on the Pi run `tailscale dns status` and note the suffix (e.g. `tail3ac861.ts.net`). The Web UI is at `http://master.<suffix>/` (e.g. `http://master.tail3ac861.ts.net/`). You can also use the Tailscale IP from `tailscale status` (e.g. `http://100.117.114.47/`).

The Web UI will prompt for the password you set during installation. Bookmark the URL on your phone for quick access.

### What works remotely

- Web UI dashboard (room control, volume, source management)
- Pi-hole toggle and stats
- Pi-hole admin (`http://master.<tailnet>.ts.net:8080/admin`)
- SSH (if `--ssh` flag was used)

### What does NOT work remotely

- Spotify Connect (requires local network for device discovery)
- Bluetooth (requires physical proximity)

### Exit node — route your phone's traffic through home

The Master can also act as a Tailscale **exit node**: while traveling, your phone sends *all* its internet traffic through your home connection. You get Pi-hole ad blocking everywhere, your home country's geo access, and safe browsing on hotel/airport Wi-Fi. (This is not a NordVPN-style anonymizer — traffic exits from your home IP, and speed is capped by your home upload bandwidth.)

1. Enable it in the Web UI: **System → Tailscale VPN → Enable exit node**.
2. Approve it once in the [Tailscale admin console](https://login.tailscale.com/admin/machines): Machines → your Master → Edit route settings → **Use as exit node**. The card shows "awaiting approval" until you do.
3. On your phone: Tailscale app → **Exit node** → select the Master. Pick "None" to turn it off when back home.

IP forwarding and CLI permissions are set up automatically by the installer (and migration `009` for existing devices). See `docs/architecture.md` → *Remote Access → Exit Node*.

## Guest Landing Page

A public welcome page at `http://master.local/guest` you can show visitors: a **Wi-Fi QR code** they scan with their camera to join your network, the password in tap-to-copy text, an optional welcome message, and a link to Jellyfin.

- Configure and turn it on from **Dashboard → Guest Page** (SSID, password, security type, message).
- The page needs **no login** — that's the point — but while it's turned **off** (the default) it reveals nothing.
- Works for any Wi-Fi network you type in (it shows whatever SSID/password you configure, typically your guest network).

## Jellyfin Media Server

SoundMaker includes Jellyfin, an open-source media server for streaming movies and TV shows to any device on your network.

> **Disabled by default.** Jellyfin is installed but not running out of the box — enable it with `sudo systemctl enable --now jellyfin` and disable it again with `sudo systemctl disable --now jellyfin`. The Dashboard's Media Server card shows its current status either way.

### Setup

1. **Enable Jellyfin**: `sudo systemctl enable --now jellyfin` (skip if already running)
2. **Access Jellyfin**: Navigate to `http://master.local:8096` in your browser
2. **First-time setup**: Complete the setup wizard to create an admin account and configure libraries
3. **Add media**: 
   - Connect a USB drive with your media files to the Raspberry Pi
   - Mount it (e.g., `sudo mount /dev/sda1 /media/movies`)
   - In Jellyfin, add a library pointing to your media location (e.g., `/media/movies`)
4. **Install client apps**: Download Jellyfin apps for your smart TV, phone, or tablet from [jellyfin.org](https://jellyfin.org/downloads/)

### Accessing from Smart TV

Most smart TV platforms have native Jellyfin apps:
- **Roku**: Install from Roku Channel Store
- **Fire TV**: Install from Amazon App Store
- **Apple TV**: Install from App Store
- **Android TV/Google TV**: Install from Play Store
- **Samsung/LG**: Use the web browser or check for native apps

Your TV and the Master Pi must be on the same local network. The TV app will auto-discover the Jellyfin server.

> **Use the apps, not a web browser.** When a device can play a file as-is ("direct play"), the Pi just sends the file and stays cool. When it can't, the Pi has to **transcode** (rewrite the video on the fly with `ffmpeg`), which pegs the CPU and overheats the Pi 5 — the most common cause of it crashing. The native Jellyfin apps on phones and streaming boxes (Apple TV, Nvidia Shield, Fire TV, Google TV) direct-play almost everything; web browsers and forced/burned-in subtitles are what trigger transcoding.

### Thermal Protection

To stop a runaway transcode from overheating and crashing the Pi, the installer caps Jellyfin's CPU usage to 2 of the 4 cores (a systemd drop-in at `/etc/systemd/system/jellyfin.service.d/10-cpu-limit.conf`). This is applied automatically on fresh installs and by migration `006_jellyfin_cpu_limit.sh` on existing ones. See `docs/architecture.md` → *Jellyfin → Thermal Protection* for tuning.

### Remote Access

Jellyfin is accessible remotely via Tailscale VPN at `http://master.<tailnet>:8096`. Note that streaming over VPN may be slow depending on your upload bandwidth.

## Network Setup

For Pi-hole to block ads network-wide, configure your router's DHCP server to hand out the Master's IP as the DNS server:

| Router DHCP setting | Value |
|---------------------|-------|
| Primary DNS | Master's IP (e.g. `192.168.0.7`) |
| Secondary DNS | `1.1.1.1` (Cloudflare fallback) |

Also reserve a static IP for the Master in your router's DHCP settings so the DNS address never changes.

## Network Requirements

- All devices on the same LAN / WiFi
- 2.4GHz WiFi available (Pi Zero 2 W only supports 2.4GHz)
- mDNS / Avahi for `.local` hostname resolution
- Static IP reservation for Master on the router
- Open TCP ports on Master: 80, 1704, 1705, 8080, 8096, 53

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system architecture, design decisions, audio pipeline diagrams, and implementation details.

## License

Private project.
