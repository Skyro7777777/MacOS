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
# RustDesk's screen capture (causing "waiting for image" forever).
#
# The fix: pre-authorize the capturing binaries by writing them into
#   ~/Library/Group Containers/group.com.apple.replayd/ScreenCaptureApprovals.plist
# with far-future date values, then kill replayd so it re-reads the plist.
#
# CRITICAL LEARNINGS (from the "waiting for image" bug on macOS 15.7.7):
#   * The plist is TCC-protected — must write as ROOT (sudo), not as the user.
#   * macOS 15.7 replayd expects a SIMPLE format: path = date string (not the
#     5-key dict that 15.3 used). We write BOTH formats to cover all versions.
#   * `killall -HUP replayd` is NOT enough — replayd doesn't re-read on HUP.
#     Must use `killall -9 replayd` (SIGKILL) so launchd restarts it fresh.
#   * Must also kill cfprefsd (both root + user) to invalidate the defaults cache.
#
# We authorize: /bin/bash (our shell), /usr/bin/screencapture (the CLI),
# /usr/bin/osascript (for AX clicks), cliclick (homebrew), and the RustDesk binary.

preauthorize_screencapture() {
  local sca_dir="$HOME/Library/Group Containers/group.com.apple.replayd"
  local sca_plist="$sca_dir/ScreenCaptureApprovals.plist"
  mkdir -p "$sca_dir" 2>/dev/null || sudo mkdir -p "$sca_dir"

  log "pre-authorizing screencapture in ScreenCaptureApprovals.plist"

  # List of binaries to pre-authorize (paths that will capture the screen)
  local bins=("/bin/bash" "/usr/bin/screencapture" "/usr/bin/osascript")
  # add cliclick if installed
  command -v cliclick >/dev/null 2>&1 && bins+=("$(command -v cliclick)")
  # add RustDesk binary
  [ -x "$RUSTDESK_BIN" ] && bins+=("$RUSTDESK_BIN")

  # Write the plist as ROOT (it's TCC-protected on 15.7).
  # Use the SIMPLE format: path = date string (proven by lapcatsoftware.com
  # for macOS 15.0-15.7). This is the format replayd expects on 15.7.
  # We pass the binary list as a JSON env var to avoid bash/python quoting issues.
  local bins_json
  bins_json=$(printf '%s\n' "${bins[@]}" | python3 -c "import json,sys; print(json.dumps([l.rstrip() for l in sys.stdin]))")
  BINS_JSON="$bins_json" SCA_PLIST="$sca_plist" sudo -E python3 <<'PYEOF'
import plistlib, os, datetime, json, shutil

plist_path = os.environ["SCA_PLIST"]
bins = json.loads(os.environ["BINS_JSON"])
os.makedirs(os.path.dirname(plist_path), exist_ok=True)

data = {}
if os.path.exists(plist_path):
    try:
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)
    except Exception:
        data = {}

