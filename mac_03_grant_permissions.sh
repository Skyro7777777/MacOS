#!/usr/bin/env bash
# =============================================================================
#  mac_03_grant_permissions.sh  —  THE PERMISSION GRANT PIPELINE
#
#  Goal: get RustDesk three TCC permissions on the macOS 15 runner:
#     1. Screen Recording        (kTCCServiceScreenCapture)
#     2. Accessibility           (kTCCServiceAccessibility)
#     3. Input Monitoring        (kTCCServiceListenEvent)
#
#  Why three layers (single method, defence-in-depth):
#
#  LAYER 1 — sqlite3 INSERT into the system TCC.db  (fast, non-UI)
#     Works reliably for Accessibility on GitHub runners; sometimes works
#     for ScreenCapture but Sequoia's tccd validates the csreq blob and may
#     silently ignore the row.  Cheap to try, so we try first.
#
#  LAYER 2 — osascript deterministic click-through  (PRIMARY for ScreenCapture)
#     bash + osascript already have Accessibility + AppleEvents on the runner
#     (confirmed by screenshot).  We open each privacy pane by deep-link URL,
#     recursively search the AX tree for RustDesk's toggle, and click it.
#     Handles the "Quit & Reopen" sheet.  This is deterministic — no AI.
#
#  LAYER 3 — ShowUI-2B local vision agent  (AI FALLBACK)
#     If osascript cannot find the element (UI hierarchy drift, or RustDesk is
#     NOT yet in the list and the "+" file-picker needs driving), we boot the
#     showlab/ShowUI-2B model LOCALLY (no API, no OpenAI), feed it screenshots
#     taken with `screencapture` (which inherits bash's Screen Recording), and
#     click with `cliclick` (which inherits bash's Accessibility).
#
#  CRITICAL ENABLER — "responsible process" inheritance:
#     screencapture / osascript / cliclick / python-subprocess spawned by bash
#     are all TCC-attributed to bash, which already has Screen Recording +
#     Accessibility.  So the AI agent can SEE the screen and CLICK without
#     needing its own TCC grants.  (We avoid mss/PIL.ImageGrab/pyautogui which
#     make the API call inside the Python binary itself.)
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 03 — grant TCC permissions to RustDesk (sqlite3 -> osascript -> ShowUI)"

require_env RUSTDESK_PASSWORD

# Restart the screenshot loop (it died with step 02's shell).  We want to
# capture the System Settings panes during osascript/ShowUI click-through.
start_screenshot_loop

# Start the dialog-dismissal loop — macOS Sequoia shows a "bypass the system
# private window picker" prompt when RustDesk/screencapture tries to capture
# the screen.  We auto-click "Allow" so the capture actually works.
start_dialog_dismissal_loop

# Log whether the user forced the ShowUI path
if [ "${USE_SHOWUI:-false}" = "true" ]; then
  warn "USE_SHOWUI=true — skipping Layers 1 (sqlite3) and 2 (osascript), going straight to ShowUI-2B"
fi

# --- 0. make sure RustDesk has REGISTERED itself in the TCC lists ------------
# A brand-new app is NOT in any privacy list until it has TRIED to use the
# protected API.  We briefly start RustDesk so the OS records it; then we kill
# it and grant the permissions while it is stopped.
register_rustdesk_in_tcc() {
  if pgrep -x RustDesk >/dev/null 2>&1; then
    warn "RustDesk already running — leaving it"
    return
  fi
  log "briefly launching RustDesk so it registers in the TCC lists..."
  take_screenshot "03_before_tcc_register"
  gui_run open -a RustDesk || true
  # give it ~6 seconds to attempt screen capture / input monitoring and
  # trigger the TCC registration
  sleep 6
  take_screenshot "03_rustdesk_running_for_tcc"
  pkill -x RustDesk 2>/dev/null || true
  sleep 1
  take_screenshot "03_after_tcc_register"
  ok "RustDesk registered (it should now appear in the privacy lists)"
}
register_rustdesk_in_tcc

