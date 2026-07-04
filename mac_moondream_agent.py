#!/usr/bin/env python3
"""
 =============================================================================
  mac_moondream_agent.py  —  moondream2-based GUI agent for granting macOS 15
  TCC permissions to RustDesk.

  Uses vikhyatk/moondream2 revision 2025-06-21 (1.86B VLM, ~3.7 GB, ~4 GB RAM
  at fp16).  Fits comfortably in the GitHub macos-15 runner's 7.93 GiB MPS limit.

  moondream2 has a native point() API: ask it to point to something and it
  returns [{"x": 0.xx, "y": 0.xx}] normalized coordinates.

  REQUIRES:
    - Python 3.12 (NOT 3.14 — PyTorch doesn't fully support 3.14 yet)
    - transformers==4.56.1 (pinned — newer versions break moondream2's
      trust_remote_code due to _tied_weights_keys → all_tied_weights_keys rename)
    - torch>=2.7.0,<2.10
    - accelerate, einops, Pillow, pyvips-binary, pyvips

  ENV VARS:
    MOONDREAM_PASSWORD  — the MAC_USER_PASSWORD from secrets
    MOONDREAM_MAX_STEPS — max steps (default 30)
 =============================================================================
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

# --- DEFENSIVE MONKEYPATCH ---------------------------------------------------
# transformers v4.57+/5.0 renamed `_tied_weights_keys` → `all_tied_weights_keys`
# in modeling_utils.py:4776, but moondream2's trust_remote_code HfMoondream
# class only defines the old name. This monkeypatch makes the old attribute
# appear as the new name so loading works on ANY transformers version.
# (Insurance — we also pin transformers==4.56.1, but this protects against
# future upgrades.)
import torch
_orig_getattr = torch.nn.Module.__getattr__
def _patched_getattr(self, name):
    if name == "all_tied_weights_keys":
        return getattr(self, "_tied_weights_keys", {})
    return _orig_getattr(self, name)
torch.nn.Module.__getattr__ = _patched_getattr

MODEL_ID = os.environ.get("MOONDREAM_MODEL", "vikhyatk/moondream2")
MODEL_REV = os.environ.get("MOONDREAM_REV", "2025-06-21")
MAX_STEPS = int(os.environ.get("MOONDREAM_MAX_STEPS", "30"))
PASSWORD = os.environ.get("MOONDREAM_PASSWORD", "")

SHOTS_DIR = Path("/tmp/apple-project/moondream-shots")
SHOTS_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(f"    [moondream] {msg}", flush=True)


def die(msg: str, code: int = 1) -> None:
    print(f"    [moondream][FAIL] {msg}", flush=True)
    sys.exit(code)


# ============================================================================
#  screen + input helpers (shell-out for TCC inheritance)
# ============================================================================

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


def open_rustdesk() -> None:
    subprocess.run(["open", "-a", "RustDesk"], check=False)
    time.sleep(3)


def bring_to_front(app_name: str) -> None:
    subprocess.run(["osascript", "-e",
                    f'tell application "System Events" to set frontmost of (first process whose name is "{app_name}") to true'],
                   check=False)
    time.sleep(0.5)


# ============================================================================
#  moondream2 model (lazy load)
# ============================================================================

_model = None
_device = None


def load_model():
    global _model, _device
    if _model is not None:
        return
    from transformers import AutoModelForCausalLM

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

    log(f"loading {MODEL_ID} (rev={MODEL_REV}) ...")
    _model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        revision=MODEL_REV,
        trust_remote_code=True,
        dtype=dtype,
        device_map={"": _device},
    )
    _model.eval()
    log("model ready")


def point_to(query: str, img_path: str) -> tuple[int, int] | None:
    """Ask moondream2 to point to something in the image.
    Returns (x, y) in pixel coordinates, or None."""
    load_model()
    from PIL import Image
    img = Image.open(img_path).convert("RGB")
    log(f"  point_to: {query}")

    # moondream2 rev 2025-06-21 has a native point() API
    result = _model.point(img, query)
    points = result.get("points", [])
    if not points:
        log(f"  no points returned: {result}")
        return None

    pt = points[0]
    x_rel = pt["x"]
    y_rel = pt["y"]
    x = int(x_rel * img.width)
    y = int(y_rel * img.height)
    log(f"  -> pixel ({x}, {y})  [rel ({x_rel:.3f}, {y_rel:.3f}), img {img.width}x{img.height}]")
    return (x, y)


def ask_yes_no(question: str, img_path: str) -> bool:
    """Ask a yes/no question via moondream2's answer_question API."""
    load_model()
    from PIL import Image
    img = Image.open(img_path).convert("RGB")
    answer = _model.answer_question(img, question)
    log(f"  Q: {question}  A: {answer!r}")
    return bool(re.search(r"\byes\b", answer or "", re.IGNORECASE))


