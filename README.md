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
│   │   ├── pihole_api.py     # Pi-hole v6 REST API client
│   │   ├── state_manager.py  # JSON state persistence
│   │   └── requirements.txt  # Python dependencies
│   ├── pihole.toml           # Pi-hole v6 config template
│   └── install_master.sh     # Master installation script
├── slave/
│   └── install_slave.sh      # Slave installation script
├── docs/
│   └── architecture.md       # Full system architecture & design
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
ssh goorlavi@soundmaker-master.local
cd /opt
sudo git clone <repo-url> soundmaker
sudo chown -R goorlavi:goorlavi /opt/soundmaker
cd /opt/soundmaker/master
sudo PIHOLE_PW=yourpassword ./install_master.sh
```

The install script handles everything: system packages, Pi-hole (unattended), Python virtual environment, backend dependencies, and the `soundmaker-backend` systemd service.

### Slave Setup

```bash
ssh goorlavi@soundmaker-slave.local
cd /opt
sudo git clone <repo-url> soundmaker
sudo chown -R goorlavi:goorlavi /opt/soundmaker
cd /opt/soundmaker/slave
sudo ./install_slave.sh
```

The Slave auto-connects to the Master. Name it from the Web UI.

### Updating

```bash
cd /opt/soundmaker
git pull
sudo ./master/install_master.sh   # only if dependencies/services changed
```

## Services

After installation, the Master exposes:

| Service | URL | Purpose |
|---------|-----|---------|
| Web UI | `http://soundmaker-master.local/` | Mobile-first dashboard |
| Backend API | `http://soundmaker-master.local/api/health` | REST API |
| Pi-hole Admin | `http://soundmaker-master.local:8080/admin` | Ad-blocking management |
| Pi-hole DNS | port 53 | Point your router/devices here for ad blocking |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Backend health check |
| GET | `/api/config` | Current system config |
| GET | `/api/pihole/status` | Pi-hole blocking state + stats |
| POST | `/api/pihole/enable` | Enable ad blocking |
| POST | `/api/pihole/disable?timer=N` | Disable ad blocking (optional timer in seconds) |

## Network Requirements

- All devices on the same LAN / WiFi
- 2.4GHz WiFi available (Pi Zero 2 W only supports 2.4GHz)
- mDNS / Avahi for `.local` hostname resolution
- Open TCP ports on Master: 80, 1704, 1705, 8080, 53

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system architecture, design decisions, audio pipeline diagrams, and implementation details.

## License

Private project.
