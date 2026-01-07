# SoundMaker – Headless Internet Radio with AirPlay

SoundMaker is a headless Raspberry Pi audio appliance. It auto-starts on boot, streams a configured internet radio URL via `mpv`, and switches to AirPlay when an iPhone connects, then resumes streaming on disconnect. It runs as systemd services, uses PulseAudio for shared output, and drives LEDs for state indication.

## Hardware
- Raspberry Pi Zero 2 W (tested)
- HDMI audio (default); USB/I2S DAC can be added later
- Optional LEDs: GPIO17 (stream), GPIO27 (AirPlay)
- Stable 5V/2A+ supply; 64GB micro-SD

## Software Features
- Internet radio streaming via `mpv`
- AirPlay input via `shairport-sync` hooks (connect/disconnect + play/stop)
- Automatic source switching: Stream → AirPlay on connect; resume Stream on disconnect
- PulseAudio backend shared between mpv and shairport-sync
- One-time Wi-Fi provisioning (NetworkManager, SSID `TopTier`, pass `123secure@`, flag at `/etc/soundmaker/wifi_provisioned`)
- Systemd services: `soundmaker.service`, `soundmaker-leds.service`, `shairport-sync.service`
- LED status via `/tmp/soundmaker_state` (written by player.py)
- Log rotation via Python logging (see `logger_setup.py`)

## Architecture
- `player.py`: entrypoint, logging, signal handling, main loop, writes state file
- `audio_controller.py`: state machine (STREAMING, AIRPLAY, IDLE, TRANSITIONING); stop/start logic
- `stream_player.py`: wraps `mpv` (PulseAudio device), restart logic
- `airplay_manager.py`: IPC FIFO at `/tmp/soundmaker_airplay_events`; reads hook events; checks shairport-sync
- `airplay_hook.sh`: invoked by shairport hooks; writes `connect`/`disconnect` to FIFO with retries
- `led_controller.py`: reads `/tmp/soundmaker_state` and drives GPIO LEDs
- `install.sh`: full install/upgrade, Wi-Fi provisioning, config generation, systemd units, backups
- Config/state files:
  - `/etc/shairport-sync.conf` (generated)
  - `/etc/systemd/system/shairport-sync.service.d/override.conf`
  - `/opt/soundmaker/` app files
  - `/tmp/soundmaker_airplay_events` (FIFO), `/tmp/soundmaker_state`

## Installation (automated)
```bash
scp *.py *.sh goorlavi@PI_IP:/home/goorlavi/
ssh goorlavi@PI_IP
chmod +x install.sh
sudo ./install.sh
```
What the installer does:
- Installs mpv, pulseaudio, shairport-sync (if missing)
- One-time Wi-Fi provisioning via nmcli (TopTier/123secure@) unless `/etc/soundmaker/wifi_provisioned` exists
- Backs up any previous install to `/opt/soundmaker_backup`
- Copies app to `/opt/soundmaker`
- Writes clean `/etc/shairport-sync.conf` (PA backend; hooks in sessioncontrol; wait_for_completion=yes)
- Creates drop-in `/etc/systemd/system/shairport-sync.service.d/override.conf` with minimal ExecStartPre (mkdir/chown pulse dir) and XDG_RUNTIME_DIR
- Creates/updates `soundmaker.service` and `soundmaker-leds.service`, enables & starts them

## Operation & Verification
- Check services:
  - `sudo systemctl status soundmaker.service`
  - `sudo systemctl status shairport-sync`
  - `sudo systemctl status soundmaker-leds.service`
- Logs:
  - Main: `sudo journalctl -u soundmaker.service -f`
  - Hooks: `sudo journalctl -t soundmaker -f`
  - Shairport: `sudo journalctl -u shairport-sync -f`
- AirPlay: connect iPhone to “SoundMaker”; stream stops on connect, resumes on disconnect
- FIFO perms: `/tmp/soundmaker_airplay_events` should be `prw-rw-rw- root root`

## Technologies
- Python 3 (subprocess, logging)
- mpv (audio backend via PulseAudio)
- shairport-sync (AirPlay) with hooks
- PulseAudio (per-user, XDG_RUNTIME_DIR=/run/user/1000)
- systemd services and drop-ins
- NetworkManager (`nmcli`) for Wi-Fi provisioning
- RPi.GPIO for LEDs

## Key Files
- `player.py`, `audio_controller.py`, `stream_player.py`, `airplay_manager.py`, `airplay_hook.sh`, `led_controller.py`
- `install.sh`, `INSTALLATION.md`, `raspberry-pi-music-player-plan.md`
- Generated configs: `/etc/shairport-sync.conf`, `/etc/systemd/system/shairport-sync.service.d/override.conf`, `/etc/systemd/system/soundmaker.service`, `/etc/systemd/system/soundmaker-leds.service`

## Current Defaults
- Stream URL: `https://uk3.internet-radio.com/proxy/1940sradio/stream`
- User: `goorlavi`
- Wi-Fi: SSID `TopTier`, pass `123secure@`
- Audio: PulseAudio → HDMI sink (default on Pi)

