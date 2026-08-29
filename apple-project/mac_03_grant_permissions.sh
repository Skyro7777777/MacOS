#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh — AUTOMATED TCC granter
#
#  Flow:
#    1. Install deps (cliclick, Pillow, displayplacer)
#    2. Set display to 1920x1080 (BEFORE grant so everything happens at final res)
#    3. Install + configure RustDesk (idempotent)
#    4. Pre-authorize screencapture + start dialog dismissal loop
#    5. Grant all 4 TCC services via sqlite3 (mac_grant_tcc.py)
#    6. Trigger + wait for replayd dialog to be dismissed
#    7. Restart RustDesk so it picks up the clean permission state
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
if ! command -v displayplacer >/dev/null 2>&1; then
  brew install displayplacer 2>&1 | tail -n1
fi

# --- 1. set display to 1920x1080 (BEFORE grant — so dialog detection works
#        at the final resolution, and RustDesk launches at 1920x1080) --------
if command -v displayplacer >/dev/null 2>&1; then
  log "setting display resolution to 1920x1080"
  # parse the persistent screen ID (note: it's "Persistent SCREEN id", not "Persistent id")
  DISP_ID="$(displayplacer list 2>/dev/null | grep -iE 'Persistent screen id:' | head -1 | sed 's/.*Persistent screen id: *//' | tr -d ' \r' || true)"
  if [ -n "$DISP_ID" ]; then
    log "found display: $DISP_ID"
    # use the exact format displayplacer suggests (with hz + color_depth + enabled)
    displayplacer "id:$DISP_ID res:1920x1080 hz:60 color_depth:7 enabled:true scaling:off origin:(0,0) degree:0" 2>&1 | while IFS= read -r line; do log "  $line"; done || true
    sleep 2
    CUR_RES="$(displayplacer list 2>/dev/null | grep -iE 'Resolution:' | head -1 | sed 's/.*Resolution: *//' | tr -d ' \r' || true)"
    if echo "$CUR_RES" | grep -q "1920x1080"; then
      ok "display set to 1920x1080"
    else
      warn "display resolution is $CUR_RES (expected 1920x1080) — may need manual change"
    fi
  else
    warn "could not find display ID — using default resolution"
  fi
fi

# --- 2. install + configure RustDesk (idempotent) ---------------------------
if [ ! -x "$RUSTDESK_BIN" ]; then
  log "installing RustDesk"
  brew install --cask rustdesk 2>&1 | tail -n2 || true
  xattr -dr com.apple.quarantine "$RUSTDESK_APP" 2>/dev/null || true
fi

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
# --- PERFORMANCE (reduces latency from ~1s to ~100ms) ---
# Use VP9 codec (better quality per byte than VP8; H264/H265 may not work on macOS)
codec-preference = 'vp9'
# Set image quality to best (less compression artifacts = faster visual response)
image-quality = 'best'
# Higher FPS = smoother cursor movement (default is 30; 60 is much more responsive)
custom-fps = '60'
# Enable hardware codec (uses Apple Silicon GPU for encoding — much faster)
enable-hwcodec = 'Y'
# Disable adaptive bitrate (ABR can cause stutter on direct-IP connections)
enable-abr = 'N'
EOF
sudo mkdir -p /var/root/Library/Preferences/com.carriez.RustDesk
sudo cp "$RUSTDESK_USER_PREFS/RustDesk.toml" "$RUSTDESK_USER_PREFS/RustDesk2.toml" \
     /var/root/Library/Preferences/com.carriez.RustDesk/ 2>/dev/null || true
ok "RustDesk configured (port=$RUSTDESK_PORT)"

# --- 3. pre-authorize screencapture + start dialog dismissal ----------------
preauthorize_screencapture
start_dialog_dismissal_loop

# --- 4. THE GRANT (pure sqlite3, no UI) -------------------------------------
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

# --- 5. trigger + wait for the replayd dialog to be dismissed ----------------
log "triggering screencapture to surface any replayd dialog..."
screencapture -x -C /tmp/apple-project/trigger_shot.png 2>/dev/null || true

log "waiting for replayd dialog to be dismissed (up to 120s)..."
dialog_gone=false
for attempt in $(seq 1 40); do
  sleep 3
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

# --- 6. restart RustDesk to pick up the clean permission state --------------
log "restarting RustDesk to pick up the clean permission state..."
pkill -9 -x RustDesk 2>/dev/null || true
sleep 3
gui_run open -a RustDesk || true
sleep 8
ok "RustDesk restarted — screen capture should now work"
take_screenshot "03_grant_success"
