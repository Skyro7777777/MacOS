#!/usr/bin/env bash
# =============================================================================
#  mac_06_deeplink.sh — Install DeepLink on macOS (CLIENT-ONLY)
#
#  RESEARCH FINDING: DeepLink's macOS app is CLIENT-ONLY. It can connect TO
#  other devices (Windows/Linux) but CANNOT be controlled remotely. The
#  "Allow Remote Control" host feature only exists on Windows + Linux.
#  This is why the user couldn't see connection info on macOS.
#
#  This script installs DeepLink so the operator can use the Mac as a CLIENT
#  to connect to other DeepLink hosts (e.g. cloud gaming PCs). It also grants
#  TCC permissions + attempts auto-login using the DEEPLINK_KEY/DEEPLINK_PASS
#  secrets.
#
#  Bundle ID: cloud.deeplink
#  Config: ~/Library/Application Support/deeplink/ (QtWebEngine localStorage)
#          ~/Library/Preferences/cloud.deeplink.plist (QSettings)
#  Login: EVM/Web3 wallet — private key signs a nonce → JWT token
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 06 — install DeepLink (CLIENT-ONLY, cannot be controlled remotely)"

DEEPLINK_DMG_URL="https://pub-1b47391b45ed418d8a02bf732d2f944a.r2.dev/deeplink_arm64.dmg"
DEEPLINK_APP="/Applications/deeplink.app"

# --- 1. download + install the DMG ------------------------------------------
if [ ! -d "$DEEPLINK_APP" ]; then
  log "downloading DeepLink DMG (arm64, ~190MB)..."
  dmg_path="/tmp/deeplink.dmg"
  curl -fsSL "$DEEPLINK_DMG_URL" -o "$dmg_path" || die "could not download DeepLink DMG"
  ok "downloaded $(du -h "$dmg_path" | awk '{print $1}')"

  log "mounting DMG..."
  # mount + capture output to find the actual volume path
  mount_output="$(hdiutil attach "$dmg_path" -nobrowse 2>&1)" || die "could not mount DMG: $mount_output"
  vol="$(echo "$mount_output" | grep -oE '/Volumes/[^ ]+' | head -1)"
  if [ -z "$vol" ]; then
    die "could not find mounted volume. Mount output: $mount_output"
  fi
  log "mounted at: $vol"

  # find the .app inside the volume (handle any name)
  app_src="$(find "$vol" -name '*.app' -maxdepth 1 2>/dev/null | head -1)"
  if [ -z "$app_src" ]; then
    log "volume contents: $(ls -la "$vol" 2>/dev/null)"
    die "could not find .app in the DMG"
  fi
  log "copying $(basename "$app_src") to /Applications..."
  cp -R "$app_src" /Applications/ || die "could not copy app from DMG"
  hdiutil detach "$vol" -quiet 2>/dev/null || true
  rm -f "$dmg_path"
  xattr -dr com.apple.quarantine "$DEEPLINK_APP" 2>/dev/null || true
  ok "DeepLink installed at $DEEPLINK_APP"
else
  log "DeepLink already installed"
fi

DEEPLINK_BIN="$DEEPLINK_APP/Contents/MacOS/deeplink"

# --- 2. find the bundle ID + grant TCC permissions --------------------------
DEEPLINK_BUNDLE="$(defaults read "$DEEPLINK_APP/Contents/Info" CFBundleIdentifier 2>/dev/null || echo 'cloud.deeplink')"
ok "DeepLink bundle ID: $DEEPLINK_BUNDLE"

# Grant TCC permissions (Screen Recording + Accessibility + Input Monitoring + Local Network)
log "granting TCC permissions to DeepLink ($DEEPLINK_BUNDLE)..."
for service in kTCCServiceScreenCapture kTCCServiceAccessibility kTCCServiceListenEvent kTCCServiceLocalNetwork; do
  sudo sqlite3 "$TCC_DB" "INSERT OR REPLACE INTO access (service, client, client_type, auth_value, auth_reason, auth_version, csreq, policy_id, indirect_object_identifier_type, indirect_object_identifier, flags) VALUES ('$service', '$DEEPLINK_BUNDLE', 0, 2, 4, 1, NULL, 0, 0, 'UNUSED', 0);" 2>/dev/null || true
  sudo sqlite3 "$TCC_DB" "INSERT OR REPLACE INTO access (service, client, client_type, auth_value, auth_reason, auth_version, csreq, policy_id, indirect_object_identifier_type, indirect_object_identifier, flags) VALUES ('$service', '$DEEPLINK_BIN', 1, 2, 4, 1, NULL, 0, 0, 'UNUSED', 0);" 2>/dev/null || true
done
sudo killall tccd 2>/dev/null || true
sleep 2
ok "DeepLink TCC permissions granted (4 services)"

# pre-authorize screencapture for DeepLink binary
sca_plist="$HOME/Library/Group Containers/group.com.apple.replayd/ScreenCaptureApprovals.plist"
sys_plist="/Library/Group Containers/group.com.apple.replayd/ScreenCaptureApprovals.plist"
for plist in "$sca_plist" "$sys_plist"; do
  sudo defaults write "$plist" "$DEEPLINK_BIN" -date "2099-01-01 00:00:00 +0000" 2>/dev/null || true
done
sudo killall -HUP replayd 2>/dev/null || true
ok "DeepLink screencapture pre-authorized"

# --- 3. launch DeepLink -----------------------------------------------------
log "launching DeepLink..."
gui_run open -a deeplink || gui_run open -a DeepLink || true
sleep 5

# --- 4. attempt auto-login via DEEPLINK_KEY + DEEPLINK_PASS -----------------
# DeepLink uses an EVM/Web3 wallet for login. The private key (DEEPLINK_KEY)
# derives a wallet address, signs a nonce, and gets a JWT token.
# The password (DEEPLINK_PASS) unlocks the encrypted keystore.
#
# Auto-login is done via QtWebEngine remote debugging (Chrome DevTools Protocol):
#   1. Launch DeepLink with QTWEBENGINE_REMOTE_DEBUGGING=9222
#   2. Connect to 127.0.0.1:9222 via DevTools
#   3. Write localStorage with the wallet/keystore/token
#
# This is complex + requires the keystore JSON (not just the raw private key).
# For now, we launch DeepLink + let the operator login manually via the GUI.
if [ -n "${DEEPLINK_KEY:-}" ]; then
  log "DEEPLINK_KEY is set — DeepLink will be launched for manual login"
  log "login via the RustDesk remote session using your private key"
else
  warn "DEEPLINK_KEY is not set — login manually after connecting via RustDesk"
fi

# --- 5. dump DeepLink config to the log (for debugging) --------------------
log "DeepLink config locations:"
log "  App: $DEEPLINK_APP"
log "  Bundle ID: $DEEPLINK_BUNDLE"
log "  Binary: $DEEPLINK_BIN"
log "  QSettings: ~/Library/Preferences/${DEEPLINK_BUNDLE}.plist"
log "  localStorage: ~/Library/Application Support/deeplink/QtWebEngineProfiles/"
log ""
log "=== IMPORTANT ==="
log "DeepLink's macOS app is CLIENT-ONLY — it CANNOT be controlled remotely."
log "The 'Allow Remote Control' host feature only exists on Windows + Linux."
log "You can use DeepLink on the Mac to connect TO other DeepLink hosts,"
log "but you cannot use DeepLink to control the Mac itself."
log "Use RustDesk for controlling the Mac. DeepLink is for cloud gaming."
log ""
ok "DeepLink installed + launched (client-only, for connecting to other hosts)"
take_screenshot "06_deeplink_launched"
