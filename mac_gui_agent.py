#!/usr/bin/env python3
"""
 =============================================================================
  mac_gui_agent.py  —  LOCAL GUI agent for granting macOS 15 TCC permissions
  to RustDesk.  Replaces the OOM-prone ShowUI-2B agent.

  Three tiers (tried in order, first success wins):

  TIER 1 — Apple Vision OCR (PyObjC, ZERO download)
     Uses the macOS BUILT-IN Vision framework (VNRecognizeTextRequest) to find
     the text "RustDesk" in the screenshot and get its bounding box.  The
     toggle switch is always at a fixed offset to the right of the app name in
     System Settings privacy panes, so we click there.  Deterministic, ~100 MB
     RAM, no GPU, no model download.

  TIER 2 — OmniParser-v2.0 YOLO icon detector (41 MB)
     If OCR finds the text but the fixed-offset click misses (toggle is in an
     unusual position), we load microsoft/OmniParser-v2.0's icon_detect YOLO
     model (40.6 MB) to find ALL clickable UI elements by pixel coordinates,
     then click the one nearest to (and to the right of) the "RustDesk" label.

  TIER 3 — moondream2 (1.86B VLM, ~4 GB RAM, native point: API)
     If both OCR and YOLO fail, we load vikhyatk/moondream2 — the smallest VLM
     with a clean grounding API.  It outputs pixel coordinates directly via the
     <point>`point:` instruction.  Fits comfortably in the 7.93 GiB MPS limit.

  CRITICAL PERMISSION TRICK — "responsible process" TCC inheritance:
     screencapture + cliclick + osascript spawned by bash inherit bash's
     Screen Recording + Accessibility TCC permission.  We NEVER call
     CGWindowListCreateImage / CGEventCreate inside the Python process.
     (pyobjc Vision OCR is the ONE exception — it uses the Vision framework
     which is TCC-attributed to the system, not to Python.  Verified working.)

  ENV VARS (set by mac_03_grant_permissions.sh):
    GUI_AGENT_GOAL         — natural-language description of what to click
    GUI_AGENT_PANE_URL     — deep-link URL of the privacy pane to open
    GUI_AGENT_SERVICE      — TCC service name (for logging)
    GUI_AGENT_HELPER_USER  — helper username (for password prompts, if any)
    GUI_AGENT_HELPER_PW    — helper password (for password prompts, if any)
    GUI_AGENT_MAX_STEPS    — (optional) max steps, default 25
    GUI_AGENT_VENV         — (optional) path to the venv with deps
 =============================================================================
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

# --- config ------------------------------------------------------------------

PANE_URL = os.environ.get("GUI_AGENT_PANE_URL", "")
GOAL = os.environ.get("GUI_AGENT_GOAL", "")
SERVICE = os.environ.get("GUI_AGENT_SERVICE", "unknown")
HELPER_USER = os.environ.get("GUI_AGENT_HELPER_USER", "")
HELPER_PASSWORD = os.environ.get("GUI_AGENT_HELPER_PW", "")
MAX_STEPS = int(os.environ.get("GUI_AGENT_MAX_STEPS", "25"))

SHOTS_DIR = Path("/tmp/apple-project/gui-agent-shots")
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME = "RustDesk"
APP_PATH = "/Applications/RustDesk.app"

# the toggle is always to the RIGHT of the app name in macOS Sequoia privacy
# panes.  The offset is empirical for the standard System Settings layout.
# (x = label_right_edge + ~40px, y = label_center)
TOGGLE_X_OFFSET = 120  # pixels to the right of the label's right edge


def log(msg: str) -> None:
    print(f"    [gui-agent] {msg}", flush=True)


def die(msg: str, code: int = 1) -> None:
    print(f"    [gui-agent][FAIL] {msg}", flush=True)
    sys.exit(code)


# ============================================================================
#  screen + input helpers  (all shell-out, for TCC inheritance)
# ============================================================================

def screenshot(path: str | None = None) -> str:
    if path is None:
        path = str(SHOTS_DIR / f"shot_{int(time.time() * 1000)}.png")
    subprocess.run(["screencapture", "-x", "-C", path], check=True)
    return path


def click_at(x: int, y: int) -> None:
    subprocess.run(["cliclick", f"c:{x},{y}"], check=True)
    time.sleep(0.5)


def type_text(text: str) -> None:
    subprocess.run(["cliclick", f"t:{text}"], check=True)
    time.sleep(0.2)


def key_return() -> None:
    subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke return'], check=False)
    time.sleep(0.4)


def key_combo_g() -> None:
    """Cmd+Shift+G (Go to folder in file pickers)."""
    subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke "g" using {command down, shift down}'],
                   check=False)
    time.sleep(1.0)


def open_pane(url: str) -> None:
    if url:
        log(f"opening pane: {url}")
        subprocess.run(["open", url], check=False)
        time.sleep(3)


# ============================================================================
#  TIER 1 — Apple Vision OCR (PyObjC, ZERO download)
# ============================================================================

def _vision_ocr(img_path: str) -> list[tuple[str, int, int, int, int]]:
    """Run macOS Vision OCR on an image.  Returns list of
    (text, x1, y1, x2, y2) in PIXEL coordinates."""
    try:
        from CoreML import MLModel  # noqa: F401  (ensures pyobjc is importable)
    except ImportError:
        pass
    try:
        import Quartz  # type: ignore
        from Vision import (  # type: ignore
            VNRecognizeTextRequest,
            VNDetectTextRectanglesRequest,
        )
        from CoreFoundation import CFURLCreateWithFileSystemPath, kCFURLPOSIXPathStyle  # type: ignore
        from Foundation import NSURL  # type: ignore
    except ImportError as e:
        log(f"  [T1 OCR] PyObjC not available: {e}")
        return []

    url = NSURL.fileURLWithPath_(img_path)
    request = VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(1)  # 1 = accurate
    request.setRecognitionLanguages_(["en-US"])

    from Foundation import NSDictionary, NSMutableArray  # type: ignore
    from Vision import VNImageRequestHandler  # type: ignore

    handler = VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    success = handler.performRequests_error_([request], None)
    if not success:
        log("  [T1 OCR] Vision request failed")
        return []

    results = request.results() or []
    # Get image dimensions for coordinate conversion
    from PIL import Image  # noqa
    with Image.open(img_path) as img:
        w, h = img.size

    boxes = []
    for obs in results:
        try:
            # VNRecognizedTextObservation has .topLeft (CGPoint in normalized
            # coords, origin bottom-left, range 0..1)
            candidate = obs.topCandidates_(1)
            if not candidate:
                continue
            text = candidate[0].string()
            bbox = obs.boundingBox()  # normalized CGRect, origin bottom-left
            # convert to pixel coords (origin top-left)
            x1 = int(bbox.origin.x * w)
            y1 = int((1 - bbox.origin.y - bbox.size.height) * h)
            x2 = int((bbox.origin.x + bbox.size.width) * w)
            y2 = int((1 - bbox.origin.y) * h)
            boxes.append((text, x1, y1, x2, y2))
        except Exception:
            continue
    return boxes


def tier1_find_and_click(img_path: str, app_name: str) -> bool:
    """Find app_name via Vision OCR, click the toggle at a fixed offset to
    the right.  Returns True if clicked."""
    log("  [T1 OCR] scanning for text...")
    boxes = _vision_ocr(img_path)
    if not boxes:
        log("  [T1 OCR] no text found (PyObjC missing or Vision failed)")
        return False

    # find the box whose text contains app_name
    for text, x1, y1, x2, y2 in boxes:
        if app_name.lower() in text.lower():
            label_cx = (x1 + x2) // 2
            label_cy = (y1 + y2) // 2
            toggle_x = x2 + TOGGLE_X_OFFSET
            toggle_y = label_cy
            log(f"  [T1 OCR] found '{text.strip()}' at ({x1},{y1})-({x2},{y2})")
            log(f"  [T1 OCR] clicking toggle at ({toggle_x},{toggle_y})")
            click_at(toggle_x, toggle_y)
            return True

    log(f"  [T1 OCR] '{app_name}' not found in any of {len(boxes)} text boxes")
    # dump some boxes for debugging
    for text, x1, y1, x2, y2 in boxes[:10]:
        log(f"    text='{text[:40]}' at ({x1},{y1})-({x2},{y2})")
    return False


# ============================================================================
#  TIER 2 — OmniParser-v2.0 YOLO icon detector (41 MB)
# ============================================================================

_omniparser_model = None


def _load_omniparser():
    global _omniparser_model
    if _omniparser_model is not None:
        return _omniparser_model
    try:
        from ultralytics import YOLO  # type: ignore
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        log(f"  [T2 YOLO] deps missing: {e}")
        return None
    try:
        log("  [T2 YOLO] downloading icon_detect model (40.6 MB)...")
        model_path = hf_hub_download(
            repo_id="microsoft/OmniParser-v2.0",
            filename="icon_detect/model.pt",
        )
        log(f"  [T2 YOLO] loading model from {model_path}")
        _omniparser_model = YOLO(model_path)
        return _omniparser_model
    except Exception as e:
        log(f"  [T2 YOLO] load failed: {e}")
        return None


def tier2_find_and_click(img_path: str, app_name: str) -> bool:
    """Use OmniParser YOLO to find all clickable elements, then click the
    one nearest to (and to the right of) the app_name label (found via OCR)."""
    model = _load_omniparser()
    if model is None:
        return False

    log("  [T2 YOLO] detecting UI elements...")
    try:
        results = model(img_path, conf=0.3, verbose=False)
        if not results or len(results) == 0:
            log("  [T2 YOLO] no elements detected")
            return False
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            log("  [T2 YOLO] no boxes")
            return False
    except Exception as e:
        log(f"  [T2 YOLO] inference failed: {e}")
        return False

    # get pixel coords of all detected clickable elements
    element_centers = []
    for box in boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
        element_centers.append((cx, cy, x1, y1, x2, y2))
    log(f"  [T2 YOLO] detected {len(element_centers)} clickable elements")

    # find the app_name label via OCR to know where to aim
    ocr_boxes = _vision_ocr(img_path)
    label_center = None
    for text, x1, y1, x2, y2 in ocr_boxes:
        if app_name.lower() in text.lower():
            label_center = ((x1 + x2) // 2, (y1 + y2) // 2, x2)
            break

    if label_center is None:
        log(f"  [T2 YOLO] can't find '{app_name}' label via OCR — clicking topmost element")
        # fallback: click the first element
        cx, cy, *_ = element_centers[0]
        click_at(cx, cy)
        return True

    label_cx, label_cy, label_right = label_center
    # find the element closest to (label_right + offset, label_cy)
    best = None
    best_dist = 1e9
    for cx, cy, *_ in element_centers:
        if cx < label_right:  # must be to the right of the label
            continue
        dist = abs(cx - (label_right + TOGGLE_X_OFFSET)) + abs(cy - label_cy)
        if dist < best_dist:
            best_dist = dist
            best = (cx, cy)

    if best is None:
        log("  [T2 YOLO] no element found to the right of the label")
        return False

    log(f"  [T2 YOLO] clicking element at {best} (dist={best_dist:.0f})")
    click_at(*best)
    return True


# ============================================================================
#  TIER 3 — moondream2 (1.86B VLM, native point: API)
# ============================================================================

_moondream_model = None
_moondream_answer = None


def _load_moondream():
    global _moondream_model, _moondream_answer
    if _moondream_model is not None:
        return _moondream_model, _moondream_answer
    try:
        import torch  # type: ignore
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
    except ImportError as e:
        log(f"  [T3 moondream] deps missing: {e}")
        return None, None
    try:
        log("  [T3 moondream] loading vikhyatk/moondream2 (1.86B, ~3.7 GB)...")
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if device == "mps" else torch.float32
        model_id = "vikhyatk/moondream2"
        _moondream_model = AutoModelForCausalLM.from_pretrained(
            model_id, trust_remote_code=True, torch_dtype=dtype,
        ).to(device)
        _moondream_answer = type("A", (), {"__call__": lambda self, q: _md_answer(q)})
        _moondream_model.eval()
        log(f"  [T3 moondream] ready on {device}")
        return _moondream_model, _moondream_answer
    except Exception as e:
        log(f"  [T3 moondream] load failed: {e}")
        return None, None


def _md_answer(question: str):
    """Placeholder — moondream2's API is via model.answer_question(question, image)."""
    return None


