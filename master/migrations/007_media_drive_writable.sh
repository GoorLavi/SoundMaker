#!/usr/bin/env bash
# SoundMaker migration: make the media drive writable by Jellyfin.
#
# Why: Jellyfin (running as the "jellyfin" user) writes trickplay thumbnail
# images next to the media files. If the media drive is mounted read-only for
# everyone except its owner, every trickplay write fails with "Permission
# denied" — but only AFTER ffmpeg has already decoded the whole video to make
# the thumbnails. The Generate Trickplay Images task then loops the entire
# library, burning CPU and overheating the Pi 5 for thumbnails it can never save.
#
# Fix: mount the exfat media drive group-writable (fmask/dmask=0002) and add the
# jellyfin user to the drive's group, so trickplay (and any other Jellyfin
# writes) succeed and the task completes in one finite pass.
#
# New installs apply the same logic via install_master.sh (configure_media_permissions).

set -euo pipefail

echo "Migration 007: making the media drive writable by Jellyfin..."

if ! systemctl list-unit-files | grep -q '^jellyfin\.service'; then
  echo "Migration 007: Jellyfin not installed, skipping."
  exit 0
fi

MOUNT=/media/content

# Only act on an exfat entry for $MOUNT in /etc/fstab.
fstab_line=$(awk -v m="$MOUNT" '$1 !~ /^#/ && $2==m && $3=="exfat" {print; exit}' /etc/fstab || true)
if [[ -z "$fstab_line" ]]; then
  echo "Migration 007: no exfat $MOUNT entry in /etc/fstab, skipping."
  exit 0
fi

changed=0

# 1. Ensure group-writable mount options (fmask/dmask=0002).
if [[ "$fstab_line" != *"dmask=0002"* ]]; then
  echo "Migration 007: adding group-write (fmask=0002,dmask=0002) to $MOUNT options..."
  sudo cp /etc/fstab "/etc/fstab.bak.$(date +%Y%m%d%H%M%S)"
  sudo awk -v m="$MOUNT" 'BEGIN{OFS=" "}
    $1 !~ /^#/ && $2==m && $3=="exfat" {
      if ($4 !~ /dmask=0002/) $4=$4",fmask=0002,dmask=0002";
      print $1,$2,$3,$4,$5,$6; next
    }
    { print }' /etc/fstab | sudo tee /etc/fstab.new > /dev/null
  sudo mv /etc/fstab.new /etc/fstab
  changed=1
else
  echo "Migration 007: $MOUNT already group-writable."
fi

# 2. Add the jellyfin user to the drive's group (gid from mount options, default 1000).
gid=$(printf '%s\n' "$fstab_line" | grep -oE 'gid=[0-9]+' | head -1 | cut -d= -f2)
gid=${gid:-1000}
grp=$(getent group "$gid" | cut -d: -f1)
if [[ -n "$grp" ]] && ! id -nG jellyfin | tr ' ' '\n' | grep -qx "$grp"; then
  echo "Migration 007: adding jellyfin to group '$grp'..."
  sudo usermod -aG "$grp" jellyfin
  changed=1
else
  echo "Migration 007: jellyfin already in the drive's group."
fi

# 3. Apply: remount the drive and restart Jellyfin so the changes take effect.
if [[ "$changed" == 1 ]]; then
  echo "Migration 007: applying changes..."
  sudo systemctl stop jellyfin || true
  sudo systemctl daemon-reload
  if sudo umount "$MOUNT" 2>/dev/null; then
    sudo mount "$MOUNT"
  else
    echo "Migration 007: $MOUNT was busy; new mount options apply on next reboot."
  fi
  sudo systemctl start jellyfin

  # Verify jellyfin can now write.
  if sudo -u jellyfin test -w "$MOUNT"; then
    echo "Migration 007: verified — jellyfin can write to $MOUNT."
  else
    echo "Migration 007: WARNING — jellyfin still cannot write to $MOUNT; a reboot may be needed."
  fi
fi

echo "Migration 007: Done."