far_future = datetime.datetime(2099, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
for b in bins:
    data[b] = far_future  # simple format: path = date

with open(plist_path, "wb") as f:
    plistlib.dump(data, f)
print(f"  authorized {len(bins)} binaries (simple date format) in {plist_path}")
PYEOF

  # Fallback: if plistlib failed, use `defaults write` as root
  if [ ! -f "$sca_plist" ]; then
    warn "  plistlib as root failed — trying defaults write as root"
    for bin in "${bins[@]}"; do
      sudo defaults write "$sca_plist" "$bin" -date "2099-01-01 00:00:00 +0000" 2>/dev/null || true
    done
  fi

  # ALSO write the 5-key dict format (for 15.3-15.6) as a secondary fallback.
  if sw_vers -productVersion 2>/dev/null | grep -qE '^15\.[3-6]\.'; then
    log "  macOS 15.3-15.6 detected — adding 5-key dict format too"
    for bin in "${bins[@]}"; do
      sudo defaults write "$sca_plist" "$bin" -dict \
        kScreenCaptureApprovalLastAlerted -date "2099-01-01 00:00:00 +0000" \
        kScreenCaptureApprovalLastUsed     -date "2099-01-01 00:00:00 +0000" \
        kScreenCapturePrivacyHintDate      -date "2099-01-01 00:00:00 +0000" \
        kScreenCapturePrivacyHintPolicy    7776000 \
        kScreenCaptureAlertableUsageCount  0 2>/dev/null || true
    done
  fi

  # CRITICAL: kill replayd with SIGKILL (not HUP) so launchd restarts it
  # fresh and it re-reads the plist. HUP does NOT trigger a re-read.
  sudo killall -9 replayd 2>/dev/null || true
  # Kill cfprefsd for BOTH root and user to invalidate the defaults cache
  sudo killall -9 cfprefsd 2>/dev/null || true
  sleep 2  # give launchd time to restart replayd
  # verify replayd restarted
  if pgrep -x replayd >/dev/null 2>&1; then
    ok "screencapture pre-authorized (replayd restarted, ${#bins[@]} binaries)"
  else
    warn "replayd did not restart after kill — screen capture may still prompt"
  fi
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

      # --- Method 2: detect the replayd "bypass window picker" dialog + click Allow
      # The replayd dialog (AX-invisible on macOS 15.4+) blocks screen capture
      # for EVERY app (bash/screencapture/RustDesk) — it's the #1 cause of
      # "waiting for image". Detection: check if any window's AX text contains
      # "bypass" or "requesting to" (the dialog body text). Even though the
      # BUTTONS are AX-invisible, the window text is often readable.
      # If found, click "Allow" at (511, 368) — the confirmed button position
      # on a 1024x768 screen (measured via pixel analysis of the actual dialog).
      if command -v cliclick >/dev/null 2>&1; then
        dialog_detected="$(osascript -e '
          tell application "System Events"
            try
              repeat with p in (every process whose background only is false)
                repeat with w in (windows of p)
                  try
                    set wName to name of w as text
                    if wName contains "bypass" or wName contains "requesting" or wName contains "screen and audio" then
                      return "FOUND:" & wName
                    end if
                  end try
                  try
                    repeat with ui in (UI elements of w)
                      try
                        set uiDesc to description of ui as text
                        if uiDesc contains "bypass" or uiDesc contains "requesting" or uiDesc contains "screen and audio" then
                          return "FOUND:" & uiDesc
                        end if
                      end try
                    end repeat
                  end try
                end repeat
              end repeat
            end try
          end tell
          return "NONE"
        ' 2>/dev/null || echo 'NONE')"
        if echo "$dialog_detected" | grep -q "FOUND"; then
          # replayd dialog detected — click "Allow" at the confirmed position
          cliclick c:511,368 2>/dev/null || true
          sleep 1
          # click again in case the first click missed (slightly different dialog size)
          cliclick c:511,380 2>/dev/null || true
        fi
      fi

      # --- Method 3: pixel-based detection (fallback if AX text is invisible too)
      # Check if the pixel at (511, 368) is blue (macOS accent #0A84FF) — if so,
      # the "Allow" button is present even if AX can't see it. We use a tiny
      # screencapture of just that pixel. screencapture inherits bash's Screen
      # Recording permission (the "responsible process" trick), so it works even
      # before RustDesk gets its own permission.
      if command -v cliclick >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
        # capture a 3x3 region around the Allow button position
        tmp_shot="/tmp/dialog_pixel_check.png"
        screencapture -R 510,367,3,3 -x "$tmp_shot" 2>/dev/null
        if [ -f "$tmp_shot" ]; then
          is_blue="$(python3 -c "
from PIL import Image
try:
    im = Image.open('$tmp_shot').convert('RGB')
    r,g,b = im.getpixel((1,1))
    # macOS accent blue: r<40, 100<g<170, b>230
    print('YES' if (r<40 and 100<g<170 and b>230) else 'NO')
except: print('NO')
" 2>/dev/null || echo 'NO')"
          if [ "$is_blue" = "YES" ]; then
            cliclick c:511,368 2>/dev/null || true
            sleep 1
          fi
          rm -f "$tmp_shot"
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
