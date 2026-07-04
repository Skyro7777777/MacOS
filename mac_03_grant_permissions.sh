#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh
#  Grant TCC permissions to RustDesk using RustDesk's OWN "Configure" button.
#
#  THE APPROACH (from analyzing a YouTube tutorial + screenshots):
#  Instead of fighting with System Settings panes directly, we click the
#  "Configure" button inside RustDesk's pink "Permissions" section.  This:
#    1. Adds RustDesk to the relevant privacy list automatically
#    2. Opens System Settings to the right pane
#    3. We click the toggle → macOS shows a PASSWORD PROMPT
#    4. We type the MAC_USER_PASSWORD (from repo secrets)
#    5. Click "Modify Settings" → macOS grants the permission at the OS level
#    6. A "Quit & Reopen" dialog appears → we click "Later" (keep RustDesk running)
#    7. Repeat for each permission RustDesk requests
#
#  WHY THIS IS BETTER than the old 3-layer / ShowUI approach:
#    - No AI model needed (no torch, no 4 GB downloads, no OOM)
#    - No TCC.db fighting (the password prompt does the real grant)
#    - No osascript AX-tree guessing (the "Configure" button is found by OCR)
#    - Deterministic: same button sequence every time
#    - Fast: ~30s per permission instead of 5-8 min
#
#  TOOLS:
#    - screencapture  (inherits bash's Screen Recording TCC)
#    - cliclick       (inherits bash's Accessibility TCC)
#    - Apple Vision OCR via PyObjC (macOS built-in, zero download)
#    - mac_ocr_helper.py (find + click buttons by text)
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — grant TCC permissions via RustDesk's Configure button flow"

require_env MAC_USER_PASSWORD

# --- 0. start screenshot + dialog-dismissal loops ---------------------------
start_screenshot_loop
start_dialog_dismissal_loop

# --- 1. set up the Python venv with PyObjC for OCR --------------------------
VENV_DIR="$STATE_DIR/ocr-venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  log "creating lightweight OCR venv (pyobjc + pillow only — no torch, no AI)"
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip 2>&1 | tail -n1
  "$VENV_DIR/bin/python" -m pip install --quiet \
      pyobjc-framework-Vision pyobjc-framework-Quartz pillow 2>&1 | tail -n2
fi
ok "OCR venv ready"

# --- 2. install cliclick if missing -----------------------------------------
if ! command -v cliclick >/dev/null 2>&1; then
  log "installing cliclick"
  brew install cliclick
fi

OCR="$VENV_DIR/bin/python $PROJECT_ROOT/mac_ocr_helper.py"

# --- 3. helper: click a button by text, with retry --------------------------
click_button() {
  local text="$1" retries="${2:-10}"
  for i in $(seq 1 "$retries"); do
    if $OCR click "$text" 2>/dev/null; then
      ok "clicked '$text'"
      return 0
    fi
    sleep 1
  done
  warn "could not find/click '$text' after $retries tries"
  return 1
}

# --- 4. helper: type the password from secrets ------------------------------
type_password() {
  log "typing password from MAC_USER_PASSWORD secret"
  $OCR type "$MAC_USER_PASSWORD"
  sleep 0.5
  # press Return to submit (or click Modify Settings)
  osascript -e 'tell application "System Events" to keystroke return' 2>/dev/null || true
  sleep 1
}