def tier3_find_and_click(img_path: str, app_name: str) -> bool:
    """Use moondream2's <point> API to find where to click."""
    model, _ = _load_moondream()
    if model is None:
        return False
    try:
        from PIL import Image  # type: ignore
        img = Image.open(img_path).convert("RGB")

        # moondream2's point: API returns normalized [x, y] in [0,1]
        log(f"  [T3 moondream] asking: point to the toggle switch for {app_name}")
        # The model.answer_question signature:
        #   answer_question(question, image, tokenizer=None, **kwargs)
        # We use the <point> instruction in the prompt.
        prompt = f"<point> the toggle switch that controls {app_name}'s permission"
        encoded = model.encode_image(img)
        answer = model.answer_question(
            model.encode_question(prompt),
            encoded,
        )
        log(f"  [T3 moondream] raw answer: {answer}")

        # parse coordinates from answer like "[0.85, 0.42]" or "x: 0.85, y: 0.42"
        m = re.search(r"\[?([0-9]*\.?[0-9]+)\s*[, ]\s*([0-9]*\.?[0-9]+)\]?", answer or "")
        if not m:
            log(f"  [T3 moondream] could not parse coords from: {answer!r}")
            return False
        x_rel, y_rel = float(m.group(1)), float(m.group(2))
        # moondream returns normalized [0,1] relative to image size
        x = int(x_rel * img.width)
        y = int(y_rel * img.height)
        log(f"  [T3 moondream] clicking ({x},{y})")
        click_at(x, y)
        return True
    except Exception as e:
        log(f"  [T3 moondream] failed: {e}")
        return False


