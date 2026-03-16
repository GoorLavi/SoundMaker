#!/usr/bin/env bash
# SoundMaker migration: install Jellyfin media server.
# This migration installs Jellyfin for existing SoundMaker deployments.
# New installs get Jellyfin automatically via install_master.sh.

set -euo pipefail

echo "Migration 005: Installing Jellyfin media server..."

# Check if already installed
if command -v jellyfin &> /dev/null || systemctl list-unit-files | grep -q jellyfin; then
  echo "Migration 005: Jellyfin is already installed, skipping."
  exit 0
fi

# Add Jellyfin repository
echo "Migration 005: Adding Jellyfin repository..."
curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/jellyfin-archive-keyring.gpg 2>/dev/null

# Determine Debian/Ubuntu codename
codename=$(lsb_release -c -s 2>/dev/null || echo "bookworm")

echo "deb [signed-by=/usr/share/keyrings/jellyfin-archive-keyring.gpg arch=$(dpkg --print-architecture)] https://repo.jellyfin.org/debian $codename main" | sudo tee /etc/apt/sources.list.d/jellyfin.list > /dev/null

# Install Jellyfin
echo "Migration 005: Installing Jellyfin package..."
sudo apt-get update -qq
sudo apt-get install -y -qq jellyfin

# Enable and start the service
echo "Migration 005: Starting Jellyfin service..."
sudo systemctl enable jellyfin
sudo systemctl start jellyfin

echo "Migration 005: Done. Jellyfin is available at http://$(hostname).local:8096"
echo "Migration 005: Complete the setup wizard in your browser to configure Jellyfin."
