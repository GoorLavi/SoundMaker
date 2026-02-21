#!/usr/bin/env bash
# SoundMaker migration: install and enable raspotify (Spotify Connect receiver).
# The Pi appears as "SoundMaker" so the morning alarm can start playback.
# Requires sudo (passwordless sudo for apt/systemctl recommended).
set -euo pipefail

if ! command -v sudo &>/dev/null; then
  echo "Migration 003: sudo not found, skipping raspotify install."
  exit 0
fi

install_raspotify() {
  if sudo systemctl list-unit-files 2>/dev/null | grep -q '^raspotify'; then
    echo "Raspotify already installed."
  else
    echo "Installing raspotify..."
    sudo apt-get update -qq
    if sudo apt-get install -y -qq raspotify 2>/dev/null; then
      echo "Installed raspotify from system repos."
    else
      echo "Adding raspotify repo..."
      curl -sSL https://dtcooper.github.io/raspotify/key.asc | sudo gpg --dearmor -o /usr/share/keyrings/raspotify-archive-keyring.gpg 2>/dev/null || true
      echo "deb [signed-by=/usr/share/keyrings/raspotify-archive-keyring.gpg] https://dtcooper.github.io/raspotify raspotify main" | sudo tee /etc/apt/sources.list.d/raspotify.list >/dev/null
      sudo apt-get update -qq
      sudo apt-get install -y -qq raspotify
    fi
  fi

  if [[ -f /etc/raspotify/conf ]]; then
    if ! grep -q 'LIBRESPOT_NAME' /etc/raspotify/conf 2>/dev/null; then
      echo 'LIBRESPOT_NAME="SoundMaker"' | sudo tee -a /etc/raspotify/conf >/dev/null
    fi
  elif [[ -f /etc/default/raspotify ]]; then
    if ! grep -q 'DEVICE_NAME' /etc/default/raspotify 2>/dev/null; then
      echo 'DEVICE_NAME="SoundMaker"' | sudo tee -a /etc/default/raspotify >/dev/null
    fi
  fi

  sudo systemctl enable raspotify 2>/dev/null || true
  sudo systemctl start raspotify 2>/dev/null || true
  echo "Raspotify enabled and started (device name: SoundMaker)."
}

install_raspotify
echo "Migration 003 done."
