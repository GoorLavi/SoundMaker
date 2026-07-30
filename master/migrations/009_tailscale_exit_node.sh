#!/usr/bin/env bash
# SoundMaker migration 009: Tailscale exit-node support + operator access.
#
# Prepares the Pi to act as a Tailscale exit node ("home VPN"):
#   1. Enables IP forwarding (required for tailscaled to route other
#      devices' traffic) via /etc/sysctl.d/99-tailscale.conf.
#   2. Sets the backend user as the Tailscale operator, so the Web UI's
#      Tailscale card can read status and toggle exit-node advertising
#      without sudo.
#
# Advertising the exit node itself is done from the Web UI
# (System → Tailscale VPN), and the device must then be approved once in
# the Tailscale admin console (https://login.tailscale.com/admin/machines).
#
# New installs get this automatically via install_master.sh.

set -euo pipefail

run_user="$(id -un)"
echo "Migration 009: enabling Tailscale exit-node support for '$run_user'..."

# 1. IP forwarding.
sudo tee /etc/sysctl.d/99-tailscale.conf > /dev/null <<SYSCTLEOF
# Managed by SoundMaker. Required for the Tailscale exit node.
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
SYSCTLEOF
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf > /dev/null
echo "Migration 009: IP forwarding enabled."

# 2. Backend user as Tailscale operator (needs an authenticated tailscaled).
if sudo tailscale status > /dev/null 2>&1; then
    if sudo tailscale set --operator="$run_user"; then
        echo "Migration 009: Tailscale operator set to '$run_user'."
    else
        echo "Migration 009: could not set operator — the Web UI Tailscale card will be read-only." >&2
    fi
else
    echo "Migration 009: Tailscale not authenticated — run 'sudo tailscale up --ssh --operator=$run_user' to finish."
fi

echo "Migration 009: done."
