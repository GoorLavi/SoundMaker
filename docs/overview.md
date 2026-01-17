# SoundMaker Overview

## Project Goal

SoundMaker is a **headless Raspberry Pi audio appliance** that:

- Streams internet radio automatically on boot
- Switches to AirPlay when an iPhone/Mac connects
- Resumes streaming when AirPlay disconnects
- Requires no screen, keyboard, or manual login
- Indicates audio state via physical LEDs
- Controllable via Apple Home app (play/stop, volume)

## Hardware

| Component    | Details                                    |
| ------------ | ------------------------------------------ |
| Board        | Raspberry Pi Zero 2 W                      |
| Audio Output | HDMI (default); USB/I2S DAC can be added   |
| Status LEDs  | GPIO17 (Stream), GPIO27 (AirPlay)          |
| Power        | Stable 5V/2A+ supply                       |
| Storage      | 64GB micro-SD card                         |
| Connectivity | 2.4GHz Wi-Fi only (no 5GHz on Pi Zero 2 W) |

## Software Features

- **Internet Radio Streaming** via `mpv` through PulseAudio
- **AirPlay Receiver** via `shairport-sync` with session hooks
- **Automatic Source Switching**: Stream stops on AirPlay connect, resumes on disconnect
- **Apple Home Integration** via Homebridge:
  - Play/stop radio from Home app (switch accessory)
  - Volume control via brightness slider (lightbulb accessory)
  - Controls ignored during AirPlay (AirPlay takes priority)
- **One-Time Wi-Fi Provisioning** using NetworkManager (`nmcli`)
- **LED Status Indicators** driven by GPIO
- **Systemd Services** for auto-start and resilience
- **Rotating Logs** via Python logging

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         SoundMaker                              │
├─────────────────────────────────────────────────────────────────┤
│  player.py            Entry point, signal handling, main loop  │
│  audio_controller.py  State machine (STREAMING/AIRPLAY/IDLE)   │
│  stream_player.py     Manages mpv process with restart logic   │
│  state_service.py     Centralized state/command file I/O       │
│  airplay_manager.py   IPC via FIFO, monitors shairport-sync    │
│  airplay_hook.sh      Called by shairport hooks → writes FIFO  │
│  led_controller.py    Reads state file → drives GPIO LEDs      │
│  homebridge_bridge.py HTTP server for Apple Home integration   │
│  config.py            CLI args and configuration               │
│  logger_setup.py      Logging with file rotation               │
│  utils.py             Helper functions                         │
└─────────────────────────────────────────────────────────────────┘

Data Flow:
  1. player.py starts → audio_controller enters STREAMING state
  2. stream_player spawns mpv → audio plays via PulseAudio
  3. AirPlay device connects → shairport-sync calls airplay_hook.sh
  4. Hook writes "connect" to FIFO → airplay_manager reads it
  5. audio_controller stops mpv → state becomes AIRPLAY
  6. AirPlay disconnects → hook writes "disconnect"
  7. audio_controller restarts mpv → state returns to STREAMING
  8. led_controller reads /tmp/soundmaker_state → updates LEDs

Apple Home Flow:
  1. Home app sends command → Homebridge
  2. Homebridge calls homebridge_bridge.py HTTP endpoints
  3. Bridge writes to /tmp/soundmaker_commands
  4. player.py reads command → executes play/stop/volume
  5. State updated in /tmp/soundmaker_state → Homebridge polls it
```

## Key Files and Paths

| Path                                                         | Purpose                        |
| ------------------------------------------------------------ | ------------------------------ |
| `/opt/soundmaker/`                                           | Application code               |
| `/etc/shairport-sync.conf`                                   | Generated shairport config     |
| `/etc/systemd/system/soundmaker.service`                     | Main service unit              |
| `/etc/systemd/system/soundmaker-leds.service`                | LED controller service         |
| `/etc/systemd/system/soundmaker-bridge.service`              | HTTP bridge for Homebridge     |
| `/etc/systemd/system/homebridge.service`                     | Homebridge (Apple Home)        |
| `/etc/systemd/system/shairport-sync.service.d/override.conf` | PulseAudio drop-in             |
| `/var/lib/homebridge/config.json`                            | Homebridge accessory config    |
| `/tmp/soundmaker_airplay_events`                             | IPC FIFO for AirPlay events    |
| `/tmp/soundmaker_state`                                      | JSON state file (mode/volume)  |
| `/tmp/soundmaker_commands`                                   | Command file for external ctrl |
| `/etc/soundmaker/wifi_provisioned`                           | Wi-Fi provisioning flag        |

## Technologies

- **Python 3** – Application logic, subprocess management, logging
- **mpv** – Audio playback with PulseAudio backend
- **shairport-sync** – AirPlay 1 receiver with session hooks
- **PulseAudio** – Shared audio server (per-user mode)
- **systemd** – Service management, auto-start, dependencies
- **NetworkManager / nmcli** – Wi-Fi provisioning
- **RPi.GPIO** – LED control on Raspberry Pi
- **Node.js / Homebridge** – Apple Home integration
- **homebridge-http-switch** – HTTP-based switch accessory
- **homebridge-http-lightbulb** – HTTP-based lightbulb (volume)

## Current Defaults

| Setting        | Value                                                    |
| -------------- | -------------------------------------------------------- |
| Stream URL     | `https://uk3.internet-radio.com/proxy/1940sradio/stream` |
| Volume         | 100                                                      |
| Wi-Fi SSID     | `TopTier`                                                |
| Wi-Fi Password | `123secure@`                                             |
| User           | `goorlavi`                                               |
