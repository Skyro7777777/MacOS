#!/usr/bin/env python3
"""
 =============================================================================
  mac_vision_agent.py  —  AI agent using Apple Vision OCR + osascript AX
  for finding and clicking UI elements.

  KEY INSIGHT from debugging:
    OCR finds TEXT, but text positions ≠ button positions. The "Allow" text
    in the dialog title is at y=217, but the "Allow" BUTTON is at y~380.
    We must find the BUTTON (via osascript AX or by clicking BELOW the text),
    not just click on any text matching "Allow".

  The flow:
    1. Take screenshot
    2. Dismiss "find devices on local networks" dialog:
       a. Try osascript AX to click the "Allow" BUTTON
       b. If that fails, use cliclick to click BELOW the "Allow" text (where buttons are)
       c. VERIFY the dialog is gone (re-screenshot, check if "Allow" text still there)
    3. Find "Configure" via OCR → click → VERIFY System Settings shows "RustDesk" text
    4. AX toggle → AX password → AX Later
    5. Only report SUCCESS if at least one toggle was actually CLICKED (not NOT_FOUND)
 =============================================================================
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

PASSWORD = os.environ.get("MAC_AGENT_PASSWORD", "")
MAX_CYCLES = int(os.environ.get("MAC_AGENT_MAX_CYCLES", "3"))

SHOTS_DIR = Path("/tmp/apple-project/vision-agent-shots")
SHOTS_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(f"    [vision] {msg}", flush=True)

def ok(msg: str) -> None:
    print(f"    [vision][ OK ] {msg}", flush=True)

def warn(msg: str) -> None:
    print(f"    [vision][WARN] {msg}", flush=True)

def die(msg: str) -> None:
    print(f"    [vision][FAIL] {msg}", flush=True)
    sys.exit(1)


def screenshot(path: str | None = None) -> str:
    if path is None:
        path = str(SHOTS_DIR / f"shot_{int(time.time() * 1000)}.png")
    subprocess.run(["screencapture", "-x", "-C", path], check=True)
    return path


def click_at(x: int, y: int) -> None:
    subprocess.run(["cliclick", f"c:{x},{y}"], check=True)
    time.sleep(0.8)


def type_text(text: str) -> None:
    subprocess.run(["cliclick", f"t:{text}"], check=True)
    time.sleep(0.3)


def press_return() -> None:
    subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke return'], check=False)
    time.sleep(0.5)


def is_process_running(name: str) -> bool:
    result = subprocess.run(
        ["osascript", "-e",
         f'tell application "System Events" to return (count of (every process whose name is "{name}")) > 0'],
        capture_output=True, text=True)
    return result.returncode == 0 and "true" in result.stdout.lower()


# ============================================================================
#  Apple Vision OCR
# ============================================================================

def ocr_screenshot(img_path: str) -> list[tuple[str, int, int, int, int]]:
    try:
        from Vision import VNRecognizeTextRequest, VNImageRequestHandler
        from Foundation import NSURL
        from PIL import Image
    except ImportError as e:
        log(f"OCR deps missing: {e}")
        return []

    url = NSURL.fileURLWithPath_(img_path)
    request = VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(1)
    request.setRecognitionLanguages_(["en-US"])

    handler = VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    success = handler.performRequests_error_([request], None)
    if not success:
        return []

    results = request.results() or []
    with Image.open(img_path) as img:
        w, h = img.size

    boxes = []
    for obs in results:
        try:
            candidate = obs.topCandidates_(1)
            if not candidate:
                continue
            text = candidate[0].string()
            bbox = obs.boundingBox()
            x1 = int(bbox.origin.x * w)
            y1 = int((1 - bbox.origin.y - bbox.size.height) * h)
            x2 = int((bbox.origin.x + bbox.size.width) * w)
            y2 = int((1 - bbox.origin.y) * h)
            boxes.append((text, x1, y1, x2, y2))
        except Exception:
            continue
    return boxes


def find_text_on_screen(target: str, img_path: str | None = None) -> tuple[int, int, int, int, int] | None:
    """Find target text via OCR. Returns (text, x1, y1, x2, y2) or None."""
    if img_path is None:
        img_path = screenshot()
    boxes = ocr_screenshot(img_path)
    target_lower = target.lower()
    for text, x1, y1, x2, y2 in boxes:
        if target_lower in text.lower():
            log(f"  OCR found '{text.strip()[:50]}' at ({x1},{y1})-({x2},{y2})")
            return (text, x1, y1, x2, y2)
    log(f"  OCR did not find '{target}' in {len(boxes)} text boxes")
    return None


def find_and_click(target: str, wait: float = 2.0) -> bool:
    """Find target text via OCR and click its center."""
    result = find_text_on_screen(target)
    if not result:
        return False
    _, x1, y1, x2, y2 = result
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    log(f"  clicking '{target}' at ({cx},{cy})")
    click_at(cx, cy)
    time.sleep(wait)
    return True


# ============================================================================
#  dialog dismissal — click the BUTTON, not the text
# ============================================================================

def dismiss_network_dialog() -> bool:
    """Dismiss 'Allow RustDesk to find devices on local networks?' dialog.

    The 'Allow' text in the dialog title is at y~217, but the 'Allow' BUTTON
    is at the BOTTOM of the dialog (~y380). We need to click the button, not
    the title text.

    Strategy:
    1. Try osascript AX to click a button named 'Allow' (works on macOS < 15.4)
    2. If that fails, use cliclick to click BELOW the dialog text where buttons are
    3. VERIFY the dialog is gone by re-screenshotting and checking for the text
    """
    log("checking for 'find devices on local networks' dialog...")

    # Check if the dialog is present (look for "find devices" or "local networks" text)
    shot = screenshot()
    dialog_text = find_text_on_screen("local networks", shot)
    if not dialog_text:
        dialog_text = find_text_on_screen("find devices", shot)
    if not dialog_text:
        log("  no network dialog found")
        return True  # dialog not present — nothing to dismiss

    _, x1, y1, x2, y2 = dialog_text
    log(f"  network dialog detected at ({x1},{y1})-({x2},{y2})")

    # Method 1: try osascript AX to click the "Allow" button
    log("  trying osascript AX to click 'Allow' button...")
    ax_result = subprocess.run(
        ["osascript", "-e",
         '''tell application "System Events"
  try
    repeat with p in (every process whose background only is false)
      repeat with w in (windows of p)
        repeat with b in (every button of w)
          try
            set bName to name of b as text
            if bName starts with "Allow" then
              click b
              return "CLICKED:" & bName
            end if
          end try
        end repeat
      end repeat
    end repeat
  end try
  return "NOT_FOUND"
end tell'''],
        capture_output=True, text=True)
    ax_output = ax_result.stdout.strip()
    if "CLICKED" in ax_output:
        ok(f"  AX clicked: {ax_output}")
        time.sleep(2)
    else:
        # Method 2: cliclick — click BELOW the dialog text where buttons are
        # Dialog buttons are typically 150-200px below the dialog title text
        # The dialog is centered horizontally (~x512 on 1024px screen)
        # "Allow" is the RIGHT button, "Don't Allow" is the LEFT button
        button_y = y2 + 160  # 160px below the bottom of the dialog text
        allow_x = 612  # right button (Allow)
        log(f"  AX failed — trying cliclick at button position ({allow_x},{button_y})")
        click_at(allow_x, button_y)
        time.sleep(2)

    # VERIFY: is the dialog gone?
    shot2 = screenshot()
    still_there = find_text_on_screen("local networks", shot2)
    if still_there:
        # try clicking "Don't Allow" instead (left button) to at least dismiss it
        dont_allow_x = 412  # left button (Don't Allow)
        button_y = y2 + 160
        log(f"  dialog still present — trying 'Don't Allow' at ({dont_allow_x},{button_y})")
        click_at(dont_allow_x, button_y)
        time.sleep(2)
        shot3 = screenshot()
        if find_text_on_screen("local networks", shot3):
            warn("  WARNING: network dialog still present after all attempts")
            return False
        else:
            ok("  network dialog dismissed (via Don't Allow)")
            return True
    else:
        ok("  network dialog dismissed")
        return True


# ============================================================================
#  the permission-granting flow
# ============================================================================

def grant_permissions() -> bool:
    log("starting permission flow (OCR + AX hybrid)")

    toggles_clicked = 0

    for cycle in range(1, MAX_CYCLES + 1):
        log(f"=== cycle {cycle}/{MAX_CYCLES} ===")

        # 1. open RustDesk
        subprocess.run(["open", "-a", "RustDesk"], check=False)
        time.sleep(3)

        # 2. dismiss network dialog (with verification)
        dismiss_network_dialog()
        time.sleep(1)

        # 3. find "Configure" via OCR and click it
        log("looking for 'Configure' button via OCR...")
        configure_result = find_text_on_screen("Configure")
        if not configure_result:
            log("no 'Configure' button found — permissions may be done")
            continue

        _, cx1, cy1, cx2, cy2 = configure_result
        configure_x = (cx1 + cx2) // 2
        configure_y = (cy1 + cy2) // 2
        log(f"  clicking 'Configure' at ({configure_x},{configure_y})")
        click_at(configure_x, configure_y)
        time.sleep(4)

        # 4. VERIFY System Settings opened AND shows "RustDesk" text
        #    (not just any window — must be the privacy pane with RustDesk listed)
        log("verifying System Settings shows RustDesk in privacy pane...")
        ss_verified = False
        for attempt in range(15):
            shot = screenshot()
            # check if "RustDesk" text appears in System Settings
            rustdesk_in_ss = find_text_on_screen("RustDesk", shot)
            if rustdesk_in_ss:
                ss_verified = True
                ok("  System Settings shows RustDesk in the privacy pane")
                break
            time.sleep(1)

        if not ss_verified:
            warn("  System Settings does NOT show RustDesk — Configure click may have missed")
            continue

        # 5. find + click the toggle next to RustDesk via AX
        log("finding RustDesk's toggle via AX...")
        toggle_result = subprocess.run(
            ["osascript", "-e",
             '''on run
  tell application "System Events"
    set procList to (every process whose name is "System Settings")
    if (count of procList) is 0 then return "NO_PROCESS"
    set theProc to item 1 of procList
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
end findSwitchForApp'''],
            capture_output=True, text=True)
        toggle_str = toggle_result.stdout.strip() if toggle_result.returncode == 0 else toggle_result.stderr.strip()
        if "CLICKED" in toggle_str:
            ok(f"  AX toggle: {toggle_str}")
            toggles_clicked += 1
        elif "ALREADY_ON" in toggle_str:
            ok(f"  AX toggle: {toggle_str}")
        else:
            warn(f"  AX toggle: {toggle_str}")
        time.sleep(3)

        # 6. type password via AX
        log("typing password via AX...")
        pw_result = subprocess.run(
            ["osascript", "-e",
             f'''on run
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
              keystroke "{PASSWORD}"
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
end run'''],
            capture_output=True, text=True)
        pw_str = pw_result.stdout.strip() if pw_result.returncode == 0 else pw_result.stderr.strip()
        if "TYPED" in pw_str:
            ok("  AX password: typed")
        else:
            warn(f"  AX password: {pw_str}")
        time.sleep(3)

        # 7. click "Later" via AX
        log("clicking 'Later' via AX...")
        later_result = subprocess.run(
            ["osascript", "-e",
             '''tell application "System Events"
  repeat with p in (every process whose name is "System Settings")
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
end tell'''],
            capture_output=True, text=True)
        later_str = later_result.stdout.strip() if later_result.returncode == 0 else later_result.stderr.strip()
        if "CLICKED" in later_str:
            ok("  AX Later: clicked")
        else:
            warn(f"  AX Later: {later_str}")
        time.sleep(2)

    # FINAL VERIFICATION: only report success if at least one toggle was clicked
    if toggles_clicked > 0:
        ok(f"permission flow complete — {toggles_clicked} toggle(s) clicked")
        return True
    else:
        warn("permission flow complete — NO toggles were clicked (permissions NOT granted)")
        return False


def main() -> int:
    if not PASSWORD:
        die("MAC_AGENT_PASSWORD env var is empty")
    if subprocess.run(["which", "cliclick"], capture_output=True).returncode != 0:
        die("cliclick not found")

    success = grant_permissions()
    if success:
        ok("SUCCESS — permissions appear granted")
        return 0
    die("FAILED — permissions were NOT granted")
    return 1


if __name__ == "__main__":
    sys.exit(main())
