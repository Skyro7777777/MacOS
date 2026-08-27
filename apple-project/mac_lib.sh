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

# --- Sequoia ScreenCapture pre-authorization (THE GOLD FIX) ------------------
# macOS 15 (Sequoia) shows a blocking dialog the first time a process tries to
# capture the screen:
#   "[app] is requesting to bypass the system private window picker and
#    directly access your screen and audio."
#   [Allow]  [Open System Settings]
#
# This dialog is owned by /usr/libexec/replayd and blocks EVERYTHING — including
# our moondream2 AI agent which needs screencapture to see the screen.
#
# The fix: pre-authorize the capturing binaries by writing them into
#   ~/Library/Group Containers/group.com.apple.replayd/ScreenCaptureApprovals.plist
# with far-future date values, then SIGHUP replayd so it re-reads the plist.
# After this, screencapture works WITHOUT any dialog.
#
# CRITICAL: macOS 15.3+ requires 5 keys, not 2. Without kScreenCapturePrivacyHintDate
# and kScreenCapturePrivacyHintPolicy, replayd shows the dialog EVERY TIME
# (known macOS bug: if kScreenCapturePrivacyHintDate is unset/epoch, it never
# updates and always alerts).
#
# We authorize: /bin/bash (our shell), /usr/bin/screencapture (the CLI),
# and the RustDesk binary (so it can capture too).

preauthorize_screencapture() {
  local sca_dir="$HOME/Library/Group Containers/group.com.apple.replayd"
  local sca_plist="$sca_dir/ScreenCaptureApprovals.plist"
  mkdir -p "$sca_dir" 2>/dev/null || true

  log "🔐 pre-authorizing screencapture in ScreenCaptureApprovals.plist"

  # Write the Python script to a temp file (avoids heredoc-in-function issues).
  local py_script="/tmp/preauth_screencapture.py"
  cat > "$py_script" <<'PYEOF'
import plistlib, os, datetime

plist_path = os.path.expanduser("~/Library/Group Containers/group.com.apple.replayd/ScreenCaptureApprovals.plist")
os.makedirs(os.path.dirname(plist_path), exist_ok=True)

data = {}
if os.path.exists(plist_path):
    try:
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)
    except Exception:
        data = {}

far_future = datetime.datetime(2099, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)

bins_to_authorize = ["/bin/bash", "/usr/bin/screencapture"]
rustdesk = "/Applications/RustDesk.app/Contents/MacOS/RustDesk"
if os.path.exists(rustdesk):
    bins_to_authorize.append(rustdesk)

# CRITICAL: macOS 15.3+ requires 5 keys, not 2. Without kScreenCapturePrivacyHintPolicy
# and kScreenCapturePrivacyHintDate, replayd shows the dialog EVERY TIME (known macOS bug:
# if kScreenCapturePrivacyHintDate is unset/epoch, it never updates and always alerts).
for b in bins_to_authorize:
    data[b] = {
        "kScreenCaptureApprovalLastAlerted": far_future,
        "kScreenCaptureApprovalLastUsed": far_future,
        "kScreenCapturePrivacyHintDate": far_future,
        "kScreenCapturePrivacyHintPolicy": 7776000,  # 90 days in seconds
        "kScreenCaptureAlertableUsageCount": 0,
    }

with open(plist_path, "wb") as f:
    plistlib.dump(data, f)

print(f"  authorized {len(bins_to_authorize)} binaries (5 keys each) in {plist_path}")
PYEOF

  # Run the Python script; if it fails, fall back to `defaults write`
  if ! python3 "$py_script" 2>/dev/null; then
    warn "  plistlib approach failed — falling back to defaults write"
    for bin in /bin/bash /usr/bin/screencapture "$RUSTDESK_BIN"; do
      defaults write "$sca_plist" "$bin" -dict \
        kScreenCaptureApprovalLastAlerted -date "2099-01-01 00:00:00 +0000" \
        kScreenCaptureApprovalLastUsed     -date "2099-01-01 00:00:00 +0000" \
        kScreenCapturePrivacyHintDate      -date "2099-01-01 00:00:00 +0000" \
        kScreenCapturePrivacyHintPolicy    7776000 \
        kScreenCaptureAlertableUsageCount  0 2>/dev/null || true
    done
  fi
  rm -f "$py_script"

  # SIGHUP replayd so it re-reads the plist
  sudo killall -HUP replayd 2>/dev/null || true
  # also flush cfprefsd so the defaults cache is invalidated
  sudo killall -u "$USER" cfprefsd 2>/dev/null || true
  sleep 1
  ok "🔐 screencapture pre-authorized (replayd reloaded, 5 keys per binary)"
}