# --- helper: is a TCC permission already granted? ---------------------------
# Reads auth_value from the system TCC.db.  auth_value == 2 means "allowed".
tcc_granted() {
  local service="$1" client="$2"
  local val
  val="$(sudo sqlite3 "$TCC_SYSTEM_DB" \
    "SELECT auth_value FROM access WHERE service='$service' AND client='$client';" 2>/dev/null || echo "")"
  [ "$val" = "2" ]
}

# --- LAYER 1: sqlite3 INSERT (best-effort) -----------------------------------
grant_via_sqlite() {
  local service="$1"
  log "  [L1 sqlite3] attempting INSERT for $service"

  # extract RustDesk's designated code requirement, compile to a binary blob,
  # hex-encode it for the csreq column (Sequoia tccd validates this)
  local csreq_hex=""
  local tmpreq="/tmp/${RUSTDESK_BUNDLE}.csreq"
  local req_text
  req_text="$(codesign -d -r- "$RUSTDESK_APP" 2>/dev/null | sed -n 's/^designated => //p')"
  if [ -n "$req_text" ]; then
    if echo "$req_text" | csreq -r=- -b="$tmpreq" 2>/dev/null; then
      csreq_hex="$(xxd -p "$tmpreq" | tr -d '\n')"
    fi
  fi
  local csreq_sql="NULL"
  if [ -n "$csreq_hex" ]; then
    csreq_sql="X'${csreq_hex}'"
  fi

  # The access table schema differs slightly across macOS versions; build the
  # INSERT to match the live column set so it never fails on a missing column.
  local cols
  cols="$(sudo sqlite3 "$TCC_SYSTEM_DB" "PRAGMA table_info(access);" 2>/dev/null | awk -F'|' '{print $2}' | paste -sd, -)"

  # only fill the columns we know about; everything else defaults to NULL/0
  local col_vals=""
  IFS=',' read -ra col_array <<< "$cols"
  for c in "${col_array[@]}"; do
    case "$c" in
      service)            col_vals+=" '${service}'," ;;
      client)             col_vals+=" '${RUSTDESK_BUNDLE}'," ;;
      client_type)        col_vals+=" 0," ;;
      auth_value)         col_vals+=" 2," ;;
      auth_reason)        col_vals+=" 4," ;;
      auth_version)       col_vals+=" 1," ;;
      csreq)              col_vals+=" ${csreq_sql}," ;;
      indirect_object_identifier_type) col_vals+=" 0," ;;
      indirect_object_identifier)      col_vals+=" 'UNUSED'," ;;
      flags)              col_vals+=" 0," ;;
      *)                  col_vals+=" NULL," ;;
    esac
  done
  col_vals="${col_vals%,}"   # strip trailing comma

  local sql="INSERT OR REPLACE INTO access (${cols}) VALUES (${col_vals});"
  if sudo sqlite3 "$TCC_SYSTEM_DB" "$sql" 2>/dev/null; then
    # restart tccd so it re-reads the DB
    sudo killall tccd 2>/dev/null || true
    sleep 2
    if tcc_granted "$service" "$RUSTDESK_BUNDLE"; then
      # NOTE: on Sequoia, the DB row may exist but tccd can still reject it
      # at runtime (csreq validation).  The "GRANTED" here means the DB row
      # is present; whether the OS actually honours it is a separate question
      # that only becomes visible when RustDesk tries to capture the screen
      # and the Sequoia "bypass window picker" dialog appears (or doesn't).
      ok "  [L1 sqlite3] $service GRANTED (DB row present — may need UI confirmation on Sequoia)"
      return 0
    fi
    warn "  [L1 sqlite3] INSERT ran but tccd did not honour it (Sequoia csreq validation?)"
  else
    warn "  [L1 sqlite3] INSERT failed (SIP / schema) — expected for ScreenCapture on Sequoia"
  fi
  return 1
}

