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
#  WHY moondream2 (not OCR, not osascript AX, not ShowUI-2B):
#    - OCR needs screencapture → triggers Sequoia "bypass window picker" dialog
#      (the dialog blocks the screenshot, OCR finds wrong text)
#    - osascript AX can't find buttons in RustDesk (Flutter app, poor AX support)
#    - ShowUI-2B OOMs on the runner's 7.93 GiB MPS limit
#    - moondream2 (1.86B, ~4 GB RAM) fits comfortably + has native <point> API
#
#  The preauthorization (ScreenCaptureApprovals.plist) + dialog-dismissal loop
#  handle the bash popup so screencapture works for moondream2.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — grant TCC permissions via moondream2 VLM"

require_env MAC_USER_PASSWORD

# --- 0. start screenshot + dialog-dismissal loops ---------------------------
start_screenshot_loop
start_dialog_dismissal_loop

# --- 1. install cliclick if missing -----------------------------------------
if ! command -v cliclick >/dev/null 2>&1; then
  log "installing cliclick"
  brew install cliclick
fi

# --- 2. create the venv with ALL deps (torch + transformers + moondream2) ---
VENV_DIR="$STATE_DIR/moondream-venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  log "creating Python virtualenv at $VENV_DIR"
  python3 -m venv "$VENV_DIR" || die "could not create venv"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip wheel setuptools 2>&1 | tail -n1
fi

# install ALL deps — torch FIRST (biggest), then transformers + moondream2 deps
if ! "$VENV_DIR/bin/python" -c "import torch" 2>/dev/null; then
  log "installing torch (~2 GB, may take a minute)..."
  "$VENV_DIR/bin/python" -m pip install --quiet torch torchvision 2>&1 | tail -n3
fi
if ! "$VENV_DIR/bin/python" -c "import transformers" 2>/dev/null; then
  log "installing transformers + einops + timm + pillow..."
  "$VENV_DIR/bin/python" -m pip install --quiet \
      "transformers>=4.47.0" einops timm pillow huggingface_hub 2>&1 | tail -n3
fi
ok "venv ready: $($VENV_DIR/bin/python -c 'import torch, transformers; print(f"torch {torch.__version__}, transformers {transformers.__version__}")')"

# --- 3. launch the moondream2 agent -----------------------------------------
# The agent handles the entire flow: find Configure → click → find toggle →
# click → type password → find Later → click → repeat.
log "launching moondream2 agent (model downloads on first run, ~3.7 GB)"
MOONDREAM_SERVICE="all-permissions" \
MOONDREAM_PASSWORD="$MAC_USER_PASSWORD" \
MOONDREAM_MAX_STEPS="30" \
"$VENV_DIR/bin/python" "$PROJECT_ROOT/mac_moondream_agent.py" || {
  warn "moondream2 agent did not complete successfully"
  warn "check the screenshots artifact for the final state"
}

# --- 4. final state ---------------------------------------------------------
take_screenshot "03_final_state"
stop_screenshot_loop
stop_dialog_dismissal_loop
ok "permission pipeline complete"
