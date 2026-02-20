# SoundMaker

A distributed home audio system built on Raspberry Pi. One **Master** receives all audio and distributes it in perfect sync to multiple **Slave** speakers throughout your home.

## What It Does

- Streams internet radio as the always-on default audio source
- Receives **Spotify Connect** and **Bluetooth** audio from phones and laptops
- Distributes synced audio to every room via [Snapcast](https://github.com/badaix/snapcast)
- Provides a mobile-first **Web UI** for room control, volume, and source management
- Runs **Pi-hole** for network-wide DNS ad blocking
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

### Updating the Pi

```bash
cd /opt/soundmaker
git pull
sudo systemctl restart soundmaker-backend.service   # pick up new code
sudo ./master/install_master.sh                     # only if dependencies/services changed
```

## Services

After installation, the Master exposes:

| Service | URL | Purpose |
|---------|-----|---------|
| Web UI | `http://master.local/` | Mobile-first dashboard (dark theme) |
| Backend API | `http://master.local/api/health` | REST API |
| Pi-hole Admin | `http://master.local:8080/admin` | Ad-blocking management |
| Pi-hole DNS | port 53 | Point your router's DHCP DNS to Master's IP |

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

## Remote Access (Tailscale VPN)

SoundMaker includes [Tailscale](https://tailscale.com/) for secure remote access. Tailscale creates an encrypted WireGuard tunnel — no port forwarding or DDNS required.

### Setup

1. Tailscale is installed automatically by `install_master.sh`.
2. After installation, authenticate once:

```bash
sudo tailscale up --ssh
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
- Open TCP ports on Master: 80, 1704, 1705, 8080, 53

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system architecture, design decisions, audio pipeline diagrams, and implementation details.

## License

Private project.
