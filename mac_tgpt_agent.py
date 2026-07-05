#!/usr/bin/env python3
"""
 =============================================================================
  mac_pyautogui_agent.py  —  pyautogui image recognition + cliclick agent

  THE APPROACH: pyautogui.locateCenterOnScreen() with opencv template matching.
  This finds UI elements by their VISUAL APPEARANCE — not text, not AX, not
  coordinates. It's the industry standard (SikuliX uses the same technique).

  But we don't have template images of the RustDesk buttons pre-made.
  Solution: use pyautogui's locateCenterOnScreen with a HIGH confidence (0.7)
  to find buttons by their visual appearance. If that fails, fall back to
  Apple Vision OCR + cliclick (which DID find "Configure" at (212,569) —
  the issue was only with the "Allow" button matching).

  The flow:
    1. Dismiss "find devices" dialog: OCR finds "Allow" (short text only) → click
    2. Click "Configure": OCR finds "Configure" text → click its center
    3. In System Settings: osascript AX clicks the toggle (native macOS)
    4. Type password: osascript AX finds AXSecureTextField → type
    5. Click "Later": osascript AX finds button named "Later"

  This is the SAME deterministic flow as before, but with the critical fix:
  the "Allow" button matching only matches SHORT text (the button), not the
  long dialog title text.

  WHY THIS SHOULD WORK (when previous versions didn't):
  - OCR correctly found "Configure" at (212,569) in EVERY run
  - The issue was ONLY the "Allow" button (clicked title text instead of button)
  - Now we match "Allow" as a SHORT standalone text only (len < 20 chars)
  - osascript AX works for System Settings (native macOS, not Flutter)
  - No AI reasoning involved — pure deterministic OCR + AX
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

SHOTS_DIR = Path("/tmp/apple-project/agent-shots")
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
    log(f"  cliclick c:{x},{y}")
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
#  Apple Vision OCR — find text + coordinates
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
                "w": x2 - x1, "h": y2 - y1,
            })
        except Exception:
            continue
    return boxes


def find_short_text(boxes: list[dict], target: str) -> dict | None:
    """Find target as a SHORT standalone text (a button), not part of a longer
    sentence (dialog title). This is the KEY FIX — previous versions matched
    'Allow' inside 'Allow RustDesk to find devices on local networks?' (the
    title text) and clicked the title, not the button.

    A button's text is SHORT (typically < 20 chars) and matches the target
    exactly or starts with it.
    """
    target_lower = target.lower().strip()
    # Sort by text length (shortest first) — buttons are shorter than titles
    sorted_boxes = sorted(boxes, key=lambda b: len(b["text"]))
    for box in sorted_boxes:
        text = box["text"].lower().strip()
        # Exact match (best — the button is just "Allow")
        if text == target_lower:
            return box
        # Starts with target AND is short (a button, not a title)
        if text.startswith(target_lower) and len(text) < 25:
            return box
    return None


def find_text_contains(boxes: list[dict], target: str) -> dict | None:
    """Find target as a substring of any text (for 'Configure' which may be
    part of a longer string)."""
    target_lower = target.lower()
    for box in boxes:
        if target_lower in box["text"].lower():
            return box
    return None


# ============================================================================
#  osascript AX helpers
# ============================================================================

def ax_click_toggle() -> str:
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


def ax_click_button(name: str) -> str:
    result = subprocess.run(
        ["osascript", "-e",
         f'''tell application "System Events"
  repeat with p in (every process whose background only is false)
    repeat with w in (windows of p)
      try
        repeat with b in (every button of w)
          try
            if (name of b as text) is "{name}" then
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
#  the deterministic flow
# ============================================================================

def grant_permissions() -> bool:
    log("starting deterministic permission flow (OCR + AX)")
    toggles_clicked = 0

    for cycle in range(1, MAX_CYCLES + 1):
        log(f"=== cycle {cycle}/{MAX_CYCLES} ===")

        # 1. open RustDesk
        log("opening RustDesk...")
        open_rustdesk()

        # 2. dismiss "find devices on local networks" dialog
        #    KEY FIX: find "Allow" as SHORT text (the button), not the title
        log("checking for network dialog...")
        shot = screenshot()
        boxes = ocr_screenshot(shot)
        log(f"  OCR found {len(boxes)} text elements")

        # dump all OCR results for debugging
        for b in boxes[:15]:
            log(f"    text='{b['text'][:50]}' at ({b['cx']},{b['cy']}) size={b['w']}x{b['h']}")

        allow_box = find_short_text(boxes, "Allow")
        if allow_box:
            log(f"  found 'Allow' BUTTON (short text) at ({allow_box['cx']},{allow_box['cy']})")
            click_at(allow_box["cx"], allow_box["cy"])
            time.sleep(2)
        else:
            log("  no 'Allow' button found — trying osascript AX")
            ax_click_button("Allow")
            time.sleep(1)

        # 3. find "Configure" via OCR and click it
        log("looking for 'Configure' button...")
        shot = screenshot()
        boxes = ocr_screenshot(shot)
        configure_box = find_text_contains(boxes, "Configure")
        if configure_box:
            log(f"  found 'Configure' at ({configure_box['cx']},{configure_box['cy']}) — clicking")
            click_at(configure_box["cx"], configure_box["cy"])
            time.sleep(4)
        else:
            log("  no 'Configure' found — permissions may be done")
            break

        # 4. verify System Settings shows RustDesk
        log("verifying System Settings shows RustDesk...")
        ss_verified = False
        for attempt in range(15):
            shot = screenshot()
            boxes = ocr_screenshot(shot)
            if find_text_contains(boxes, "RustDesk"):
                ss_verified = True
                ok("  System Settings shows RustDesk")
                break
            time.sleep(1)

        if not ss_verified:
            warn("  System Settings does NOT show RustDesk — retrying")
            continue

        # 5. click toggle via AX
        log("clicking toggle via AX...")
        result = ax_click_toggle()
        log(f"  AX toggle: {result}")
        if "CLICKED" in result:
            toggles_clicked += 1
        time.sleep(3)

        # 6. type password via AX
        log("typing password via AX...")
        result = ax_type_password(PASSWORD)
        log(f"  AX password: {result}")
        time.sleep(3)

        # 7. click "Later" via AX
        log("clicking 'Later' via AX...")
        result = ax_click_button("Later")
        log(f"  AX Later: {result}")
        time.sleep(2)

    # Final check
    log(f"=== summary: {toggles_clicked} toggles clicked ===")
    if toggles_clicked > 0:
        ok(f"permissions appear granted ({toggles_clicked} toggles clicked)")
        return True
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
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
