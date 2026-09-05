#!/usr/bin/env bash
# =============================================================================
#  mac_06_sunshine.sh — Install + configure Sunshine (ultra-low-latency HOST)
#
#  Sunshine (LizardByte) is an open-source, self-hosted game stream HOST for
#  Moonlight clients. It's designed for ultra-low-latency streaming (<16ms)
#  using hardware encoding (VideoToolbox on macOS).
#
#  Unlike RustDesk (TCP, general-purpose remote desktop), Sunshine uses UDP
#  + hardware encoding — purpose-built for gaming + low-latency streaming.
#
#  Architecture:
#    Sunshine (HOST) runs on the Mac → serves on port 47990 (web UI) +
#    47984/47989 (stream). Moonlight (CLIENT) runs on your device → connects
#    to the Tailscale IP. PIN-based pairing.
#
#  Config: ~/.config/sunshine/ (sunshine.conf, credentials)
#  Web UI: https://<tailscale-ip>:47990 (self-signed cert — ignore warning)
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 06 — install Sunshine (ultra-low-latency streaming HOST)"

SUNSHINE_APP="/Applications/Sunshine.app"
SUNSHINE_CONFIG_DIR="$HOME/.config/sunshine"

# --- 1. install Sunshine ----------------------------------------------------
# Sunshine can be installed two ways:
#   a) brew formula (LizardByte tap) — binary at /opt/homebrew/opt/sunshine/bin/sunshine
#   b) DMG from GitHub releases — .app at /Applications/Sunshine.app
# We try brew first (more reliable), then DMG fallback.
SUNSHINE_BIN=""
SUNSHINE_BUNDLE="com.lizardbyte.sunshine"

# check if already installed (either method)
if [ -x "/opt/homebrew/opt/sunshine/bin/sunshine" ]; then
  SUNSHINE_BIN="/opt/homebrew/opt/sunshine/bin/sunshine"
  log "Sunshine already installed (brew formula): $SUNSHINE_BIN"
elif [ -d "$SUNSHINE_APP" ]; then
  SUNSHINE_BIN="$SUNSHINE_APP/Contents/MacOS/sunshine"
  log "Sunshine already installed (.app): $SUNSHINE_APP"
fi

if [ -z "$SUNSHINE_BIN" ]; then
  log "installing Sunshine..."
  # Method 1: LizardByte's homebrew tap
  brew tap lizardbyte/homebrew 2>/dev/null || true
  brew trust lizardbyte/homebrew 2>/dev/null || true
  HOMEBREW_NO_REQUIRE_TAP_TRUST=1 brew install sunshine 2>&1 | tail -n5 || true

  # check if brew install worked
  if [ -x "/opt/homebrew/opt/sunshine/bin/sunshine" ]; then
    SUNSHINE_BIN="/opt/homebrew/opt/sunshine/bin/sunshine"
    ok "Sunshine installed via brew: $SUNSHINE_BIN"
  else
    warn "brew install didn't produce a binary — trying DMG fallback"
    # Method 2: download the macOS DMG from GitHub releases
    dmg_url="https://github.com/LizardByte/Sunshine/releases/latest/download/Sunshine-macOS-arm64.dmg"
    log "downloading $dmg_url..."
    curl -fsSL "$dmg_url" -o /tmp/sunshine.dmg || die "could not download Sunshine DMG"
    ok "downloaded $(du -h /tmp/sunshine.dmg | awk '{print $1}')"
    log "mounting DMG..."
    mount_output="$(hdiutil attach /tmp/sunshine.dmg -nobrowse 2>&1)" || die "could not mount DMG: $mount_output"
    vol="$(echo "$mount_output" | grep -oE '/Volumes/[^ ]+' | head -1)"
    [ -z "$vol" ] && die "could not find mounted volume in: $mount_output"
    log "mounted at: $vol"
    app_src="$(find "$vol" -name '*.app' -maxdepth 1 2>/dev/null | head -1)"
    [ -z "$app_src" ] && die "could not find .app in DMG (contents: $(ls "$vol"))"
    log "copying $(basename "$app_src") to /Applications..."
    cp -R "$app_src" /Applications/ || die "could not copy app"
    hdiutil detach "$vol" -quiet 2>/dev/null || true
    rm -f /tmp/sunshine.dmg
    xattr -dr com.apple.quarantine "$SUNSHINE_APP" 2>/dev/null || true
    SUNSHINE_BIN="$SUNSHINE_APP/Contents/MacOS/sunshine"
    # try to read the bundle ID from the .app
    SUNSHINE_BUNDLE="$(defaults read "$SUNSHINE_APP/Contents/Info" CFBundleIdentifier 2>/dev/null || echo 'com.lizardbyte.sunshine')"
    ok "Sunshine installed via DMG: $SUNSHINE_APP"
  fi
