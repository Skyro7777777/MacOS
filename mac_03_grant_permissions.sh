#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh
#  Grant TCC permissions using tgpt (online 20B AI) + Apple Vision OCR.
#
#  THE APPROACH:
#    - tgpt: online AI (GPT-OSS-20B via Pollinations) — no API key, no download
#    - Apple Vision OCR: built-in macOS neural network — sees the screen
#    - cliclick: clicks elements — inherits bash's Accessibility TCC
#
#  The flow:
#    1. Take screenshot → Apple Vision OCR → get all text + coordinates
#    2. Send OCR text to tgpt: "What should I click next?"
#    3. tgpt responds: "Click the Configure button"
#    4. Find "Configure" in OCR results → cliclick click its coordinates
#    5. Repeat until tgpt says "done"
#
#  WHY THIS IS BETTER than Open Interpreter + Ollama:
#    - No 4.7 GB model download (instant start)
#    - 20B model (smarter than llama3.1:8b for reasoning)
#    - No venv/setuptools/pkg_resources/pywinctl issues
#    - No pyautogui crash (we use cliclick directly)
#    - Simpler: ~200 lines vs 500+ lines of OI config + patches
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — grant TCC permissions via tgpt (20B) + Apple Vision OCR"

require_env MAC_USER_PASSWORD

# --- 0. install deps --------------------------------------------------------
if ! command -v cliclick >/dev/null 2>&1; then
  log "installing cliclick"
  brew install cliclick
fi

# install tgpt (10 MB, instant — no API key, no model download)
if ! command -v tgpt >/dev/null 2>&1; then
  log "installing tgpt (terminal AI, no API key, ~10 MB)"
  curl -sSL https://raw.githubusercontent.com/aandrew-me/tgpt/main/install | bash -s /usr/local/bin 2>&1 | tail -n3
fi
ok "tgpt ready: $(tgpt --version 2>/dev/null || echo 'installed')"

# install pyobjc for Apple Vision OCR (small, ~50 MB, no torch)
VENV_DIR="$STATE_DIR/ocr-venv"
if [ ! -x "$VENV_DIR/bin/python" ] || ! "$VENV_DIR/bin/python" -c "from Vision import VNRecognizeTextRequest" 2>/dev/null; then
  log "creating OCR venv (pyobjc + pillow only — no torch, no AI model)"
  rm -rf "$VENV_DIR"
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip 2>&1 | tail -n1
  "$VENV_DIR/bin/python" -m pip install --quiet \
      pyobjc-framework-Vision pyobjc-framework-Quartz pillow 2>&1 | tail -n2
fi
ok "OCR venv ready"

# --- 1. start screenshot + dialog-dismissal loops ---------------------------
start_screenshot_loop
start_dialog_dismissal_loop

# --- 2. launch the tgpt agent -----------------------------------------------
log "launching tgpt agent (20B model + Apple Vision OCR + cliclick)"
MAC_AGENT_PASSWORD="$MAC_USER_PASSWORD" \
MAC_AGENT_MAX_STEPS="20" \
"$VENV_DIR/bin/python" "$PROJECT_ROOT/mac_tgpt_agent.py" || {
  warn "tgpt agent did not complete successfully"
  warn "check the screenshots artifact for the final state"
  exit 1
}

# --- 3. final state ---------------------------------------------------------
take_screenshot "03_final_state"
stop_screenshot_loop
stop_dialog_dismissal_loop
ok "permission pipeline complete (tgpt + OCR, no local model download)"
