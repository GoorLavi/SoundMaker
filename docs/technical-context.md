# Technical Context – SoundMaker

Deep-dive reference for hardware, OS, networking, audio pipeline, IPC, services, and failure handling.

---

## Hardware

| Component        | Specification                                               |
| ---------------- | ----------------------------------------------------------- |
| Board            | Raspberry Pi Zero 2 W                                       |
| Audio            | HDMI (default); PulseAudio allows USB/I2S DAC later         |
| LEDs             | GPIO17 (Stream), GPIO27 (AirPlay) with series resistors     |
| Power            | Stable 5V/2A+ (preferably 3A), high-quality micro-USB cable |
| Storage          | 64GB micro-SD (PNY Elite, Class-10, UHS-I tested)           |
| Debug (optional) | Mini-HDMI → HDMI cable, USB keyboard + OTG adapter          |

### Hardware Lessons Learned

- Pi Zero 2 W **does not support 5GHz Wi-Fi** – 2.4GHz only
- Headless auto-configuration via `cloud-init` / `user-config` is **unreliable** on Pi Zero 2 W
- First boot with screen + keyboard recommended for initial setup

---

## Operating System & User

| Item         | Value                                     |
| ------------ | ----------------------------------------- |
| OS           | Raspberry Pi OS Lite (32-bit recommended) |
| Primary user | `goorlavi` (UID 1000)                     |
| XDG runtime  | `/run/user/1000`                          |
| Locale       | `en_US.UTF-8`                             |
| Keyboard     | English (US)                              |

### Why 32-bit Lite

- Most stable choice for Pi Zero 2 W
- Fewer Wi-Fi driver issues than 64-bit
- Ideal for headless + systemd-based systems
- No desktop overhead

---

## Network / Wi-Fi Provisioning

| Setting     | Value                              |
| ----------- | ---------------------------------- |
| Target SSID | `TopTier`                          |
| Password    | `123secure@`                       |
| Interface   | `wlan0`                            |
| Flag file   | `/etc/soundmaker/wifi_provisioned` |

### Provisioning Flow

1. `install.sh` checks if flag file exists
2. If missing: uses NetworkManager (`nmcli`) to configure Wi-Fi
3. Creates flag file after successful provisioning
4. Subsequent installs skip provisioning

### Wi-Fi Requirements

- WPA2-PSK encryption
- Visible SSID (no hidden networks)
- Country code set to `IL`

### Verification Commands

```bash
ip link                    # Verify wlan0 exists
iw dev wlan0 link          # Check connection status
ip a show wlan0            # Show IP address
```

### Stability

- Wi-Fi power saving disabled for reliability

---

## Audio Pipeline

### Components

| Layer            | Technology                                                         |
| ---------------- | ------------------------------------------------------------------ |
| Sound server     | PulseAudio (per-user, socket at `/run/user/1000/pulse`)            |
| Stream playback  | `mpv` via PulseAudio (`--audio-device=pulse`)                      |
| AirPlay receiver | `shairport-sync` with PulseAudio backend (`output_backend = "pa"`) |
| Default sink     | HDMI (`alsa_output.platform-3f902000.hdmi.hdmi-stereo`)            |

### How Sharing Works

- PulseAudio acts as shared audio server
- Both `mpv` and `shairport-sync` connect to PulseAudio
- SoundMaker stops `mpv` when AirPlay starts (no mixing needed)
- `XDG_RUNTIME_DIR=/run/user/1000` required for both services

---

## Application Components

| File                  | Responsibility                                                                   |
| --------------------- | -------------------------------------------------------------------------------- |
| `player.py`           | Entry point, signal handling, logging, main loop, writes `/tmp/soundmaker_state` |
| `audio_controller.py` | State machine (STREAMING, AIRPLAY, IDLE, TRANSITIONING); stop/start logic        |
| `stream_player.py`    | Manages `mpv` process; restart logic; passes `XDG_RUNTIME_DIR` to subprocess     |
| `airplay_manager.py`  | Sets up FIFO `/tmp/soundmaker_airplay_events`, checks shairport status           |
| `airplay_hook.sh`     | Called by shairport hooks; writes `connect`/`disconnect` to FIFO with retries    |
| `led_controller.py`   | Reads `/tmp/soundmaker_state`, drives GPIO LEDs                                  |
| `config.py`           | CLI argument parsing and configuration                                           |
| `logger_setup.py`     | Logging setup with file rotation                                                 |
| `utils.py`            | Helper functions                                                                 |

---

## IPC and State Files

| File                             | Purpose                                | Permissions            |
| -------------------------------- | -------------------------------------- | ---------------------- |
| `/tmp/soundmaker_airplay_events` | FIFO for AirPlay events                | `prw-rw-rw- root:root` |
| `/tmp/soundmaker_state`          | Current audio state for LED controller | Written by `player.py` |

### FIFO Flow

1. `soundmaker.service` creates FIFO via `airplay_manager.py`
2. `ExecStartPost` chowns FIFO to `root:root` for shairport access
3. `shairport-sync` hooks call `airplay_hook.sh`
4. Hook writes event to FIFO with retry logic
5. `player.py` reads events and switches audio mode

---

## Systemd Services

### soundmaker.service

