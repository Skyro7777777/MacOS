#!/usr/bin/env bash
# =============================================================================
#  mac_04_start_rustdesk.sh
#  Launch RustDesk inside the runner's Aqua GUI session (so it can capture the
#  screen via WindowServer) and verify it is listening on the direct-IP port
#  21118 for incoming Tailscale connections.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 04 — launch RustDesk in GUI session + verify port $RUSTDESK_PORT"

# --- 1. make sure nothing stale is running ----------------------------------
pkill -x RustDesk 2>/dev/null || true
sleep 1

# --- 2. (re)apply the direct-IP config in case prefs got reset ---------------
gui_run "$RUSTDESK_BIN" --password "$RUSTDESK_PASSWORD" || true
gui_run "$RUSTDESK_BIN" --option direct-server=Y || true
gui_run "$RUSTDESK_BIN" --option "direct-access-port=$RUSTDESK_PORT" || true
gui_run "$RUSTDESK_BIN" --option relay-server= || true
gui_run "$RUSTDESK_BIN" --option custom-rendezvous-server= || true
gui_run "$RUSTDESK_BIN" --option api-server= || true

# --- 3. load the LaunchAgent (KeepAlive) and also open the app --------------
# LaunchAgent ensures it restarts if it crashes; open -a brings the window up.
launchctl load "/Users/$RUNNER_USER/Library/LaunchAgents/com.carriez.RustDesk_server.plist" 2>/dev/null || true
gui_run open -a RustDesk || true

# --- 4. wait for the direct-server port to come up --------------------------
log "waiting for RustDesk to listen on TCP $RUSTDESK_PORT ..."
if ! wait_for 45 port_open "$RUSTDESK_PORT"; then
  warn "RustDesk not listening on $RUSTDESK_PORT after 45s"
  warn "process list:"
  pgrep -lf RustDesk || warn "  (no RustDesk process found)"
  warn "letting the job continue — the client may still connect once RustDesk finishes booting"
else
  ok "RustDesk is listening on TCP $RUSTDESK_PORT"
  lsof -nP -iTCP:"$RUSTDESK_PORT" -sTCP:LISTEN | tail -n +1
fi

# --- 5. print the connection block ------------------------------------------
TS_IP="$(cat "$STATE_DIR/tailscale-ip" 2>/dev/null || echo UNKNOWN)"
TS_HOST="$(cat "$STATE_DIR/tailscale-hostname" 2>/dev/null || echo UNKNOWN)"
RD_ID="$(cat "$STATE_DIR/rustdesk-id" 2>/dev/null || echo UNKNOWN)"
RD_PASS="$(cat "$STATE_DIR/rustdesk-password" 2>/dev/null || echo UNKNOWN)"

cat > "$STATE_DIR/connection-info.txt" <<EOF

==============================================================================
  THE APPLE PROJECT  —  macOS 15 runner is ready for remote control
==============================================================================

  TRANSPORT ........ Tailscale (WireGuard, no relay)
  Tailscale IPv4 ... $TS_IP
  Tailscale host ... $TS_HOST

  REMOTE DESKTOP ... RustDesk direct-IP mode (NO rendezvous, NO relay server)
  RustDesk port .... $RUSTDESK_PORT  (TCP)
  RustDesk ID ...... $RD_ID
  RustDesk password  $RD_PASS

  ┌──────────────────────────────────────────────────────────────────────┐
  │  HOW TO CONNECT (Windows 11 or Android)                             │
  │                                                                     │
  │  1. Install Tailscale on your client device and sign in to the      │
  │     SAME tailnet as the auth key used in the workflow.              │
  │        Windows: https://tailscale.com/download/windows              │
  │        Android: https://tailscale.com/download/android              │
  │                                                                     │
  │  2. Install the RustDesk client (1.3+):                             │
  │        Windows: https://rustdesk.com/download                       │
  │        Android: Google Play -> "RustDesk"                           │
  │                                                                     │
  │  3. In RustDesk, set up the client for direct-IP only (optional     │
  │     but recommended so it never touches RustDesk's public servers): │
  │        Settings -> Network -> ID/Relay server -> leave BLANK.       │
  │                                                                     │
  │  4. In the RustDesk "Connect" / "ID" field type the runner's        │
  │     Tailscale IPv4 (optionally with :port):                         │
  │                                                                     │
  │        $TS_IP:21118                                                 │
  │                                                                     │
  │     (or just $TS_IP if 21118 is the default on your client)         │
  │                                                                     │
  │  5. When prompted, enter the RustDesk password:                     │
  │                                                                     │
  │        $RD_PASS                                                     │
  │                                                                     │
  │  6. You should now see & control the macOS 15 desktop.              │
  │                                                                     │
  │  WHEN DONE:  create the done-flag file to end the workflow:         │
  │        touch $DONE_FLAG                                             │
  │     (easiest: open Terminal on the Mac via RustDesk and run it,     │
  │      or use Tailscale SSH:  ssh $MAC_USER@$TS_HOST)                 │
  └──────────────────────────────────────────────────────────────────────┘

  Helper user (for SSH / password prompts): $MAC_USER
  (passwordless sudo is enabled for $MAC_USER)

==============================================================================
EOF

cat "$STATE_DIR/connection-info.txt"
ok "connection info written to $STATE_DIR/connection-info.txt"
