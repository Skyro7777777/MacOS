#!/usr/bin/env python3
"""
 =============================================================================
  mac_showui_agent.py  —  LOCAL vision agent for granting macOS 15 TCC
  permissions to RustDesk when osascript's deterministic click-through cannot
  find the element (UI hierarchy drift, or RustDesk is not yet in the list and
  the "+" file-picker needs driving).

  MODEL:  showlab/ShowUI-2B  (https://huggingface.co/showlab/ShowUI-2B)
          ~2B params, ~4.2 GB.  Runs LOCALLY — no API key, no OpenAI, no relay.
          On the GitHub macos-15 (Apple Silicon M1) runner it uses MPS (fp16);
          falls back to CPU fp32 if MPS is unavailable.

  CRITICAL PERMISSION TRICK — "responsible process" inheritance:
    We NEVER call CGWindowListCreateImage / CGEventCreate inside the Python
    process.  Instead we shell out to the system binaries:
        screencapture  ->  inherits bash's Screen Recording  (sees the screen)
        cliclick       ->  inherits bash's Accessibility      (injects input)
    Both are TCC-attributed to bash, which the runner already grants.
    (mss / PIL.ImageGrab / pyautogui / pynput would need their OWN TCC grants
     and would fail — we deliberately avoid them.)

  ENV VARS (set by mac_03_grant_permissions.sh):
    SHOWUI_GOAL           — natural-language description of what to click
    SHOWUI_PANE_URL       — deep-link URL of the privacy pane to open
    SHOWUI_SERVICE        — kTCCService* name (for logging)
    SHOWUI_HELPER_USER    — helper username (for password prompts, if any)
    SHOWUI_HELPER_PASSWORD— helper password (for password prompts, if any)
    SHOWUI_DIR            — (optional) custom model cache dir
    SHOWUI_MAX_STEPS      — (optional) max grounding steps, default 25
 =============================================================================
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# --- model setup -------------------------------------------------------------

MODEL_ID = os.environ.get("SHOWUI_MODEL", "showlab/ShowUI-2B")
LOCAL_DIR = os.environ.get("SHOWUI_DIR", str(Path.home() / ".cache" / "showui-2b"))
MAX_STEPS = int(os.environ.get("SHOWUI_MAX_STEPS", "25"))
PANE_URL = os.environ.get("SHOWUI_PANE_URL", "")
GOAL = os.environ.get("SHOWUI_GOAL", "")
SERVICE = os.environ.get("SHOWUI_SERVICE", "unknown")
HELPER_USER = os.environ.get("SHOWUI_HELPER_USER", "")
HELPER_PASSWORD = os.environ.get("SHOWUI_HELPER_PASSWORD", "")

SHOTS_DIR = Path("/tmp/apple-project/showui-shots")
SHOTS_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(f"    [showui] {msg}", flush=True)


def die(msg: str, code: int = 1) -> None:
    print(f"    [showui][FAIL] {msg}", flush=True)
    sys.exit(code)


# --- lazy model load (only when actually needed) -----------------------------

_model = None
_processor = None
_device = None
_min_px = 256 * 28 * 28
_max_px = 1344 * 28 * 28


def load_model():
    global _model, _processor, _device
    if _model is not None:
        return
    log(f"loading {MODEL_ID} (cache={LOCAL_DIR}) ...")
    import torch  # noqa: WPS433
    from PIL import Image  # noqa: WPS433
    from transformers import AutoProcessor, Qwen2VLForConditionalGeneration  # noqa: WPS433

    if torch.backends.mps.is_available():
        _device = "mps"
        dtype = torch.float16
    elif torch.cuda.is_available():
        _device = "cuda"
        dtype = torch.float16
    else:
        _device = "cpu"
        dtype = torch.float32
    log(f"device={_device} dtype={dtype}")

    # NOTE: device_map="mps" is not reliably supported across accelerate
    # versions; load on CPU then .to(device) — works everywhere (MPS/CUDA/CPU).
    _model = Qwen2VLForConditionalGeneration.from_pretrained(
        MODEL_ID,
        cache_dir=LOCAL_DIR,
        torch_dtype=dtype,
    )
    _model.to(_device)
    _model.eval()
    _processor = AutoProcessor.from_pretrained(
        MODEL_ID, cache_dir=LOCAL_DIR, min_pixels=_min_px, max_pixels=_max_px
    )
    log("model ready")


# --- screen + input helpers (all shell-out, for TCC inheritance) -------------

def screenshot(path: str = None) -> str:
    """Capture the screen via the system `screencapture` binary.
    Inheriting bash's Screen Recording permission — no Python TCC needed."""
    if path is None:
        path = str(SHOTS_DIR / f"shot_{int(time.time() * 1000)}.png")
    # -x no sound, -C include cursor
    subprocess.run(["screencapture", "-x", "-C", path], check=True)
    return path


