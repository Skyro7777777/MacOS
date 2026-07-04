#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh
#  Grant TCC permissions to RustDesk using RUSTDESK'S OWN "Configure" button.
#
#  THE APPROACH:
#  Drive the ENTIRE flow via osascript (AppleScript + System Events), which
#  accesses the Accessibility (AX) tree DIRECTLY — NO SCREENSHOTS NEEDED.
#  This completely avoids the Sequoia "bypass window picker" dialog that
#  blocks every screencapture call.
#
#  Flow (from the YouTube tutorial screenshots):
#    1. Bring RustDesk to focus
#    2. Find + click the "Configure" button in RustDesk's pink Permissions section
#       → RustDesk adds itself to the privacy list + opens System Settings
#    3. In System Settings, find + click the toggle next to "RustDesk"
#       → macOS shows a password prompt
#    4. Type the MAC_USER_PASSWORD (from repo secrets)
#    5. Click "Modify Settings" (or press Return)
#       → macOS grants the permission at the OS level
#    6. "Quit & Reopen" dialog → click "Later" (keep RustDesk running)
#    7. Repeat for each permission (Screen Recording, Accessibility, Input Monitoring)
#
#  WHY osascript INSTEAD of OCR/screenshots:
#    - screencapture triggers the Sequoia "bypass window picker" dialog (blocks everything)
#    - preauthorization via ScreenCaptureApprovals.plist doesn't reliably work
#    - OCR is fragile (finds wrong text, clicks wrong things)
#    - osascript accesses the AX tree directly — NO screenshots, NO dialogs
#    - bash + osascript already have Accessibility + AppleEvents on the runner
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — grant TCC permissions via osascript AX-tree (no screenshots)"

require_env MAC_USER_PASSWORD

# --- 0. start screenshot + dialog-dismissal loops (for debugging artifacts) -
# The screenshot loop may trigger the bash dialog, but the dialog-dismissal
# loop will auto-click "Allow*" so screenshots still work for the artifact.
start_screenshot_loop
start_dialog_dismissal_loop

# --- 1. install cliclick (for password typing fallback) ---------------------
if ! command -v cliclick >/dev/null 2>&1; then
  log "installing cliclick"
  brew install cliclick
fi

# --- 2. helper: bring RustDesk to front -------------------------------------
focus_rustdesk() {
  log "bringing RustDesk to front"
  osascript -e '
    tell application "System Events"
      set frontmost of (first process whose name is "RustDesk") to true
    end tell
  ' 2>/dev/null || gui_run open -a RustDesk || true
  sleep 1
}

# --- 3. helper: click a button in a given app by its AX name ----------------
# Usage: ax_click_button "RustDesk" "Configure"
#        ax_click_button "System Settings" "Later"
ax_click_button() {
  local app_name="$1" button_name="$2"
  log "  AX: looking for '$button_name' in '$app_name'"
  local result
  result="$(osascript <<APPLESCRIPT 2>&1
on run
  tell application "System Events"
    -- find the process
    set procList to (every process whose name is "$app_name")
    if (count of procList) is 0 then
      return "NO_PROCESS"
    end if
    set theProc to item 1 of procList
    if not (frontmost of theProc) then
      set frontmost of theProc to true
      delay 0.5
    end if
    -- search ALL windows for a button named "$button_name"
    repeat with w in (windows of theProc)
      try
        -- try direct buttons first
        repeat with b in (every button of w)
          try
            if (name of b as text) is "$button_name" then
              click b
              return "CLICKED"
            end if
          end try
        end repeat
        -- recursively search groups for buttons
        set foundBtn to my findButtonInGroup(w, "$button_name")
        if foundBtn is not missing value then
          click foundBtn
          return "CLICKED"
        end if
      end try
    end repeat
    return "NOT_FOUND"
  end tell
end run

on findButtonInGroup(theElem, btnName)
  tell application "System Events"
    set kids to {}
    try
      set kids to UI elements of theElem
    end try
    -- check direct buttons
    repeat with kid in kids
      try
        set kidRole to role of kid
        if kidRole is "AXButton" or kidRole is "AXCheckBox" or kidRole is "AXSwitch" then
          try
            if (name of kid as text) is btnName then
              return kid
            end if
          end try
        end if
      end try
    end repeat
    -- recurse into groups
    repeat with kid in kids
      try
        set kidRole to role of kid
        if kidRole is "AXGroup" or kidRole is "AXSplitGroup" or kidRole is "AXLayoutArea" then
          set res to my findButtonInGroup(kid, btnName)
          if res is not missing value then return res
        end if
      end try
    end repeat
    return missing value
  end tell
end findButtonInGroup
APPLESCRIPT
)"
  case "$result" in
    CLICKED) ok "  AX: clicked '$button_name' in '$app_name'"; return 0 ;;
    NO_PROCESS) warn "  AX: process '$app_name' not found"; return 1 ;;
    NOT_FOUND) warn "  AX: '$button_name' not found in '$app_name'"; return 1 ;;
    *) warn "  AX: error: $result"; return 1 ;;
  esac
}

