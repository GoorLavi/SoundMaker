# Technical Context – SoundMaker

Deep-dive reference for hardware, OS, networking, audio pipeline, IPC, services, and failure handling.

## Hardware

- Raspberry Pi Zero 2 W (tested)
- Audio: HDMI (default); supports PulseAudio so USB/I2S DAC can be added later
- LEDs: GPIO17 (Stream), GPIO27 (AirPlay)
- Power: stable 5V/2A+, 64GB micro-SD

## Operating System & User

- Raspberry Pi OS Lite (32-bit recommended)
- Primary user: `goorlavi`
- XDG runtime: `/run/user/1000`

## Network / Wi-Fi Provisioning

- One-time provisioning via NetworkManager (`nmcli`) in `install.sh`
- Target SSID: `TopTier`, password: `123secure@`
- Interface: `wlan0`
- Flag file: `/etc/soundmaker/wifi_provisioned` (provision only once)
- If NetworkManager missing or `wlan0` absent, provisioning aborts

## Audio Pipeline

- PulseAudio (per-user, socket under `/run/user/1000/pulse`)
- Stream playback: `mpv` via PulseAudio (`--audio-device=pulse`)
- AirPlay: `shairport-sync` with PulseAudio backend (`output_backend = "pa"`)
- Shared sink: PulseAudio allows shairport and mpv to coexist; SoundMaker stops mpv when AirPlay starts

## Application Components

- `player.py`: entrypoint, signal handling, logging, main loop, writes state file `/tmp/soundmaker_state`
- `audio_controller.py`: state machine (STREAMING, AIRPLAY, IDLE, TRANSITIONING); stop/start logic
- `stream_player.py`: manages `mpv` process; restart logic; uses `XDG_RUNTIME_DIR=/run/user/1000`
- `airplay_manager.py`: sets up/opens FIFO `/tmp/soundmaker_airplay_events`, checks shairport status
- `airplay_hook.sh`: called by shairport hooks; writes `connect`/`disconnect` to FIFO with retries
- `led_controller.py`: reads `/tmp/soundmaker_state` and drives GPIO LEDs
- `logger_setup.py`, `config.py`, `utils.py`: logging, args/config, helpers

## IPC and State Files

- AirPlay event FIFO: `/tmp/soundmaker_airplay_events` (mode 666; owned root:root after service post-start)
- Audio state file: `/tmp/soundmaker_state` (written by `player.py`, read by LED controller)

## Systemd Services

- `soundmaker.service`:
  - User/Group: `goorlavi`
  - Env: `XDG_RUNTIME_DIR=/run/user/1000`
  - ExecStartPre: `mkdir -p /run/user/1000/pulse && chown -R goorlavi:goorlavi /run/user/1000/pulse`
  - ExecStart: `/usr/bin/python3 /opt/soundmaker/player.py`
  - ExecStartPost: chown FIFO to root:root if present
  - Restart on failure
- `shairport-sync.service.d/override.conf`:
  - User/Group: `goorlavi`
  - Env: `XDG_RUNTIME_DIR=/run/user/1000`
  - ExecStartPre: `mkdir -p /run/user/1000/pulse && chown goorlavi:goorlavi /run/user/1000/pulse`
- `soundmaker-leds.service`: runs `led_controller.py` as root after soundmaker

## Shairport Configuration (Generated)

- `/etc/shairport-sync.conf`:
  - `general`: `name = "SoundMaker"; output_backend = "pa"; wait_for_completion = "yes";`
  - `sessioncontrol`: hooks
    - `run_this_when_a_remote_connects = "/opt/soundmaker/airplay_hook.sh connect";`
    - `run_this_when_a_remote_disconnects = "/opt/soundmaker/airplay_hook.sh disconnect";`
    - `run_this_before_play_begins = "/opt/soundmaker/airplay_hook.sh connect";`
    - `run_this_after_play_ends = "/opt/soundmaker/airplay_hook.sh disconnect";`

## Default Stream & Behavior

- Stream URL: `https://uk3.internet-radio.com/proxy/1940sradio/stream`
- Volume default: 100
- On AirPlay connect: stop mpv, switch state to AIRPLAY
- On AirPlay disconnect: restart mpv, switch state to STREAMING

## Failure Handling / Resilience

- mpv restart logic in `stream_player.py` with backoff and max attempts
- FIFO creation tolerant of existing/root-owned pipes; permissions set to 666
- Hooks retried with timeouts to avoid blocking shairport
- Services restart on failure (`Restart=on-failure`)

## Install/Upgrade Notes (install.sh)

- Backs up prior install to `/opt/soundmaker_backup`
- Writes clean shairport config and override (idempotent)
- Ensures PulseAudio per-user dir exists before starting services
- Leaves FIFO chown to root in `soundmaker.service` ExecStartPost

## Verification

- Services: `sudo systemctl status soundmaker.service shairport-sync soundmaker-leds.service`
- Logs: `sudo journalctl -u soundmaker.service -f`, `sudo journalctl -t soundmaker -f`, `sudo journalctl -u shairport-sync -f`
- FIFO perms: `ls -l /tmp/soundmaker_airplay_events` → `prw-rw-rw- root root`
- AirPlay: connect “SoundMaker”; stream stops; disconnect resumes
