#!/bin/bash
# SoundMaker Installation Script
# Automates the installation of SoundMaker Internet Radio Player on Raspberry Pi

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
USERNAME="goorlavi"
APP_DIR="/opt/soundmaker"
SERVICE_NAME="soundmaker.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
LED_SERVICE_NAME="soundmaker-leds.service"
LED_SERVICE_FILE="/etc/systemd/system/${LED_SERVICE_NAME}"
BACKUP_DIR="/opt/soundmaker_backup"

# Wi-Fi Provisioning Configuration
WIFI_SSID="TopTier"
WIFI_PASSWORD="123secure@"
WIFI_INTERFACE="wlan0"
WIFI_CONNECTION_NAME="SoundMaker-TopTier"
PROVISIONING_FLAG="/etc/soundmaker/wifi_provisioned"

# Functions
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_error "Please run as root or with sudo"
        exit 1
    fi
}

check_player_file() {
    if [ ! -f "player.py" ]; then
        print_error "player.py not found in current directory"
        print_info "Please run this script from the directory containing player.py"
        exit 1
    fi
}

check_user_exists() {
    if ! id "$USERNAME" &>/dev/null; then
        print_error "User '$USERNAME' does not exist"
        print_info "Please update USERNAME variable in the script or create the user"
        exit 1
    fi
}

check_wifi_provisioned() {
    if [ -f "$PROVISIONING_FLAG" ]; then
        return 0  # Already provisioned
    else
        return 1  # Not provisioned
    fi
}

check_networkmanager_prerequisites() {
    print_info "Checking NetworkManager prerequisites..."
    
    # Check if NetworkManager is installed and running
    if ! command -v nmcli &> /dev/null; then
        print_error "NetworkManager (nmcli) is not installed"
        print_error "Wi-Fi provisioning requires NetworkManager. Please install it first."
        exit 1
    fi
    
    if ! systemctl is-active --quiet NetworkManager 2>/dev/null; then
        print_error "NetworkManager service is not running"
        print_error "Please start NetworkManager: sudo systemctl start NetworkManager"
        exit 1
    fi
    
    # Check if wlan0 interface exists
    if ! ip link show "$WIFI_INTERFACE" &> /dev/null; then
        print_error "Wi-Fi interface '$WIFI_INTERFACE' does not exist"
        print_error "Wi-Fi provisioning requires the '$WIFI_INTERFACE' interface."
        exit 1
    fi
    
    print_info "NetworkManager prerequisites check passed"
}

remove_existing_wifi_profile() {
    print_info "Checking for existing Wi-Fi profiles..."
    
    # Find and remove any existing connection with the same SSID
    EXISTING_CONN=$(nmcli -t -f NAME,802-11-wireless.ssid connection show 2>/dev/null | grep -i ":$WIFI_SSID$" | cut -d: -f1 | head -n1)
    
    if [ -n "$EXISTING_CONN" ]; then
        print_info "Removing existing Wi-Fi profile: $EXISTING_CONN"
        nmcli connection delete "$EXISTING_CONN" 2>/dev/null || true
    fi
    
    # Also check for connection with our specific name
    if nmcli connection show "$WIFI_CONNECTION_NAME" &>/dev/null; then
        print_info "Removing existing connection: $WIFI_CONNECTION_NAME"
        nmcli connection delete "$WIFI_CONNECTION_NAME" 2>/dev/null || true
    fi
    
    # Remove any netplan-generated profiles (if they exist)
    if [ -d "/etc/netplan" ]; then
        NETPLAN_FILES=$(grep -r "TopTier\|$WIFI_SSID" /etc/netplan/ 2>/dev/null | cut -d: -f1 | sort -u)
        if [ -n "$NETPLAN_FILES" ]; then
            print_warning "Found netplan configuration files that may conflict. Consider reviewing:"
            echo "$NETPLAN_FILES" | while read -r file; do
                print_warning "  - $file"
            done
        fi
    fi
}