# --- LAYER 2: osascript click-through ---------------------------------------
grant_via_osascript() {
  local service="$1" pane_url="$2"
  log "  [L2 osascript] opening pane + clicking toggle for $service"
  local script="$PROJECT_ROOT/mac_grant_permissions.applescript"
  if [ ! -f "$script" ]; then die "missing $script"; fi

  # The AppleScript returns one of: GRANTED | ALREADY_ON | NOT_IN_LIST | ERROR
  local result
  result="$(osascript "$script" "$pane_url" "$RUSTDESK_BUNDLE" "RustDesk" 2>&1)" || true
  log "  [L2 osascript] result: $result"

  case "$result" in
    GRANTED|ALREADY_ON)
      # tccd needs a moment to reflect the UI toggle
      sleep 2
      if tcc_granted "$service" "$RUSTDESK_BUNDLE"; then
        ok "  [L2 osascript] $service GRANTED"
        return 0
      fi
      # the UI toggle may have been flipped but tccd hasn't written it yet;
      # accept the UI result as success anyway
      ok "  [L2 osascript] $service toggled via UI (tccd write may lag)"
      return 0
      ;;
    NOT_IN_LIST)
      warn "  [L2 osascript] RustDesk not in the $service list — needs ShowUI to drive the + file picker"
      ;;
    *)
      warn "  [L2 osascript] could not toggle $service (UI hierarchy drift?) — falling back to ShowUI"
      ;;
  esac
  return 1
}

# --- LAYER 3: GUI agent (3-tier: Apple Vision OCR → OmniParser YOLO → moondream2)
# This replaces the OOM-prone ShowUI-2B agent.  The new agent (mac_gui_agent.py)
# uses the macOS BUILT-IN Vision framework for OCR (zero download, ~100 MB RAM)
# as the primary method, with OmniParser-v2.0's 40 MB YOLO icon detector as
# fallback #1, and moondream2 (1.86B, ~4 GB RAM) as the true last-resort VLM.
grant_via_showui() {
  local service="$1" pane_url="$2" goal="$3"
  log "  [L3 GUI agent] booting 3-tier agent (OCR → YOLO → moondream2) for: $goal"

  # one-time deps
  if ! command -v cliclick >/dev/null 2>&1; then
    log "  installing cliclick (input injector — inherits bash Accessibility)"
    brew install cliclick
  fi

  # Use a virtualenv (PEP 668 blocks pip --user on the system Python).
  # The venv is cached across the 3 permission attempts (same job).
  local venv_dir="$STATE_DIR/gui-agent-venv"
  if [ ! -x "$venv_dir/bin/python" ]; then
    log "  creating Python virtualenv at $venv_dir"
    python3 -m venv "$venv_dir" || die "could not create venv"
    "$venv_dir/bin/python" -m pip install --quiet --upgrade pip wheel setuptools 2>&1 | tail -n1
  fi

  # --- TIER 1 deps (always install — cheap): pyobjc + Pillow ---
  # pyobjc-framework-Vision gives us VNRecognizeTextRequest (macOS built-in OCR).
  if ! "$venv_dir/bin/python" -c "import Vision" 2>/dev/null; then
    log "  installing Tier-1 deps: pyobjc-framework-Vision + Pillow (small, fast)"
    "$venv_dir/bin/python" -m pip install --quiet \
        pyobjc-framework-Vision pyobjc-framework-Quartz pillow 2>&1 | tail -n2
  fi
  ok "  Tier 1 (Apple Vision OCR) ready"

  # --- TIER 2 deps (medium): ultralytics + huggingface_hub for OmniParser YOLO ---
  if ! "$venv_dir/bin/python" -c "import ultralytics" 2>/dev/null; then
    log "  installing Tier-2 deps: ultralytics + huggingface_hub (for OmniParser YOLO, 40 MB model)"
    "$venv_dir/bin/python" -m pip install --quiet ultralytics huggingface_hub 2>&1 | tail -n2
  fi
  ok "  Tier 2 (OmniParser YOLO) ready"

  # --- TIER 3 deps (heavy, lazy): torch + transformers for moondream2 ---
  # Only install if the env var GUI_AGENT_SKIP_VLM is not set.  This lets the
  # operator skip the ~2 GB torch download if Tiers 1+2 are sufficient.
  if [ "${GUI_AGENT_SKIP_VLM:-false}" != "true" ]; then
    if ! "$venv_dir/bin/python" -c "import torch" 2>/dev/null; then
      log "  installing Tier-3 deps: torch + transformers (for moondream2, ~2 GB download)"
      "$venv_dir/bin/python" -m pip install --quiet torch torchvision 2>&1 | tail -n2
      "$venv_dir/bin/python" -m pip install --quiet \
          "transformers>=4.47.0" einops timm 2>&1 | tail -n2
    fi
    ok "  Tier 3 (moondream2 VLM) ready"
  else
    warn "  Tier 3 (moondream2) skipped (GUI_AGENT_SKIP_VLM=true)"
  fi

  # launch the agent
  log "  launching GUI agent"
  GUI_AGENT_GOAL="$goal" \
  GUI_AGENT_PANE_URL="$pane_url" \
  GUI_AGENT_SERVICE="$service" \
  GUI_AGENT_HELPER_USER="$MAC_USER" \
  GUI_AGENT_HELPER_PW="$(sudo sed -n 's/^MAC_USER_PASSWORD=//p' "$STATE_DIR/helper-user.env" 2>/dev/null)" \
  GUI_AGENT_VENV="$venv_dir" \
  "$venv_dir/bin/python" "$PROJECT_ROOT/mac_gui_agent.py" && {
    ok "  [L3 GUI agent] $service GRANTED"
    return 0
  }
  warn "  [L3 GUI agent] could not grant $service"
  return 1
}