def click_at(x: int, y: int) -> None:
    """Click via `cliclick` — inherits bash's Accessibility permission."""
    subprocess.run(["cliclick", f"c:{x},{y}"], check=True)
    time.sleep(0.4)


def double_click_at(x: int, y: int) -> None:
    subprocess.run(["cliclick", f"dc:{x},{y}"], check=True)
    time.sleep(0.4)


def type_text(text: str) -> None:
    subprocess.run(["cliclick", f"t:{text}"], check=True)
    time.sleep(0.2)


def key_combo(mod: str, key: str) -> None:
    """e.g. key_combo('cmd','g').  Uses cliclick's key-stroke syntax."""
    # cliclick kp:cmd+a  then  kt:return  is fiddly; use osascript for combos
    subprocess.run(
        ["osascript", "-e",
         f'tell application "System Events" to key code {keycode_for(key)} using {mod} down'],
        check=False,
    )
    time.sleep(0.3)


def keycode_for(key: str) -> str:
    table = {
        "return": "36", "enter": "36", "tab": "48", "space": "49",
        "escape": "53", "delete": "51", "g": "5", "a": "0",
        "up": "126", "down": "125", "left": "123", "right": "124",
    }
    return table.get(key.lower(), "36")


def open_pane(url: str) -> None:
    if url:
        log(f"opening pane: {url}")
        subprocess.run(["open", url], check=False)
        time.sleep(3)


# --- ShowUI-2B grounding -----------------------------------------------------

SYS_PROMPT = (
    "Based on the screenshot of the page, I give a text description and you "
    "give its corresponding location. The coordinate represents a clickable "
    "location [x, y] for an element, which is a relative coordinate on the "
    "screenshot, scaled from 0 to 1."
)


def ground(query: str, img_path: str):
    """Ask ShowUI-2B to find a clickable [x_rel, y_rel] in [0,1] for `query`.
    Returns (x_rel, y_rel) or None."""
    load_model()
    import torch  # noqa: WPS433
    from PIL import Image  # noqa: WPS433
    from qwen_vl_utils import process_vision_info  # noqa: WPS433

    img = Image.open(img_path).convert("RGB")
    messages = [{"role": "user", "content": [
        {"type": "text", "text": SYS_PROMPT},
        {"type": "image", "image": img, "min_pixels": _min_px, "max_pixels": _max_px},
        {"type": "text", "text": query},
    ]}]
    text = _processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, _ = process_vision_info(messages)
    inputs = _processor(
        text=[text], images=image_inputs, padding=True, return_tensors="pt"
    ).to(_device)
    with torch.no_grad():
        out = _model.generate(**inputs, max_new_tokens=128)
    out_ids = [o[len(i):] for i, o in zip(inputs.input_ids, out)]
    txt = _processor.batch_decode(out_ids, skip_special_tokens=True,
                                  clean_up_tokenization_spaces=False)[0].strip()
    # parse "[x, y]" or "x, y"
    m = re.search(r"\[?([0-9]*\.?[0-9]+)\s*,\s*([0-9]*\.?[0-9]+)\]?", txt)
    if not m:
        log(f"  grounding parse FAIL: {txt!r}")
        return None
    try:
        x_rel, y_rel = float(m.group(1)), float(m.group(2))
    except ValueError:
        return None
    # sanity: ShowUI-2B sometimes emits pixel coords instead of [0,1];
    # if both > 1.5, assume pixels and normalise using image size.
    if x_rel > 1.5 or y_rel > 1.5:
        x_rel /= img.width
        y_rel /= img.height
    return (x_rel, y_rel, img.width, img.height, txt)


def ask_yes_no(question: str, img_path: str) -> bool:
    """Ask a yes/no visual question.  ShowUI-2B is a grounding model, so we
    frame it as: 'find the element that indicates YES <question>'.  If it
    returns coords near a visible checkmark/blue toggle, we treat as yes."""
    # This is a simplification; for robust yes/no we'd use a VLM chat model.
    # For now: re-ground the target and check the toggle colour via pixel sniff.
    return False  # callers use verify_toggle instead


def verify_toggle_on(app_name: str, img_path: str) -> bool:
    """Heuristic: find the toggle next to app_name; sample a pixel at its
    centre; a blue (ON) toggle has high blue channel, a grey (OFF) toggle has
    low saturation.  Returns True if ON."""
    res = ground(f"the toggle switch immediately to the right of {app_name}", img_path)
    if not res:
        return False
    x_rel, y_rel, w, h, _ = res
    x, y = int(x_rel * w), int(y_rel * h)
    from PIL import Image  # noqa: WPS433
    img = Image.open(img_path).convert("RGB")
    # sample a small region around the toggle centre
    r_sum = g_sum = b_sum = 0
    n = 0
    for dx in range(-6, 7, 2):
        for dy in range(-4, 5, 2):
            px = img.getpixel((max(0, min(w - 1, x + dx)), max(0, min(h - 1, y + dy))))
            r_sum += px[0]; g_sum += px[1]; b_sum += px[2]; n += 1
    r, g, b = r_sum / n, g_sum / n, b_sum / n
    log(f"  toggle pixel @({x},{y}) avg RGB=({r:.0f},{g:.0f},{b:.0f})")
    # macOS "ON" toggle is blue (#0A84FF-ish on Sequoia): high blue, b>r, b>g
    return b > 120 and b > r + 15 and b > g + 15