provision_wifi() {
    print_info "Starting Wi-Fi provisioning..."
    
    # Check prerequisites (exits on failure)
    check_networkmanager_prerequisites
    
    # Remove existing profiles
    remove_existing_wifi_profile
    
    # Ensure wlan0 is managed by NetworkManager
    print_info "Ensuring $WIFI_INTERFACE is managed by NetworkManager..."
    nmcli device set "$WIFI_INTERFACE" managed yes 2>/dev/null || true
    
    # Create new Wi-Fi connection
    print_info "Creating Wi-Fi connection to '$WIFI_SSID'..."
    if ! nmcli connection add \
        type wifi \
        con-name "$WIFI_CONNECTION_NAME" \
        ifname "$WIFI_INTERFACE" \
        ssid "$WIFI_SSID" \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "$WIFI_PASSWORD" 2>/dev/null; then
        print_error "Failed to create Wi-Fi connection"
        exit 1
    fi
    
    # Enable autoconnect
    print_info "Enabling autoconnect for Wi-Fi connection..."
    nmcli connection modify "$WIFI_CONNECTION_NAME" connection.autoconnect yes
    
    # Activate connection
    print_info "Activating Wi-Fi connection..."
    if ! nmcli connection up "$WIFI_CONNECTION_NAME" 2>/dev/null; then
        print_error "Failed to activate Wi-Fi connection"
        # Clean up the connection we created
        nmcli connection delete "$WIFI_CONNECTION_NAME" 2>/dev/null || true
        exit 1
    fi
    
    # Wait for connection with timeout (30 seconds)
    print_info "Waiting for Wi-Fi connection to establish..."
    TIMEOUT=30
    ELAPSED=0
    CONNECTED=false
    
    while [ $ELAPSED -lt $TIMEOUT ]; do
        if nmcli connection show "$WIFI_CONNECTION_NAME" 2>/dev/null | grep -q "GENERAL.STATE.*activated"; then
            # Check if IP address is assigned
            if ip addr show "$WIFI_INTERFACE" 2>/dev/null | grep -q "inet "; then
                CONNECTED=true
                break
            fi
        fi
        sleep 1
        ELAPSED=$((ELAPSED + 1))
        echo -n "."
    done
    echo ""
    
    if [ "$CONNECTED" = false ]; then
        print_error "Wi-Fi connection failed to establish within timeout"
        print_error "Connection may still be in progress. Check with: nmcli connection show $WIFI_CONNECTION_NAME"
        # Don't delete the connection - it might still connect
        exit 1
    fi
    
    # Verify connectivity
    print_info "Verifying Wi-Fi connectivity..."
    CONN_STATE=$(nmcli connection show "$WIFI_CONNECTION_NAME" 2>/dev/null | grep "GENERAL.STATE" | awk '{print $2}')
    IP_ADDR=$(ip addr show "$WIFI_INTERFACE" 2>/dev/null | grep "inet " | awk '{print $2}' | head -n1)
    
    if [ -z "$IP_ADDR" ]; then
        print_error "Wi-Fi connected but no IP address assigned"
        exit 1
    fi
    
    print_info "Wi-Fi connection established successfully"
    print_info "  Connection: $WIFI_CONNECTION_NAME"
    print_info "  State: $CONN_STATE"
    print_info "  IP Address: $IP_ADDR"
    
    # Create provisioning flag
    print_info "Creating provisioning flag..."
    mkdir -p "$(dirname "$PROVISIONING_FLAG")"
    touch "$PROVISIONING_FLAG"
    print_info "Wi-Fi provisioning completed and marked as provisioned"
}

check_and_provision_wifi() {
    if check_wifi_provisioned; then
        print_info "Wi-Fi already provisioned (flag exists: $PROVISIONING_FLAG)"
        print_info "Skipping Wi-Fi provisioning"
        return 0
    fi
    
    print_info "Wi-Fi not yet provisioned - starting provisioning process"
    provision_wifi
}

