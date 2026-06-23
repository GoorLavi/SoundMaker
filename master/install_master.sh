#!/usr/bin/env bash
#
# SoundMaker — Master installation script
#
# Installs and configures all services on the Raspberry Pi 5 Master.
# Must be run as root.  Safe to re-run (idempotent).
#
# Usage:
#   sudo ./install_master.sh              # interactive (prompts for passwords/domain)
#   sudo PIHOLE_PW=secret SOUNDMAKER_PW=secret SOUNDMAKER_DOMAIN=soundmaker.duckdns.org ./install_master.sh
#
# Environment variables (all optional — prompted interactively if missing):
#   PIHOLE_PW            — Pi-hole admin password
#   SOUNDMAKER_PW        — SoundMaker Web UI password
#   SOUNDMAKER_DOMAIN    — Public domain for HTTPS (e.g. soundmaker.duckdns.org)
#   SPOTIFY_CLIENT_ID    — Spotify app client ID (from developer.spotify.com)
#   SPOTIFY_CLIENT_SECRET — Spotify app client secret

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
STATE_DIR="/opt/soundmaker/state"
ENV_FILE="/opt/soundmaker/.env"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { echo -e "\e[32m[SoundMaker]\e[0m $*"; }
warn()  { echo -e "\e[33m[SoundMaker]\e[0m $*"; }
error() { echo -e "\e[31m[SoundMaker]\e[0m $*" >&2; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (sudo)."
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# 0. Pre-checks
# ---------------------------------------------------------------------------

require_root
info "Starting SoundMaker Master installation..."

# Ensure state directory exists
mkdir -p "$STATE_DIR"
chown -R "${SUDO_USER:-pi}:${SUDO_USER:-pi}" "$STATE_DIR"

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------

info "Updating system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv curl git > /dev/null

# ---------------------------------------------------------------------------
# 2. Tailscale VPN
# ---------------------------------------------------------------------------

install_tailscale() {
    if command -v tailscale &> /dev/null; then
        info "Tailscale is already installed, skipping."
    else
        info "Installing Tailscale..."
        curl -fsSL https://tailscale.com/install.sh | sh
    fi

    systemctl enable tailscaled
    systemctl start tailscaled

    if ! tailscale status &> /dev/null; then
        warn "Tailscale installed but not authenticated."
        warn "After installation completes, run:  sudo tailscale up --ssh"
    else
        info "Tailscale is running."
    fi
}

install_tailscale

# ---------------------------------------------------------------------------
# 3. Pi-hole
# ---------------------------------------------------------------------------

install_pihole() {
    if command -v pihole &> /dev/null; then
        info "Pi-hole is already installed, skipping installer."
    else
        info "Installing Pi-hole (unattended)..."

        # Create pihole user/group if they don't exist
        if ! id -u pihole &> /dev/null; then
            groupadd -f pihole
            useradd -r -g pihole -s /usr/sbin/nologin -d /home/pihole -c "PiHole" pihole 2>/dev/null || true
        fi

        # Place config before installer so it runs in "upgrade" mode
        mkdir -p /etc/pihole
        cp "$SCRIPT_DIR/pihole.toml" /etc/pihole/pihole.toml
        chown pihole:pihole /etc/pihole/pihole.toml
        chmod 644 /etc/pihole/pihole.toml

        # Run the official installer
        curl -sSL https://install.pi-hole.net | bash /dev/stdin --unattended

        # Update gravity (blocklists)
        pihole -g
    fi

    # Set Pi-hole web password
    if [[ -n "${PIHOLE_PW:-}" ]]; then
        info "Setting Pi-hole password from PIHOLE_PW env var..."
        pihole setpassword "$PIHOLE_PW"
    else
        info "Set the Pi-hole admin password:"
        pihole -a -p
    fi

    # Make sure Pi-hole is running on port 8080 (avoid conflict with SoundMaker on port 80)
    if [[ -f /etc/pihole/pihole.toml ]]; then
        info "Pi-hole web interface will be available on port 8080."
    fi

    systemctl enable pihole-FTL
    systemctl restart pihole-FTL
    info "Pi-hole installed and running."
}

install_pihole

# ---------------------------------------------------------------------------
# 4. Caddy (HTTPS reverse proxy)
# ---------------------------------------------------------------------------

install_caddy() {
    if command -v caddy &> /dev/null; then
        info "Caddy is already installed, skipping."
    else
        info "Installing Caddy..."
        apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https > /dev/null
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list > /dev/null
        apt-get update -qq
        apt-get install -y -qq caddy > /dev/null
    fi

    local domain="${SOUNDMAKER_DOMAIN:-}"
    if [[ -z "$domain" ]]; then
        read -rp "[SoundMaker] Enter your public domain for HTTPS (e.g. soundmaker.duckdns.org): " domain
        if [[ -z "$domain" ]]; then
            warn "No domain provided. Caddy will not be configured."
            warn "You can manually edit /etc/caddy/Caddyfile later."
            return
        fi
    fi

    info "Writing Caddyfile for $domain → localhost:8081 ..."
    cat > /etc/caddy/Caddyfile <<CADDYEOF
$domain {
    reverse_proxy 127.0.0.1:8081
}
CADDYEOF

    systemctl enable caddy
    systemctl reload caddy 2>/dev/null || systemctl restart caddy
    info "Caddy running — HTTPS on $domain → backend on :8081"
}

install_caddy

# ---------------------------------------------------------------------------
# 5. Raspotify (Spotify Connect)
# ---------------------------------------------------------------------------

install_raspotify() {
    if command -v raspotify &> /dev/null || systemctl list-unit-files | grep -q raspotify; then
        info "Raspotify is already installed, skipping."
    else
        info "Installing raspotify..."
        curl -sL https://dtcooper.github.io/raspotify/install.sh | sh -s -- -y 2>/dev/null || {
            warn "Raspotify install script failed. Trying apt..."
            curl -sSL https://dtcooper.github.io/raspotify/key.asc | gpg --dearmor -o /usr/share/keyrings/raspotify-archive-keyring.gpg 2>/dev/null
            echo "deb [signed-by=/usr/share/keyrings/raspotify-archive-keyring.gpg] https://dtcooper.github.io/raspotify raspotify main" | tee /etc/apt/sources.list.d/raspotify.list > /dev/null
            apt-get update -qq
            apt-get install -y -qq raspotify > /dev/null
        }
    fi

    if [[ -f /etc/raspotify/conf ]]; then
        if ! grep -q 'LIBRESPOT_NAME' /etc/raspotify/conf; then
            info "Configuring raspotify device name..."
            echo 'LIBRESPOT_NAME="SoundMaker"' >> /etc/raspotify/conf
        fi
    elif [[ -f /etc/default/raspotify ]]; then
        if ! grep -q 'DEVICE_NAME' /etc/default/raspotify; then
            info "Configuring raspotify device name..."
            echo 'DEVICE_NAME="SoundMaker"' >> /etc/default/raspotify
        fi
    fi

    systemctl enable raspotify
    systemctl restart raspotify
    info "Raspotify installed — Pi appears as 'SoundMaker' on Spotify."
}