# --- the three permissions ---------------------------------------------------
PERMISSIONS=(
  "$TCC_SCREEN_CAPTURE|$URL_SCREEN_CAPTURE|the ON toggle switch next to RustDesk in the Screen & System Audio Recording list (click it ON; if RustDesk is not listed, click the + button, navigate to /Applications/RustDesk.app, click Open, then flip the toggle ON; dismiss any Quit & Reopen sheet by clicking Later)"
  "$TCC_ACCESSIBILITY|$URL_ACCESSIBILITY|the ON toggle switch next to RustDesk in the Accessibility list (click it ON; use the + button and file picker if RustDesk is not listed)"
  "$TCC_INPUT_MONITORING|$URL_INPUT_MONITORING|the ON toggle switch next to RustDesk in the Input Monitoring list (click it ON; use the + button and file picker if RustDesk is not listed)"
)

FAILED=()
for entry in "${PERMISSIONS[@]}"; do
  IFS='|' read -r service url goal <<< "$entry"
  log "=== Permission: $service ==="
  take_screenshot "03_before_${service}"

  if tcc_granted "$service" "$RUSTDESK_BUNDLE"; then
    ok "$service already granted — skipping"
    take_screenshot "03_${service}_already_granted"
    continue
  fi

  # When USE_SHOWUI=true, skip Layers 1 and 2 and go straight to ShowUI-2B.
  if [ "${USE_SHOWUI:-false}" != "true" ]; then
    grant_via_sqlite    "$service"            && { take_screenshot "03_${service}_after_sqlite_ok"; continue; }
    take_screenshot "03_${service}_after_sqlite_fail"
    grant_via_osascript "$service" "$url"     && { take_screenshot "03_${service}_after_osascript_ok"; continue; }
    take_screenshot "03_${service}_after_osascript_fail"
  fi
  grant_via_showui    "$service" "$url" "$goal" && { take_screenshot "03_${service}_after_showui_ok"; continue; }
  take_screenshot "03_${service}_after_showui_fail"

  err "FAILED to grant $service by any method"
  FAILED+=("$service")
done

# --- summary ----------------------------------------------------------------
log "=== permission grant summary ==="
for entry in "${PERMISSIONS[@]}"; do
  IFS='|' read -r service url goal <<< "$entry"
  if tcc_granted "$service" "$RUSTDESK_BUNDLE"; then
    ok "$service  -> GRANTED"
  else
    # the UI may have toggled it but tccd hasn't synced; do a soft re-check
    warn "$service  -> NOT CONFIRMED in TCC.db (may still work via UI toggle)"
  fi
done

if [ "${#FAILED[@]}" -gt 0 ]; then
  warn "permissions not confirmed via TCC.db: ${FAILED[*]}"
  warn "RustDesk may still work if the UI toggles are ON — mac_04 will do a live check."
fi
ok "permission pipeline complete"
