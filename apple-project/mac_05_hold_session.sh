#!/usr/bin/env bash
# =============================================================================
#  mac_05_hold_session.sh
#  Keep the GitHub Actions job alive so the operator can drive the macOS 15
#  desktop over Tailscale + RustDesk.  Exits when EITHER:
#     - the done-flag file appears ($DONE_FLAG), or
#     - the hold timeout (HOLD_MINUTES) elapses.
#  Also heartbeats every 30s so the GitHub Actions log stays alive and the
#  operator can see how long is left.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 05 — holding session open for remote control"

HOLD_MINUTES_INT="${HOLD_MINUTES:-120}"
# cap at the workflow timeout to avoid a race where we outlive the job
if [ "$HOLD_MINUTES_INT" -gt 235 ]; then HOLD_MINUTES_INT=235; fi
DEADLINE=$(( $(date +%s) + HOLD_MINUTES_INT * 60 ))

# show the connection block again for convenience
[ -f "$STATE_DIR/connection-info.txt" ] && cat "$STATE_DIR/connection-info.txt"

log "session will stay alive until $(date -r "$DEADLINE" '+%H:%M:%S') local runner time"
log "(or until you create the done-flag:  touch $DONE_FLAG)"

# remove any stale flag
rm -f "$DONE_FLAG"

# --- restart the dialog-dismissal loop for the hold session ----------------
# Each workflow step runs in a separate shell, so the loop from step 03 died
# when step 03 exited. We restart it here so "Accept" / "Allow" dialogs are
# auto-clicked while the operator is connected.
# CRITICAL: this loop clicks ONLY "Accept", "Allow", "Later", "Not Now" —
# it NEVER clicks "Cancel" or "Don't Allow" (which would reject the connection).
start_dialog_dismissal_loop

# Also take a periodic screenshot (every 30s) so we can see the desktop state
# in the artifact if the operator reports an issue.
SCREENSHOT_INTERVAL=30 start_screenshot_loop

elapsed=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if [ -f "$DONE_FLAG" ]; then
    ok "done-flag detected — ending session cleanly"
    rm -f "$DONE_FLAG"
    stop_dialog_dismissal_loop
    stop_screenshot_loop
    exit 0
  fi
  # heartbeat every 30s (GitHub kills jobs that go 10+ min with no log output)
  if [ $((elapsed % 30)) -eq 0 ] && [ "$elapsed" -gt 0 ]; then
    remaining=$(( (DEADLINE - $(date +%s)) / 60 ))
    # also check RustDesk is still listening
    if port_open "$RUSTDESK_PORT"; then
      log "still alive — ${remaining} min remaining  (RustDesk :$RUSTDESK_PORT OK, touch $DONE_FLAG to finish)"
    else
      warn "still alive — ${remaining} min remaining  (RustDesk NOT listening! — may need restart)"
    fi
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done

stop_dialog_dismissal_loop
stop_screenshot_loop
warn "hold timeout reached ($HOLD_MINUTES_INT min) — ending session"
exit 0