# --- high-level actions ------------------------------------------------------

def click_and_wait(query: str, wait: float = 1.5) -> bool:
    """Ground `query` on the current screen, click it, wait.  Returns True on success."""
    shot = screenshot()
    res = ground(query, shot)
    if not res:
        log(f"  could not find: {query!r}")
        return False
    x_rel, y_rel, w, h, raw = res
    x, y = int(x_rel * w), int(y_rel * h)
    log(f"  found {query!r} -> ({x},{y})  [raw={raw!r}]")
    click_at(x, y)
    time.sleep(wait)
    return True


def add_app_via_filepicker(app_path: str, app_name: str) -> bool:
    """Drive the '+' button + file picker to add an app to a privacy list.
    Uses Cmd+Shift+G 'Go to folder' for reliability (no need to navigate)."""
    log("app not in list — driving + file picker")
    if not click_and_wait("the plus + button at the bottom of the app list", 2.0):
        log("  could not click + — aborting filepicker")
        return False
    # file picker is open; jump straight to the path with Cmd+Shift+G
    subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke "g" using {command down, shift down}'],
                   check=False)
    time.sleep(1.0)
    type_text(app_path)
    time.sleep(0.4)
    subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke return'], check=False)
    time.sleep(1.2)
    # now the app is selected in the picker; click Open
    if not click_and_wait("the Open button", 1.5):
        # fallback: press Return
        subprocess.run(["osascript", "-e",
                        'tell application "System Events" to keystroke return'], check=False)
        time.sleep(1.0)
    log(f"  added {app_name} via file picker")
    return True


def dismiss_quit_reopen() -> None:
    """Click 'Later' on the Quit & Reopen sheet if present."""
    for _ in range(3):
        if click_and_wait("the Later button", 0.6):
            return
        time.sleep(0.5)


# --- main --------------------------------------------------------------------

def main() -> int:
    log(f"service={SERVICE}  goal={GOAL[:80]}...")
    if not GOAL:
        die("SHOWUI_GOAL env var is empty")

    # ensure cliclick is available
    if subprocess.run(["which", "cliclick"], capture_output=True).returncode != 0:
        die("cliclick not found — brew install cliclick first")

    open_pane(PANE_URL)

    app_path = "/Applications/RustDesk.app"
    app_name = "RustDesk"

    success = False
    for step in range(MAX_STEPS):
        log(f"--- step {step + 1}/{MAX_STEPS} ---")
        shot = screenshot()

        # 1. is RustDesk already in the list with toggle ON?
        if verify_toggle_on(app_name, shot):
            log("toggle is ON — done")
            success = True
            break

        # 2. is RustDesk in the list at all?  try to click its toggle directly
        res = ground(f"the toggle switch next to {app_name}", shot)
        if res:
            x_rel, y_rel, w, h, raw = res
            log(f"  found {app_name} toggle at ({int(x_rel*w)},{int(y_rel*h)}) [raw={raw!r}]")
            click_at(int(x_rel * w), int(y_rel * h))
            time.sleep(1.8)
            dismiss_quit_reopen()
            # re-verify
            shot2 = screenshot()
            if verify_toggle_on(app_name, shot2):
                log("toggle now ON — done")
                success = True
                break
            log("toggle click did not confirm ON; retrying")
            continue

        # 3. RustDesk not in list — add via + file picker
        log(f"  {app_name} not found in list — adding via + file picker")
        if add_app_via_filepicker(app_path, app_name):
            time.sleep(1.5)
            # now toggle it
            shot3 = screenshot()
            res2 = ground(f"the toggle switch next to {app_name}", shot3)
            if res2:
                x_rel, y_rel, w, h, _ = res2
                click_at(int(x_rel * w), int(y_rel * h))
                time.sleep(1.8)
                dismiss_quit_reopen()
                shot4 = screenshot()
                if verify_toggle_on(app_name, shot4):
                    log("toggle ON after filepicker add — done")
                    success = True
                    break
        else:
            log("  filepicker flow failed — retrying whole step")
            time.sleep(1.0)

    if success:
        log("SUCCESS — permission appears granted")
        return 0
    die(f"could not grant {SERVICE} within {MAX_STEPS} steps")
    return 1


if __name__ == "__main__":
    sys.exit(main())
