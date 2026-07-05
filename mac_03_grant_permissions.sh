#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh
#  Grant TCC permissions to RustDesk using a DETERMINISTIC hybrid approach:
#    - Fixed coordinates for RustDesk's "Configure" button (Flutter app, no AX)
#    - osascript AX-tree for System Settings (native macOS, AX works)
#    - osascript AX for the SecurityAgent password prompt
#
#  NO AI MODEL NEEDED. This is deterministic, fast (~30s), and can't hallucinate.
#
#  The flow:
#    1. Open RustDesk → pink "Permissions" section with "Configure" button
#    2. Click "Configure" at a FIXED coordinate (always ~(210, 565) on 1024x768)
#    3. In System Settings, use osascript AX to find RustDesk's toggle → click ON
#    4. Use osascript AX to find SecurityAgent's password field → type password
#    5. Use osascript AX to click "Later" (dismiss "Quit & Reopen")
#    6. Repeat for each permission (max 3 cycles, NOT 30)
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — grant TCC permissions (deterministic: fixed coords + osascript AX)"

require_env MAC_USER_PASSWORD

# --- 0. install cliclick + start loops --------------------------------------
if ! command -v cliclick >/dev/null 2>&1; then
  log "installing cliclick"
  brew install cliclick
fi
start_screenshot_loop
start_dialog_dismissal_loop

# --- 1. write the osascript scripts to temp files (avoids heredoc issues) ---
TOGGLE_SCRIPT="/tmp/ax_click_toggle.scpt"
PASSWORD_SCRIPT="/tmp/ax_type_password.scpt"
LATER_SCRIPT="/tmp/ax_click_later.scpt"

cat > "$TOGGLE_SCRIPT" <<'SCPT'
on run argv
  set appName to item 1 of argv as text
  tell application "System Events"
    set procList to (every process whose name is "System Settings")
    if (count of procList) is 0 then return "NO_PROCESS"
    set theProc to item 1 of procList
    if (count of windows of theProc) is 0 then return "NO_WINDOW"
    set theWindow to window 1 of theProc
    set theSwitch to my findSwitchForApp(theWindow, appName)
    if theSwitch is missing value then return "NOT_FOUND"
    try
      set switchVal to value of theSwitch
      if switchVal is 1 then return "ALREADY_ON"
    end try
    try
      set value of theSwitch to 1
    on error
      click theSwitch
    end try
    return "CLICKED"
  end tell
end run

on findSwitchForApp(theElement, appName)
  tell application "System Events"
    set elemRole to missing value
    try
      set elemRole to role of theElement
    end try
    set kids to {}
    try
      set kids to UI elements of theElement
    end try
    if elemRole is in {"AXGroup", "AXRow", "AXOutlineRow", "AXLayoutArea", "AXSplitGroup"} then
      set foundSwitch to missing value
      set foundText to false
      repeat with kid in kids
        try
          set kidRole to role of kid
          if kidRole is in {"AXSwitch", "AXCheckBox", "AXCheckbox"} then
            set foundSwitch to kid
          else if kidRole is "AXStaticText" or kidRole is "AXTextField" then
            try
              if (value of kid as text) contains appName then
                set foundText to true
              end if
            end try
          end if
        end try
      end repeat
      if foundSwitch is not missing value and foundText then
        return foundSwitch
      end if
    end if
    repeat with kid in kids
      try
        set res to my findSwitchForApp(kid, appName)
        if res is not missing value then return res
      end try
    end repeat
    return missing value
  end tell
end findSwitchForApp
SCPT

cat > "$PASSWORD_SCRIPT" <<'SCPT'
on run argv
  set pw to item 1 of argv as text
  tell application "System Events"
    repeat with procName in {"SecurityAgent", "CoreServicesUIAgent"}
      set procList to (every process whose name is procName)
      if (count of procList) > 0 then
        set theProc to item 1 of procList
        repeat with w in (windows of theProc)
          try
            set pwField to missing value
            repeat with ui in (UI elements of w)
              try
                if (role of ui) is "AXSecureTextField" then
                  set pwField to ui
                  exit repeat
                end if
              end try
            end repeat
            if pwField is not missing value then
              set focused of pwField to true
              keystroke pw
              delay 0.5
              keystroke return
              return "TYPED"
            end if
          end try
        end repeat
      end if
    end repeat
    return "NO_PROMPT"
  end tell