# --- 5. helper: handle one full permission cycle ----------------------------
# This handles the complete flow for ONE "Configure" button click:
#   Configure → System Settings opens → click toggle → password prompt →
#   type password → Modify Settings → Quit & Reopen → Later
grant_one_permission() {
  local attempt="$1"
  log "=== permission cycle #$attempt ==="

  # 5a. make sure RustDesk is open + in focus
  gui_run open -a RustDesk 2>/dev/null || true
  sleep 2

  # 5b. look for a "Configure" button in RustDesk's pink Permissions section
  take_screenshot "03_cycle${attempt}_looking_for_configure"
  if ! $OCR find "Configure" 2>/dev/null | grep -q "^[0-9]"; then
    log "no 'Configure' button found — all permissions may be granted already"
    return 0  # no more Configure buttons = all done
  fi

  # 5c. click the Configure button
  log "clicking 'Configure' button in RustDesk"
  click_button "Configure" 5 || return 1
  sleep 3  # wait for System Settings to open
  take_screenshot "03_cycle${attempt}_after_configure_click"

  # 5d. wait for the toggle to appear in System Settings (RustDesk should be in the list)
  log "waiting for RustDesk to appear in the privacy list..."
  local toggle_found=false
  for i in $(seq 1 15); do
    if $OCR find "RustDesk" 2>/dev/null | grep -q "^[0-9]"; then
      toggle_found=true
      break
    fi
    sleep 1
  done
  if [ "$toggle_found" = "false" ]; then
    warn "RustDesk not found in the privacy list after 15s"
    take_screenshot "03_cycle${attempt}_rustdesk_not_in_list"
    return 1
  fi
  ok "RustDesk is in the list"

  # 5e. click the toggle (120px right of the "RustDesk" label)
  log "clicking the toggle next to RustDesk"
  $OCR click_toggle "RustDesk" 2>/dev/null || true
  sleep 2
  take_screenshot "03_cycle${attempt}_after_toggle_click"

  # 5f. handle the password prompt ("Enter your password to allow this")
  log "waiting for password prompt..."
  local pw_prompt_found=false
  for i in $(seq 1 10); do
    if $OCR find "password" 2>/dev/null | grep -q "^[0-9]"; then
      pw_prompt_found=true
      break
    fi
    # the password prompt might already be gone if the toggle was already ON
    if $OCR find "Quit" 2>/dev/null | grep -q "^[0-9]"; then
      log "no password prompt — toggle was already ON, jumping to Quit & Reopen"
      break
    fi
    sleep 1
  done

  if [ "$pw_prompt_found" = "true" ]; then
    log "password prompt found — typing password"
    type_password
    sleep 2
    take_screenshot "03_cycle${attempt}_after_password"

    # click "Modify Settings" if it appears (sometimes Return is enough)
    $OCR click "Modify Settings" 2>/dev/null || true
    sleep 2
  fi

  # 5g. handle the "Quit & Reopen" dialog → click "Later" to keep RustDesk running
  log "looking for 'Quit & Reopen' or 'Later' dialog..."
  for i in $(seq 1 10); do
    if $OCR find "Later" 2>/dev/null | grep -q "^[0-9]"; then
      log "clicking 'Later' to keep RustDesk running"
      $OCR click "Later" 2>/dev/null || true
      sleep 1
      break
    fi
    sleep 1
  done

  take_screenshot "03_cycle${attempt}_done"
  ok "permission cycle #$attempt complete"
  return 0
}

# --- 6. run the permission cycles -------------------------------------------
# RustDesk shows one "Configure" button at a time for each missing permission
# (Screen Recording, then Accessibility, then Input Monitoring).  We loop up
# to 6 times to cover all three + retries.
MAX_CYCLES=6
for cycle in $(seq 1 "$MAX_CYCLES"); do
  grant_one_permission "$cycle" || true

  # check if any "Configure" button remains
  sleep 2
  if ! $OCR find "Configure" 2>/dev/null | grep -q "^[0-9]"; then
    ok "no more 'Configure' buttons — all permissions granted"
    break
  fi
done

# --- 7. final verification --------------------------------------------------
take_screenshot "03_final_state"
log "=== permission grant summary ==="

# Check if RustDesk still shows a pink Permissions section
if $OCR find "Configure" 2>/dev/null | grep -q "^[0-9]"; then
  warn "RustDesk still shows a 'Configure' button — some permissions may be missing"
  warn "check the screenshots artifact for the final desktop state"
else
  ok "no 'Configure' button remaining — all permissions appear granted"
fi

stop_screenshot_loop
stop_dialog_dismissal_loop
ok "permission pipeline complete"
