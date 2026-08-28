#!/usr/bin/env bash
# =============================================================================
#  mac_lib.sh — shared helpers for The Apple Project.
#  Source me:   source "$(dirname "$0")/mac_lib.sh"
# =============================================================================
set -o pipefail

# --- pretty logging ---------------------------------------------------------
log()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
ok()   { printf '[ OK ] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }
err()  { printf '[FAIL] %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# --- runner identity + paths ------------------------------------------------
RUNNER_USER="${RUNNER_USER:-runner}"
MAC_USER="${MAC_USER:-cihelper}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${STATE_DIR:-/tmp/apple-project}"
mkdir -p "$STATE_DIR"; chmod 1777 "$STATE_DIR"
DONE_FLAG="$STATE_DIR/remote-done"
export RUNNER_USER MAC_USER PROJECT_ROOT STATE_DIR DONE_FLAG

# --- require a secret env var -----------------------------------------------
require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    die "Required env var $name is empty. Add it as a GitHub repo Secret."
  fi
  return 0  # explicitly return 0 so set -e doesn't kill the caller
}

# --- run as the GUI user (inside the Aqua session) --------------------------
gui_run() {
  sudo -u "$RUNNER_USER" env HOME="/Users/$RUNNER_USER" USER="$RUNNER_USER" LOGNAME="$RUNNER_USER" "$@"
}

# --- is a TCP port listening? -----------------------------------------------
port_open() { lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; }

# --- wait until a predicate is true, with timeout (seconds) -----------------
wait_for() {
  local timeout="$1"; shift; local elapsed=0
  until "$@"; do
    sleep 1; elapsed=$((elapsed + 1))
    [ "$elapsed" -ge "$timeout" ] && return 1
  done; return 0
}

# --- RustDesk + TCC constants -----------------------------------------------
RUSTDESK_APP="/Applications/RustDesk.app"
RUSTDESK_BIN="$RUSTDESK_APP/Contents/MacOS/RustDesk"
RUSTDESK_BUNDLE="com.carriez.rustdesk"          # MUST be lowercase (matches codesign)
RUSTDESK_PREFS_DIR="/Users/$RUNNER_USER/Library/Preferences/com.carriez.RustDesk"
RUSTDESK_PORT="21118"
TCC_DB="/Library/Application Support/com.apple.TCC/TCC.db"
export RUSTDESK_APP RUSTDESK_BIN RUSTDESK_BUNDLE RUSTDESK_PREFS_DIR RUSTDESK_PORT TCC_DB

# --- take a single screenshot (for debugging) -------------------------------
# screencapture inherits bash's Screen Recording TCC permission.
take_screenshot() {
  local label="${1:-shot}"
  mkdir -p "$STATE_DIR/screenshots"
  local ts; ts="$(date +%Y%m%d_%H%M%S)"
  screencapture -x -C "$STATE_DIR/screenshots/${ts}_${label}.png" 2>/dev/null || true
}

# =============================================================================
#  Sequoia ScreenCapture pre-authorization
#  Writes far-future dates to ScreenCaptureApprovals.plist to suppress the
#  replayd "bypass window picker" dialog. Best-effort — the dialog-dismissal
#  loop (below) is the reliable fallback.
# =============================================================================
preauthorize_screencapture() {
  local sca_dir="$HOME/Library/Group Containers/group.com.apple.replayd"
  local sca_plist="$sca_dir/ScreenCaptureApprovals.plist"
  local sys_dir="/Library/Group Containers/group.com.apple.replayd"
  sudo mkdir -p "$sca_dir" "$sys_dir" 2>/dev/null || true

  local bins=("/bin/bash" "/usr/bin/screencapture" "/usr/bin/osascript" "$RUSTDESK_BIN")
  command -v cliclick >/dev/null 2>&1 && bins+=("$(command -v cliclick)")

  # Write plist (user + system) as root — TCC-protected on 15.7
  for plist in "$sca_plist" "$sys_dir/ScreenCaptureApprovals.plist"; do
    for bin in "${bins[@]}"; do
      sudo defaults write "$plist" "$bin" -date "2099-01-01 00:00:00 +0000" 2>/dev/null || true
    done
  done
  sudo killall -HUP replayd 2>/dev/null || true
  sudo killall -HUP cfprefsd 2>/dev/null || true
  ok "screencapture pre-authorized (${#bins[@]} binaries, user+system plist)"
}

# =============================================================================
#  Dialog auto-dismissal loop (RESOLUTION-INDEPENDENT)
#
#  Scans the screen for the macOS accent-blue "Allow" button (the replayd
#  "bypass window picker" dialog) and clicks its center. Works at ANY
#  resolution (1024x768, 1920x1080, etc.) by scanning the center region.
#
#  ALSO clicks named buttons via osascript: Accept, Allow, Later, Not Now.
#  NEVER clicks Cancel / Don't Allow (those reject connections + deny perms).
# =============================================================================
DIALOG_DISMISS_PID=""
export DIALOG_DISMISS_PID

# Find + click the blue "Allow" button by scanning the screen center.
# Returns 0 if a button was found + clicked, 1 if not.
# OPTIMIZED: samples a small region (not the full screen) for speed.
click_blue_allow_button() {
  command -v python3 >/dev/null 2>&1 || return 1
  command -v cliclick >/dev/null 2>&1 || return 1
  local shot="/tmp/_dialog_scan.png"
  screencapture -x -C "$shot" 2>/dev/null || return 1
  local result
  result="$(python3 -c "
from PIL import Image
im = Image.open('$shot').convert('RGB')
w, h = im.size
cx, cy = w//2, h//2
blue = []
for y in range(max(0,cy-80), min(h,cy+80)):
    for x in range(max(0,cx-300), min(w,cx+300), 2):
        r,g,b = im.getpixel((x,y))
        if r<40 and 100<g<170 and b>230:
            blue.append((x,y))
if len(blue) < 30:
    print('NONE')
else:
    from collections import Counter
    yc = Counter(p[1] for p in blue)
    btn_rows = {y for y,c in yc.items() if c > 15}
    if not btn_rows:
        print('NONE')
    else:
        bp = [p for p in blue if p[1] in btn_rows]
        bxs = [p[0] for p in bp]
        bys = [p[1] for p in bp]
        if max(bxs)-min(bxs) > 80:
            print(f'{min(bxs)},{min(bys)},{max(bxs)},{max(bys)}')
        else:
            print('NONE')
" 2>/dev/null)"
  rm -f "$shot"
  if [ -n "$result" ] && [ "$result" != "NONE" ]; then
    # result = x1,y1,x2,y2 (button bounding box)
    local x1 y1 x2 y2 cx cy left_x right_x
    IFS=',' read -r x1 y1 x2 y2 <<< "$result"
    cx=$(( (x1 + x2) / 2 ))
    cy=$(( (y1 + y2) / 2 ))
    left_x=$(( x1 + (x2-x1)/6 ))
    right_x=$(( x1 + (x2-x1)*5/6 ))
    # Click MULTIPLE positions: left, center, right (center may be white text)
    cliclick c:"$left_x","$cy" 2>/dev/null || true
    sleep 0.3
    cliclick c:"$cx","$cy" 2>/dev/null || true
    sleep 0.3
    cliclick c:"$right_x","$cy" 2>/dev/null || true
    return 0
  fi
  return 1
}

start_dialog_dismissal_loop() {
  [ -n "$DIALOG_DISMISS_PID" ] && kill -0 "$DIALOG_DISMISS_PID" 2>/dev/null && return 0
  (
    while true; do
      # Method 1: osascript — click safe buttons by NAME
      # (Accept, Allow, Later, Not Now — NEVER Cancel / Don't Allow)
      osascript -e '
        try
          tell application "System Events"
            repeat with p in (every process whose background only is false)
              repeat with w in (windows of p)
                try
                  repeat with b in (every button of w)
                    try
                      set n to name of b as text
                      if n starts with "Allow" or n is "Accept" or n is "Later" or n is "Not Now" then
                        click b
                        return "clicked:" & n
                      end if
                    end try
                  end repeat
                end try
              end repeat
            end repeat
          end tell
        end try
      ' 2>/dev/null || true

      # Method 2: pixel scan — find + click the blue "Allow" button
      # (resolution-independent: scans screen center for macOS accent blue)
      click_blue_allow_button

      sleep 1
    done
  ) &
  DIALOG_DISMISS_PID=$!
  disown 2>/dev/null || true
  log "dialog-dismissal loop started (PID=$DIALOG_DISMISS_PID, interval=1s, multi-click)"
}

stop_dialog_dismissal_loop() {
  [ -n "$DIALOG_DISMISS_PID" ] && kill "$DIALOG_DISMISS_PID" 2>/dev/null || true
  [ -n "$DIALOG_DISMISS_PID" ] && wait "$DIALOG_DISMISS_PID" 2>/dev/null || true
  DIALOG_DISMISS_PID=""
}
