#!/usr/bin/env bash
# SoundMaker migration 008: enable power controls and log access.
#
# Grants the backend user two capabilities used by the new System-tab features:
#   1. Membership in the `systemd-journal` group, so the log viewer can read
#      the journal without sudo.
#   2. Passwordless sudo for exactly two commands — restart the backend and
#      reboot the Pi — via /etc/sudoers.d/soundmaker. Both use `systemd-run`
#      so the action runs as a transient timer and survives the restart.
#
# New installs get this automatically via install_master.sh.

set -euo pipefail

run_user="$(id -un)"
echo "Migration 008: enabling power controls and log access for '$run_user'..."

# 1. Journal read access (applies after the backend is restarted).
sudo usermod -aG systemd-journal "$run_user" 2>/dev/null || \
    echo "Migration 008: could not add $run_user to systemd-journal group (log viewer may be empty)."

# 2. Scoped passwordless sudo for restart + reboot.
sudoers_file="/etc/sudoers.d/soundmaker"
sudo tee "$sudoers_file" > /dev/null <<SUDOEOF
# Managed by SoundMaker.
# Allows the backend to restart itself and reboot the Pi from the Web UI, and
# nothing else. systemd-run schedules the action as a transient timer so it
# survives the backend being restarted.
$run_user ALL=(root) NOPASSWD: /usr/bin/systemd-run --on-active=2 systemctl restart soundmaker-backend.service, /usr/bin/systemd-run --on-active=2 systemctl reboot
SUDOEOF
sudo chmod 440 "$sudoers_file"

if sudo visudo -cf "$sudoers_file" > /dev/null 2>&1; then
    echo "Migration 008: power controls enabled."
else
    echo "Migration 008: generated sudoers file is invalid — removing it." >&2
    sudo rm -f "$sudoers_file"
    exit 1
fi

echo "Migration 008: done. Restart the backend for journal (log viewer) access to take effect."
