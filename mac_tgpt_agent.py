#!/usr/bin/env python3
"""
 =============================================================================
  mac_ax_agent.py  —  PURE osascript AX agent (no OCR, no AI, no cliclick)

  FRESH START. Forget everything that didn't work:
  - Apple Vision OCR: trash (finds wrong text, wrong coordinates)
  - moondream2/ShowUI-2B: OOM or hallucinated coordinates
  - tgpt: can't reason about GUI
  - cliclick at fixed coords: button isn't where we think it is
  - Clicking RustDesk's "Configure" button: never actually worked

  NEW APPROACH: Skip the Configure button entirely. Open System Settings
  DIRECTLY via URL, then use the "+" button to add RustDesk to each privacy
  list. Everything via osascript AX (which works for native macOS).

  The flow (for each of 3 permissions):
    1. open "x-apple.systempreferences:...Privacy_ScreenCapture" (direct URL)
    2. osascript AX: click the "+" button in the privacy list
    3. osascript AX: in the file picker, press Cmd+Shift+G, type path, Enter
    4. osascript AX: click "Open" (or press Enter)
    5. Now RustDesk is in the list — osascript AX: click the toggle ON
    6. SecurityAgent password prompt appears — osascript AX: type password
    7. osascript AX: click "Later" (dismiss Quit & Reopen)

  No screenshots needed. No OCR. No AI. No cliclick. No Configure button.
  Pure osascript AX driving native macOS System Settings.
 =============================================================================
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

PASSWORD = os.environ.get("MAC_AGENT_PASSWORD", "")

# The three privacy panes and their direct-open URLs
PERMISSIONS = [
    ("Screen Recording", "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture"),
    ("Accessibility", "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility"),
    ("Input Monitoring", "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ListenEvent"),
]

RUSTDESK_PATH = "/Applications/RustDesk.app"


def log(msg: str) -> None:
    print(f"    [ax] {msg}", flush=True)

def ok(msg: str) -> None:
    print(f"    [ax][ OK ] {msg}", flush=True)

def warn(msg: str) -> None:
    print(f"    [ax][WARN] {msg}", flush=True)


def osascript(script: str, timeout: int = 10) -> str:
    """Run an AppleScript and return stdout. Returns error string on failure."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return f"ERROR: {result.stderr.strip()[:200]}"
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as e:
        return f"EXCEPTION: {e}"


def open_pane(url: str) -> None:
    """Open a System Settings pane directly via URL."""
    subprocess.run(["open", url], check=False)
    time.sleep(3)


def click_plus_button() -> str:
    """Click the '+' button in the privacy list to add an app.
    System Settings privacy panes have a '+' button at the bottom of the list.
    We search for it by AX identifier since the button may not have a text name."""
    return osascript('''
tell application "System Events"
    set theProc to first process whose name is "System Settings"
    if (count of windows of theProc) is 0 then return "NO_WINDOW"
    set theWindow to window 1 of theProc
    -- search recursively for a button with a "+" or "add" description
    set theButton to my findPlusButton(theWindow)
    if theButton is missing value then return "NOT_FOUND"
    click theButton
    return "CLICKED"
end tell

on findPlusButton(theElement)
    tell application "System Events"
        try
            set kids to UI elements of theElement
        on error
            return missing value
        end try
        repeat with kid in kids
            try
                set kidRole to role of kid
                if kidRole is "AXButton" then
                    try
                        set kidDesc to description of kid as text
                        if kidDesc contains "+" or kidDesc contains "Add" or kidDesc contains "add" then
                            return kid
                        end if
                    end try
                    try
                        set kidTitle to title of kid as text
                        if kidTitle contains "+" or kidTitle contains "Add" then
                            return kid
                        end if
                    end try
                    -- also check if it's a small button at the bottom (by position)
                    try
                        set kidPos to position of kid
                        set kidSize to size of kid
                        -- buttons at the bottom of the window, left side
                        set winPos to position of (window 1 of (first process whose name is "System Settings"))
                        set winSize to size of (window 1 of (first process whose name is "System Settings"))
                        if (item 2 of kidPos) > (item 2 of winPos) + (item 2 of winSize) - 100 then
                            -- it's near the bottom of the window — likely the + button
                            if (item 1 of kidSize) < 30 and (item 2 of kidSize) < 30 then
                                return kid
                            end if
                        end if
                    end try
                end if
            end try
            -- recurse into groups
            try
                set kidRole to role of kid
                if kidRole is in {"AXGroup", "AXSplitGroup", "AXLayoutArea", "AXScrollArea"} then
                    set res to my findPlusButton(kid)
                    if res is not missing value then return res
                end if
            end try
        end repeat
        return missing value
    end tell
end findPlusButton
''', timeout=15)