# ============================================================================
#  the permission-granting flow
# ============================================================================

def find_and_click(query: str, wait: float = 2.0) -> bool:
    """Take a screenshot, ask moondream to point to query, click it."""
    shot = screenshot()
    pt = point_to(query, shot)
    if not pt:
        return False
    click_at(*pt)
    time.sleep(wait)
    return True


def grant_permissions() -> bool:
    log("starting permission flow")

    for step in range(MAX_STEPS):
        log(f"=== step {step + 1}/{MAX_STEPS} ===")

        # 1. make sure RustDesk is open + in front
        bring_to_front("RustDesk")
        shot = screenshot()

        # 2. is there a "Configure" button visible?
        log("looking for 'Configure' button in RustDesk...")
        configure_pt = point_to("the Configure button in the pink permissions section", shot)
        if not configure_pt:
            # try a different phrasing
            configure_pt = point_to("the pink Configure button", shot)
        if not configure_pt:
            # maybe all permissions are granted already
            log("no Configure button found — checking if permissions are done")
            has_perms = ask_yes_no("Is there a pink Permissions section with a Configure button visible?", shot)
            if not has_perms:
                log("no pink Permissions section — all permissions appear granted!")
                return True
            continue

        # 3. click Configure
        log(f"clicking Configure at {configure_pt}")
        click_at(*configure_pt)
        time.sleep(4)  # wait for System Settings to open

        # 4. System Settings should now be open with RustDesk in the list
        bring_to_front("System Settings")
        time.sleep(1)
        shot2 = screenshot()

        # 5. find + click the toggle next to RustDesk
        log("looking for RustDesk's toggle switch...")
        toggle_pt = point_to("the toggle switch next to RustDesk", shot2)
        if not toggle_pt:
            toggle_pt = point_to("the toggle switch to the right of RustDesk", shot2)
        if toggle_pt:
            log(f"clicking toggle at {toggle_pt}")
            click_at(*toggle_pt)
            time.sleep(3)

            # 6. handle the password prompt
            shot3 = screenshot()
            log("looking for password field...")
            has_pw = ask_yes_no("Is there a password input field visible?", shot3)
            if has_pw:
                log("typing password...")
                pw_pt = point_to("the password input field", shot3)
                if pw_pt:
                    click_at(*pw_pt)
                    time.sleep(0.3)
                type_text(PASSWORD)
                time.sleep(0.5)
                press_return()
                time.sleep(2)

                # 7. click "Modify Settings" if it appears
                shot4 = screenshot()
                ms_pt = point_to("the Modify Settings button", shot4)
                if ms_pt:
                    log(f"clicking Modify Settings at {ms_pt}")
                    click_at(*ms_pt)
                    time.sleep(2)

            # 8. handle "Quit & Reopen" → click "Later"
            shot5 = screenshot()
            log("looking for 'Later' button...")
            later_pt = point_to("the Later button", shot5)
            if later_pt:
                log(f"clicking Later at {later_pt}")
                click_at(*later_pt)
                time.sleep(2)
            else:
                # maybe it's "Quit & Reopen" — click that instead and reopen
                qr_pt = point_to("the Quit and Reopen button", shot5)
                if qr_pt:
                    log(f"clicking Quit & Reopen at {qr_pt}")
                    click_at(*qr_pt)
                    time.sleep(3)
                    open_rustdesk()

            log("permission cycle complete — checking for more...")
            continue
        else:
            log("could not find the toggle — retrying")
            continue

        time.sleep(2)

    log(f"reached max steps ({MAX_STEPS}) — stopping")
    return False


def main() -> int:
    if not PASSWORD:
        die("MOONDREAM_PASSWORD env var is empty")

    if subprocess.run(["which", "cliclick"], capture_output=True).returncode != 0:
        die("cliclick not found")

    ok_flag = grant_permissions()
    if ok_flag:
        log("SUCCESS — all permissions appear granted")
        return 0
    die("could not grant all permissions")
    return 1


if __name__ == "__main__":
    sys.exit(main())
