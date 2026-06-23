#!/usr/bin/env bash
# SoundMaker migration: cap Jellyfin's CPU to prevent thermal crashes on the Pi 5.
#
# Why: Jellyfin transcodes video with ffmpeg, which can peg all 4 cores. On a
# Pi 5 that drives the SoC toward its ~110 °C emergency-shutdown point and cuts
# power, producing an unclean reboot (filesystem journal recovery on next boot).
# This migration installs a systemd drop-in limiting Jellyfin to at most 2 cores.
#
# New installs get this automatically via install_master.sh.

set -euo pipefail

echo "Migration 006: Applying Jellyfin CPU limit (thermal protection)..."

# Nothing to do if Jellyfin isn't installed.
if ! systemctl list-unit-files | grep -q '^jellyfin\.service'; then
  echo "Migration 006: Jellyfin is not installed, skipping."
  exit 0
fi

DROPIN_DIR=/etc/systemd/system/jellyfin.service.d
DROPIN_FILE="$DROPIN_DIR/10-cpu-limit.conf"

sudo mkdir -p "$DROPIN_DIR"
sudo tee "$DROPIN_FILE" > /dev/null <<'CPUEOF'
# Managed by SoundMaker — thermal protection for the Pi 5.
# CPUQuota=200% limits Jellyfin to at most 2 of the 4 cores so transcoding
# cannot overheat the board. CPUWeight=50 makes it yield to DNS / the web UI.
# Adjust CPUQuota to trade playback smoothness against peak temperature.
[Service]
CPUQuota=200%
CPUWeight=50
CPUEOF

echo "Migration 006: Reloading systemd and restarting Jellyfin..."
sudo systemctl daemon-reload
sudo systemctl restart jellyfin

echo "Migration 006: Done. Jellyfin is now limited to 2 CPU cores."