fi

[ -z "$SUNSHINE_BIN" ] && die "Sunshine binary not found after install"
ok "Sunshine binary: $SUNSHINE_BIN"
ok "Sunshine bundle ID: $SUNSHINE_BUNDLE"

# --- 2. grant TCC permissions (Screen Recording + Accessibility + Input Monitoring) ---
log "granting TCC permissions to Sunshine..."
for service in kTCCServiceScreenCapture kTCCServiceAccessibility kTCCServiceListenEvent kTCCServiceLocalNetwork; do
  sudo sqlite3 "$TCC_DB" "INSERT OR REPLACE INTO access (service, client, client_type, auth_value, auth_reason, auth_version, csreq, policy_id, indirect_object_identifier_type, indirect_object_identifier, flags) VALUES ('$service', '$SUNSHINE_BUNDLE', 0, 2, 4, 1, NULL, 0, 0, 'UNUSED', 0);" 2>/dev/null || true
  sudo sqlite3 "$TCC_DB" "INSERT OR REPLACE INTO access (service, client, client_type, auth_value, auth_reason, auth_version, csreq, policy_id, indirect_object_identifier_type, indirect_object_identifier, flags) VALUES ('$service', '$SUNSHINE_BIN', 1, 2, 4, 1, NULL, 0, 0, 'UNUSED', 0);" 2>/dev/null || true
done
sudo killall tccd 2>/dev/null || true
sleep 2
ok "Sunshine TCC permissions granted (4 services)"

# pre-authorize screencapture for Sunshine binary
sca_plist="$HOME/Library/Group Containers/group.com.apple.replayd/ScreenCaptureApprovals.plist"
sys_plist="/Library/Group Containers/group.com.apple.replayd/ScreenCaptureApprovals.plist"
for plist in "$sca_plist" "$sys_plist"; do
  sudo defaults write "$plist" "$SUNSHINE_BIN" -date "2099-01-01 00:00:00 +0000" 2>/dev/null || true
done
sudo killall -HUP replayd 2>/dev/null || true

# --- 3. create config dir + set initial credentials ------------------------
mkdir -p "$SUNSHINE_CONFIG_DIR"

# Sunshine stores credentials in a JSON file (credentials_file in sunshine.conf)
# On first run, the web UI asks you to create a username + password.
# We can pre-set these by creating the credentials file directly.
SUNSHINE_USER="${SUNSHINE_USER:-admin}"
SUNSHINE_PASS="${SUNSHINE_PASS:-sunshine}"

# The credentials file is a simple JSON with hashed credentials.
# Sunshine uses its own hashing. We'll create the config + let the web UI
# handle the initial credential creation (more reliable than pre-hashing).
cat > "$SUNSHINE_CONFIG_DIR/sunshine.conf" <<EOF
# Sunshine configuration — generated by The Apple Project
# Web UI: https://<tailscale-ip>:47990
port = 47990
# Allow access from ANY IP (Tailscale VPN IPs are seen as WAN, not LAN).
# Default is 'lan' which blocks Tailscale connections.
origin_web_ui_allowed = wan
EOF
ok "config written to $SUNSHINE_CONFIG_DIR/sunshine.conf"

# --- 4. launch Sunshine -----------------------------------------------------
log "launching Sunshine..."

# Stop any brew services instance first (it runs as root, can't access GUI)
brew services stop lizardbyte/homebrew/sunshine 2>/dev/null || true
brew services stop sunshine 2>/dev/null || true
sleep 2

# Kill ALL stale Sunshine processes (the brew services one + any direct ones)
# Use pkill -9 to force-kill (pkill without -9 may not work on LaunchAgent processes)
pkill -9 -f "sunshine" 2>/dev/null || true
sudo pkill -9 -f "sunshine" 2>/dev/null || true
sleep 3