install_raspotify

# ---------------------------------------------------------------------------
# 6. Jellyfin (media server)
# ---------------------------------------------------------------------------

install_jellyfin() {
    if command -v jellyfin &> /dev/null || systemctl list-unit-files | grep -q jellyfin; then
        info "Jellyfin is already installed, skipping."
    else
        info "Installing Jellyfin media server..."
        
        # Add Jellyfin repository
        curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key | gpg --dearmor -o /usr/share/keyrings/jellyfin-archive-keyring.gpg 2>/dev/null
        
        # Determine Debian/Ubuntu codename
        local codename
        codename=$(lsb_release -c -s 2>/dev/null || echo "bookworm")
        
        echo "deb [signed-by=/usr/share/keyrings/jellyfin-archive-keyring.gpg arch=$(dpkg --print-architecture)] https://repo.jellyfin.org/debian $codename main" | tee /etc/apt/sources.list.d/jellyfin.list > /dev/null
        
        apt-get update -qq
        apt-get install -y -qq jellyfin > /dev/null
    fi

    # Cap Jellyfin's CPU so video transcoding can't overheat and crash the Pi 5.
    # The Pi 5 has 4 cores; stacked transcodes can peg all of them, drive the SoC
    # to its ~110 °C emergency-shutdown point, and cut power (causing an unclean
    # reboot). CPUQuota=200% limits Jellyfin to at most 2 cores; CPUWeight=50 makes
    # it yield to DNS / the web UI under load. A single transcode still plays fine.
    info "Applying Jellyfin CPU limit (thermal protection)..."
    mkdir -p /etc/systemd/system/jellyfin.service.d
    cat > /etc/systemd/system/jellyfin.service.d/10-cpu-limit.conf <<'CPUEOF'
# Managed by SoundMaker install_master.sh — thermal protection for the Pi 5.
# See docs/architecture.md (Jellyfin section). Adjust CPUQuota to trade
# playback smoothness against peak temperature.
[Service]
CPUQuota=200%
CPUWeight=50
CPUEOF

    systemctl daemon-reload
    systemctl enable jellyfin
    systemctl restart jellyfin

    info "Jellyfin installed (CPU-limited) — web UI at http://$(hostname).local:8096"
}