# --- 4. helper: click the toggle next to "RustDesk" in System Settings ------
# The toggle is an AXSwitch whose parent row also contains "RustDesk" text.
ax_click_toggle_for_rustdesk() {
  log "  AX: looking for RustDesk's toggle in System Settings"
  local result
  result="$(osascript <<'APPLESCRIPT' 2>&1
on run
  tell application "System Events"
    set procList to (every process whose name is "System Settings")
    if (count of procList) is 0 then return "NO_PROCESS"
    set theProc to item 1 of procList
    if (count of windows of theProc) is 0 then return "NO_WINDOW"
    set theWindow to window 1 of theProc
    -- recursively search for a switch whose row contains "RustDesk"
    set theSwitch to my findSwitchForApp(theWindow, "RustDesk")
    if theSwitch is missing value then return "NOT_FOUND"
    -- check if already ON
    try
      set switchVal to value of theSwitch
      if switchVal is 1 then return "ALREADY_ON"
    end try
    -- click it ON
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
    -- if this is a group/row that has BOTH a switch and matching text
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
    -- recurse
    repeat with kid in kids
      try
        set res to my findSwitchForApp(kid, appName)
        if res is not missing value then return res
      end try
    end repeat
    return missing value
  end tell
end findSwitchForApp
APPLESCRIPT
)"
  case "$result" in
    CLICKED) ok "  AX: clicked RustDesk's toggle"; return 0 ;;
    ALREADY_ON) ok "  AX: RustDesk's toggle is already ON"; return 0 ;;
    NO_PROCESS) warn "  AX: System Settings not running"; return 1 ;;
    NO_WINDOW) warn "  AX: System Settings has no window"; return 1 ;;
    NOT_FOUND) warn "  AX: RustDesk toggle not found in the AX tree"; return 1 ;;
    *) warn "  AX: error: $result"; return 1 ;;
  esac
}

# --- 5. helper: handle the password prompt ----------------------------------
# After clicking the toggle, macOS shows "Privacy & Security is trying to
# modify your system settings. Enter your password to allow this."
# We find the password text field, type the password, and submit.
handle_password_prompt() {
  log "  AX: looking for password prompt"
  local result
  result="$(osascript <<APPLESCRIPT 2>&1
on run
  tell application "System Events"
    -- the password prompt can belong to "SecurityAgent" or "CoreServicesUIAgent"
    repeat with procName in {"SecurityAgent", "CoreServicesUIAgent"}
      set procList to (every process whose name is procName)
      if (count of procList) > 0 then
        set theProc to item 1 of procList
        repeat with w in (windows of theProc)
          try
            -- find the password text field (AXSecureTextField)
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
              -- type the password
              set focused of pwField to true
              keystroke "$MAC_USER_PASSWORD"
              delay 0.5
              -- press Return or click "Modify Settings" / "OK"
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
APPLESCRIPT
)"
  case "$result" in
    TYPED) ok "  AX: typed password + pressed Return"; return 0 ;;
    NO_PROMPT) warn "  AX: no password prompt found (toggle may have been already ON)"; return 0 ;;
    *) warn "  AX: password error: $result"; return 1 ;;
  esac
}

