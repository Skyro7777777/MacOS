#!/usr/bin/env python3
"""
 =============================================================================
  mac_tgpt_agent.py  —  AI agent using tgpt (online 20B model) + Apple Vision OCR

  tgpt is a terminal AI that uses GPT-OSS-20B (via Pollinations) — a 20B
  reasoning model, much smarter than local 8B models. No API key, no download.

  The flow:
    1. Take screenshot via screencapture (inherits bash's Screen Recording TCC)
    2. Run Apple Vision OCR → get all text + coordinates on screen
    3. Send the OCR text to tgpt: "Here's what I see. What should I click?"
    4. tgpt responds with what to click (e.g. "Click the Configure button")
    5. Find that text in our OCR results → get its coordinates → cliclick click
    6. Take another screenshot → repeat until done

  This is a REASONING AI (20B model) + VISION (Apple OCR) + ACTION (cliclick).
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
MAX_STEPS = int(os.environ.get("MAC_AGENT_MAX_STEPS", "20"))

SHOTS_DIR = Path("/tmp/apple-project/tgpt-agent-shots")
SHOTS_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(f"    [tgpt] {msg}", flush=True)

def ok(msg: str) -> None:
    print(f"    [tgpt][ OK ] {msg}", flush=True)

def warn(msg: str) -> None:
    print(f"    [tgpt][WARN] {msg}", flush=True)


# ============================================================================
#  screen + input helpers
# ============================================================================

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
#  Apple Vision OCR — see the screen
# ============================================================================

def ocr_screenshot(img_path: str) -> list[dict]:
    """Run macOS Vision OCR. Returns list of {text, x1, y1, x2, y2, cx, cy}."""
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
    """Find target text in OCR results. Returns the box dict or None."""
    target_lower = target.lower()
    for box in boxes:
        if target_lower in box["text"].lower():
            return box
    return None


# ============================================================================
#  tgpt — the AI reasoning brain (20B model, no API key)
# ============================================================================

def ask_tgpt(prompt: str) -> str:
    """Ask tgpt a question and get the response. Non-interactive."""
    result = subprocess.run(
        ["tgpt", "-q", prompt],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        # retry once (Pollinations can be flaky)
        time.sleep(2)
        result = subprocess.run(
            ["tgpt", "-q", prompt],
            capture_output=True, text=True, timeout=30
        )
    return result.stdout.strip() if result.returncode == 0 else ""


def get_screen_description(boxes: list[dict]) -> str:
    """Build a text description of what's on screen from OCR results."""
    if not boxes:
        return "(empty screen — no text detected)"
    lines = []
    for i, box in enumerate(boxes):
        lines.append(f"  [{i}] '{box['text'][:60]}' at ({box['cx']},{box['cy']})")
    return "\n".join(lines)


def ask_tgpt_what_to_do(screen_desc: str, task_context: str) -> dict:
    """Ask tgpt what to do next given the screen description.
    Returns {action: 'click'|'type'|'press_return'|'done', target: str, reasoning: str}."""
    prompt = f"""You are controlling a macOS 15 computer to grant permissions to RustDesk.

TASK: {task_context}

Here is what you see on screen right now (text elements with their pixel coordinates on a 1024x768 screen):

{screen_desc}

Based on what you see, what should you do next? Respond in EXACTLY this JSON format (no other text):

{{"action": "click", "target": "the text of the button/element to click", "reasoning": "why"}}
{{"action": "type", "target": "the text to type", "reasoning": "why"}}
{{"action": "press_return", "target": "", "reasoning": "why"}}
{{"action": "done", "target": "", "reasoning": "why"}}

Rules:
- For "click", the target must be text that appears in the screen description above
- For "type", the target is the exact text to type (e.g. a password)
- For "done", use this when all permissions appear to be granted (no pink Permissions section visible)
- Respond with ONLY the JSON, no markdown, no explanation outside the JSON"""

    response = ask_tgpt(prompt)
    log(f"  tgpt response: {response[:200]}")

    # parse JSON from response
    try:
        # find JSON in the response
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data
    except Exception:
        pass

    # fallback: try to parse manually
    if "done" in response.lower():
        return {"action": "done", "target": "", "reasoning": response}
    return {"action": "unknown", "target": "", "reasoning": response}


# ============================================================================
#  the main flow
# ============================================================================

def grant_permissions() -> bool:
    log("starting permission flow (tgpt 20B + Apple Vision OCR + cliclick)")

    task_context = """Grant TCC permissions to RustDesk. Steps:
1. If a dialog asks "Allow RustDesk to find devices on local networks?", click "Allow"
2. Click the "Configure" button in RustDesk's pink Permissions section
3. In System Settings, click the toggle next to "RustDesk" to turn it ON
4. When the password prompt appears, type the password and press Enter
5. If "Quit & Reopen" appears, click "Later"
6. Repeat until no more "Configure" buttons (all permissions granted)
The password is: """ + PASSWORD

    for step in range(MAX_STEPS):
        log(f"=== step {step + 1}/{MAX_STEPS} ===")

        # 1. take screenshot + OCR
        shot = screenshot()
        boxes = ocr_screenshot(shot)
        screen_desc = get_screen_description(boxes)

        if not boxes:
            log("no text detected on screen — opening RustDesk")
            open_rustdesk()
            continue

        # 2. ask tgpt what to do
        decision = ask_tgpt_what_to_do(screen_desc, task_context)
        action = decision.get("action", "unknown")
        target = decision.get("target", "")
        reasoning = decision.get("reasoning", "")

        log(f"  action: {action}")
        log(f"  target: {target}")
        log(f"  reasoning: {reasoning[:100]}")

        if action == "done":
            ok("tgpt says all permissions are granted!")
            return True

        elif action == "click":
            # find the target text in OCR results
            box = find_text_in_ocr(boxes, target)
            if box:
                log(f"  clicking '{target}' at ({box['cx']},{box['cy']})")
                click_at(box["cx"], box["cy"])
            else:
                warn(f"  could not find '{target}' on screen — retrying next step")

        elif action == "type":
            log(f"  typing: {target[:20]}...")
            # click center of screen first to focus the text field
            click_at(512, 384)
            time.sleep(0.3)
            type_text(target)
            time.sleep(0.5)

        elif action == "press_return":
            log("  pressing Return")
            press_return()

        else:
            warn(f"  unknown action: {action}")

        time.sleep(2)

    warn(f"reached max steps ({MAX_STEPS}) — stopping")
    return False


def main() -> int:
    if not PASSWORD:
        print("[tgpt][FAIL] MAC_AGENT_PASSWORD env var is empty", flush=True)
        return 1

    if subprocess.run(["which", "tgpt"], capture_output=True).returncode != 0:
        print("[tgpt][FAIL] tgpt not found — install it first", flush=True)
        return 1

    if subprocess.run(["which", "cliclick"], capture_output=True).returncode != 0:
        print("[tgpt][FAIL] cliclick not found — install it first", flush=True)
        return 1

    success = grant_permissions()
    if success:
        ok("SUCCESS — all permissions appear granted")
        return 0
    warn("FAILED — permissions were NOT granted")
    return 1


if __name__ == "__main__":
    sys.exit(main())
