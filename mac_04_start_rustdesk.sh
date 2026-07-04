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

# Restart the screenshot loop (died with step 03's shell).  This is the most
# critical step to capture — we need to see whether RustDesk actually launches,
# whether its window appears, and whether any error dialog blocks the port.
start_screenshot_loop

# Restart the dialog-dismissal loop — macOS Sequoia shows a "bypass the system
# private window picker" prompt when RustDesk tries to capture the screen.
# This loop auto-clicks "Allow" so RustDesk can actually see the desktop.
start_dialog_dismissal_loop

take_screenshot "04_start"

# --- 0. enable macOS Remote Login (SSH) so the operator can ssh in over the
#     Tailscale IP to touch the done-flag file without using the RustDesk GUI.
#     (Tailscale's own --ssh doesn't work with the brew CLI build — see
#     mac_01_install_tailscale.sh — so we enable the built-in macOS sshd instead.)
#
#     NOTE: `systemsetup -setremotelogin on` FAILS on Sequoia without Full
#     Disk Access.  Use the modern `launchctl bootstrap` API on the ssh.plist
#     LaunchDaemon instead — this works on Sequoia without extra TCC grants.
log "enabling Remote Login (sshd) for done-flag SSH fallback"
sudo launchctl bootstrap system /System/Library/LaunchDaemons/ssh.plist 2>/dev/null || {
  # if already bootstrapped, just enable it
  sudo launchctl enable system/com.openssh.sshd 2>/dev/null || true
  sudo launchctl kickstart -k system/com.openssh.sshd 2>/dev/null || true
}
sudo launchctl enable system/com.openssh.sshd 2>/dev/null || true

# --- 1. make sure nothing stale is running ----------------------------------
pkill -x RustDesk 2>/dev/null || true
sleep 1

# --- 2. config was already written by mac_02 (RustDesk.toml + RustDesk2.toml
#     with the [options] subtable).  The RustDesk CLI flags --password/--option
#     require root and refuse to run as the user, so we do NOT re-apply them
#     here.  The TOML files are the source of truth.

# --- 3. load the launchd plists via the modern bootstrap API ----------------
# `launchctl load` is deprecated on macOS 15; use `launchctl bootstrap`.
#   - LaunchDaemon (root, --service):  bootstrap into the system domain
#   - LaunchAgent (user, --server):    bootstrap into the runner's GUI domain
log "loading RustDesk LaunchDaemon (root, --service)"
sudo launchctl bootstrap system /Library/LaunchDaemons/com.carriez.RustDesk_service.plist 2>/dev/null || {
  # already bootstrapped from a prior run — kickstart it instead
  sudo launchctl kickstart -k system/com.carriez.RustDesk_service 2>/dev/null || true
}

log "loading RustDesk LaunchAgent (runner, --server, Aqua session)"
sudo launchctl bootstrap "gui/$RUNNER_UID" "/Users/$RUNNER_USER/Library/LaunchAgents/com.carriez.RustDesk_server.plist" 2>/dev/null || {
  sudo launchctl kickstart -k "gui/$RUNNER_UID/com.carriez.RustDesk_server" 2>/dev/null || true
}

# also open the GUI app so it registers with LaunchServices and shows its window
gui_run open -a RustDesk || true

# Give RustDesk time to (a) bring up its window and (b) trigger the Sequoia
# "bypass window picker" privacy prompt.  The dialog-dismissal loop (started
# above) will auto-click "Allow" on that prompt.  We wait 15s so the loop
# (2s interval) has several chances to catch and dismiss it.
log "waiting 15s for RustDesk window + Sequoia privacy dialog auto-dismiss..."
sleep 15
take_screenshot "04_after_rustdesk_launch"

# Check if any "bypass" dialog is STILL on screen after the dismissal loop
if osascript -e '
  tell application "System Events"
    repeat with p in (every process whose name is "CoreServicesUIAgent" or name is "SecurityAgent")
      repeat with w in (windows of p)
        try
          set wName to name of w
          if wName contains "bypass" or wName contains "screen" then return "STILL_PRESENT"
        end try
      end repeat
    end repeat
  end tell
  return "NO_DIALOG"
' 2>/dev/null | grep -q "STILL_PRESENT"; then
  warn "Sequoia privacy dialog still present after auto-dismiss — RustDesk may not capture the screen"
  take_screenshot "04_dialog_still_present"
else
  ok "no privacy dialog blocking (or auto-dismissed)"
fi

# --- 4. wait for the direct-server port to come up --------------------------
log "waiting for RustDesk to listen on TCP $RUSTDESK_PORT ..."
if ! wait_for 45 port_open "$RUSTDESK_PORT"; then
  warn "RustDesk not listening on $RUSTDESK_PORT after 45s"
  warn "process list:"
  pgrep -lf RustDesk || warn "  (no RustDesk process found)"
  take_screenshot "04_port_check_failed"
  warn "letting the job continue — the client may still connect once RustDesk finishes booting"
else
  ok "RustDesk is listening on TCP $RUSTDESK_PORT"
  lsof -nP -iTCP:"$RUSTDESK_PORT" -sTCP:LISTEN | tail -n +1
  take_screenshot "04_port_check_ok"
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
  │     (open Terminal on the Mac via the RustDesk session and run it,  │
  │      or enable Remote Login below and ssh cihelper@$TS_IP)          │
  └──────────────────────────────────────────────────────────────────────┘

  Helper user (for password prompts): $MAC_USER
  (passwordless sudo is enabled for $MAC_USER)

==============================================================================
EOF

cat "$STATE_DIR/connection-info.txt"
ok "connection info written to $STATE_DIR/connection-info.txt"

# Final screenshot showing the desktop state before the hold session begins.
# This is the "reality check" shot — what does the Mac actually look like?
take_screenshot "04_final_desktop_state"
stop_screenshot_loop
stop_dialog_dismissal_loop

# List how many screenshots we captured (for the log)
SHOT_COUNT="$(find "$SCREENSHOT_DIR" -name '*.png' 2>/dev/null | wc -l | tr -d ' ')"
ok "captured $SHOT_COUNT screenshots total -> $SCREENSHOT_DIR"
log "screenshots will be uploaded as a GitHub Actions artifact in the next step"