# --- 6. the full permission cycle -------------------------------------------
grant_one_permission() {
  local attempt="$1"
  log "=== permission cycle #$attempt ==="
  take_screenshot "03_cycle${attempt}_start"

  # 6a. focus RustDesk
  focus_rustdesk
  sleep 1

  # 6b. look for the "Configure" button in RustDesk
  if ax_click_button "RustDesk" "Configure"; then
    log "  clicked Configure — waiting for System Settings to open..."
    sleep 4
    take_screenshot "03_cycle${attempt}_after_configure"

    # 6c. wait for System Settings to have a window
    for i in $(seq 1 10); do
      if osascript -e 'tell application "System Events" to return (count of windows of (first process whose name is "System Settings"))' 2>/dev/null | grep -q "[1-9]"; then
        ok "  System Settings window is open"
        break
      fi
      sleep 1
    done

    # 6d. click the toggle next to RustDesk
    sleep 1
    ax_click_toggle_for_rustdesk || true
    take_screenshot "03_cycle${attempt}_after_toggle"
    sleep 2

    # 6e. handle the password prompt
    handle_password_prompt
    sleep 2
    take_screenshot "03_cycle${attempt}_after_password"

    # 6f. handle "Quit & Reopen" → click "Later"
    # The dialog can belong to System Settings or a separate process
    ax_click_button "System Settings" "Later" 2>/dev/null || true
    sleep 1
    # also try SecurityAgent / CoreServicesUIAgent for the Later button
    ax_click_button "SecurityAgent" "Later" 2>/dev/null || true
    ax_click_button "CoreServicesUIAgent" "Later" 2>/dev/null || true
    take_screenshot "03_cycle${attempt}_done"
    ok "  permission cycle #$attempt complete"
    return 0
  else
    # no Configure button = either all permissions granted, or RustDesk isn't showing it
    log "  no 'Configure' button found — may be all permissions granted"
    return 1
  fi
}

# --- 7. run the permission cycles -------------------------------------------
MAX_CYCLES=6
for cycle in $(seq 1 "$MAX_CYCLES"); do
  grant_one_permission "$cycle" || true
  sleep 2

  # check if any "Configure" button remains
  if ! osascript -e '
    tell application "System Events"
      try
        set theProc to first process whose name is "RustDesk"
        repeat with w in (windows of theProc)
          repeat with b in (every button of w)
            try
              if (name of b as text) is "Configure" then return "FOUND"
            end try
          end repeat
        end repeat
      end try
      return "NONE"
    end tell
  ' 2>/dev/null | grep -q "FOUND"; then
    ok "no more 'Configure' buttons — all permissions granted"
    break
  fi
done

# --- 8. final state ---------------------------------------------------------
take_screenshot "03_final_state"
log "=== permission grant summary ==="

# Check if RustDesk still shows a "Configure" button
configure_check="$(osascript -e '
  tell application "System Events"
    try
      set theProc to first process whose name is "RustDesk"
      repeat with w in (windows of theProc)
        repeat with b in (every button of w)
          try
            if (name of b as text) is "Configure" then return "STILL_HAS_CONFIGURE"
          end try
        end repeat
      end repeat
    end try
    return "NO_CONFIGURE"
  end tell
' 2>/dev/null)"

if [ "$configure_check" = "STILL_HAS_CONFIGURE" ]; then
  warn "RustDesk still shows a 'Configure' button — some permissions may be missing"
else
  ok "no 'Configure' button remaining — all permissions appear granted"
fi

stop_screenshot_loop
stop_dialog_dismissal_loop
ok "permission pipeline complete"
