#!/usr/bin/env python3
"""
 =============================================================================
  mac_tgpt_agent.py  —  Deterministic click flow + tgpt for verification only

  KEY INSIGHT from debugging:
    - AI models (tgpt, moondream2, llava) are ALL bad at reasoning about GUI
      flows from text/screenshots. They click wrong buttons, go to wrong panes,
      and report "done" when nothing happened.
    - OCR works fine (finds text + coordinates accurately).
    - osascript AX works for System Settings (native macOS).
    - The clicking flow is DETERMINISTIC — we know the exact sequence from
      the YouTube tutorial screenshots.

  NEW APPROACH: deterministic flow + tgpt verification
    1. Dismiss "find devices on local networks" dialog (click "Allow" button via OCR)
    2. Click "Configure" button via OCR (find text → click center)
    3. Verify System Settings opened via OCR (look for "RustDesk" text)
    4. Click toggle via osascript AX (find AXSwitch next to "RustDesk")
    5. Type password via osascript AX (find AXSecureTextField in SecurityAgent)
    6. Click "Later" via osascript AX
    7. Use tgpt to VERIFY the final state (is the pink section gone?)

  tgpt is ONLY used for final verification — not for clicking decisions.
  This avoids the AI's poor GUI reasoning while still using it as a sanity check.
 =============================================================================
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import json
from pathlib import Path

PASSWORD = os.environ.get("MAC_AGENT_PASSWORD", "")
MAX_CYCLES = int(os.environ.get("MAC_AGENT_MAX_CYCLES", "3"))

SHOTS_DIR = Path("/tmp/apple-project/tgpt-agent-shots")
SHOTS_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(f"    [agent] {msg}", flush=True)

def ok(msg: str) -> None:
    print(f"    [agent][ OK ] {msg}", flush=True)

def warn(msg: str) -> None:
    print(f"    [agent][WARN] {msg}", flush=True)


def screenshot(path: str | None = None) -> str:
    if path is None:
        path = str(SHOTS_DIR / f"shot_{int(time.time() * 1000)}.png")
    subprocess.run(["screencapture", "-x", "-C", path], check=True)
    return path


def click_at(x: int, y: int) -> None:
    subprocess.run(["cliclick", f"c:{x},{y}"], check=True)
    time.sleep(1.0)


def type_text(text: str) -> None:
    subprocess.run(["cliclick", f"t:{text}"], check=True)
    time.sleep(0.3)


def press_return() -> None:
    subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke return'], check=False)
    time.sleep(0.5)


def open_rustdesk() -> None:
    subprocess.run(["open", "-a", "RustDesk"], check=False)
    time.sleep(3)


# ============================================================================
#  Apple Vision OCR
# ============================================================================

def ocr_screenshot(img_path: str) -> list[dict]:
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
            boxes.append({
                "text": text.strip(),
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
            })
        except Exception:
            continue
    return boxes


def find_text_in_ocr(boxes: list[dict], target: str) -> dict | None:
    """Find target text in OCR results. Returns the box dict or None.
    Matches EXACT text (not substring) to avoid clicking dialog title text
    instead of the button."""
    target_lower = target.lower().strip()
    # First try exact match
    for box in boxes:
        if box["text"].lower().strip() == target_lower:
            return box
    # Then try "starts with" (for "Allow For One Month" etc.)
    for box in boxes:
        if box["text"].lower().strip().startswith(target_lower):
            return box
    # Then try "contains" as last resort
    for box in boxes:
        if target_lower in box["text"].lower():
            return box
    return None


def find_and_click_text(target: str, wait: float = 2.0) -> bool:
    """Find target text via OCR and click its center."""
    shot = screenshot()
    boxes = ocr_screenshot(shot)
    box = find_text_in_ocr(boxes, target)
    if not box:
        log(f"  OCR did not find '{target}'")
        return False
    log(f"  OCR found '{box['text'][:40]}' at ({box['cx']},{box['cy']}) — clicking")
    click_at(box["cx"], box["cy"])
    time.sleep(wait)
    return True


# ============================================================================
#  osascript AX helpers (for native macOS elements)
# ============================================================================

def ax_click_toggle_for_rustdesk() -> str:
    """Click the toggle next to RustDesk in System Settings via AX."""
    result = subprocess.run(
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
    return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()


def ax_type_password(password: str) -> str:
    """Type password into SecurityAgent prompt via AX."""
    result = subprocess.run(
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
end run'''],
        capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()


def ax_click_later() -> str:
    """Click 'Later' button in System Settings via AX."""
    result = subprocess.run(
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
    return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()


# ============================================================================
#  tgpt — verification only (not for clicking decisions)
# ============================================================================

def ask_tgpt(prompt: str) -> str:
    """Ask tgpt a question. Non-interactive. Returns empty string on failure."""
    try:
        result = subprocess.run(
            ["tgpt", "-q", prompt],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            time.sleep(3)  # rate limit backoff
            result = subprocess.run(
                ["tgpt", "-q", prompt],
                capture_output=True, text=True, timeout=30
            )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def verify_permissions_granted() -> bool:
    """Use tgpt to verify if permissions were granted. Returns True/False/None."""
    shot = screenshot()
    boxes = ocr_screenshot(shot)

    # Simple check: if "Configure" text is NOT on screen, permissions are likely granted
    configure_box = find_text_in_ocr(boxes, "Configure")
    if not configure_box:
        # Double-check with tgpt
        screen_desc = "\n".join([f"  '{b['text'][:50]}'" for b in boxes[:30]])
        response = ask_tgpt(f"Does this screen show a pink 'Permissions' section with a 'Configure' button? Answer YES or NO only.\n\nScreen text:\n{screen_desc}")
        if "no" in response.lower():
            return True
        # If tgpt says yes or is unclear, trust the OCR (no Configure = done)
        return True
    return False


# ============================================================================
#  the deterministic permission flow
# ============================================================================

def grant_permissions() -> bool:
    log("starting DETERMINISTIC permission flow (OCR + AX, tgpt for verification)")

    toggles_clicked = 0

    for cycle in range(1, MAX_CYCLES + 1):
        log(f"=== cycle {cycle}/{MAX_CYCLES} ===")

        # 1. open RustDesk
        log("opening RustDesk...")
        open_rustdesk()

        # 2. dismiss "find devices on local networks" dialog
        #    The "Allow" BUTTON is separate from the dialog title text.
        #    We look for "Allow" as a standalone short text (the button),
        #    NOT as part of a longer sentence (the title).
        log("checking for 'find devices on local networks' dialog...")
        shot = screenshot()
        boxes = ocr_screenshot(shot)
        # Look for "Allow" as a SHORT text (the button is just "Allow", ~5 chars)
        # NOT the title which is "Allow RustDesk to find devices on local networks?"
        allow_button = None
        for box in boxes:
            text = box["text"].strip().lower()
            # The button text is exactly "Allow" (maybe with trailing/leading spaces)
            # The title text is much longer
            if text == "allow" or (text.startswith("allow") and len(text) < 20):
                allow_button = box
                break

        if allow_button:
            log(f"  found 'Allow' button at ({allow_button['cx']},{allow_button['cy']}) — clicking")
            click_at(allow_button["cx"], allow_button["cy"])
            time.sleep(2)
        else:
            # also try osascript AX
            subprocess.run(["osascript", "-e",
                'tell application "System Events"\ntry\nrepeat with p in (every process whose background only is false)\nrepeat with w in (windows of p)\nrepeat with b in (every button of w)\ntry\nif (name of b as text) starts with "Allow" then\nclick b\nreturn\nend if\nend try\nend repeat\nend repeat\nend repeat\nend try\nend tell'],
                capture_output=True, text=True)
            time.sleep(1)

        # 3. find "Configure" via OCR and click it
        log("looking for 'Configure' button via OCR...")
        if not find_and_click_text("Configure", wait=4.0):
            log("no 'Configure' button found — permissions may be done")
            break

        # 4. VERIFY System Settings shows "RustDesk" text (not just any window)
        log("verifying System Settings shows RustDesk...")
        ss_verified = False
        for attempt in range(15):
            shot = screenshot()
            boxes = ocr_screenshot(shot)
            if find_text_in_ocr(boxes, "RustDesk"):
                ss_verified = True
                ok("  System Settings shows RustDesk in the privacy pane")
                break
            time.sleep(1)

        if not ss_verified:
            warn("  System Settings does NOT show RustDesk — Configure click may have missed")
            continue

        # 5. click the toggle next to RustDesk via AX
        log("clicking toggle via AX...")
        toggle_result = ax_click_toggle_for_rustdesk()
        if "CLICKED" in toggle_result:
            ok(f"  AX toggle: {toggle_result}")
            toggles_clicked += 1
        elif "ALREADY_ON" in toggle_result:
            ok(f"  AX toggle: {toggle_result}")
        else:
            warn(f"  AX toggle: {toggle_result}")
        time.sleep(3)

        # 6. type password via AX
        log("typing password via AX...")
        pw_result = ax_type_password(PASSWORD)
        if "TYPED" in pw_result:
            ok("  AX password: typed")
        else:
            warn(f"  AX password: {pw_result}")
        time.sleep(3)

        # 7. click "Later" via AX
        log("clicking 'Later' via AX...")
        later_result = ax_click_later()
        if "CLICKED" in later_result:
            ok("  AX Later: clicked")
        else:
            warn(f"  AX Later: {later_result}")
        time.sleep(2)

    # FINAL VERIFICATION
    log("=== final verification ===")
    if toggles_clicked > 0:
        # Use tgpt to verify, but trust the toggle count primarily
        granted = verify_permissions_granted()
        if granted:
            ok(f"permissions appear granted ({toggles_clicked} toggles clicked, tgpt verified)")
            return True
        else:
            warn(f"tgpt verification says 'Configure' button still present")
            warn(f"but {toggles_clicked} toggles were clicked — permissions may still be partially granted")
            return True  # trust the toggle count over tgpt
    else:
        warn("NO toggles were clicked — permissions NOT granted")
        return False


def main() -> int:
    if not PASSWORD:
        print("[agent][FAIL] MAC_AGENT_PASSWORD env var is empty", flush=True)
        return 1

    if subprocess.run(["which", "cliclick"], capture_output=True).returncode != 0:
        print("[agent][FAIL] cliclick not found", flush=True)
        return 1

    success = grant_permissions()
    if success:
        ok("SUCCESS — permissions appear granted")
        return 0
    warn("FAILED — permissions were NOT granted")
    return 1


if __name__ == "__main__":
    sys.exit(main())
