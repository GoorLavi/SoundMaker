#!/usr/bin/env bash
# SoundMaker migration: fix raspotify config.
# Rewrites /etc/default/raspotify with a clean config:
#   - LIBRESPOT_NAME="SoundMaker"  (so the Pi appears correctly in Spotify's device list)
#   - LIBRESPOT_DEVICE="vc4-hdmi-0"  (HDMI output for the soundbar)
set -euo pipefail

CONF="/etc/default/raspotify"

if [[ ! -f "$CONF" ]]; then
  echo "Migration 004: $CONF not found — is raspotify installed? Skipping."
  exit 0
fi

echo "Migration 004: rewriting $CONF with clean raspotify config..."
sudo tee "$CONF" > /dev/null <<'EOF'
LIBRESPOT_NAME="SoundMaker"
LIBRESPOT_DEVICE="vc4-hdmi-0"
EOF

echo "Migration 004: restarting raspotify..."
sudo systemctl restart raspotify

echo "Migration 004: done. Pi will appear as 'SoundMaker' on HDMI output."
