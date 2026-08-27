#!/usr/bin/env bash
# =============================================================================
#  mac_04_start_rustdesk.sh  —  simplified: just verify RustDesk is listening
#  RustDesk was already launched in step 03 (web remote). This step just:
#    1. Loads the launchd plists (if RustDesk was killed)
#    2. Verifies port 21118 is listening
#    3. Prints the connection info
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 04 — verify RustDesk is listening on port $RUSTDESK_PORT"

# --- restart the dialog-dismissal loop (step 03's died with its shell) -------
# This covers the gap between step 03 and step 05 — if RustDesk triggers the
# replayd "bypass window picker" dialog when it starts capturing, this loop
# will click "Allow" automatically.
start_dialog_dismissal_loop

# --- 0. enable Remote Login (SSH) for done-flag fallback --------------------
sudo launchctl bootstrap system /System/Library/LaunchDaemons/ssh.plist 2>/dev/null || {
  sudo launchctl enable system/com.openssh.sshd 2>/dev/null || true
  sudo launchctl kickstart -k system/com.openssh.sshd 2>/dev/null || true
}
sudo launchctl enable system/com.openssh.sshd 2>/dev/null || true

# --- 1. make sure RustDesk is running (relaunch if killed) ------------------
if ! pgrep -x RustDesk >/dev/null 2>&1; then
  log "RustDesk not running — relaunching"
  gui_run open -a RustDesk || true
  sleep 5
fi

# --- 2. check port 21118 ----------------------------------------------------
log "checking if RustDesk is listening on TCP $RUSTDESK_PORT ..."
if wait_for 30 port_open "$RUSTDESK_PORT"; then
  ok "RustDesk is listening on TCP $RUSTDESK_PORT"
  lsof -nP -iTCP:"$RUSTDESK_PORT" -sTCP:LISTEN 2>/dev/null | tail -n +1
else
  warn "RustDesk NOT listening on $RUSTDESK_PORT"
  warn "(you may need to grant permissions via the web remote first)"
  warn "(the web remote from step 03 may still be open — use it to grant permissions)"
fi

# --- 3. print connection info -----------------------------------------------
TS_IP="$(cat "$STATE_DIR/tailscale-ip" 2>/dev/null || echo UNKNOWN)"
TS_HOST="$(cat "$STATE_DIR/tailscale-hostname" 2>/dev/null || echo UNKNOWN)"
RD_ID="$(cat "$STATE_DIR/rustdesk-id" 2>/dev/null || echo UNKNOWN)"
RD_PASS="$(cat "$STATE_DIR/rustdesk-password" 2>/dev/null || echo UNKNOWN)"

cat > "$STATE_DIR/connection-info.txt" <<EOF

==============================================================================
  THE APPLE PROJECT  —  macOS 15 runner
==============================================================================

  TRANSPORT ........ Tailscale (WireGuard, no relay)
  Tailscale IPv4 ... $TS_IP
  Tailscale host ... $TS_HOST

  WEB REMOTE ....... http://$TS_IP:8080
    (click-to-control in your browser — no RustDesk client needed)
    (use this if RustDesk permissions aren't granted yet)

  RUSTDESK ......... direct-IP mode (NO rendezvous, NO relay)
  RustDesk port .... $RUSTDESK_PORT  (TCP)
  RustDesk ID ...... $RD_ID
  RustDesk password  $RD_PASS
    (connect via RustDesk client to $TS_IP:$RUSTDESK_PORT)

  SSH .............. ssh cihelper@$TS_IP
    (password from MAC_USER_PASSWORD secret)

  Helper user ...... $MAC_USER
  Helper password .. (from MAC_USER_PASSWORD secret)

==============================================================================
EOF

cat "$STATE_DIR/connection-info.txt"
ok "connection info written to $STATE_DIR/connection-info.txt"