install_jellyfin

# ---------------------------------------------------------------------------
# 7. Python backend
# ---------------------------------------------------------------------------

setup_backend() {
    local backend_dir="$SCRIPT_DIR/backend"

    info "Setting up Python virtual environment..."
    python3 -m venv "$backend_dir/.venv"
    "$backend_dir/.venv/bin/pip" install --quiet --upgrade pip
    "$backend_dir/.venv/bin/pip" install --quiet -r "$backend_dir/requirements.txt"

    # Hash the SoundMaker Web UI password
    local sm_pw="${SOUNDMAKER_PW:-}"
    if [[ -z "$sm_pw" ]]; then
        read -rsp "[SoundMaker] Set a password for the Web UI: " sm_pw
        echo
        if [[ -z "$sm_pw" ]]; then
            error "Web UI password cannot be empty."
            exit 1
        fi
    fi

    info "Hashing SoundMaker Web UI password..."
    local sm_pw_hash
    sm_pw_hash=$(echo -n "$sm_pw" | "$backend_dir/.venv/bin/python3" -c "import sys, bcrypt; print(bcrypt.hashpw(sys.stdin.read().encode(), bcrypt.gensalt(rounds=12)).decode())")

    local spotify_id="${SPOTIFY_CLIENT_ID:-}"
    local spotify_secret="${SPOTIFY_CLIENT_SECRET:-}"
    if [[ -z "$spotify_id" ]]; then
        read -rp "[SoundMaker] Spotify Client ID (leave empty to skip): " spotify_id
    fi
    if [[ -n "$spotify_id" && -z "$spotify_secret" ]]; then
        read -rp "[SoundMaker] Spotify Client Secret: " spotify_secret
    fi

    info "Writing environment config to $ENV_FILE ..."
    cat > "$ENV_FILE" <<ENVEOF
SOUNDMAKER_STATE_DIR=$STATE_DIR
PIHOLE_BASE_URL=http://localhost:8080
PIHOLE_PASSWORD=${PIHOLE_PW:-changeme}
SOUNDMAKER_PASSWORD_HASH=$sm_pw_hash
SPOTIFY_CLIENT_ID=${spotify_id}
SPOTIFY_CLIENT_SECRET=${spotify_secret}
ENVEOF
    chmod 600 "$ENV_FILE"
    chown "${SUDO_USER:-pi}:${SUDO_USER:-pi}" "$ENV_FILE"

    info "Backend ready."
}

setup_backend

# ---------------------------------------------------------------------------
# 8. systemd service for the SoundMaker backend
# ---------------------------------------------------------------------------

install_service() {
    local service_file="/etc/systemd/system/soundmaker-backend.service"
    local backend_dir="$SCRIPT_DIR/backend"
    local run_user="${SUDO_USER:-pi}"

    info "Installing systemd service..."

    cat > "$service_file" <<EOF
[Unit]
Description=SoundMaker Backend
After=network-online.target pihole-FTL.service caddy.service
Wants=network-online.target

[Service]
Type=simple
User=$run_user
WorkingDirectory=$backend_dir
EnvironmentFile=$ENV_FILE
ExecStart=$backend_dir/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8081
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable soundmaker-backend.service
    systemctl restart soundmaker-backend.service

    info "soundmaker-backend.service is active."
}

install_service

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

domain="${SOUNDMAKER_DOMAIN:-$(hostname).local}"

info "============================================"
info " SoundMaker Master installation complete!"
info ""
info " Web UI (HTTPS): https://$domain"
info " Web UI (local): http://$(hostname).local:8081"
info " Pi-hole admin:  http://$(hostname).local:8080/admin"
info " Jellyfin:       http://$(hostname).local:8096"
info " Backend API:    http://127.0.0.1:8081/api/health"
info ""
info " Spotify OAuth redirect URI (add to Spotify Dashboard):"
info "   https://$domain/api/spotify/callback"
info ""
info " Remote access (Tailscale):"
info "   Run:  sudo tailscale up --ssh"
info "   Then access the UI from anywhere via Tailscale."
info ""
info " Network: port-forward 80 and 443 on your router to this Pi."
info "============================================"
