#!/usr/bin/env bash
# =============================================================================
#  mac_05_hold_session.sh
#  Keeps the job alive so the operator can drive the Mac via RustDesk.
#  Restarts the dialog-dismissal loop (each step is a separate shell).
#  Exits when the done-flag appears OR the hold timeout elapses.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 05 — holding session open for remote control"

HOLD_MINUTES_INT="${HOLD_MINUTES:-120}"
[ "$HOLD_MINUTES_INT" -gt 235 ] && HOLD_MINUTES_INT=235
DEADLINE=$(( $(date +%s) + HOLD_MINUTES_INT * 60 ))

[ -f "$STATE_DIR/connection-info.txt" ] && cat "$STATE_DIR/connection-info.txt"

log "session alive until $(date -r "$DEADLINE" '+%H:%M:%S') runner time"
log "(end: ssh cihelper@<ip> 'touch $DONE_FLAG'  or  wait for timeout)"

rm -f "$DONE_FLAG"

# restart the dialog-dismissal loop (died with step 04's shell)
start_dialog_dismissal_loop

# prevent display/system sleep during the hold session (each step is a new shell,
# so the caffeinate from step 03 died). This is the #1 fix for "loses connection
# easily" — macOS sleeps the display and drops the RustDesk connection.
pkill -f "caffeinate -dis" 2>/dev/null || true
caffeinate -d -i -s &
CAFFEINATE_PID=$!
disown 2>/dev/null || true
log "caffeinate started (PID=$CAFFEINATE_PID) — display will stay awake"

# take a periodic screenshot every 15s for debugging (if operator reports issues)
(
  mkdir -p "$STATE_DIR/screenshots"
  while true; do
    screencapture -x -C "$STATE_DIR/screenshots/hold_$(date +%Y%m%d_%H%M%S).png" 2>/dev/null || true
    sleep 15
  done
) &
HOLD_SHOT_PID=$!
disown 2>/dev/null || true
log "hold screenshot loop started (PID=$HOLD_SHOT_PID, every 15s)"

elapsed=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if [ -f "$DONE_FLAG" ]; then
    ok "done-flag detected — ending session cleanly"
    rm -f "$DONE_FLAG"
    stop_dialog_dismissal_loop
    kill "$HOLD_SHOT_PID" 2>/dev/null || true
    exit 0
  fi
  # heartbeat every 30s (GitHub kills jobs with 10+ min of no log output)
  if [ $((elapsed % 30)) -eq 0 ] && [ "$elapsed" -gt 0 ]; then
    remaining=$(( (DEADLINE - $(date +%s)) / 60 ))
    rd="OK"; port_open "$RUSTDESK_PORT" || rd="DOWN"
    log "alive — ${remaining}min left (RustDesk:$rd, touch $DONE_FLAG to end)"
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done

stop_dialog_dismissal_loop
kill "$HOLD_SHOT_PID" 2>/dev/null || true
warn "hold timeout reached ($HOLD_MINUTES_INT min) — ending session"