handle_existing_installation() {
    print_info "Checking for existing installation..."
    
    # Check if main service exists and is running
    if systemctl list-unit-files | grep -q "^${SERVICE_NAME}"; then
        if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
            print_info "Stopping existing service..."
            systemctl stop "$SERVICE_NAME" || true
        fi
        
        print_info "Disabling existing service..."
        systemctl disable "$SERVICE_NAME" || true
    fi
    
    # Check if LED service exists and is running
    if systemctl list-unit-files | grep -q "^${LED_SERVICE_NAME}"; then
        if systemctl is-active --quiet "$LED_SERVICE_NAME" 2>/dev/null; then
            print_info "Stopping existing LED service..."
            systemctl stop "$LED_SERVICE_NAME" || true
        fi
        
        print_info "Disabling existing LED service..."
        systemctl disable "$LED_SERVICE_NAME" || true
    fi
    
    # Check if application directory exists
    if [ -d "$APP_DIR" ] && [ "$(ls -A $APP_DIR 2>/dev/null)" ]; then
        print_warning "Existing installation found at $APP_DIR"
        
        # Create backup
        print_info "Creating backup of existing installation..."
        mkdir -p "$BACKUP_DIR"
        cp -r "$APP_DIR"/* "$BACKUP_DIR/" 2>/dev/null || true
        
        # Backup service file if it exists
        if [ -f "$SERVICE_FILE" ]; then
            cp "$SERVICE_FILE" "$BACKUP_DIR/" 2>/dev/null || true
        fi
        
        # Backup logs if they exist
        if [ -d "/home/$USERNAME/.soundmaker" ]; then
            cp -r "/home/$USERNAME/.soundmaker" "$BACKUP_DIR/.soundmaker_backup" 2>/dev/null || true
        fi
        
        print_info "Backup created at $BACKUP_DIR"
        
        # Remove old files
        print_info "Removing old installation files..."
        rm -rf "$APP_DIR"/* 2>/dev/null || true
        
        # Remove old service files
        if [ -f "$SERVICE_FILE" ]; then
            rm -f "$SERVICE_FILE"
            print_info "Removed old service file"
        fi
        
        if [ -f "$LED_SERVICE_FILE" ]; then
            rm -f "$LED_SERVICE_FILE"
            print_info "Removed old LED service file"
        fi
        
        # Reload systemd
        systemctl daemon-reload || true
        
        print_info "Old installation cleaned up"
    else
        print_info "No existing installation found - performing fresh install"
    fi
}

install_mpv() {
    print_info "Checking for mpv..."
    if command -v mpv &> /dev/null; then
        print_info "mpv is already installed: $(mpv --version | head -n 1)"
    else
        print_info "Installing mpv..."
        apt-get update
        apt-get install -y mpv
        print_info "mpv installed successfully"
    fi
}

install_pulseaudio() {
    print_info "Checking for PulseAudio..."
    if command -v pulseaudio &> /dev/null; then
        print_info "PulseAudio is already installed: $(pulseaudio --version 2>/dev/null | head -n 1)"
    else
        print_info "Installing PulseAudio..."
        apt-get update
        apt-get install -y pulseaudio pulseaudio-utils
        print_info "PulseAudio installed successfully"
    fi
}

install_shairport() {
    print_info "Checking for shairport-sync..."
    if command -v shairport-sync &> /dev/null; then
        print_info "shairport-sync is already installed: $(shairport-sync -V 2>&1 | head -n 1)"
    else
        print_info "Installing shairport-sync..."
        apt-get update
        apt-get install -y shairport-sync
        print_info "shairport-sync installed successfully"
    fi
}

install_gpio_dependencies() {
    print_info "Checking for RPi.GPIO library..."
    
    # Check if python3-rpi.gpio package is installed
    if dpkg -l | grep -q "^ii.*python3-rpi.gpio"; then
        print_info "RPi.GPIO is already installed"
    else
        # Check if we're on a Raspberry Pi
        if [ -f /proc/device-tree/model ] && grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
            print_info "Installing RPi.GPIO library..."
            apt-get update
            apt-get install -y python3-rpi.gpio
            print_info "RPi.GPIO installed successfully"
        else
            print_warning "Not running on Raspberry Pi - RPi.GPIO installation skipped"
            print_warning "LED controller will not work without RPi.GPIO"
        fi
    fi
}

configure_shairport() {
    print_info "Configuring shairport-sync hooks..."
    
    SHAIRPORT_CONF="/etc/shairport-sync.conf"
    HOOK_SCRIPT="$APP_DIR/airplay_hook.sh"
    
    if [ ! -f "$HOOK_SCRIPT" ]; then
        print_warning "Hook script not found, skipping shairport-sync configuration"
        return
    fi
    
    # Backup original config if it exists (once)
    if [ -f "$SHAIRPORT_CONF" ] && [ ! -f "${SHAIRPORT_CONF}.bak" ]; then
        cp "$SHAIRPORT_CONF" "${SHAIRPORT_CONF}.bak"
        print_info "Backed up original shairport-sync.conf to ${SHAIRPORT_CONF}.bak"
    fi
    
    # Write a clean, minimal, idempotent configuration
    cat > "$SHAIRPORT_CONF" << EOF
// Minimal shairport-sync configuration generated by install.sh

general = {
    name = "SoundMaker";
    output_backend = "pa";
    wait_for_completion = "yes";
};

sessioncontrol = {
    run_this_when_a_remote_connects = "$HOOK_SCRIPT connect";
    run_this_when_a_remote_disconnects = "$HOOK_SCRIPT disconnect";
    run_this_before_play_begins = "$HOOK_SCRIPT connect";
    run_this_after_play_ends = "$HOOK_SCRIPT disconnect";
};
EOF
    print_info "Wrote clean shairport-sync.conf with PulseAudio backend and hooks"
    
    # Restart shairport-sync if it's running
    if systemctl is-active --quiet shairport-sync 2>/dev/null; then
        print_info "Restarting shairport-sync to apply configuration..."
        systemctl restart shairport-sync
    else
        print_info "Enabling and starting shairport-sync..."
        systemctl enable shairport-sync
        systemctl start shairport-sync
    fi
}

configure_shairport_pulse_override() {
    print_info "Configuring shairport-sync to use PulseAudio under user $USERNAME..."
    OVERRIDE_DIR="/etc/systemd/system/shairport-sync.service.d"
    mkdir -p "$OVERRIDE_DIR"
    cat > "$OVERRIDE_DIR/override.conf" << EOF
[Service]
User=${USERNAME}
Group=${USERNAME}
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStartPre=/bin/bash -c 'mkdir -p /run/user/1000/pulse && chown ${USERNAME}:${USERNAME} /run/user/1000/pulse'
EOF
    print_info "shairport-sync override created at $OVERRIDE_DIR/override.conf"
}

setup_directories() {
    print_info "Creating application directory..."
    mkdir -p "$APP_DIR"
    print_info "Directory created: $APP_DIR"
}

copy_files() {
    print_info "Copying SoundMaker files to $APP_DIR..."
    
    # Copy all Python modules
    for file in *.py; do
        if [ -f "$file" ]; then
            cp "$file" "$APP_DIR/"
            chmod 644 "$APP_DIR/$file"
            print_info "  Copied: $file"
        fi
    done
    
    # Make player.py and led_controller.py executable
    chmod +x "$APP_DIR/player.py"
    if [ -f "$APP_DIR/led_controller.py" ]; then
        chmod +x "$APP_DIR/led_controller.py"
    fi
    
    # Copy hook script if it exists
    if [ -f "airplay_hook.sh" ]; then
        cp airplay_hook.sh "$APP_DIR/airplay_hook.sh"
        chmod +x "$APP_DIR/airplay_hook.sh"
        print_info "  Copied: airplay_hook.sh"
    fi
    
    # Set ownership
    chown -R "$USERNAME:$USERNAME" "$APP_DIR"
    print_info "Files copied successfully"
}

create_service_file() {
    print_info "Creating systemd service file..."
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Internet Radio Player (SoundMaker)
After=network-online.target sound.target
Wants=network-online.target
Requires=network-online.target

[Service]
Type=simple
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=${APP_DIR}
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStartPre=/bin/bash -c 'mkdir -p /run/user/1000/pulse && chown -R ${USERNAME}:${USERNAME} /run/user/1000/pulse'
ExecStart=/usr/bin/python3 ${APP_DIR}/player.py
ExecStartPost=/bin/bash -c 'sleep 2 && if [ -p /tmp/soundmaker_airplay_events ]; then chown root:root /tmp/soundmaker_airplay_events 2>/dev/null || true; fi'
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
    print_info "Service file created: $SERVICE_FILE"
}

enable_service() {
    print_info "Reloading systemd daemon..."
    systemctl daemon-reload
    
    print_info "Enabling service to start on boot..."
    systemctl enable "$SERVICE_NAME"
    
    print_info "Starting service..."
    systemctl start "$SERVICE_NAME"
    
    # Wait a moment for service to start
    sleep 2
    
    # Check status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_info "Service is running successfully!"
    else
        print_warning "Service may not be running. Check status with: sudo systemctl status $SERVICE_NAME"
    fi
}

create_led_service_file() {
    print_info "Creating LED service file..."
    cat > "$LED_SERVICE_FILE" << EOF
[Unit]
Description=SoundMaker LED Status Controller
After=soundmaker.service
Wants=soundmaker.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/python3 ${APP_DIR}/led_controller.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
    print_info "LED service file created: $LED_SERVICE_FILE"
}

enable_led_service() {
    print_info "Reloading systemd daemon..."
    systemctl daemon-reload
    
    print_info "Enabling LED service to start on boot..."
    systemctl enable "$LED_SERVICE_NAME"
    
    print_info "Starting LED service..."
    systemctl start "$LED_SERVICE_NAME"
    
    # Wait a moment for service to start
    sleep 1
    
    # Check status
    if systemctl is-active --quiet "$LED_SERVICE_NAME"; then
        print_info "LED service is running successfully!"
    else
        print_warning "LED service may not be running. Check status with: sudo systemctl status $LED_SERVICE_NAME"
    fi
}

verify_installation() {
    print_info "Verifying installation..."
    
    # Check if main service is active
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_info "✓ Main service is active"
    else
        print_warning "✗ Main service is not active"
    fi
    
    # Check if LED service is active
    if systemctl is-active --quiet "$LED_SERVICE_NAME" 2>/dev/null; then
        print_info "✓ LED service is active"
    else
        print_warning "✗ LED service is not active"
    fi
    
    # Check if mpv process is running
    if pgrep -x "mpv" > /dev/null; then
        print_info "✓ mpv process is running"
    else
        print_warning "✗ mpv process not found (may take a moment to start)"
    fi
    
    # Check if files exist
    if [ -f "$APP_DIR/player.py" ]; then
        print_info "✓ Player file exists"
    else
        print_error "✗ Player file not found"
    fi
    
    # Check for LED controller
    if [ -f "$APP_DIR/led_controller.py" ]; then
        print_info "✓ LED controller file exists"
    else
        print_warning "✗ LED controller file not found"
    fi
    
    # Check for all required modules
    REQUIRED_FILES=("config.py" "logger_setup.py" "stream_player.py" "audio_controller.py" "airplay_manager.py" "utils.py")
    for file in "${REQUIRED_FILES[@]}"; do
        if [ -f "$APP_DIR/$file" ]; then
            print_info "✓ $file exists"
        else
            print_warning "✗ $file not found"
        fi
    done
}

print_summary() {
    echo ""
    print_info "Installation complete!"
    echo ""
    
    if [ -d "$BACKUP_DIR" ] && [ "$(ls -A $BACKUP_DIR 2>/dev/null)" ]; then
        print_info "Backup of old installation saved at: $BACKUP_DIR"
        print_info "You can remove it after confirming everything works: sudo rm -rf $BACKUP_DIR"
        echo ""
    fi
    
    echo "Useful commands:"
    echo "  Check status:  sudo systemctl status $SERVICE_NAME"
    echo "  View logs:     sudo journalctl -u $SERVICE_NAME -f"
    echo "  Restart:       sudo systemctl restart $SERVICE_NAME"
    echo "  Stop:          sudo systemctl stop $SERVICE_NAME"
    echo ""
}

# Main installation process
main() {
    echo "=========================================="
    echo "  SoundMaker Installation Script"
    echo "=========================================="
    echo ""
    
    check_root
    check_and_provision_wifi
    check_player_file
    check_user_exists
    
    # Handle existing installation first
    handle_existing_installation
    echo ""
    
    print_info "Starting installation..."
    echo ""
    
    install_mpv
    install_pulseaudio
    install_shairport
    install_gpio_dependencies
    setup_directories
    copy_files
    configure_shairport
    configure_shairport_pulse_override
    create_service_file
    enable_service
    create_led_service_file
    enable_led_service
    
    print_info "Restarting shairport-sync and SoundMaker to apply PulseAudio settings..."
    systemctl daemon-reload
    systemctl restart shairport-sync
    systemctl restart "$SERVICE_NAME"
    systemctl restart "$LED_SERVICE_NAME" || true
    
    echo ""
    verify_installation
    print_summary
}

# Run main function
main

