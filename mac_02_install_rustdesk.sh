#!/usr/bin/env bash
# =============================================================================
#  mac_02_install_rustdesk.sh
#  Install RustDesk and configure it for DIRECT-IP-only operation:
#
#     direct-server = Y                 (host listens on TCP 21118)
#     direct-access-port = 21118
#     custom-rendezvous-server = ''     (no hbbs — no ID registration server)
#     relay-server = ''                 (no hbbr — no relay)
#     api-server = ''                   (no public API)
#     verification-method = use-fixed-password
#     password = $RUSTDESK_PASSWORD
#
#  The client (Windows 11 / Android RustDesk app) then dials:
#        <runner-tailscale-IPv4>:21118
#  directly over the Tailscale WireGuard tunnel.  No third party, no relay,
#  no rendezvous, no API key.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 02 — install + configure RustDesk (direct-IP, no relay)"

require_env RUSTDESK_PASSWORD

# --- 1. install RustDesk ----------------------------------------------------
if [ -x "$RUSTDESK_BIN" ]; then
  warn "RustDesk already installed at $RUSTDESK_APP — reinstalling fresh"
  rm -rf "$RUSTDESK_APP"
fi

# Primary path: Homebrew cask (notarized, Sequoia-compatible, auto-quarantine strip)
if command -v brew >/dev/null 2>&1; then
  log "installing via 'brew install --cask rustdesk'"
  brew install --cask rustdesk || {
    warn "brew cask install failed — falling back to direct DMG download"
    install_via_dmg
  }
else
  warn "brew not found — falling back to direct DMG download"
  install_via_dmg
fi

# strip quarantine attribute regardless of install method
xattr -dr com.apple.quarantine "$RUSTDESK_APP" 2>/dev/null || true

[ -x "$RUSTDESK_BIN" ] || die "RustDesk binary not present at $RUSTDESK_BIN after install"
ok "RustDesk installed: $($RUSTDESK_BIN --version 2>/dev/null || echo 'unknown version')"

# --- 2. write the direct-IP RustDesk2.toml ----------------------------------
# This file is read at startup.  Empty strings for the server fields = no
# rendezvous / relay / API.  direct-server=Y makes the host itself listen.
mkdir -p "$RUSTDESK_PREFS_DIR"
cat > "$RUSTDESK_PREFS_DIR/RustDesk2.toml" <<EOF
# Written by The_Apple_Project — direct-IP, relay-less configuration.
custom-rendezvous-server = ''
relay-server = ''
api-server = ''
direct-server = 'Y'
direct-access-port = '${RUSTDESK_PORT}'
verification-method = 'use-fixed-password'
EOF
ok "wrote $RUSTDESK_PREFS_DIR/RustDesk2.toml (direct-server=Y, no relay)"

# --- 3. set the fixed password + a stable ID via CLI ------------------------
# --password sets the connection password the client must type.
# --set-id gives a stable, memorable ID (purely cosmetic for direct-IP, but
# keeps RustDesk happy and lets `--get-id` return something predictable).
RUSTDESK_ID="${RUSTDESK_ID:-$(date +%s | tail -c 9)}"
log "setting RustDesk password + id=$RUSTDESK_ID"

# RustDesk CLI must run in a GUI context to write its prefs correctly;
# launchctl asuser drops us into the runner's Aqua domain.
gui_run "$RUSTDESK_BIN" --set-id "$RUSTDESK_ID" || true
gui_run "$RUSTDESK_BIN" --password "$RUSTDESK_PASSWORD" || true
gui_run "$RUSTDESK_BIN" --option direct-server=Y || true
gui_run "$RUSTDESK_BIN" --option "direct-access-port=$RUSTDESK_PORT" || true
gui_run "$RUSTDESK_BIN" --option relay-server= || true
gui_run "$RUSTDESK_BIN" --option custom-rendezvous-server= || true
gui_run "$RUSTDESK_BIN" --option api-server= || true
gui_run "$RUSTDESK_BIN" --option verification-method=use-fixed-password || true

echo "$RUSTDESK_ID" > "$STATE_DIR/rustdesk-id"
echo "$RUSTDESK_PASSWORD" > "$STATE_DIR/rustdesk-password"
chmod 600 "$STATE_DIR/rustdesk-password"
ok "RustDesk id=$RUSTDESK_ID  password=********  (stored in $STATE_DIR/rustdesk-password)"

# --- 4. macOS application firewall: allow RustDesk through ------------------
# GitHub runners ship with the firewall off, but be defensive.
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off 2>/dev/null || true
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add "$RUSTDESK_BIN" 2>/dev/null || true
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp "$RUSTDESK_BIN" 2>/dev/null || true

# --- 5. install the launchd LaunchAgent (GUI session) -----------------------
# A pure root LaunchDaemon CANNOT capture the screen — WindowServer only
# talks to processes in a user GUI session.  We install the user-level
# LaunchAgent so RustDesk starts inside the runner's Aqua login.
install_launch_agent

ok "RustDesk configured for direct-IP on port $RUSTDESK_PORT (no relay)"
log "next step will grant Screen Recording / Accessibility / Input Monitoring"
exit 0

# =============================================================================
#  helpers
# =============================================================================
install_via_dmg() {
  local dmg="/tmp/rustdesk.dmg"
  # GitHub release download URL pattern for RustDesk
  local ver="1.3.9"
  local url="https://github.com/rustdesk/rustdesk/releases/download/${ver}/rustdesk-${ver}-x86_64.dmg"
  # try arm64 first (macos-15 runner is Apple Silicon), then x86_64
  local arch_url="https://github.com/rustdesk/rustdesk/releases/download/${ver}/rustdesk-${ver}-aarch64.dmg"
  log "downloading RustDesk DMG (arm64 preferred)"
  if curl -fsSL "$arch_url" -o "$dmg" 2>/dev/null; then
    : # arm64 ok
  else
    curl -fsSL "$url" -o "$dmg" || die "could not download RustDesk DMG"
  fi
  log "mounting DMG and copying .app"
  hdiutil attach "$dmg" -nobrowse -quiet
  local vol; vol="$(hdiutil attach "$dmg" -nobrowse | grep -o '/Volumes/.*' | head -n1)"
  cp -R "$vol/RustDesk.app" /Applications/ || die "could not copy RustDesk.app"
  hdiutil detach "$vol" -quiet 2>/dev/null || true
  rm -f "$dmg"
}

install_launch_agent() {
  local label="com.carriez.RustDesk_server"
  local plist="/Users/$RUNNER_USER/Library/LaunchAgents/${label}.plist"
  mkdir -p "$(dirname "$plist")"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${RUSTDESK_BIN}</string>
    <string>--service</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Interactive</string>
</dict>
</plist>
EOF
  ok "LaunchAgent installed at $plist"
  # do NOT load it yet — mac_04_start_rustdesk.sh will, AFTER permissions are granted
}