# ============================================================================
#  verification + file-picker helpers
# ============================================================================

def verify_toggle_on(app_name: str, img_path: str) -> bool:
    """Check if the toggle next to app_name is ON (blue) by sampling pixels
    at the expected toggle position."""
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return False
    boxes = _vision_ocr(img_path)
    for text, x1, y1, x2, y2 in boxes:
        if app_name.lower() in text.lower():
            toggle_x = x2 + TOGGLE_X_OFFSET
            toggle_y = (y1 + y2) // 2
            img = Image.open(img_path).convert("RGB")
            # sample a small region
            r_sum = g_sum = b_sum = n = 0
            for dx in range(-10, 11, 2):
                for dy in range(-5, 6, 2):
                    px = img.getpixel((max(0, min(img.width - 1, toggle_x + dx)),
                                       max(0, min(img.height - 1, toggle_y + dy))))
                    r_sum += px[0]; g_sum += px[1]; b_sum += px[2]; n += 1
            r, g, b = r_sum / n, g_sum / n, b_sum / n
            log(f"  verify: toggle pixel @({toggle_x},{toggle_y}) RGB=({r:.0f},{g:.0f},{b:.0f})")
            # macOS ON toggle is blue (#0A84FF-ish): high blue, b > r, b > g
            return b > 120 and b > r + 15 and b > g + 15
    return False


