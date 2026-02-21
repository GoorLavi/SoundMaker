#!/usr/bin/env bash
# SoundMaker migration: Caddy HTTPS proxy, raspotify, alarm/Spotify support.
#
# System-level changes (Caddy, raspotify, port change) require re-running
# install_master.sh with root. This migration records the version transition
# and prints instructions.
set -euo pipefail

echo "Migration 002: Caddy + Spotify Connect alarm"
echo ""
echo "This update adds:"
echo "  - Caddy as HTTPS reverse proxy (backend moves from port 80 → 8081)"
echo "  - Raspotify (Spotify Connect receiver)"
echo "  - Morning wake-up alarm (Spotify Web API + scheduler)"
echo ""
echo "ACTION REQUIRED: Re-run the install script to apply system changes:"
echo "  sudo SOUNDMAKER_DOMAIN=your-domain.example.com ./master/install_master.sh"
echo ""
echo "After re-running install_master.sh:"
echo "  1. Port-forward 80 and 443 on your router to this Pi"
echo "  2. Add the redirect URI to your Spotify app:"
echo "     https://YOUR_DOMAIN/api/spotify/callback"
echo "  3. Restart the backend: sudo systemctl restart soundmaker-backend"
echo ""
echo "Migration 002 done."
