#!/bin/bash
#
# macOS GitHub Actions Runner Remote Control Setup Script
# 
# This script sets up remote control for GitHub Actions macOS runners.
# It handles:
# 1. Installing Tailscale for VPN access
# 2. Setting up VNC for remote desktop
# 3. Auto-granting screen recording permissions using PyAutoGUI
#
# Key insight: bash already has screen recording permission on GitHub Actions
# macOS runners, so we can use Python scripts to automate permission dialogs.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VNC_PASSWORD="${VNC_PASSWORD:-Apple@123}"
TAILSCALE_AUTH_KEY="${TAILSCALE_AUTH_KEY:-}"
USER_PASSWORD="${USER_PASSWORD:-Apple@123}"
ADMIN_USER="${ADMIN_USER:-runner}"
MONITOR_DURATION="${MONITOR_DURATION:-300}"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on macOS
check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        log_error "This script is designed for macOS only!"
        exit 1
    fi
    log_success "Running on macOS: $(sw_vers -productVersion)"
}

# Install required packages
install_dependencies() {
    log_info "Installing dependencies..."
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        log_info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    
    # Install Python packages
    log_info "Installing Python packages..."
    pip3 install pyautogui Pillow mss opencv-python --quiet || pip install pyautogui Pillow mss opencv-python --quiet
    
    # Install system tools if needed
    # brew install tesseract # For OCR (optional)
    
    log_success "Dependencies installed"
}

# Setup Tailscale
setup_tailscale() {
    log_info "Setting up Tailscale..."
    
    if [[ -z "$TAILSCALE_AUTH_KEY" ]]; then
        log_warning "TAILSCALE_AUTH_KEY not set. Skipping Tailscale setup."
        log_warning "Set the TAILSCALE_AUTH_KEY environment variable or TAILSCALE_AUTH_KEY secret in GitHub Actions."
        return 1
    fi
    
    # Download and install Tailscale
    log_info "Downloading Tailscale..."
    curl -fsSL https://pkgs.tailscale.com/stable/Tailscale.pkg -o /tmp/Tailscale.pkg
    
    log_info "Installing Tailscale..."
    sudo installer -pkg /tmp/Tailscale.pkg -target /
    
    # Start Tailscale daemon
    log_info "Starting Tailscale..."
    sudo /Applications/Tailscale.app/Contents/MacOS/Tailscale up --authkey="$TAILSCALE_AUTH_KEY" --accept-routes --ssh
    
    # Get Tailscale IP
    TAILSCALE_IP=$(sudo /Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4 2>/dev/null || echo "")
    if [[ -n "$TAILSCALE_IP" ]]; then
        log_success "Tailscale connected! IP: $TAILSCALE_IP"
    else
        log_warning "Could not get Tailscale IP, but Tailscale may still be connecting..."
    fi
    
    log_success "Tailscale setup complete"
}

# Start permission dialog monitor in background
start_permission_monitor() {
    log_info "Starting permission dialog monitor..."
    
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Run the permission clicker in background
    python3 "$SCRIPT_DIR/permission_clicker.py" --monitor "$MONITOR_DURATION" &
    PERMISSION_MONITOR_PID=$!
    
    log_success "Permission monitor started (PID: $PERMISSION_MONITOR_PID)"
    
    # Give it a moment to initialize
    sleep 2
}

# Setup VNC (Remote Management)
setup_vnc() {
    log_info "Setting up VNC/Remote Management..."
    
    # Start permission monitor first
    start_permission_monitor
    
    # Enable Remote Management with VNC
    log_info "Enabling Remote Management..."
    
    KICKSTART="/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart"
    
    if [[ -f "$KICKSTART" ]]; then
        # Activate and configure Remote Management
        sudo "$KICKSTART" -activate -configure -access -on -privs -all -restart -agent -quiet 2>/dev/null || true
        
        # Set VNC password (legacy VNC support)
        sudo "$KICKSTART" -configure -clientopts -setvnclegacy -vnclegacy yes -setvncpw -vncpw "$VNC_PASSWORD" -quiet 2>/dev/null || true
        
        log_success "VNC configured with password"
    else
        log_error "Remote Management kickstart not found!"
        return 1
    fi
    
    # Alternative: Use Screen Sharing (built-in)
    log_info "Enabling Screen Sharing service..."
    sudo launchctl load -w /System/Library/LaunchDaemons/com.apple.screensharing.plist 2>/dev/null || true
    
    log_success "VNC setup complete"
}

