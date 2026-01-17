# SoundMaker Installation Guide

Complete installation guide for setting up SoundMaker Internet Radio Player on Raspberry Pi.

## Prerequisites

- Raspberry Pi (tested on Raspberry Pi Zero 2 W)
- Raspberry Pi OS Lite (32-bit recommended)
- SSH access to the Pi
- Network connectivity (Wi-Fi or Ethernet)
- Audio output device (HDMI, USB audio adapter, or I2S DAC)
- For AirPlay support: iOS device or Mac with AirPlay capability (optional)

## Quick Installation (Automated)

The easiest way to install SoundMaker is using the automated installation script.

### Step 1: Transfer Files to Raspberry Pi

From your development machine (macOS/Linux), transfer all SoundMaker files:

```bash
# Replace PI_IP with your actual Pi IP address
# Transfer all Python modules, hook script, and install script
scp *.py *.sh goorlavi@PI_IP:/home/goorlavi/
```

Or transfer the entire directory:

```bash
scp -r /path/to/SoundMaker goorlavi@PI_IP:/home/goorlavi/
```

### Step 2: SSH into Raspberry Pi

```bash
ssh goorlavi@PI_IP
```

### Step 3: Run the Installation Script

```bash
# Make script executable
chmod +x install.sh

# Run the installation script (requires sudo)
sudo ./install.sh
```

The script will automatically:

- Check prerequisites
- Install mpv if needed
- Install shairport-sync for AirPlay support (optional)
- Create application directory
- Copy all SoundMaker files to `/opt/soundmaker/`
- Configure shairport-sync hooks for AirPlay detection
- Create systemd service file
- Enable and start the service
- Verify installation

### Step 4: Verify Installation

```bash
# Check service status
sudo systemctl status soundmaker.service

# View logs
sudo journalctl -u soundmaker.service -f
```

That's it! The player should now be running and will start automatically on boot.

---

## Manual Installation

If you prefer to install manually or need to customize the installation, follow these steps:

### Step 1: Transfer Files to Raspberry Pi

From your development machine (macOS/Linux), transfer all SoundMaker files:

```bash
# Replace PI_IP with your actual Pi IP address
# Transfer all Python modules, hook script, and install script
scp *.py *.sh goorlavi@PI_IP:/home/goorlavi/
```

### Step 2: SSH into Raspberry Pi

```bash
ssh goorlavi@PI_IP
```

## Step 3: Install Dependencies

### Install mpv media player

```bash
sudo apt-get update
sudo apt-get install -y mpv
```

Verify installation:

```bash
mpv --version
```

## Step 4: Set Up Application Directory

```bash
# Create application directory
sudo mkdir -p /opt/soundmaker

# Copy all SoundMaker files
sudo cp ~/*.py ~/*.sh /opt/soundmaker/ 2>/dev/null || true

# Make scripts executable
sudo chmod +x /opt/soundmaker/player.py
sudo chmod +x /opt/soundmaker/airplay_hook.sh 2>/dev/null || true

# Set ownership
sudo chown -R goorlavi:goorlavi /opt/soundmaker
```

## Step 5: Test the Player Manually

Before setting up auto-start, test the player:

```bash
# Test stream accessibility
python3 /opt/soundmaker/player.py --test

# If test passes, try running it manually (Ctrl+C to stop)
python3 /opt/soundmaker/player.py
```

You should hear audio playing. If not, check:

- Audio output device is connected
- Volume is not muted
- HDMI audio is enabled (if using HDMI)

## Step 6: Create systemd Service

Create the systemd service file:

```bash
sudo nano /etc/systemd/system/soundmaker.service
```

Paste the following content:

```ini
[Unit]
Description=Internet Radio Player (SoundMaker)
After=network-online.target sound.target
Wants=network-online.target
Requires=network-online.target

[Service]
Type=simple
User=goorlavi
Group=goorlavi
WorkingDirectory=/opt/soundmaker
ExecStart=/usr/bin/python3 /opt/soundmaker/player.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

## Step 7: Enable and Start the Service

```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable soundmaker.service

# Start the service now (without rebooting)
sudo systemctl start soundmaker.service

# Check the status
sudo systemctl status soundmaker.service
```

## Step 8: Verify Installation

### Check service status

```bash
# Should show "active (running)"
sudo systemctl is-active soundmaker.service

# View service status
sudo systemctl status soundmaker.service
```

### Check logs

```bash
# View recent logs
sudo journalctl -u soundmaker.service -n 50

