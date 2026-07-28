#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh  →  REPLACED with web remote + manual control
#
#  Instead of fighting with TCC permissions automatically (which failed 40+
#  times), we start a WEB REMOTE that lets YOU control the macOS desktop from
#  your browser. You manually:
#    1. Click the "Configure" button in RustDesk
#    2. Click the toggle in System Settings
#    3. Type the password (shown in the log)
#    4. Click "Later"
#    5. Repeat for each permission
#
#  The web remote uses screencapture (proven to work) + cliclick (proven to
#  work). No VNC, no framebuffer, no black screen. No RustDesk permissions
#  needed for the web remote itself — it uses bash's pre-granted TCC.
#
#  After you finish granting permissions, the web remote stays open so you
#  can control the desktop. RustDesk is also running (once you grant it
#  permissions, you can switch to RustDesk for real-time control).
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — web remote (manual permission granting + desktop control)"

require_env MAC_USER_PASSWORD

# --- 0. install deps --------------------------------------------------------
if ! command -v cliclick >/dev/null 2>&1; then
  log "installing cliclick"
  brew install cliclick
fi

# --- 1. install RustDesk (so you can grant it permissions via web remote) ---
if [ ! -x "$RUSTDESK_BIN" ]; then
  log "installing RustDesk"
  brew install --cask rustdesk 2>&1 | tail -n3
  xattr -dr com.apple.quarantine "$RUSTDESK_APP" 2>/dev/null || true
fi

# --- 2. write RustDesk config (direct-IP mode, no relay) --------------------
RUSTDESK_ID="${RUSTDESK_ID:-$(date +%s | tail -c 9)}"
RUSTDESK_USER_PREFS="/Users/$RUNNER_USER/Library/Preferences/com.carriez.RustDesk"
sudo -u "$RUNNER_USER" mkdir -p "$RUSTDESK_USER_PREFS"
sudo -u "$RUNNER_USER" tee "$RUSTDESK_USER_PREFS/RustDesk.toml" >/dev/null <<EOF
id = '${RUSTDESK_ID}'
password = '${RUSTDESK_PASSWORD}'
EOF
sudo -u "$RUNNER_USER" tee "$RUSTDESK_USER_PREFS/RustDesk2.toml" >/dev/null <<EOF
[options]
custom-rendezvous-server = ''
relay-server = ''
api-server = ''
direct-server = 'Y'
direct-access-port = '${RUSTDESK_PORT}'
verification-method = 'use-fixed-password'
EOF
sudo mkdir -p /var/root/Library/Preferences/com.carriez.RustDesk
sudo cp "$RUSTDESK_USER_PREFS/RustDesk.toml" "$RUSTDESK_USER_PREFS/RustDesk2.toml" \
     /var/root/Library/Preferences/com.carriez.RustDesk/
echo "$RUSTDESK_ID" > "$STATE_DIR/rustdesk-id"
echo "$RUSTDESK_PASSWORD" > "$STATE_DIR/rustdesk-password"
chmod 600 "$STATE_DIR/rustdesk-password"
ok "RustDesk installed + configured (id=$RUSTDESK_ID, port=$RUSTDESK_PORT)"

# --- 3. launch RustDesk (so it appears on screen for permission granting) ---
log "launching RustDesk on screen..."
gui_run open -a RustDesk || true
sleep 3

# --- 4. start screenshot + dialog-dismissal loops (for artifact) ------------
start_screenshot_loop
start_dialog_dismissal_loop

# --- 5. start the web remote ------------------------------------------------
log "starting web remote on port 8080..."
log ""
log "=============================================================================="
log "  WEB REMOTE IS READY"
log "=============================================================================="
log ""
log "  Open this URL in your browser:"
log "    http://$(cat "$STATE_DIR/tailscale-ip" 2>/dev/null || echo '<tailscale-ip>'):8080"
log ""
log "  You can now control the macOS desktop from your browser:"
log "    - CLICK on the screenshot to click that position"
log "    - RIGHT-CLICK for right-click"
log "    - Type text in the text box + click 'Type'"
log "    - Press Return / Tab / Escape / Cmd+Shift+G with the buttons"
log ""
log "  TO GRANT RUSTDESK PERMISSIONS MANUALLY:"
log "    1. If a dialog 'Allow RustDesk to find devices?' appears, click 'Allow'"
log "    2. Click the 'Configure' button in RustDesk's pink section"
log "    3. In System Settings, click the toggle next to 'RustDesk'"
log "    4. When the password prompt appears, type: $MAC_USER_PASSWORD"
log "    5. Click 'Modify Settings' or press Return"
log "    6. Click 'Later' (dismiss Quit & Reopen)"
log "    7. Repeat for each permission (Screen Recording, Accessibility, Input Monitoring)"
log ""
log "  After granting permissions, RustDesk will listen on port $RUSTDESK_PORT"
log "  and you can connect via RustDesk client for real-time control."
log ""
log "  The web remote stays open so you can keep controlling the desktop."
log "  The macOS user password is: $MAC_USER_PASSWORD"
log ""
log "=============================================================================="

# Run the web remote (blocks until the hold session ends)
python3 "$PROJECT_ROOT/web_remote.py" 8080 &
WEB_PID=$!
log "web remote PID=$WEB_PID"

# --- 6. wait for the hold session to end (or web remote to die) -------------
# The web remote runs in the background. We wait here so the step doesn't
# complete until the operator is done (or the workflow timeout hits).
# Step 05 (hold session) will also run after this step completes.
log "web remote is running — step 03 will stay alive until the web remote exits"
log "(the web remote runs forever; the workflow timeout-minutes will cap it)"

# Wait for the web remote process
wait $WEB_PID 2>/dev/null || true

stop_screenshot_loop
stop_dialog_dismissal_loop
ok "web remote stopped"
