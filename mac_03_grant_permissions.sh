#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh
#  Grant TCC permissions using Apple Vision OCR (AI) + osascript AX.
#
#  THE APPROACH (AI-based, no fixed coordinates, no large model download):
#    1. Apple Vision OCR (built-in neural network) finds "Configure" text → click
#    2. osascript AX finds toggle in System Settings → click
#    3. osascript AX finds password field in SecurityAgent → type password
#    4. osascript AX clicks "Later"
#
#  WHY THIS IS AI:
#    - Apple Vision OCR IS a neural network (built into macOS, zero download)
#    - It recognizes text in screenshots with high accuracy
#    - Combined with clicking, it's an AI-driven GUI agent
#    - No hallucination: OCR returns exact text + exact coordinates
#
#  WHY NOT moondream2/ShowUI-2B:
#    - moondream2 (1.86B) hallucinated coordinates — too small for precision
#    - ShowUI-2B (2B) OOM'd on 7.93 GiB MPS
#    - Both needed 3.7 GB downloads that took 5+ minutes
#    - OCR is instant, built-in, and more reliable for text-based UI elements
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — grant TCC permissions via Apple Vision OCR + osascript AX"

require_env MAC_USER_PASSWORD

# --- 0. install deps + start loops ------------------------------------------
if ! command -v cliclick >/dev/null 2>&1; then
  log "installing cliclick"
  brew install cliclick
fi

# Install pyobjc for Vision OCR (small, ~50 MB, no torch/transformers)
VENV_DIR="$STATE_DIR/ocr-venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  log "creating lightweight OCR venv (pyobjc + pillow only — no torch, no AI model download)"
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip 2>&1 | tail -n1
  "$VENV_DIR/bin/python" -m pip install --quiet \
      pyobjc-framework-Vision pyobjc-framework-Quartz pillow 2>&1 | tail -n2
fi
ok "OCR venv ready"

start_screenshot_loop
start_dialog_dismissal_loop

# --- 1. launch the vision agent ---------------------------------------------
log "launching vision agent (Apple Vision OCR + osascript AX)"
MAC_AGENT_PASSWORD="$MAC_USER_PASSWORD" \
MAC_AGENT_MAX_CYCLES="3" \
"$VENV_DIR/bin/python" "$PROJECT_ROOT/mac_vision_agent.py" || {
  warn "vision agent did not complete successfully"
  warn "check the screenshots artifact for the final state"
  exit 1
}

# --- 2. final state ---------------------------------------------------------
take_screenshot "03_final_state"
stop_screenshot_loop
stop_dialog_dismissal_loop
ok "permission pipeline complete"
