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

elapsed=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if [ -f "$DONE_FLAG" ]; then
    ok "done-flag detected — ending session cleanly"
    rm -f "$DONE_FLAG"
    stop_dialog_dismissal_loop
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
warn "hold timeout reached ($HOLD_MINUTES_INT min) — ending session"