# Create or update user for remote access
setup_user() {
    log_info "Setting up user for remote access..."
    
    # Check if user already exists
    if id "$ADMIN_USER" &>/dev/null; then
        log_info "User $ADMIN_USER already exists"
    else
        # Create admin user
        log_info "Creating admin user: $ADMIN_USER"
        sudo sysadminctl -addUser "$ADMIN_USER" -password "$USER_PASSWORD" -admin 2>/dev/null || true
    fi
    
    # Enable automatic login for the user (optional, helps with GUI)
    # sudo defaults write /Library/Preferences/com.apple.loginwindow autoLoginUser "$ADMIN_USER"
    
    log_success "User setup complete"
}

# Setup RustDesk as alternative remote desktop
setup_rustdesk() {
    log_info "Setting up RustDesk as alternative..."
    
    # Download RustDesk
    RUSTDESK_URL="https://github.com/rustdesk/rustdesk/releases/download/1.3.6/rustdesk-1.3.6-x86_64.dmg"
    
    log_info "Downloading RustDesk..."
    curl -fsSL "$RUSTDESK_URL" -o /tmp/rustdesk.dmg
    
    # Mount and install
    log_info "Installing RustDesk..."
    hdiutil attach /tmp/rustdesk.dmg -quiet
    sudo cp -R /Volumes/RustDesk/RustDesk.app /Applications/ 2>/dev/null || true
    hdiutil detach /Volumes/RustDesk -quiet 2>/dev/null || true
    
    # Start permission monitor for RustDesk
    start_permission_monitor
    
    # Launch RustDesk to trigger permission request
    open /Applications/RustDesk.app 2>/dev/null || true
    
    log_success "RustDesk installed"
}

# Print connection info
print_connection_info() {
    echo ""
    echo "=========================================="
    echo "       CONNECTION INFORMATION"
    echo "=========================================="
    echo ""
    
    # Get IP addresses
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "N/A")
    TAILSCALE_IP=$(/Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4 2>/dev/null || echo "N/A")
    
    echo "Local IP: $LOCAL_IP"
    echo "Tailscale IP: $TAILSCALE_IP"
    echo ""
    echo "VNC Port: 5900"
    echo "VNC Password: $VNC_PASSWORD"
    echo ""
    echo "User: $ADMIN_USER"
    echo "Password: $USER_PASSWORD"
    echo ""
    echo "To connect via VNC:"
    echo "  1. Install Tailscale on your local machine"
    echo "  2. Connect to the same Tailscale network"
    echo "  3. Use VNC viewer to connect to: $TAILSCALE_IP:5900"
    echo "  4. Enter password: $VNC_PASSWORD"
    echo ""
    echo "=========================================="
}

# Main function
main() {
    log_info "Starting macOS Remote Control Setup..."
    echo ""
    
    # Step 1: Check macOS
    check_macos
    
    # Step 2: Install dependencies
    install_dependencies
    
    # Step 3: Setup user
    setup_user
    
    # Step 4: Setup Tailscale (requires TAILSCALE_AUTH_KEY)
    setup_tailscale || true
    
    # Step 5: Setup VNC
    setup_vnc
    
    # Step 6: Print connection info
    print_connection_info
    
    log_success "Setup complete!"
    
    # Keep the permission monitor running
    log_info "Permission monitor will run for $MONITOR_DURATION seconds"
    log_info "Press Ctrl+C to stop early"
    
    # Wait for permission monitor to finish
    if [[ -n "$PERMISSION_MONITOR_PID" ]]; then
        wait "$PERMISSION_MONITOR_PID" 2>/dev/null || true
    fi
}

# Run main function
main "$@"
