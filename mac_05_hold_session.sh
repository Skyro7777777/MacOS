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

elapsed=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if [ -f "$DONE_FLAG" ]; then
    ok "done-flag detected — ending session cleanly"
    rm -f "$DONE_FLAG"
    exit 0
  fi
  # heartbeat every 30s (GitHub kills jobs that go 10+ min with no log output)
  if [ $((elapsed % 30)) -eq 0 ] && [ "$elapsed" -gt 0 ]; then
    remaining=$(( (DEADLINE - $(date +%s)) / 60 ))
    log "still alive — ${remaining} min remaining  (touch $DONE_FLAG to finish)"
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done

warn "hold timeout reached ($HOLD_MINUTES_INT min) — ending session"
exit 0
