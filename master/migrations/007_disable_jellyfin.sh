#!/usr/bin/env bash
# SoundMaker migration: disable Jellyfin by default.
#
# Why: media streaming is optional and the Pi 5 has limited thermal/CPU
# headroom. Jellyfin stays installed (so it can be turned back on anytime)
# but no longer runs or starts on boot unless explicitly re-enabled.
#
# New installs get this automatically via install_master.sh.

set -euo pipefail

echo "Migration 007: Disabling Jellyfin..."

# Nothing to do if Jellyfin isn't installed.
if ! systemctl list-unit-files | grep -q '^jellyfin\.service'; then
  echo "Migration 007: Jellyfin is not installed, skipping."
  exit 0
fi

sudo systemctl disable --now jellyfin

echo "Migration 007: Done. Jellyfin is stopped and will not start on boot."
echo "Migration 007: Re-enable anytime with: sudo systemctl enable --now jellyfin"
