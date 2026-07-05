#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh
#  Grant TCC permissions using Open Interpreter (local LLaVA 7B via Ollama).
#
#  THE APPROACH:
#  Open Interpreter is an AI agent that can SEE the screen, REASON about what
#  to do, and CLICK UI elements. Unlike our rigid script, it can ADAPT when
#  things don't go as expected — if a dialog appears, it dismisses it; if a
#  click misses, it tries again; if the UI changes, it adjusts.
#
#  We give it a SINGLE multi-step prompt:
#    "Open RustDesk. Dismiss any dialogs. Click Configure. Click the toggle
#     next to RustDesk. Type the password <PASSWORD>. Click Modify Settings.
#     Click Later. Repeat for each permission."
#
#  The AI runs FULLY LOCAL via Ollama (llava:7b, ~4.7 GB). No API key.
#
#  PREREQS:
#    - Ollama (brew install ollama) + llava:7b model pulled
#    - open-interpreter==0.4.3 (pip install)
#    - cliclick (brew install cliclick)
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — grant TCC permissions via Open Interpreter (local LLaVA)"

require_env MAC_USER_PASSWORD

# --- 0. install deps + start loops ------------------------------------------
if ! command -v cliclick >/dev/null 2>&1; then
  log "installing cliclick"
  brew install cliclick
fi

# --- 1. install Ollama + pull llava:7b model --------------------------------
if ! command -v ollama >/dev/null 2>&1; then
  log "installing Ollama (local LLM runtime)"
  brew install ollama
fi

# start ollama serve in the background (if not already running)
if ! pgrep -x ollama >/dev/null 2>&1; then
  log "starting ollama serve (background)"
  nohup ollama serve > /tmp/ollama.log 2>&1 &
  sleep 5
fi

# pull llava:7b if not already pulled (~4.7 GB, visible progress)
log "checking for llava:7b model..."
if ! ollama list 2>/dev/null | grep -q "llava:7b"; then
  log "pulling llava:7b model (~4.7 GB, visible progress)..."
  ollama pull llava:7b
fi
ok "ollama + llava:7b ready"

# --- 2. install Open Interpreter --------------------------------------------
# CRITICAL: create a FRESH venv every run. The venv cache was causing
# pkg_resources to be missing even after installing setuptools (Python 3.12
# venvs don't include setuptools by default, and cached venvs from previous
# runs without setuptools break). A fresh venv + setuptools + OI takes ~30s.
VENV_DIR="$STATE_DIR/oi-venv"
log "creating fresh Python venv for Open Interpreter"
rm -rf "$VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip 2>&1 | tail -n1

log "installing setuptools==80.10.2 (required by OI — setuptools 82+ REMOVED pkg_resources)"
# CRITICAL: setuptools 82.0.0+ removed pkg_resources entirely. Open Interpreter
# 0.4.3 imports pkg_resources, so we MUST pin setuptools to 80.10.2 (the last
# version that includes it). See https://setuptools.pypa.io/en/latest/deprecated/pkg_resources.html
"$VENV_DIR/bin/python" -m pip install --quiet "setuptools==80.10.2" 2>&1 | tail -n1

log "installing open-interpreter==0.4.3 (the version with --os mode)"
"$VENV_DIR/bin/python" -m pip install --quiet "open-interpreter==0.4.3" 2>&1 | tail -n3

# VERIFY pkg_resources is actually importable
if ! "$VENV_DIR/bin/python" -c "import pkg_resources" 2>/dev/null; then
  warn "pkg_resources still missing after setuptools install — trying force-reinstall"
  "$VENV_DIR/bin/python" -m pip install --force-reinstall setuptools 2>&1 | tail -n2
fi
ok "open-interpreter ready"

# --- 3. start screenshot + dialog-dismissal loops ---------------------------
start_screenshot_loop
start_dialog_dismissal_loop

# --- 4. write the Open Interpreter script -----------------------------------
OI_SCRIPT="/tmp/oi_grant_permissions.py"
cat > "$OI_SCRIPT" <<PYEOF
import os, sys, time
os.environ["INTERPRETER_FORCE_LOCAL"] = "1"