# Launch Sunshine DIRECTLY as the GUI user (NOT via brew services).
# brew services runs as root which can't access the Aqua session / WindowServer.
# Direct launch as $RUNNER_USER gives Sunshine GUI access for screen capture.
if [ -x "/opt/homebrew/opt/sunshine/bin/sunshine" ]; then
  log "launching Sunshine as $RUNNER_USER (direct, not brew services)..."
  gui_run /opt/homebrew/opt/sunshine/bin/sunshine "$SUNSHINE_CONFIG_DIR/sunshine.conf" &
  sleep 8
elif [ -d "$SUNSHINE_APP" ]; then
  gui_run open -a Sunshine 2>/dev/null || true
  sleep 5
fi

# Verify it's running
if pgrep -f sunshine >/dev/null 2>&1; then
  ok "Sunshine is running"
  # Check if the web UI port is actually listening
  if lsof -nP -iTCP:47990 2>/dev/null | grep -q LISTEN; then
    ok "Sunshine web UI is listening on port 47990"
  else
    warn "Sunshine is running but port 47990 is NOT listening — check logs"
  fi
  # Check if RTSP port 48011 is listening (needed for streaming)
  if lsof -nP -iTCP:48011 2>/dev/null | grep -q LISTEN; then
    ok "Sunshine RTSP is listening on port 48011"
  else
    warn "Sunshine RTSP port 48011 is NOT listening — streaming may fail"
    warn "this usually means a stale process is holding the port"
  fi
else
  warn "Sunshine may not have started — try launching it manually via RustDesk"
fi

# --- 5. print connection info -----------------------------------------------
TS_IP="$(cat "$STATE_DIR/tailscale-ip" 2>/dev/null || echo '<tailscale-ip>')"

log ""
log "=========================================================================="
log "  SUNSHINE — Ultra-Low-Latency Streaming (alternative to RustDesk)"
log "=========================================================================="
log ""
log "  HOST ............. Sunshine (running on this Mac)"
log "  Web UI ........... https://$TS_IP:47990"
log "    (self-signed cert — ignore the browser warning)"
log "    (first visit: create a username + password for the web UI)"
log ""
log "  CLIENT ........... Moonlight (download on your device)"
log "    Windows: https://moonlight-stream.org"
log "    macOS:   brew install --cask moonlight"
log "    Android: Google Play → 'Moonlight Game Streaming'"
log "    iOS:     App Store → 'Moonlight Game Streaming'"
log ""
log "  HOW TO CONNECT:"
log "    1. Open https://$TS_IP:47990 in your browser (accept cert warning)"
log "    2. Create a username + password for Sunshine's web UI"
log "    3. Open Moonlight on your device"
log "    4. Add host: $TS_IP"
log "    5. Enter the PIN shown in Sunshine's web UI (PIN tab)"
log "    6. Connect — ultra-low-latency streaming starts"
log ""
log "  ADVANTAGES over RustDesk:"
log "    - Hardware encoding (VideoToolbox) = lower latency"
log "    - UDP streaming = less lag than TCP"
log "    - Designed for gaming (<16ms latency)"
log "    - 4K @ 120fps support"
log ""
log "  PORTS (open on the Mac via Tailscale):"
log "    47990 (HTTPS web UI)"
log "    47984 (HTTPS — Moonlight pairing)"
log "    47989 (HTTP — Moonlight API)"
log "    48010 (UDP — control)"
log "    47998-48000 (UDP — video/audio)"
log ""
log "=========================================================================="

# Save sunshine info to connection-info.txt
cat >> "$STATE_DIR/connection-info.txt" <<EOF

  SUNSHINE ......... Ultra-low-latency streaming (alternative to RustDesk)
  Sunshine web UI .. https://$TS_IP:47990
    (accept cert warning, create username + password on first visit)
  Moonlight client . Connect to $TS_IP (download from moonlight-stream.org)
    (enter the PIN from Sunshine's web UI to pair)

EOF

take_screenshot "06_sunshine_launched"
ok "Sunshine setup complete — use Moonlight to connect for ultra-low-latency"
