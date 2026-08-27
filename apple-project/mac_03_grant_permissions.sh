#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh  —  AUTOMATED TCC granter (Phase 1)
#
#  Grants Screen Recording + Accessibility + Input Monitoring to RustDesk by
#  writing directly to the system TCC.db. NO clicking. NO AI. NO human.
#
#  This works because the GitHub macos-15 runner ships with SIP DISABLED
#  (actions/runner-images#8162), so the system TCC.db is root-writable, and the
#  pre-granted bash/hosted-compute-agent/provisioner entries all carry an EMPTY
#  csreq blob (tccd does not validate csreq on this image). We mirror that
#  pattern. Verified by mac_diagnose.py + an AX read showing RustDesk's Screen
#  Recording toggle = ON.
#
#  Fallback: if the granter fails (e.g. a future macOS bumps SIP back on), set
#  the env var FALLBACK_WEB_REMOTE=1 to start web_remote.py for manual control.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — automated TCC permission granter"

require_env MAC_USER_PASSWORD
require_env RUSTDESK_PASSWORD

# --- 0. deps ---------------------------------------------------------------
if ! command -v cliclick >/dev/null 2>&1; then
  brew install cliclick 2>&1 | tail -n2
fi

# --- 1. make sure RustDesk is installed + configured (idempotent) -----------
# (matches mac_02; kept here so step 03 is self-sufficient even if 02 was skipped)
if [ ! -x "$RUSTDESK_BIN" ]; then
  log "RustDesk not found — installing"
  brew install --cask rustdesk 2>&1 | tail -n3 || true
  xattr -dr com.apple.quarantine "$RUSTDESK_APP" 2>/dev/null || true
fi

# write/refresh the direct-IP config (plaintext; RustDesk re-encrypts on save)
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
# Pre-grant ALL permissions — no "Accept incoming connection?" dialog
allow-clipboard = 'Y'
allow-file-transfer = 'Y'
allow-file-copy = 'Y'
allow-audio = 'Y'
allow-keyboard = 'Y'
allow-mouse = 'Y'
allow-restart = 'Y'
allow-cam = 'Y'
EOF
sudo mkdir -p /var/root/Library/Preferences/com.carriez.RustDesk
sudo cp "$RUSTDESK_USER_PREFS/RustDesk.toml" "$RUSTDESK_USER_PREFS/RustDesk2.toml" \
     /var/root/Library/Preferences/com.carriez.RustDesk/ 2>/dev/null || true
echo "$RUSTDESK_ID" > "$STATE_DIR/rustdesk-id"
echo "$RUSTDESK_PASSWORD" > "$STATE_DIR/rustdesk-password"
chmod 600 "$STATE_DIR/rustdesk-password"
ok "RustDesk configured (id=$RUSTDESK_ID, port=$RUSTDESK_PORT)"

# --- 2. pre-authorize screencapture (kills the replayd "bypass picker" dialog)
preauthorize_screencapture

# --- 3. screenshot + dialog-dismissal loops (for artifact + to auto-dismiss) -
start_screenshot_loop
start_dialog_dismissal_loop

# --- 4. THE GRANT (pure sqlite3, no UI) -------------------------------------
log "running mac_grant_tcc.py ..."
set +e
python3 "$PROJECT_ROOT/mac_grant_tcc.py" > "$STATE_DIR/grant_output.log" 2>&1
GRANT_RC=$?
set -e
cat "$STATE_DIR/grant_output.log"

if [ "$GRANT_RC" -eq 0 ]; then
  ok "AUTOMATED GRANT SUCCEEDED — RustDesk has Screen Recording + Accessibility + Input Monitoring + Local Network"
  # Take a success screenshot but KEEP the dialog-dismissal loop running —
  # it's needed during the hold session (step 05) to auto-click "Accept" on
  # RustDesk's incoming-connection dialog + "Allow" on any late system dialogs.
  # Only stop the screenshot loop (we don't need per-5s screenshots during hold).
  stop_screenshot_loop
  take_screenshot "03_grant_success"
  # do NOT stop_dialog_dismissal_loop — it stays alive for step 05
  log "dialog-dismissal loop kept running for the hold session (step 05)"
  exit 0
fi

# --- 5. fallback: optional manual web remote --------------------------------
warn "automated granter exited $GRANT_RC"
if [ "${FALLBACK_WEB_REMOTE:-0}" = "1" ]; then
  log "FALLBACK_WEB_REMOTE=1 — starting web_remote.py for MANUAL control"
  log "open in your browser: http://$(cat "$STATE_DIR/tailscale-ip" 2>/dev/null || echo '<ts-ip>'):8080"
  log "grant Screen Recording / Accessibility / Input Monitoring manually,"
  log "then create the done-flag:  touch $DONE_FLAG"
  python3 "$PROJECT_ROOT/web_remote.py" 8080 &
  WEB_PID=$!
  wait $WEB_PID 2>/dev/null || true
  stop_screenshot_loop
  stop_dialog_dismissal_loop
  exit 0
fi

# no fallback — surface the failure
take_screenshot "03_grant_failed"
die "automated granter failed (rc=$GRANT_RC). Set FALLBACK_WEB_REMOTE=1 to enable manual web remote control."