def drive_file_picker(app_path: str) -> str:
    """After clicking '+', a file picker opens. Drive it to select the app.
    Use Cmd+Shift+G to open the 'Go to folder' sheet, type the path, Enter."""
    log(f"  driving file picker to select {app_path}")
    time.sleep(2)  # wait for file picker to open

    # Cmd+Shift+G to open the Go to folder sheet
    osascript('tell application "System Events" to keystroke "g" using {command down, shift down}')
    time.sleep(1.5)

    # Type the path
    osascript(f'tell application "System Events" to keystroke "{app_path}"')
    time.sleep(0.5)

    # Press Enter to go to the folder
    osascript('tell application "System Events" to keystroke return')
    time.sleep(1.5)

    # Press Enter again to select the app (it should be highlighted)
    osascript('tell application "System Events" to keystroke return')
    time.sleep(2)

    return "DONE"


def click_toggle_for_rustdesk() -> str:
    """Click the toggle next to RustDesk in the privacy list via AX."""
    return osascript('''
tell application "System Events"
    set theProc to first process whose name is "System Settings"
    if (count of windows of theProc) is 0 then return "NO_WINDOW"
    set theWindow to window 1 of theProc
    set theSwitch to my findSwitchForApp(theWindow, "RustDesk")
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

on findSwitchForApp(theElement, appName)
    tell application "System Events"
        try
            set kids to UI elements of theElement
        on error
            return missing value
        end try
        try
            set elemRole to role of theElement
        on error
            set elemRole to ""
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
''', timeout=15)


def type_password(password: str) -> str:
    """Type password into the SecurityAgent prompt via AX."""
    return osascript(f'''
tell application "System Events"
    repeat with procName in {{"SecurityAgent", "CoreServicesUIAgent"}}
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
                        keystroke "{password}"
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
''', timeout=10)


def click_later() -> str:
    """Click 'Later' button via AX."""
    return osascript('''
tell application "System Events"
    repeat with p in (every process whose background only is false)
        repeat with w in (windows of p)
            try
                repeat with b in (every button of w)
                    try
                        if (name of b as text) is "Later" then
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
''', timeout=10)


def is_rustdesk_in_list() -> bool:
    """Check if RustDesk is already in the privacy list."""
    result = click_toggle_for_rustdesk()
    return result != "NOT_FOUND" and result != "NO_WINDOW"


def grant_one_permission(name: str, url: str) -> bool:
    """Grant one permission (Screen Recording, Accessibility, or Input Monitoring)."""
    log(f"=== granting {name} ===")

    # 1. open the privacy pane directly
    log(f"  opening {name} pane...")
    open_pane(url)

    # 2. check if RustDesk is already in the list
    if is_rustdesk_in_list():
        ok(f"  RustDesk already in {name} list — clicking toggle")
    else:
        # 3. RustDesk not in list — click "+" to add it
        log(f"  RustDesk not in list — clicking '+' button...")
        result = click_plus_button()
        log(f"  '+' button: {result}")
        if "CLICKED" not in result:
            warn(f"  could not click '+' button: {result}")
            return False

        # 4. drive the file picker to select RustDesk.app
        result = drive_file_picker(RUSTDESK_PATH)
        log(f"  file picker: {result}")
        time.sleep(2)

        # 5. check if RustDesk is now in the list
        if not is_rustdesk_in_list():
            warn(f"  RustDesk still not in list after adding — may need to retry")
            # try again with a different file picker approach
            time.sleep(2)

    # 6. click the toggle ON
    log(f"  clicking toggle...")
    result = click_toggle_for_rustdesk()
    log(f"  toggle: {result}")
    if "CLICKED" in result:
        ok(f"  toggle clicked ON")
    elif "ALREADY_ON" in result:
        ok(f"  toggle already ON — permission granted")
        return True
    else:
        warn(f"  toggle failed: {result}")
        return False

    time.sleep(3)

    # 7. type password (if prompt appears)
    log(f"  typing password...")
    result = type_password(PASSWORD)
    log(f"  password: {result}")
    time.sleep(3)

    # 8. click "Later" (if Quit & Reopen dialog appears)
    log(f"  clicking 'Later'...")
    result = click_later()
    log(f"  Later: {result}")
    time.sleep(2)

    return True


def main() -> int:
    if not PASSWORD:
        print("[ax][FAIL] MAC_AGENT_PASSWORD env var is empty", flush=True)
        return 1

    log("starting PURE AX permission flow (no OCR, no AI, no cliclick)")

    granted = 0
    for name, url in PERMISSIONS:
        if grant_one_permission(name, url):
            granted += 1
        time.sleep(2)

    log(f"=== summary: {granted}/{len(PERMISSIONS)} permissions granted ===")
    if granted > 0:
        ok(f"permissions appear granted ({granted}/{len(PERMISSIONS)})")
        return 0
    warn("NO permissions were granted")
    return 1


if __name__ == "__main__":
    sys.exit(main())
