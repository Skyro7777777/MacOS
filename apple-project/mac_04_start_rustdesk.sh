#!/usr/bin/env bash
# =============================================================================
#  mac_04_start_rustdesk.sh
#    1. Enable SSH (for done-flag fallback)
#    2. Restart dialog-dismissal loop (covers step 03 -> 05 gap)
#    3. Verify RustDesk is listening on port 21118
#    4. Get the ACTUAL RustDesk ID (via --get-id CLI, not the toml)
#    5. Print the connection-info block
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 04 — verify RustDesk + print connection info"

# --- 0. enable Remote Login (SSH) for done-flag fallback --------------------
sudo launchctl bootstrap system /System/Library/LaunchDaemons/ssh.plist 2>/dev/null || {
  sudo launchctl enable system/com.openssh.sshd 2>/dev/null || true
  sudo launchctl kickstart -k system/com.openssh.sshd 2>/dev/null || true
}

# --- 1. restart dialog dismissal loop (covers gap until step 05) ------------
start_dialog_dismissal_loop

# --- 2. verify RustDesk is listening ----------------------------------------
if ! pgrep -x RustDesk >/dev/null 2>&1; then
  log "RustDesk not running — relaunching"
  gui_run open -a RustDesk || true
  sleep 5
fi

log "checking RustDesk on TCP $RUSTDESK_PORT ..."
if wait_for 30 port_open "$RUSTDESK_PORT"; then
  ok "RustDesk is listening on TCP $RUSTDESK_PORT"
else
  warn "RustDesk NOT listening on $RUSTDESK_PORT"
fi

# --- 3. get the ACTUAL RustDesk ID via CLI ----------------------------------
# RustDesk --get-id prints the real ID RustDesk resolved at startup.
# This is more reliable than parsing RustDesk.toml (which may be encrypted).
sleep 3  # give RustDesk time to fully initialize
RD_ID="$(gui_run "$RUSTDESK_BIN" --get-id 2>/dev/null || echo '')"
if [ -z "$RD_ID" ]; then
  # fallback: read from the toml (may be encrypted/overwritten)
  RD_TOML="$RUSTDESK_PREFS_DIR/RustDesk.toml"
  RD_ID="$(grep -oE "^id *= *'[^']*'" "$RD_TOML" 2>/dev/null | head -1 | sed "s/^id *= *'//;s/'$//" || true)"
  if [ -z "$RD_ID" ] || [ "${RD_ID#00}" != "$RD_ID" ]; then
    RD_ID="$(cat "$STATE_DIR/rustdesk-id" 2>/dev/null || echo UNKNOWN)"
    warn "could not get RustDesk ID via CLI — using configured: $RD_ID"
  else
    ok "RustDesk ID from toml: $RD_ID"
  fi
else
  ok "actual RustDesk ID (via --get-id): $RD_ID"
fi
echo "$RD_ID" > "$STATE_DIR/rustdesk-id"

# password: always use plaintext from state file (toml may be encrypted)
RD_PASS="$(cat "$STATE_DIR/rustdesk-password" 2>/dev/null || echo UNKNOWN)"

# --- 4. print connection info -----------------------------------------------
TS_IP="$(cat "$STATE_DIR/tailscale-ip" 2>/dev/null || echo UNKNOWN)"
TS_HOST="$(cat "$STATE_DIR/tailscale-hostname" 2>/dev/null || echo UNKNOWN)"

cat > "$STATE_DIR/connection-info.txt" <<EOF

==============================================================================
  THE APPLE PROJECT  —  macOS 15 runner
==============================================================================

  TRANSPORT ........ Tailscale (WireGuard, no relay)
  Tailscale IPv4 ... $TS_IP
  Tailscale host ... $TS_HOST

  RUSTDESK ......... direct-IP mode (NO rendezvous, NO relay)
  RustDesk port .... $RUSTDESK_PORT  (TCP)
  RustDesk ID ...... $RD_ID
  RustDesk password  $RD_PASS
    (connect via RustDesk client to $TS_IP:$RUSTDESK_PORT)
    (or enter just the IP:port in RustDesk's "Enter remote ID" field)

  SSH .............. ssh cihelper@$TS_IP
    (password from MAC_USER_PASSWORD secret)
    (end session: ssh cihelper@$TS_IP 'touch /tmp/apple-project/remote-done')

  Display .......... 1920x1080
  Appearance ....... Dark mode
  Sleep ............ Disabled (caffeinate keeps display + system awake)

==============================================================================
EOF

cat "$STATE_DIR/connection-info.txt"
ok "connection info written"
