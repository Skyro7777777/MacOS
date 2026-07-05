#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh
#  Grant TCC permissions to RustDesk using moondream2 (local VLM, 1.86B).
#
#  THE APPROACH:
#  1. Open RustDesk → it shows a pink "Permissions" section with "Configure" button
#  2. moondream2 points to "Configure" → cliclick clicks it
#     → RustDesk adds itself to the privacy list + opens System Settings
#  3. moondream2 points to the toggle next to "RustDesk" → cliclick clicks it
#     → macOS shows a password prompt
#  4. moondream2 points to the password field → cliclick clicks it
#  5. Type MAC_USER_PASSWORD (from repo secrets) → press Return
#     → macOS grants the permission at the OS level
#  6. moondream2 points to "Later" → cliclick clicks it (dismiss "Quit & Reopen")
#  7. Repeat for each permission
#
#  CRITICAL VERSION PINS (from deep research, Task ID 30):
#    - Python 3.12 (NOT 3.14 — PyTorch doesn't fully support 3.14)
#    - transformers==4.56.1 (pinned — v4.57+/5.0 broke moondream2's
#      trust_remote_code via _tied_weights_keys → all_tied_weights_keys rename)
#    - torch>=2.7.0,<2.10
#    - moondream2 revision 2025-06-21 (has native point() API)
#
#  The preauthorization (ScreenCaptureApprovals.plist with 5 keys) +
#  dialog-dismissal loop (cliclick by coordinates) handle the bash popup
#  so screencapture works for moondream2.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — grant TCC permissions via moondream2 VLM"

require_env MAC_USER_PASSWORD

# --- 0. install cliclick FIRST (needed by dialog-dismissal loop) -------------
if ! command -v cliclick >/dev/null 2>&1; then
  log "installing cliclick (needed for dialog dismissal + AI clicking)"
  brew install cliclick
fi

# --- 0b. start screenshot + dialog-dismissal loops ---------------------------
# NOW cliclick is available for the dialog-dismissal loop to use.
start_screenshot_loop
start_dialog_dismissal_loop

# --- 2. ensure Python 3.12 is available -------------------------------------
# The runner's default python3 is 3.14 (too new for PyTorch). We need 3.12.
# Check if 3.12 is available (either as python3.12 or via setup-python).
PY312=""
if command -v python3.12 >/dev/null 2>&1; then
  PY312="$(command -v python3.12)"
elif [ -x "/Users/runner/hostedtoolcache/Python/3.12.10/arm64/bin/python3.12" ]; then
  PY312="/Users/runner/hostedtoolcache/Python/3.12.10/arm64/bin/python3.12"
elif /usr/bin/python3 -c "import sys; exit(0 if sys.version_info[:2] == (3,12) else 1)" 2>/dev/null; then
  PY312="/usr/bin/python3"
fi

if [ -z "$PY312" ]; then
  log "Python 3.12 not found — installing via Homebrew"
  brew install python@3.12
  PY312="$(command -v python3.12 2>/dev/null || echo /opt/homebrew/bin/python3.12)"
fi
ok "using Python: $PY312 ($($PY312 --version 2>&1))"

# --- 3. create the venv with Python 3.12 + ALL deps -------------------------
VENV_DIR="$STATE_DIR/moondream-venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  log "creating Python 3.12 virtualenv at $VENV_DIR"
  "$PY312" -m venv "$VENV_DIR" || die "could not create venv with $PY312"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip wheel setuptools 2>&1 | tail -n1
fi

# install ALL deps with EXACT version pins:
#   - transformers==4.56.1 (pinned — newer breaks moondream2 trust_remote_code)
#   - torch>=2.7.0,<2.10 (PyTorch with MPS support, not too new)
#   - accelerate, einops, Pillow, pyvips-binary, pyvips (moondream2 deps)
if ! "$VENV_DIR/bin/python" -c "import torch" 2>/dev/null; then
  log "installing torch>=2.7.0,<2.10 (~2 GB, may take a minute)..."
  "$VENV_DIR/bin/python" -m pip install --quiet "torch>=2.7.0,<2.10" torchvision 2>&1 | tail -n3
fi
if ! "$VENV_DIR/bin/python" -c "import transformers; assert transformers.__version__ == '4.56.1'" 2>/dev/null; then
  log "installing transformers==4.56.1 (PINNED for moondream2 compatibility)..."
  "$VENV_DIR/bin/python" -m pip install --quiet "transformers==4.56.1" 2>&1 | tail -n3
fi
if ! "$VENV_DIR/bin/python" -c "import accelerate, einops, pyvips" 2>/dev/null; then
  log "installing accelerate + einops + Pillow + pyvips..."
  "$VENV_DIR/bin/python" -m pip install --quiet \
      "accelerate>=1.10.0" "Pillow>=11.0.0" einops \
      "pyvips-binary==8.16.0" "pyvips==2.2.3" 2>&1 | tail -n3
fi
ok "venv ready: $($VENV_DIR/bin/python -c 'import torch, transformers; print(f"torch {torch.__version__}, transformers {transformers.__version__}")')"

# --- 3b. pre-download the moondream2 model with VISIBLE progress -------------
# Without this, the 3.7 GB download happens silently inside from_pretrained —
# the tqdm progress bar is hidden in CI (non-TTY shells don't render \r
# animation), so it looks like the script is hung for 5+ minutes.
# Pre-downloading with huggingface_hub shows progress in the GHA log.
log "pre-downloading moondream2 model (~3.7 GB) with progress bars..."
HF_HUB_DISABLE_PROGRESS_BARS=0 HF_HUB_ENABLE_HF_TRANSFER=0 \
"$VENV_DIR/bin/python" -c "
from huggingface_hub import snapshot_download
import sys
print('  downloading vikhyatk/moondream2 (rev=2025-06-21)...', flush=True)
print('  (if this seems stuck, it IS downloading — watch for progress bars)', flush=True)
snapshot_download(
    repo_id='vikhyatk/moondream2',
    revision='2025-06-21',
    repo_type='model',
)
print('  model cached successfully', flush=True)
" 2>&1 | while IFS= read -r line; do log "  $line"; done
ok "moondream2 model pre-downloaded"

# --- 4. launch the moondream2 agent -----------------------------------------
log "launching moondream2 agent (model loads from cache, ~15s)"
MOONDREAM_PASSWORD="$MAC_USER_PASSWORD" \
MOONDREAM_MAX_STEPS="30" \
"$VENV_DIR/bin/python" "$PROJECT_ROOT/mac_moondream_agent.py" || {
  warn "moondream2 agent did not complete successfully"
  warn "check the screenshots artifact for the final state"
}

# --- 5. final state ---------------------------------------------------------
take_screenshot "03_final_state"
stop_screenshot_loop
stop_dialog_dismissal_loop
ok "permission pipeline complete"