# Follow logs in real-time
sudo journalctl -u soundmaker.service -f
```

### Verify mpv is running

```bash
ps aux | grep mpv
```

You should see an mpv process running.

## Step 9: Test Auto-Start on Boot

Reboot the Pi to verify it starts automatically:

```bash
sudo reboot
```

After reboot, SSH back in and check:

```bash
sudo systemctl status soundmaker.service
```

The service should be running automatically.

## AirPlay Support

SoundMaker includes automatic AirPlay support. When an AirPlay device connects, streaming automatically stops and AirPlay audio plays. When the device disconnects, streaming resumes automatically.

### How It Works

1. **shairport-sync** runs as a systemd service, waiting for AirPlay connections
2. When a device connects/disconnects, **shairport-sync** calls the hook script
3. The hook script writes events to a named pipe
4. **SoundMaker** reads events from the pipe and switches audio sources accordingly

### Using AirPlay

1. Ensure shairport-sync is installed and running:

   ```bash
   sudo systemctl status shairport-sync
   ```

2. On your iOS device or Mac, look for "SoundMaker" in AirPlay devices

3. Connect to SoundMaker via AirPlay

4. Streaming will automatically stop and AirPlay audio will play

5. When you disconnect, streaming will automatically resume

### Troubleshooting AirPlay

- **Can't see SoundMaker in AirPlay list:**

  - Check that shairport-sync is running: `sudo systemctl status shairport-sync`
  - Ensure both devices are on the same Wi-Fi network
  - Check firewall settings

- **AirPlay connects but no audio:**

  - Check audio output device (HDMI, USB, etc.)
  - Verify shairport-sync configuration: `sudo nano /etc/shairport-sync.conf`

- **Streaming doesn't resume after disconnect:**
  - Check SoundMaker logs: `sudo journalctl -u soundmaker.service -f`
  - Verify hook script is executable: `ls -la /opt/soundmaker/airplay_hook.sh`

## Configuration Options

### Change Stream URL

Edit the service file:

```bash
sudo nano /etc/systemd/system/soundmaker.service
```

Modify the `ExecStart` line:

```ini
ExecStart=/usr/bin/python3 /opt/soundmaker/player.py --url https://your-stream-url.com/stream
```

Reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart soundmaker.service
```

### Change Volume

Edit the service file and modify `ExecStart`:

```ini
ExecStart=/usr/bin/python3 /opt/soundmaker/player.py --volume 80
```

### Use Custom URL and Volume

```ini
ExecStart=/usr/bin/python3 /opt/soundmaker/player.py --url https://example.com/stream --volume 75
```

## Command-Line Options

The player supports the following command-line options:

- `--url URL`: Stream URL to play (default: 1940s Radio stream)
- `--volume 0-100`: Volume level (default: 100)
- `--test`: Test stream accessibility and exit
- `--verbose` or `-v`: Enable debug logging

Examples:

```bash
# Test a stream
python3 /opt/soundmaker/player.py --url https://example.com/stream --test

# Run with custom volume
python3 /opt/soundmaker/player.py --volume 80

# Verbose logging
python3 /opt/soundmaker/player.py --verbose
```

## Troubleshooting

### Service fails to start

1. **Check logs:**

   ```bash
   sudo journalctl -u soundmaker.service -n 100
   ```

2. **Verify mpv is installed:**

   ```bash
   which mpv
   mpv --version
   ```

3. **Test manually as service user:**

   ```bash
   sudo -u goorlavi python3 /opt/soundmaker/player.py --test
   ```

4. **Check file permissions:**

   ```bash
   ls -la /opt/soundmaker/player.py
   ```

5. **Verify username in service file:**

   ```bash
   # Check current username
   whoami

   # Verify it matches service file
   sudo cat /etc/systemd/system/soundmaker.service | grep User=
   ```

### No audio output

1. **Check audio device:**

   ```bash
   # List audio devices
   aplay -l

   # Test audio
   speaker-test -t sine -f 1000 -l 1
   ```

2. **For HDMI audio, ensure it's enabled:**

   ```bash
   # Check HDMI audio status
   tvservice -s
   ```

3. **Check volume:**
   ```bash
   alsamixer
   ```

### Network issues

1. **Check network connectivity:**

   ```bash
   ping -c 3 8.8.8.8
   ```

2. **Check network service status:**

   ```bash
   systemctl status NetworkManager-wait-online.service
   # or
   systemctl status networking.service
   ```

3. **Test stream URL manually:**
   ```bash
   curl -I https://uk3.internet-radio.com/proxy/1940sradio/stream
   ```

### Service keeps restarting

1. **Check for errors in logs:**

   ```bash
   sudo journalctl -u soundmaker.service -n 100 | grep -i error
   ```

2. **Check restart count:**

   ```bash
   sudo systemctl status soundmaker.service | grep "restart counter"
   ```

3. **Test stream accessibility:**
   ```bash
   python3 /opt/soundmaker/player.py --test
   ```

## Service Management Commands

```bash
# Start service
sudo systemctl start soundmaker.service

# Stop service
sudo systemctl stop soundmaker.service

# Restart service
sudo systemctl restart soundmaker.service

# Check status
sudo systemctl status soundmaker.service

# View logs
sudo journalctl -u soundmaker.service -f

# Disable auto-start on boot
sudo systemctl disable soundmaker.service

# Enable auto-start on boot
sudo systemctl enable soundmaker.service
```

## Log Files

The player creates log files in the user's home directory:

- Location: `~/.soundmaker/player.log`
- Rotation: 10MB per file, keeps 3 backups
- View logs: `cat ~/.soundmaker/player.log`

## Uninstallation

To remove SoundMaker:

```bash
# Stop and disable service
sudo systemctl stop soundmaker.service
sudo systemctl disable soundmaker.service

# Remove service file
sudo rm /etc/systemd/system/soundmaker.service

# Reload systemd
sudo systemctl daemon-reload

# Remove application files
sudo rm -rf /opt/soundmaker

# Remove log directory (optional)
rm -rf ~/.soundmaker
```

## Notes

- The service waits for network connectivity before starting (`network-online.target`)
- The service automatically restarts on failure (up to systemd limits)
- Logs are written to both systemd journal and file (`~/.soundmaker/player.log`)
- HDMI audio is the default output (can be changed to USB or I2S DAC)
- The player supports high-quality audio formats (MP3, AAC, Opus, etc.)

## Support

For issues or questions, check:

- Service logs: `sudo journalctl -u soundmaker.service`
- Player logs: `~/.soundmaker/player.log`
- System logs: `sudo journalctl -xe`
