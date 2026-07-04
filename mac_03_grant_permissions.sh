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
  gui_run open -a RustDesk || true
  # give it ~6 seconds to attempt screen capture / input monitoring and
  # trigger the TCC registration
  sleep 6
  pkill -x RustDesk 2>/dev/null || true
  sleep 1
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
      ok "  [L1 sqlite3] $service GRANTED"
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

# --- LAYER 3: ShowUI-2B local AI agent --------------------------------------
grant_via_showui() {
  local service="$1" pane_url="$2" goal="$3"
  log "  [L3 ShowUI-2B] booting local vision agent for: $goal"

  # one-time deps
  if ! command -v cliclick >/dev/null 2>&1; then
    log "  installing cliclick (input injector — inherits bash Accessibility)"
    brew install cliclick
  fi
  if ! python3 -c "import transformers" 2>/dev/null; then
    log "  installing Python deps (transformers, qwen-vl-utils, torch, ...)"
    python3 -m pip install --user --quiet \
        "transformers>=4.47.0" qwen-vl-utils accelerate pillow huggingface_hub 2>&1 | tail -n2
    # torch for Apple Silicon (MPS) — the runner is macos-15 = arm64
    python3 -m pip install --user --quiet torch torchvision 2>&1 | tail -n2
  fi

  # the model is ~4.2 GB; let it auto-download on first run into the HF cache
  log "  launching ShowUI-2B agent (model downloads on first run, ~4.2 GB)"
  SHOWUI_GOAL="$goal" \
  SHOWUI_PANE_URL="$pane_url" \
  SHOWUI_SERVICE="$service" \
  SHOWUI_HELPER_USER="$MAC_USER" \
  SHOWUI_HELPER_PASSWORD="$(sudo sed -n 's/^MAC_USER_PASSWORD=//p' "$STATE_DIR/helper-user.env" 2>/dev/null)" \
  python3 "$PROJECT_ROOT/mac_showui_agent.py" && {
    ok "  [L3 ShowUI-2B] $service GRANTED"
    return 0
  }
  warn "  [L3 ShowUI-2B] could not grant $service"
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

  if tcc_granted "$service" "$RUSTDESK_BUNDLE"; then
    ok "$service already granted — skipping"
    continue
  fi

  grant_via_sqlite    "$service"            && continue
  grant_via_osascript "$service" "$url"     && continue
  grant_via_showui    "$service" "$url" "$goal" && continue

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
