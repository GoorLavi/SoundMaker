#!/usr/bin/env bash
#
# SoundMaker — Master installation script
#
# Installs and configures all services on the Raspberry Pi 5 Master.
# Must be run as root.  Safe to re-run (idempotent).
#
# Usage:
#   sudo ./install_master.sh              # interactive (prompts for Pi-hole password)
#   sudo PIHOLE_PW=secret ./install_master.sh   # non-interactive

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
# 2. Pi-hole
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
# 3. Python backend
# ---------------------------------------------------------------------------

setup_backend() {
    local backend_dir="$SCRIPT_DIR/backend"

    info "Setting up Python virtual environment..."
    python3 -m venv "$backend_dir/.venv"
    "$backend_dir/.venv/bin/pip" install --quiet --upgrade pip
    "$backend_dir/.venv/bin/pip" install --quiet -r "$backend_dir/requirements.txt"

    # Write the env file that the systemd service will load.
    # The Pi-hole password is needed so the backend can authenticate to the Pi-hole API.
    info "Writing environment config to $ENV_FILE ..."
    cat > "$ENV_FILE" <<ENVEOF
SOUNDMAKER_STATE_DIR=$STATE_DIR
PIHOLE_BASE_URL=http://localhost:8080
PIHOLE_PASSWORD=${PIHOLE_PW:-changeme}
ENVEOF
    chmod 600 "$ENV_FILE"
    chown "${SUDO_USER:-pi}:${SUDO_USER:-pi}" "$ENV_FILE"

    info "Backend ready."
}

setup_backend

# ---------------------------------------------------------------------------
# 4. systemd service for the SoundMaker backend
# ---------------------------------------------------------------------------

install_service() {
    local service_file="/etc/systemd/system/soundmaker-backend.service"
    local backend_dir="$SCRIPT_DIR/backend"
    local run_user="${SUDO_USER:-pi}"

    info "Installing systemd service..."

    cat > "$service_file" <<EOF
[Unit]
Description=SoundMaker Backend
After=network-online.target pihole-FTL.service
Wants=network-online.target

[Service]
Type=simple
User=$run_user
WorkingDirectory=$backend_dir
EnvironmentFile=$ENV_FILE
ExecStart=$backend_dir/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 80
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

info "============================================"
info " SoundMaker Master installation complete!"
info ""
info " Web UI:        http://$(hostname).local"
info " Pi-hole admin: http://$(hostname).local:8080/admin"
info " Backend API:   http://$(hostname).local/api/health"
info "============================================"
