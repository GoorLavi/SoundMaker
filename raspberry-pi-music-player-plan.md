# Raspberry Pi Internet Music Player – Full Setup & Plan

This document summarizes **the entire process we went through**, from a fresh Raspberry Pi to a fully working, headless system, and defines a **clear future plan for the code**.

The goal: a single document you can open in your IDE and immediately know where to continue.

---

## 1. Project Goal

Build a **headless Internet music player**:

- Runs on Raspberry Pi
- Music is streamed from an **online URL**
- Written in Python
- Starts automatically after boot
- Managed entirely via SSH (no screen, no login)

---

## 2. Hardware

- Raspberry Pi Zero 2 W
- 64GB Micro-SD card (PNY Elite, Class-10, UHS-I)
- Stable power supply 5V 2A+ (preferably 3A)
- High-quality Micro-USB power cable
- Mini-HDMI → HDMI cable (debug only)
- USB Type-A keyboard + Micro-USB OTG adapter

---

## 3. Operating System

### Selected OS

- **Raspberry Pi OS Lite (32-bit)**
- No desktop / GUI

### Why this OS

- Most stable choice for Pi Zero 2 W
- Fewer Wi-Fi issues than 64-bit
- Ideal for headless + systemd-based systems

---

## 4. Initial Installation – Lessons Learned

### Issues encountered

- `cloud-init / user-config` service failed
- Wi-Fi did not come up
- `wlan0` did not exist
- SSH was unreachable

### Conclusion

> Headless auto-configuration on Pi Zero 2 W is unreliable.

### Working solution

- Clean OS install **without user-config**
- First boot with screen + keyboard
- Manual configuration only

---

## 5. Password Reset via SD Card (Recovery Mode)

Performed steps:

- Booted with `init=/bin/bash`
- Changed password using `passwd`
- Understood that in this mode:
  - `systemd` is not running
  - Wi-Fi is unavailable
  - `wlan0` will not appear (this is expected)

Afterwards:

- Removed `init=/bin/bash`
- Normal reboot

---

## 6. Locale & Keyboard Configuration

Configured inside the system:

- Locale: `en_US.UTF-8`
- Keyboard layout: `English (US)`

Purpose:

- Prevent Hebrew keyboard layout issues
- Avoid password input problems

---

## 7. Wi-Fi

### Hardware limitations

- Pi Zero 2 W **does not support 5GHz**
- 2.4GHz only

### Valid configuration

- WPA2-PSK
- Visible SSID
- Country set to `IL`

### Verification commands

- `ip link` → verify `wlan0`
- `iw dev wlan0 link`
- `ip a show wlan0`

### Stability improvement

- Disabled Wi-Fi power saving

---

## 8. SSH

### Enable SSH

```bash
sudo systemctl enable ssh
sudo systemctl start ssh
```

### Connect

```bash
ssh user@PI_IP
```

Status: **SSH fully working and stable** ✅

---

## 9. Development Workflow

### Local development

- Code written on macOS
- Python 3

### Transfer code to Pi

```bash
scp player.py user@PI_IP:/home/user/
```

### Manual execution

```bash
python3 ~/player.py
```

Successfully tested.

---

## 10. Current State (Checkpoint)

✔ Raspberry Pi boots correctly  
✔ Wi-Fi connected  
✔ SSH accessible  
✔ Python script runs manually  
✔ Full remote control achieved

---

## 11. Future Code Plan

### Objective

Play Internet audio streams reliably and automatically.

### Phase 1 – Basic playback

- Use `mpv` or `vlc` as playback backend
- Control playback via Python (`subprocess`)

### Phase 2 – Process management

- Start / stop logic
- Automatic restart on failure
- Structured logging

### Phase 3 – systemd service

- Auto-start after boot
- No user login required
- Depends on `network-online.target`

### Phase 4 – Optional extensions

- Multiple streams
- Simple HTTP API
- Mobile control
- Bluetooth audio output
- Volume management

---

## 12. systemd – Concept Overview (Future)

The Python script will be managed by a systemd service:

- `ExecStart=python3 /opt/soundmaker/player.py`
- `Restart=on-failure`
- `After=network-online.target`

---

## 13. Guiding Principles

- Headless-first design
- Everything documented
- No magic configuration
- Small, testable steps
- systemd over cron

---

## 14. Clear Next Step

Next development step:

- Choose playback backend (recommended: **mpv**)
- Write a minimal Python stream player
- Verify audio output

From here on, this is **pure development**, not survival.

---

**Status: Stable system, ready for development.**
