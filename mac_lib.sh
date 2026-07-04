#!/usr/bin/env bash
# =============================================================================
#  mac_lib.sh — shared helpers for The_Apple_Project scripts.
#  Source me:   source "$(dirname "$0")/mac_lib.sh"
# =============================================================================
set -o pipefail

# --- pretty logging ---------------------------------------------------------
if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'
  C_BLU=$'\033[34m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_BLU=""; C_DIM=""; C_RST=""
fi

log()  { printf '%s[%s]%s %s\n' "$C_BLU" "$(date +%H:%M:%S)" "$C_RST" "$*"; }
ok()   { printf '%s[ OK ]%s %s\n' "$C_GRN" "$C_RST" "$*"; }
warn() { printf '%s[WARN]%s %s\n' "$C_YEL" "$C_RST" "$*"; }
err()  { printf '%s[FAIL]%s %s\n' "$C_RED" "$C_RST" "$*" >&2; }
die()  { err "$*"; exit 1; }

# --- runner identity --------------------------------------------------------
RUNNER_USER="${RUNNER_USER:-runner}"            # the user that owns the Aqua session
RUNNER_UID="$(id -u "$RUNNER_USER" 2>/dev/null || echo 501)"
export RUNNER_USER RUNNER_UID

# helper user (created by mac_00_setup_user.sh) — used for password prompts
MAC_USER="${MAC_USER:-cihelper}"
export MAC_USER

# paths
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${STATE_DIR:-/tmp/apple-project}"
mkdir -p "$STATE_DIR"
# Make STATE_DIR world-writable (1777) so BOTH the runner user (RustDesk,
# AppleScript) AND the cihelper SSH user can touch the done-flag file.
# Without this, `ssh cihelper@... 'touch /tmp/apple-project/remote-done'`
# fails with "Permission denied".
chmod 1777 "$STATE_DIR"
export PROJECT_ROOT STATE_DIR

# the file whose existence ends the hold loop in mac_05_hold_session.sh
DONE_FLAG="$STATE_DIR/remote-done"
export DONE_FLAG

# --- require secret ---------------------------------------------------------
require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    die "Required environment variable $name is empty. Add it as a GitHub repo Secret."
  fi
}

# --- run a command as the GUI user (runner) inside the Aqua session --------
# Usage: gui_run <command...>
#
# The GHA workflow already runs as $RUNNER_USER inside the runner's Aqua
# login session, so a process spawned here can talk to WindowServer.  We use
# `sudo -u` (not `launchctl asuser`) because the latter runs as root and
# leaves $HOME pointing at /var/root — which would send RustDesk's prefs to
# the wrong directory.  sudo -u + explicit HOME keeps everything under
# /Users/$RUNNER_USER and in the GUI session.
gui_run() {
  sudo -u "$RUNNER_USER" \
       env HOME="/Users/$RUNNER_USER" USER="$RUNNER_USER" \
       LOGNAME="$RUNNER_USER" "$@"
}

# --- is a TCP port listening? ----------------------------------------------
port_open() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN
}

# --- wait until a predicate is true, with timeout (seconds) ----------------
wait_for() {
  local timeout="$1"; shift
  local elapsed=0
  until "$@"; do
    sleep 1; elapsed=$((elapsed + 1))
    if [ "$elapsed" -ge "$timeout" ]; then return 1; fi
  done
  return 0
}

# --- macOS 15 Sequoia deep-link URLs for privacy panes ---------------------
#   verified for System Settings on macOS 15 (Sequoia)
URL_SCREEN_CAPTURE="x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture"
URL_ACCESSIBILITY="x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility"
URL_INPUT_MONITORING="x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ListenEvent"
URL_FULL_DISK="x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_AllFiles"
export URL_SCREEN_CAPTURE URL_ACCESSIBILITY URL_INPUT_MONITORING URL_FULL_DISK

# --- RustDesk constants -----------------------------------------------------
RUSTDESK_APP="/Applications/RustDesk.app"
RUSTDESK_BIN="$RUSTDESK_APP/Contents/MacOS/RustDesk"
RUSTDESK_BUNDLE="com.carriez.RustDesk"
RUSTDESK_PREFS_DIR="/Users/$RUNNER_USER/Library/Preferences/com.carriez.RustDesk"
RUSTDESK_PORT="21118"
export RUSTDESK_APP RUSTDESK_BIN RUSTDESK_BUNDLE RUSTDESK_PREFS_DIR RUSTDESK_PORT

# --- TCC service names ------------------------------------------------------
TCC_SCREEN_CAPTURE="kTCCServiceScreenCapture"
TCC_ACCESSIBILITY="kTCCServiceAccessibility"
TCC_INPUT_MONITORING="kTCCServiceListenEvent"
TCC_SYSTEM_DB="/Library/Application Support/com.apple.TCC/TCC.db"
export TCC_SCREEN_CAPTURE TCC_ACCESSIBILITY TCC_INPUT_MONITORING TCC_SYSTEM_DB

# --- screenshot capture ------------------------------------------------------
# screencapture inherits bash's Screen Recording TCC permission (the "responsible
# process" model attributes child processes to bash, which is pre-granted on the
# GHA macos-15 runner).  We capture periodic + labeled screenshots into a shared
# directory so they can be uploaded as a GitHub Actions artifact for debugging.

SCREENSHOT_DIR="$STATE_DIR/screenshots"
SCREENSHOT_INTERVAL="${SCREENSHOT_INTERVAL:-5}"   # seconds between loop shots
SCREENSHOT_LOOP_PID=""
export SCREENSHOT_DIR SCREENSHOT_INTERVAL

# Take a single timestamped screenshot with a descriptive label.
# Usage: take_screenshot "after_rustdesk_install"
take_screenshot() {
  local label="${1:-shot}"
  mkdir -p "$SCREENSHOT_DIR"
  local ts; ts="$(date +%Y%m%d_%H%M%S)"
  local path="$SCREENSHOT_DIR/${ts}_${label}.png"
  # -x no sound, -C include cursor
  screencapture -x -C "$path" 2>/dev/null || true
  log "📸 screenshot: ${ts}_${label}.png"
}

# Start a background screenshot loop for the current step.  The loop runs as a
# child of THIS shell, so it inherits bash's Screen Recording permission.  It
# dies automatically when the step's shell exits — call start_screenshot_loop
# again at the top of the next step if you want continuous capture.
start_screenshot_loop() {
  mkdir -p "$SCREENSHOT_DIR"
  # don't start twice in the same shell
  if [ -n "$SCREENSHOT_LOOP_PID" ] && kill -0 "$SCREENSHOT_LOOP_PID" 2>/dev/null; then
    return 0
  fi
  # background subshell — dies with the parent shell
  (
    while true; do
      ts="$(date +%Y%m%d_%H%M%S)"
      screencapture -x -C "$SCREENSHOT_DIR/loop_${ts}.png" 2>/dev/null || true
      sleep "$SCREENSHOT_INTERVAL"
    done
  ) &
  SCREENSHOT_LOOP_PID=$!
  disown 2>/dev/null || true
  log "📸 screenshot loop started (PID=$SCREENSHOT_LOOP_PID, interval=${SCREENSHOT_INTERVAL}s)"
}

# Stop the background screenshot loop (called at the end of a step).
stop_screenshot_loop() {
  if [ -n "$SCREENSHOT_LOOP_PID" ]; then
    kill "$SCREENSHOT_LOOP_PID" 2>/dev/null || true
    wait "$SCREENSHOT_LOOP_PID" 2>/dev/null || true
    SCREENSHOT_LOOP_PID=""
    log "📸 screenshot loop stopped"
  fi
}
