#!/usr/bin/env bash
# =============================================================================
#  mac_06_deeplink.sh — Install + configure DeepLink as an alternative to RustDesk
#
#  DeepLink (deeplinkgame.com) is a remote desktop + cloud gaming service.
#  Unlike RustDesk (P2P/direct-IP), DeepLink uses relay servers + requires
#  an account (private key) for login. The "Allow Remote Control" feature
#  shows a Device ID + Password that a remote client can connect to.
#
#  This script:
#    1. Downloads + installs the DeepLink macOS DMG (arm64)
#    2. Grants TCC permissions (Screen Recording + Accessibility + Input Monitoring)
#       using the same sqlite3 approach as RustDesk
#    3. Launches DeepLink
#    4. Dumps its config/preferences to find the Device ID + Password
#    5. If DEEPLINK_PRIVATE_KEY is set, writes it to the config for auto-login
#
#  The connection info (Device ID + Password) is printed to the log.
#  Note: DeepLink may require login before showing connection info.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 06 — install + configure DeepLink (alternative to RustDesk)"

DEEPLINK_DMG_URL="https://pub-1b47391b45ed418d8a02bf732d2f944a.r2.dev/deeplink_arm64.dmg"
DEEPLINK_APP="/Applications/DeepLink.app"

# --- 1. download + install the DMG ------------------------------------------
if [ ! -d "$DEEPLINK_APP" ]; then
  log "downloading DeepLink DMG (arm64, ~190MB)..."
  local_dmg="/tmp/deeplink.dmg"
  curl -fsSL "$DEEPLINK_DMG_URL" -o "$local_dmg" || die "could not download DeepLink DMG"

  log "mounting DMG + copying app..."
  hdiutil attach "$local_dmg" -nobrowse -quiet 2>/dev/null
  vol="$(hdiutil info 2>/dev/null | grep '/Volumes/DeepLink' | head -1 | awk '{print $NF}')"
  [ -z "$vol" ] && vol="/Volumes/DeepLink"
  cp -R "$vol/DeepLink.app" /Applications/ || die "could not copy DeepLink.app"
  hdiutil detach "$vol" -quiet 2>/dev/null || true
  rm -f "$local_dmg"
  xattr -dr com.apple.quarantine "$DEEPLINK_APP" 2>/dev/null || true
  ok "DeepLink installed"
else
  log "DeepLink already installed"
fi

DEEPLINK_BIN="$DEEPLINK_APP/Contents/MacOS/DeepLink"

# --- 2. find the bundle ID + grant TCC permissions --------------------------
# Read the actual bundle ID from Info.plist
DEEPLINK_BUNDLE="$(defaults read "$DEEPLINK_APP/Contents/Info" CFBundleIdentifier 2>/dev/null || echo '')"
if [ -z "$DEEPLINK_BUNDLE" ]; then
  warn "could not read DeepLink bundle ID — trying common names"
  DEEPLINK_BUNDLE="com.deeplink.app"
fi
ok "DeepLink bundle ID: $DEEPLINK_BUNDLE"

# Grant TCC permissions (Screen Recording + Accessibility + Input Monitoring + Local Network)
# Same sqlite3 approach as RustDesk — works because SIP is off on the GitHub runner
log "granting TCC permissions to DeepLink ($DEEPLINK_BUNDLE)..."
for service in kTCCServiceScreenCapture kTCCServiceAccessibility kTCCServiceListenEvent kTCCServiceLocalNetwork; do
  sudo sqlite3 "$TCC_DB" "INSERT OR REPLACE INTO access (service, client, client_type, auth_value, auth_reason, auth_version, csreq, policy_id, indirect_object_identifier_type, indirect_object_identifier, flags) VALUES ('$service', '$DEEPLINK_BUNDLE', 0, 2, 4, 1, NULL, 0, 0, 'UNUSED', 0);" 2>/dev/null || true
  # Also write the binary path (client_type=1, matching the bash/hosted-compute-agent pattern)
  sudo sqlite3 "$TCC_DB" "INSERT OR REPLACE INTO access (service, client, client_type, auth_value, auth_reason, auth_version, csreq, policy_id, indirect_object_identifier_type, indirect_object_identifier, flags) VALUES ('$service', '$DEEPLINK_BIN', 1, 2, 4, 1, NULL, 0, 0, 'UNUSED', 0);" 2>/dev/null || true
done
sudo killall tccd 2>/dev/null || true
sleep 2
ok "DeepLink TCC permissions granted (4 services)"

