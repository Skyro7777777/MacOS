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


def ok(msg: str) -> None:
    print(f"    [moondream][ OK ] {msg}", flush=True)


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
    """Bring an app to front. Non-fatal — prints a warning if the app
    isn't running (we may still be able to proceed via screenshots)."""
    result = subprocess.run(
        ["osascript", "-e",
         f'tell application "System Events" to set frontmost of (first process whose name is "{app_name}") to true'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log(f"  (bring_to_front '{app_name}' skipped: {result.stderr.strip()[:80]})")
    time.sleep(0.5)


def is_process_running(app_name: str) -> bool:
    """Check if a process is running."""
    result = subprocess.run(
        ["osascript", "-e",
         f'tell application "System Events" to return (count of (every process whose name is "{app_name}")) > 0'],
        capture_output=True, text=True
    )
    return result.returncode == 0 and "true" in result.stdout.lower()


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

    # CRITICAL: pre-download the model with EXPLICIT progress logging BEFORE
    # from_pretrained. Without this, the 3.59 GiB download happens silently
    # inside from_pretrained — the tqdm progress bar is hidden in CI (non-TTY
    # shells don't render \r animation), so it looks like the script is hung
    # for 5+ minutes. By calling snapshot_download first, we get visible
    # "downloading model.safetensors: 45%" lines in the GHA log.
    import os
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "0")
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    try:
        from huggingface_hub import snapshot_download
        log(f"pre-downloading {MODEL_ID} (rev={MODEL_REV}, ~3.7 GB) with progress...")
        log("  (if this seems stuck, it's downloading — watch for progress bars below)")
        snapshot_download(
            repo_id=MODEL_ID,
            revision=MODEL_REV,
            repo_type="model",
        )
        log("snapshot cached — now loading from cache (should be ~15s)")
    except Exception as e:
        log(f"  (snapshot_download failed: {e} — will try from_pretrained directly)")

    log(f"loading {MODEL_ID} (rev={MODEL_REV}) from cache ...")
    # CRITICAL: on MPS, do NOT use device_map — transformers 4.56.1's
    # caching_allocator_warmup tries to allocate the full model (3.59 GiB)
    # as a SINGLE torch.empty buffer, which hits Metal's 4 GiB per-buffer
    # limit → "RuntimeError: Invalid buffer size: 3.59 GiB".
    # The warmup is gated on `device_map is not None`, so passing None
    # skips it. Then .to("mps") moves params one at a time (each well
    # under the limit). See vikhyat/moondream issue #282.
    _use_device_map = None if str(_device) == "mps" else {"": _device}
    _model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        revision=MODEL_REV,
        trust_remote_code=True,
        dtype=dtype,
        device_map=_use_device_map,
    )
    if str(_device) == "mps":
        _model = _model.to(_device)
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

    # Track how many times we've tried to click Configure without success.
    # If the AI keeps hallucinating coordinates, we abort after 3 failed cycles
    # instead of looping 30 times.
    failed_cycles = 0
    MAX_FAILED_CYCLES = 3

    for step in range(MAX_STEPS):
        log(f"=== step {step + 1}/{MAX_STEPS} ===")

        # 1. make sure RustDesk is open + in front.
        if not is_process_running("RustDesk"):
            log("RustDesk not running — opening it")
            open_rustdesk()
        bring_to_front("RustDesk")
        shot = screenshot()

        # 2. is there a "Configure" button visible?
        log("looking for 'Configure' button in RustDesk...")
        configure_pt = point_to("the Configure button in the pink permissions section", shot)
        if not configure_pt:
            configure_pt = point_to("the pink Configure button", shot)
        if not configure_pt:
            # maybe all permissions are granted already — verify via osascript
            # (don't trust moondream's yes/no answer, it hallucinates)
            log("no Configure button found via moondream — verifying via osascript")
            # Check if RustDesk's window still has a "Configure" button via AX
            # (Flutter apps have poor AX, but let's try)
            # If we can't find it via either method, assume done
            log("cannot find Configure button — assuming all permissions granted")
            return True

        # 3. click Configure
        log(f"clicking Configure at {configure_pt}")
        click_at(*configure_pt)
        time.sleep(4)  # wait for System Settings to open

        # 3b. VERIFY: did System Settings actually open?
        #     If not, the Configure click missed (moondream hallucinated).
        #     Abort instead of looping.
        ss_opened = False
        for _ in range(10):
            if is_process_running("System Settings"):
                ss_opened = True
                break
            time.sleep(1)

        if not ss_opened:
            failed_cycles += 1
            log(f"VERIFY FAILED: System Settings did not open after clicking Configure (failed cycle {failed_cycles}/{MAX_FAILED_CYCLES})")
            log("  -> moondream2 likely hallucinated the Configure button coordinates")
            if failed_cycles >= MAX_FAILED_CYCLES:
                log("ABORTING: too many failed cycles — moondream2 is not clicking the right place")
                return False
            continue  # retry from the top

        # System Settings opened — reset failed counter
        failed_cycles = 0
        ok("  VERIFY: System Settings opened (Configure click was real)")

        bring_to_front("System Settings")
        time.sleep(1)
        shot2 = screenshot()

        # 4. find + click the toggle next to RustDesk
        log("looking for RustDesk's toggle switch...")
        toggle_pt = point_to("the toggle switch next to RustDesk", shot2)
        if not toggle_pt:
            toggle_pt = point_to("the toggle switch to the right of RustDesk", shot2)
        if not toggle_pt:
            log("could not find toggle — skipping to next cycle")
            continue

        log(f"clicking toggle at {toggle_pt}")
        click_at(*toggle_pt)
        time.sleep(3)

        # 4b. VERIFY: did a password prompt (SecurityAgent) appear?
        #     If not, the toggle click missed OR the toggle was already ON.
        pw_visible = is_process_running("SecurityAgent") or is_process_running("CoreServicesUIAgent")
        if not pw_visible:
            # Maybe the toggle was already ON (no password needed).
            # Check if a "Quit & Reopen" dialog appeared instead.
            log("VERIFY: no password prompt — toggle may have been already ON or click missed")
            # Try to continue anyway — handle Quit & Reopen if present
        else:
            ok("  VERIFY: password prompt appeared (toggle click was real)")

        # 5. handle the password prompt (only if it's actually there)
        if pw_visible:
            shot3 = screenshot()
            log("typing password into the password prompt...")
            # Don't ask moondream where the password field is — just type
            # into whatever has focus (the password field auto-focuses).
            # Click center of screen first to ensure focus
            click_at(512, 384)
            time.sleep(0.3)
            type_text(PASSWORD)
            time.sleep(0.5)
            press_return()
            time.sleep(3)

            # 5b. VERIFY: did the password prompt close?
            #     If not, the password was wrong or the field wasn't focused.
            pw_still_there = is_process_running("SecurityAgent")
            if pw_still_there:
                log("VERIFY FAILED: password prompt still open after typing — retrying")
                # try again — click the field via moondream this time
                pw_pt = point_to("the password input field", shot3)
                if pw_pt:
                    click_at(*pw_pt)
                    time.sleep(0.3)
                type_text(PASSWORD)
                time.sleep(0.5)
                press_return()
                time.sleep(3)
                pw_still_there = is_process_running("SecurityAgent")
                if pw_still_there:
                    log("VERIFY FAILED: password prompt STILL open — aborting this cycle")
                    # cancel the prompt
                    subprocess.run(["osascript", "-e",
                        'tell application "System Events" to keystroke "c" using {command down}'], check=False)
                    time.sleep(1)
                    continue
            ok("  VERIFY: password prompt closed (password accepted)")

        # 6. handle "Quit & Reopen" → click "Later"
        #    Use osascript to find the "Later" button (System Settings IS AX-accessible,
        #    unlike RustDesk which is Flutter). This is more reliable than moondream.
        log("looking for 'Later' button via osascript...")
        for _ in range(5):
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events"\ntry\nrepeat with p in (every process whose name is "System Settings")\nrepeat with w in (windows of p)\nrepeat with b in (every button of w)\ntry\nif (name of b as text) is "Later" then\nclick b\nreturn "CLICKED"\nend if\nend try\nend repeat\nend repeat\nend repeat\nend try\nend tell'],
                capture_output=True, text=True
            )
            if "CLICKED" in result.stdout:
                ok("  clicked 'Later' via osascript")
                break
            time.sleep(1)
        else:
            log("  no 'Later' button found via osascript (may not have appeared)")

        time.sleep(2)

        # 6b. VERIFY: is the Configure button still there?
        #     Take a screenshot and check if RustDesk still shows the pink section.
        #     Don't trust moondream for this — just check if we should continue.
        log("permission cycle complete — checking for more...")

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