# --- Sequoia privacy-dialog auto-dismissal -----------------------------------
# macOS 15 (Sequoia) shows several modal dialogs that block RustDesk from
# sending screen frames to the client (causing "waiting for image" forever):
#
#   1. "Allow RustDesk to find devices on local networks?"  [system, AX-invisible]
#      -> Needs "Allow" (right button). Pre-granted via TCC.db Local Network,
#         but this loop is the safety net.
#
#   2. "[app] is requesting to bypass the system private window picker..." [replayd]
#      -> Needs "Allow". Pre-suppressed via preauthorize_screencapture plist,
#         but this loop is the safety net.
#
#   3. RustDesk's own "Accept incoming connection from <user>?" [RustDesk app]
#      -> Needs "Accept". Pre-suppressed by allow-* options in RustDesk2.toml,
#         but this loop is the safety net.
#
# CRITICAL DESIGN RULES (learned from the "waiting for image" bug):
#   * NEVER click "Cancel" or "Don't Allow" -- on RustDesk's incoming-connection
#     dialog, "Cancel" REJECTS the user's connection (the #1 cause of stuck sessions).
#   * NEVER click a coordinate grid -- it randomly hits "Don't Allow" / "Cancel"
#     and interferes with the operator's mouse once they connect.
#   * DO click "Accept", "Allow", "Later", "Not Now" via osascript (these are
#     safe -- they never reject a connection or deny a permission).
#   * For AX-invisible SYSTEM dialogs (macOS 15.4+), click ONE precise position
#     for "Allow" (right button of centered dialog) -- but ONLY when a system
#     dialog process is detected, to avoid random clicking.

DIALOG_DISMISS_PID=""
export DIALOG_DISMISS_PID

# System dialog processes that indicate an AX-invisible dialog is on screen
# (on macOS 15.4+ these hide their buttons from System Events)
_SYSTEM_DIALOG_PROCS="UserAccessAgent|CoreServicesUIAgent|nesessionmanager|usernotificationsd|loginwindow"

start_dialog_dismissal_loop() {
  # don't start twice in the same shell
  if [ -n "$DIALOG_DISMISS_PID" ] && kill -0 "$DIALOG_DISMISS_PID" 2>/dev/null; then
    return 0
  fi
  (
    while true; do
      # --- Method 1: osascript -- click safe buttons by NAME -----------------
      # Works for: RustDesk "Accept", "Allow" on macOS <15.4, "Later", "Not Now"
      # Does NOT click "Cancel" or "Don't Allow" (those reject connections/perms)
      osascript -e '
        try
          tell application "System Events"
            repeat with p in (every process whose background only is false)
              repeat with w in (windows of p)
                try
                  repeat with b in (every button of w)
                    try
                      set bName to name of b as text
                      if bName starts with "Allow" then
                        click b
                        return "dismissed:" & bName & " in " & (name of p as text)
                      end if
                      if bName is "Accept" then
                        click b
                        return "dismissed:" & bName & " in " & (name of p as text)
                      end if
                      if bName is "Later" then
                        click b
                        return "dismissed:" & bName & " in " & (name of p as text)
                      end if
                      if bName is "Not Now" then
                        click b
                        return "dismissed:" & bName & " in " & (name of p as text)
                      end if
                    end try
                  end repeat
                end try
              end repeat
            end repeat
          end tell
        end try
      ' 2>/dev/null || true

      # --- Method 2: cliclick -- ONE precise click for AX-invisible dialogs --
      # Only fires when a known system-dialog process is frontmost, to avoid
      # random clicking when the operator is controlling the desktop.
      # The "Allow" button on a centered system dialog is the RIGHT button,
      # roughly 60% from the left edge of the dialog (~612,400 on 1024x768).
      if command -v cliclick >/dev/null 2>&1; then
        front_proc="$(osascript -e 'tell application "System Events" to return name of first application process whose frontmost is true' 2>/dev/null || echo '')"
        if echo "$front_proc" | grep -qE "$_SYSTEM_DIALOG_PROCS"; then
          # System dialog is frontmost -- click "Allow" (right button)
          cliclick c:612,400 2>/dev/null || true
          sleep 0.5
          cliclick c:612,430 2>/dev/null || true
        fi
      fi
      sleep 3
    done
  ) &
  DIALOG_DISMISS_PID=$!
  disown 2>/dev/null || true
  log "dialog-dismissal loop started (PID=$DIALOG_DISMISS_PID, interval=3s)"
  log "  clicks: Allow, Accept, Later, Not Now (NEVER Cancel / Don't Allow)"
}

stop_dialog_dismissal_loop() {
  if [ -n "$DIALOG_DISMISS_PID" ]; then
    kill "$DIALOG_DISMISS_PID" 2>/dev/null || true
    wait "$DIALOG_DISMISS_PID" 2>/dev/null || true
    DIALOG_DISMISS_PID=""
    log "dialog-dismissal loop stopped"
  fi
}
