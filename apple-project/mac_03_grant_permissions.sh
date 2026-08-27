#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh — AUTOMATED TCC granter (Phase 1)
#
#  Grants Screen Recording + Accessibility + Input Monitoring + Local Network
#  to RustDesk by writing directly to the system TCC.db (SIP is off on the
#  GitHub macos-15 runner). No clicking, no AI, no human.
#
#  Flow:
#    1. Install deps (cliclick, Pillow)
#    2. Install + configure RustDesk (idempotent)
#    3. Pre-authorize screencapture (suppress replayd dialog)
#    4. Grant all 4 TCC services via sqlite3 (mac_grant_tcc.py)
#    5. Trigger screencapture to surface the replayd dialog
#    6. Wait for the dialog-dismissal loop to click "Allow"
#    7. Restart RustDesk so it picks up the clean permission state
#       (clears the pink "Permissions" banner)
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — automated TCC permission granter"
require_env MAC_USER_PASSWORD
require_env RUSTDESK_PASSWORD

# --- 0. deps ---------------------------------------------------------------
if ! command -v cliclick >/dev/null 2>&1; then
  brew install cliclick 2>&1 | tail -n1
fi
if ! python3 -c "import PIL" 2>/dev/null; then
  pip3 install Pillow 2>&1 | tail -n1 || true
fi

# --- 1. install + configure RustDesk (idempotent) ---------------------------
if [ ! -x "$RUSTDESK_BIN" ]; then
  log "installing RustDesk"
  brew install --cask rustdesk 2>&1 | tail -n2 || true
  xattr -dr com.apple.quarantine "$RUSTDESK_APP" 2>/dev/null || true
fi

# write direct-IP config (plaintext; RustDesk re-encrypts on save)
RUSTDESK_USER_PREFS="$RUSTDESK_PREFS_DIR"
sudo -u "$RUNNER_USER" mkdir -p "$RUSTDESK_USER_PREFS"
RUSTDESK_ID="${RUSTDESK_ID:-$(date +%s | tail -c 9)}"
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
ok "RustDesk configured (id=$RUSTDESK_ID, port=$RUSTDESK_PORT)"

# --- 2. pre-authorize screencapture + start dialog dismissal ----------------
preauthorize_screencapture
start_dialog_dismissal_loop

# --- 3. THE GRANT (pure sqlite3, no UI) -------------------------------------
log "running mac_grant_tcc.py ..."
set +e
python3 "$PROJECT_ROOT/mac_grant_tcc.py" > "$STATE_DIR/grant_output.log" 2>&1
GRANT_RC=$?
set -e
cat "$STATE_DIR/grant_output.log"

if [ "$GRANT_RC" -ne 0 ]; then
  take_screenshot "03_grant_failed"
  die "automated granter failed (rc=$GRANT_RC)"
fi

ok "GRANT SUCCEEDED — 4 services in TCC.db"

# --- 4. trigger + wait for the replayd dialog to be dismissed ----------------
# The preauthorization plist may not suppress the dialog immediately.
# We trigger it (screencapture) + wait for the dialog-dismissal loop to click
# "Allow" (up to 120s). Only THEN do we restart RustDesk — so it launches into
# a clean state (TCC granted + replayd approved) and doesn't cache "no perm".
log "triggering screencapture to surface any replayd dialog..."
screencapture -x -C /tmp/apple-project/trigger_shot.png 2>/dev/null || true

log "waiting for replayd dialog to be dismissed (up to 120s)..."
dialog_gone=false
for attempt in $(seq 1 40); do
  sleep 3
  # check if the blue Allow button is gone (scan screen center)
  if ! click_blue_allow_button 2>/dev/null; then
    ok "dialog dismissed (or never appeared) — screen clear!"
    dialog_gone=true
    break
  fi
  log "  attempt $attempt: dialog still present — waiting..."
done

if [ "$dialog_gone" = "false" ]; then
  warn "replayd dialog still present after 120s — clicking Allow manually..."
  click_blue_allow_button || true
  sleep 3
fi
take_screenshot "03_after_dialog_click"

# --- 5. restart RustDesk to pick up the clean permission state --------------
# RustDesk caches its permission check at launch. If it launched before the
# dialog was dismissed, it cached "no Screen Recording" -> pink banner forever.
# Restarting NOW (after TCC grant + replayd approval) clears the pink banner.
log "restarting RustDesk to pick up the clean permission state..."
pkill -9 -x RustDesk 2>/dev/null || true
sleep 3
gui_run open -a RustDesk || true
sleep 8
ok "RustDesk restarted — screen capture should now work"
take_screenshot "03_grant_success"

# keep the dialog-dismissal loop running for step 05 (each step is a new shell,
# so it dies when this script exits — step 05 restarts it)
log "dialog-dismissal loop will be restarted in step 05"