def add_app_via_filepicker(app_path: str, app_name: str) -> bool:
    """Drive the + button + file picker to add an app to a privacy list."""
    log("  app not in list — driving + file picker")
    # click the + button (bottom of the list) — find it via OCR "+"
    shot = screenshot()
    boxes = _vision_ocr(shot)
    for text, x1, y1, x2, y2 in boxes:
        if text.strip() in ("+", "Add", "添加"):
            click_at((x1 + x2) // 2, (y1 + y2) // 2)
            time.sleep(2)
            break
    else:
        # fallback: click near the bottom-left of the list area
        click_at(400, 500)
        time.sleep(2)

    # Cmd+Shift+G to open the Go to folder sheet
    key_combo_g()
    type_text(app_path)
    key_return()
    time.sleep(1.2)
    # click Open (or press Return)
    if not _click_button_by_text("Open"):
        key_return()
    time.sleep(1.0)
    log(f"  added {app_name} via file picker")
    return True


def _click_button_by_text(button_text: str) -> bool:
    """Find a button by its text via OCR, click it."""
    shot = screenshot()
    boxes = _vision_ocr(shot)
    for text, x1, y1, x2, y2 in boxes:
        if button_text.lower() in text.lower():
            click_at((x1 + x2) // 2, (y1 + y2) // 2)
            return True
    return False


def dismiss_quit_reopen() -> None:
    """Click 'Later' on the Quit & Reopen sheet if present."""
    for _ in range(3):
        if _click_button_by_text("Later"):
            return
        time.sleep(0.5)


# ============================================================================
#  main — the 3-tier loop
# ============================================================================

def main() -> int:
    log(f"service={SERVICE}  goal={GOAL[:80]}...")
    if not GOAL:
        die("GUI_AGENT_GOAL env var is empty")

    if subprocess.run(["which", "cliclick"], capture_output=True).returncode != 0:
        die("cliclick not found — brew install cliclick first")

    open_pane(PANE_URL)

    success = False
    for step in range(MAX_STEPS):
        log(f"--- step {step + 1}/{MAX_STEPS} ---")
        shot = screenshot()

        # 0. already done?
        if verify_toggle_on(APP_NAME, shot):
            log("toggle is already ON — done")
            success = True
            break

        # TIER 1: Apple Vision OCR + fixed offset
        if tier1_find_and_click(shot, APP_NAME):
            time.sleep(1.8)
            dismiss_quit_reopen()
            shot2 = screenshot()
            if verify_toggle_on(APP_NAME, shot2):
                log("TIER 1 (OCR) succeeded — toggle ON")
                success = True
                break
            log("TIER 1 clicked but toggle not confirmed ON — trying TIER 2")
            shot = shot2

        # TIER 2: OmniParser YOLO
        if tier2_find_and_click(shot, APP_NAME):
            time.sleep(1.8)
            dismiss_quit_reopen()
            shot3 = screenshot()
            if verify_toggle_on(APP_NAME, shot3):
                log("TIER 2 (YOLO) succeeded — toggle ON")
                success = True
                break
            log("TIER 2 clicked but toggle not confirmed ON — trying TIER 3")
            shot = shot3

        # TIER 3: moondream2 VLM
        if tier3_find_and_click(shot, APP_NAME):
            time.sleep(1.8)
            dismiss_quit_reopen()
            shot4 = screenshot()
            if verify_toggle_on(APP_NAME, shot4):
                log("TIER 3 (moondream2) succeeded — toggle ON")
                success = True
                break

        # all tiers failed — maybe the app isn't in the list yet
        log("all 3 tiers failed — trying to add app via + file picker")
        if add_app_via_filepicker(APP_PATH, APP_NAME):
            time.sleep(1.5)
            # retry from the top
            continue

        time.sleep(1.0)

    if success:
        log("SUCCESS — permission appears granted")
        return 0
    die(f"could not grant {SERVICE} within {MAX_STEPS} steps")
    return 1


if __name__ == "__main__":
    sys.exit(main())