end run
SCPT

cat > "$LATER_SCRIPT" <<'SCPT'
on run
  tell application "System Events"
    repeat with p in (every process whose name is "System Settings")
      repeat with w in (windows of p)
        try
          repeat with b in (every button of w)
            try
              set bName to name of b as text
              if bName is "Later" then
                click b
                return "CLICKED"
              end if
            end try
          end repeat
        end try
      end repeat
    end repeat
    return "NOT_FOUND"
  end tell
end run
SCPT

# --- 2. the full permission cycle (max 3 cycles, NOT 30) ---------------------
MAX_CYCLES=3

for cycle in $(seq 1 "$MAX_CYCLES"); do
  log "=== permission cycle $cycle/$MAX_CYCLES ==="
  take_screenshot "03_cycle${cycle}_start"

  # 2a. open RustDesk
  gui_run open -a RustDesk 2>/dev/null || true
  sleep 3

  # 2b. click the Configure button at the fixed coordinate
  log "clicking Configure at fixed coordinate (210, 565)"
  cliclick c:210,565 2>/dev/null || true
  sleep 4
  take_screenshot "03_cycle${cycle}_after_configure"

  # 2c. verify System Settings opened
  if ! osascript -e 'tell application "System Events" to return (count of (every process whose name is "System Settings")) > 0' 2>/dev/null | grep -q "true"; then
    warn "System Settings did not open — Configure click may have missed"
    take_screenshot "03_cycle${cycle}_settings_not_open"
    continue
  fi
  ok "  System Settings opened"

  # 2d. wait for System Settings window
  for i in $(seq 1 10); do
    if osascript -e 'tell application "System Events" to return (count of windows of (first process whose name is "System Settings"))' 2>/dev/null | grep -q "[1-9]"; then
      break
    fi
    sleep 1
  done

  # 2e. click the toggle next to RustDesk via AX
  log "finding RustDesk's toggle via AX..."
  toggle_result="$(osascript "$TOGGLE_SCRIPT" "RustDesk" 2>&1 || true)"
  case "$toggle_result" in
    CLICKED) ok "  AX: clicked toggle" ;;
    ALREADY_ON) ok "  AX: toggle already ON" ;;
    *) warn "  AX: toggle result: $toggle_result" ;;
  esac
  take_screenshot "03_cycle${cycle}_after_toggle"
  sleep 3

  # 2f. type the password via AX
  log "typing password via AX..."
  pw_result="$(osascript "$PASSWORD_SCRIPT" "$MAC_USER_PASSWORD" 2>&1 || true)"
  case "$pw_result" in
    TYPED) ok "  AX: typed password" ;;
    *) warn "  AX: password result: $pw_result" ;;
  esac
  sleep 3
  take_screenshot "03_cycle${cycle}_after_password"

  # 2g. click "Later" via AX
  log "clicking 'Later' via AX..."
  later_result="$(osascript "$LATER_SCRIPT" 2>&1 || true)"
  case "$later_result" in
    CLICKED) ok "  AX: clicked Later" ;;
    *) warn "  AX: Later result: $later_result" ;;
  esac
  sleep 2
  take_screenshot "03_cycle${cycle}_done"
done

# --- 3. final state ---------------------------------------------------------
take_screenshot "03_final_state"
stop_screenshot_loop
stop_dialog_dismissal_loop

# Check if permissions were granted
if pgrep -x SecurityAgent >/dev/null 2>&1; then
  warn "SecurityAgent still running — a password prompt may be stuck"
  warn "permissions may NOT be granted — check screenshots artifact"
  exit 1
fi

ok "permission pipeline complete (deterministic, no AI model, ~30s)"