```ini
[Service]
User=goorlavi
Group=goorlavi
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStartPre=+/bin/bash -c 'mkdir -p /run/user/1000/pulse && chown -R goorlavi:goorlavi /run/user/1000'
ExecStartPre=/bin/bash -c 'pulseaudio --start || true'
ExecStart=/usr/bin/python3 /opt/soundmaker/player.py
ExecStartPost=/bin/bash -c 'sleep 2 && chown root:root /tmp/soundmaker_airplay_events 2>/dev/null || true'
Restart=on-failure
```

**Notes:**

- First `ExecStartPre` uses `+` prefix to run as root (creates runtime dir on headless boot)
- Second `ExecStartPre` ensures PulseAudio is running
- `ExecStartPost` fixes FIFO ownership for shairport hooks

### shairport-sync.service.d/override.conf

```ini
[Service]
User=goorlavi
Group=goorlavi
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStartPre=+/bin/bash -c 'mkdir -p /run/user/1000 /run/user/1000/pulse && chown goorlavi:goorlavi /run/user/1000 /run/user/1000/pulse'
```

**Notes:**

- Drop-in override runs shairport as user (not system user)
- Creates PulseAudio runtime directory before service starts

### soundmaker-leds.service

- Runs `led_controller.py` as root (GPIO access)
- Depends on `soundmaker.service`
- Reads `/tmp/soundmaker_state` to determine LED states

---

## Shairport Configuration

Generated at `/etc/shairport-sync.conf`:

```
general = {
  name = "SoundMaker";
  output_backend = "pa";
  wait_for_completion = "yes";
  volume_range_db = 60;
  volume_max_db = 0;
  default_airplay_volume = -12.0;
};

pa = {
  application_name = "SoundMaker AirPlay";
};

sessioncontrol = {
  run_this_when_a_remote_connects = "/opt/soundmaker/airplay_hook.sh connect";
  run_this_when_a_remote_disconnects = "/opt/soundmaker/airplay_hook.sh disconnect";
  run_this_before_play_begins = "/opt/soundmaker/airplay_hook.sh connect";
  run_this_after_play_ends = "/opt/soundmaker/airplay_hook.sh disconnect";
};
```

**Key settings:**

- `output_backend = "pa"` – Use PulseAudio instead of ALSA
- `wait_for_completion = "yes"` – Wait for hooks to finish
- `volume_range_db = 60` – Full volume range for phone control
- `volume_max_db = 0` – True maximum volume (0dB = full scale)
- `default_airplay_volume = -12.0` – Start at ~80% volume when connecting
- Four hooks ensure reliable connect/disconnect detection

---

## Default Stream & Behavior

| Setting               | Value                                                    |
| --------------------- | -------------------------------------------------------- |
| Stream URL            | `https://uk3.internet-radio.com/proxy/1940sradio/stream` |
| Volume                | 100                                                      |
| On AirPlay connect    | Stop mpv, state → AIRPLAY                                |
| On AirPlay disconnect | Restart mpv, state → STREAMING                           |

---

## Failure Handling / Resilience

| Component              | Recovery Mechanism                                                  |
| ---------------------- | ------------------------------------------------------------------- |
| mpv crashes            | `stream_player.py` restarts with backoff and max attempts           |
| FIFO exists            | `airplay_manager.py` tolerates existing/root-owned pipes            |
| Hook timeout           | `airplay_hook.sh` retries with timeouts to avoid blocking shairport |
| Service crash          | systemd `Restart=on-failure` restarts services                      |
| PulseAudio not running | `ExecStartPre` starts PulseAudio before main process                |

---

## Install/Upgrade Notes (install.sh)

| Action            | Details                                                               |
| ----------------- | --------------------------------------------------------------------- |
| Backup            | Prior install backed up to `/opt/soundmaker_backup`                   |
| Config generation | Writes clean `shairport-sync.conf` and systemd overrides (idempotent) |
| ExecStartPre      | Uses `+` prefix to run as root on headless boot                       |
| PulseAudio        | Started automatically so audio works without SSH login                |
| FIFO permissions  | Set to `root:root` via `ExecStartPost`                                |

---

## Development Workflow

### Local Development

- Code written on macOS using any editor
- Python 3 required

### Transfer to Pi

```bash
scp *.py *.sh goorlavi@PI_IP:/home/goorlavi/
```

### Run Installation

```bash
ssh goorlavi@PI_IP
chmod +x install.sh
sudo ./install.sh
```

### Manual Testing

```bash
python3 /opt/soundmaker/player.py --test    # Test stream
python3 /opt/soundmaker/player.py           # Run manually
```

---

## Verification Commands

### Service Status

```bash
sudo systemctl status soundmaker.service
sudo systemctl status shairport-sync
sudo systemctl status soundmaker-leds.service
```

### Logs

```bash
sudo journalctl -u soundmaker.service -f     # Main service
sudo journalctl -t soundmaker -f             # Hook messages
sudo journalctl -u shairport-sync -f         # Shairport
```

### FIFO Permissions

```bash
ls -l /tmp/soundmaker_airplay_events
# Expected: prw-rw-rw- root root
```

### PulseAudio

```bash
sudo -u goorlavi pactl info
sudo -u goorlavi pactl list sinks short
```

### AirPlay Test

1. Connect iPhone to "SoundMaker" in AirPlay menu
2. Stream should stop, AirPlay audio plays
3. Disconnect → stream resumes
