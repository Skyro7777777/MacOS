#!/usr/bin/env bash
# =============================================================================
#  mac_04_start_rustdesk.sh
#    1. Sets display resolution to 1920x1080 (via displayplacer)
#    2. Enables SSH (for done-flag fallback)
#    3. Restarts RustDesk if killed + verifies port 21118
#    4. Reads the ACTUAL RustDesk ID (RustDesk may generate its own on launch)
#    5. Prints the connection-info block
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 04 — set resolution + verify RustDesk + print connection info"

# --- 0. set display resolution to 1920x1080 --------------------------------
# The GitHub macos-15 runner defaults to 1024x768. Setting 1920x1080 gives a
# much more usable desktop for remote control. Uses displayplacer (brew).
if ! command -v displayplacer >/dev/null 2>&1; then
  log "installing displayplacer"
  brew install displayplacer 2>&1 | tail -n1
fi
if command -v displayplacer >/dev/null 2>&1; then
  log "setting display resolution to 1920x1080"
  # get the first display's persistent ID (|| true prevents set -e from killing
  # the script if grep finds no match)
  DISP_ID="$(displayplacer list 2>/dev/null | grep -oE 'Persistent id: [A-F0-9-]+' | head -1 | awk '{print $3}' || true)"
  if [ -n "$DISP_ID" ]; then
    displayplacer "id:$DISP_ID res:1920x1080 scaling:on origin:(0,0) degree:0" 2>/dev/null && \
      ok "display set to 1920x1080" || warn "displayplacer set failed — using default resolution"
  else
    warn "could not find display ID — using default resolution"
  fi
else
  warn "displayplacer not installed — using default resolution"
fi

# --- 1. enable Remote Login (SSH) for done-flag fallback --------------------
sudo launchctl bootstrap system /System/Library/LaunchDaemons/ssh.plist 2>/dev/null || {
  sudo launchctl enable system/com.openssh.sshd 2>/dev/null || true
  sudo launchctl kickstart -k system/com.openssh.sshd 2>/dev/null || true
}

# --- 2. make sure RustDesk is running ---------------------------------------
if ! pgrep -x RustDesk >/dev/null 2>&1; then
  log "RustDesk not running — relaunching"
  gui_run open -a RustDesk || true
  sleep 5
fi

# --- 3. verify port 21118 ---------------------------------------------------
log "checking RustDesk on TCP $RUSTDESK_PORT ..."
if wait_for 30 port_open "$RUSTDESK_PORT"; then
  ok "RustDesk is listening on TCP $RUSTDESK_PORT"
else
  warn "RustDesk NOT listening on $RUSTDESK_PORT"
fi

# --- 4. read the ACTUAL RustDesk ID + use plaintext password ---------------
# RustDesk rewrites RustDesk.toml on launch — it may encrypt the password
# (strings starting with "00" are encrypted). So we DON'T read the password
# from the toml (it would show as encrypted gibberish). Instead we always use
# the plaintext password from the state file (what we configured in step 03).
#
# For the ID: we try to read it from the toml. If it's encrypted or missing,
# we fall back to the ID we wrote (RustDesk uses the ID from the toml — if we
# wrote one, it uses ours; if the toml is encrypted, RustDesk still uses
# whatever ID it resolved at startup, which matches what we wrote).
sleep 3
RD_TOML="$RUSTDESK_PREFS_DIR/RustDesk.toml"
RD_ID="$(grep -oE "^id *= *'[^']*'" "$RD_TOML" 2>/dev/null | head -1 | sed "s/^id *= *'//;s/'$//" || true)"
# if the ID starts with "00" it's encrypted — fall back to the plaintext state file
if [ -z "$RD_ID" ] || [ "${RD_ID#00}" != "$RD_ID" ]; then
  RD_ID="$(cat "$STATE_DIR/rustdesk-id" 2>/dev/null || echo UNKNOWN)"
  log "using configured RustDesk ID: $RD_ID"
else
  ok "actual RustDesk ID from config: $RD_ID"
fi
echo "$RD_ID" > "$STATE_DIR/rustdesk-id"

# ALWAYS use the plaintext password from the state file (never the encrypted toml value)
RD_PASS="$(cat "$STATE_DIR/rustdesk-password" 2>/dev/null || echo UNKNOWN)"

# --- 5. print connection info -----------------------------------------------
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

  SSH .............. ssh cihelper@$TS_IP
    (password from MAC_USER_PASSWORD secret)
    (end session: ssh cihelper@$TS_IP 'touch /tmp/apple-project/remote-done')

  Display .......... 1920x1080

==============================================================================
EOF

cat "$STATE_DIR/connection-info.txt"
ok "connection info written to $STATE_DIR/connection-info.txt"