# --- 3. pre-authorize screencapture for DeepLink binary ---------------------
# Add DeepLink to the ScreenCaptureApprovals.plist (same as RustDesk)
sca_plist="$HOME/Library/Group Containers/group.com.apple.replayd/ScreenCaptureApprovals.plist"
sys_plist="/Library/Group Containers/group.com.apple.replayd/ScreenCaptureApprovals.plist"
for plist in "$sca_plist" "$sys_plist"; do
  sudo defaults write "$plist" "$DEEPLINK_BIN" -date "2099-01-01 00:00:00 +0000" 2>/dev/null || true
done
sudo killall -HUP replayd 2>/dev/null || true
ok "DeepLink screencapture pre-authorized"

# --- 4. launch DeepLink -----------------------------------------------------
log "launching DeepLink..."
gui_run open -a DeepLink || true
sleep 5

# --- 5. dump DeepLink config/preferences to find Device ID + Password -------
log "searching for DeepLink config files..."
# Check common config locations
for dir in \
  "/Users/$RUNNER_USER/Library/Preferences" \
  "/Users/$RUNNER_USER/Library/Application Support" \
  "/Users/$RUNNER_USER/Library/Containers"; do
  found="$(find "$dir" -iname '*deeplink*' -maxdepth 2 2>/dev/null || true)"
  if [ -n "$found" ]; then
    log "found DeepLink config in $dir:"
    echo "$found" | while IFS= read -r f; do log "  $f"; done
  fi
done

# Dump the preferences plist (if it exists)
DEEPLINK_PREFS="/Users/$RUNNER_USER/Library/Preferences/${DEEPLINK_BUNDLE}.plist"
if [ -f "$DEEPLINK_PREFS" ]; then
  log "DeepLink preferences ($DEEPLINK_PREFS):"
  sudo -u "$RUNNER_USER" defaults read "$DEEPLINK_BUNDLE" 2>/dev/null | while IFS= read -r line; do log "  $line"; done || true
fi

# --- 6. if DEEPLINK_PRIVATE_KEY is set, try to write it to the config -------
if [ -n "${DEEPLINK_PRIVATE_KEY:-}" ]; then
  log "DEEPLINK_PRIVATE_KEY is set — attempting auto-login configuration..."
  # DeepLink uses a private key for login. The exact config format is unknown,
  # so we write it to several possible locations + let the app pick it up.
  # This is experimental — may need adjustment based on what the config dump shows.
  sudo -u "$RUNNER_USER" defaults write "$DEEPLINK_BUNDLE" privateKey -string "$DEEPLINK_PRIVATE_KEY" 2>/dev/null || true
  sudo -u "$RUNNER_USER" defaults write "$DEEPLINK_BUNDLE" private_key -string "$DEEPLINK_PRIVATE_KEY" 2>/dev/null || true
  sudo -u "$RUNNER_USER" defaults write "$DEEPLINK_BUNDLE" account_key -string "$DEEPLINK_PRIVATE_KEY" 2>/dev/null || true
  # Also write to Application Support (in case DeepLink stores config there)
  app_support="/Users/$RUNNER_USER/Library/Application Support/DeepLink"
  sudo -u "$RUNNER_USER" mkdir -p "$app_support" 2>/dev/null || true
  sudo -u "$RUNNER_USER" tee "$app_support/config.json" >/dev/null 2>&1 <<EOF || true
{"privateKey": "$DEEPLINK_PRIVATE_KEY"}
EOF
  ok "private key written to config (experimental)"
  # Restart DeepLink to pick up the config
  pkill -9 -x DeepLink 2>/dev/null || true
  sleep 2
  gui_run open -a DeepLink || true
  sleep 5
else
  warn "DEEPLINK_PRIVATE_KEY is not set — DeepLink may not show connection info"
  log "to enable DeepLink auto-login, create a DeepLink account + add the private"
  log "key as a GitHub secret named DEEPLINK_PRIVATE_KEY"
fi

# --- 7. take a screenshot to see the DeepLink UI state ----------------------
take_screenshot "06_deeplink_launched"

# --- 8. print connection info (if found) ------------------------------------
log "=== DEEPLINK CONNECTION INFO ==="
log "DeepLink is installed + launched with TCC permissions granted."
log "If you have a DeepLink account, login via the RustDesk remote session."
log "The 'Allow Remote Control' section will show your Device ID + Password."
log ""
log "Bundle ID: $DEEPLINK_BUNDLE"
log "Binary: $DEEPLINK_BIN"
log ""
log "NOTE: DeepLink uses relay servers (not direct-IP like RustDesk)."
log "      It requires an account + private key for login."
log "      Connection speed depends on DeepLink's server location."
log ""
log "To connect from your client:"
log "  1. Open DeepLink on your Windows/Android/Mac device"
log "  2. Enter the Device ID shown in the Mac's 'Allow Remote Control' section"
log "  3. Enter the Password shown there"
log ""
ok "DeepLink setup complete (alternative to RustDesk)"