from interpreter import interpreter

# Configure for FULLY LOCAL operation (no API key, no cloud)
interpreter.offline = True
interpreter.auto_run = True          # CI: no confirmations needed
interpreter.loop = True              # keep going until task is done
interpreter.llm.model = "ollama/llava:7b"
interpreter.llm.api_base = "http://localhost:11434"
interpreter.llm.api_key = "fake_key"  # required by litellm even for local
interpreter.llm.supports_vision = True
interpreter.llm.context_window = 8192
interpreter.llm.max_tokens = 2000

# Enable the computer API (screen capture + click + type)
interpreter.computer.import_computer_api = True
interpreter.computer.emit_images = True
interpreter.computer.offline = True

print("    [oi] Open Interpreter configured — local LLaVA 7B via Ollama", flush=True)
print("    [oi] starting multi-step permission task...", flush=True)

# The multi-step task prompt
task = """You are controlling a macOS 15 computer. Your task is to grant permissions to RustDesk.

Follow these steps IN ORDER. After each step, take a screenshot to verify it worked before proceeding:

1. Open RustDesk (it may already be open). If a dialog appears asking "Allow RustDesk to find devices on local networks?", click "Allow".

2. In RustDesk, find the pink "Permissions" section. Click the "Configure" button inside it.

3. System Settings will open showing a privacy pane (Screen Recording, Accessibility, or Input Monitoring). Find "RustDesk" in the list. Click the toggle switch next to it to turn it ON.

4. A password prompt will appear asking for the password. The password is: ${MAC_USER_PASSWORD}. Type this password into the password field and press Enter (or click "Modify Settings").

5. A "Quit & Reopen" dialog may appear. Click "Later" (do NOT click "Quit & Reopen").

6. Go back to step 1 and repeat until RustDesk no longer shows a pink "Permissions" section (meaning all permissions are granted).

IMPORTANT NOTES:
- If any dialog blocks the screen, dismiss it first (click "Allow", "Later", "Cancel", or "Don't Allow" as appropriate)
- If a click doesn't work the first time, try again at a slightly different position
- After each click, take a screenshot to verify the result
- If you see "RustDesk" with a toggle that is already ON (blue), skip to the next permission
- The screen resolution is 1024x768
- You have at most 3 permission cycles to complete

Report what you did at each step."""

print("    [oi] task prompt ready, launching...", flush=True)

try:
    interpreter.chat(task)
    print("    [oi] task completed", flush=True)
    sys.exit(0)
except Exception as e:
    print(f"    [oi] ERROR: {e}", flush=True)
    sys.exit(1)
PYEOF

# --- 5. run Open Interpreter ------------------------------------------------
log "launching Open Interpreter with multi-step permission task"
# CRITICAL: do NOT filter the output — we need to see ALL errors.
# Open Interpreter's error messages are essential for debugging.
# Write full output to a log file AND print it (unfiltered).
OI_LOG="/tmp/apple-project/oi-output.log"
"$VENV_DIR/bin/python" "$OI_SCRIPT" 2>&1 | tee "$OI_LOG"
OI_EXIT=${PIPESTATUS[0]}
log "Open Interpreter exited with code $OI_EXIT"

# show the last 30 lines of OI output for debugging
if [ "$OI_EXIT" -ne 0 ]; then
  warn "Open Interpreter failed — last 30 lines of output:"
  tail -n 30 "$OI_LOG" 2>/dev/null | while IFS= read -r line; do
    warn "  $line"
  done
fi

# --- 6. final state ---------------------------------------------------------
take_screenshot "03_final_state"
stop_screenshot_loop
stop_dialog_dismissal_loop

if [ "$OI_EXIT" -eq 0 ]; then
  ok "permission pipeline complete (Open Interpreter + local LLaVA)"
else
  warn "Open Interpreter did not complete successfully"
  warn "check the screenshots artifact for the final state"
  exit 1
fi
