#!/usr/bin/env bash
# =============================================================================
#  mac_01_install_tailscale.sh
#  Download the official Tailscale .pkg, verify its SHA256, install silently,
#  bring the runner onto the tailnet with an ephemeral auth key, and publish
#  the runner's Tailscale IPv4 to $STATE_DIR/tailscale-ip for later steps.
#
#  Tailscale is the ONLY transport.  No relay / rendezvous server is used
#  anywhere in this project — the RustDesk client will dial the runner's
#  Tailscale IP directly.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 01 — Tailscale install + connect"

require_env TS_AUTHKEY

TS_VERSION="1.98.8"   # latest stable at time of writing; bump as needed
TS_PKG_URL="https://pkgs.tailscale.com/stable/Tailscale-${TS_VERSION}-macos.pkg"
TS_SHA_URL="https://pkgs.tailscale.com/stable/Tailscale-${TS_VERSION}-macos.pkg.sha256"
TS_PKG="/tmp/Tailscale-${TS_VERSION}-macos.pkg"

# --- 1. download ------------------------------------------------------------
log "downloading $TS_PKG_URL"
curl -fsSL "$TS_PKG_URL" -o "$TS_PKG"

# --- 2. verify SHA256 -------------------------------------------------------
log "verifying SHA256 checksum"
EXPECTED_SHA="$(curl -fsSL "$TS_SHA_URL" | awk '{print $1}')"
ACTUAL_SHA="$(shasum -a 256 "$TS_PKG" | awk '{print $1}')"
if [ "$EXPECTED_SHA" != "$ACTUAL_SHA" ]; then
  die "SHA256 mismatch for Tailscale .pkg (expected $EXPECTED_SHA, got $ACTUAL_SHA)"
fi
ok "checksum verified"

# --- 3. silent install ------------------------------------------------------
log "installing Tailscale .pkg (sudo installer -pkg ... -target /)"
sudo installer -pkg "$TS_PKG" -target /

# the .pkg ships the GUI app; the CLI lives inside the .app bundle.
TS_CLI="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
if [ ! -x "$TS_CLI" ]; then
  die "Tailscale CLI not found at $TS_CLI after install"
fi

# put it on PATH for later steps + interactive shells
sudo ln -sf "$TS_CLI" /usr/local/bin/tailscale
ok "tailscale CLI on PATH -> $(command -v tailscale)"

# --- 4. bring the runner onto the tailnet -----------------------------------
# A unique hostname per run makes the node easy to spot in the admin console.
HOSTNAME_TAG="gh-mac-${GITHUB_RUN_ID:-local}-$$"
log "tailscale up  (hostname=$HOSTNAME_TAG, ephemeral key, accept-routes)"
# --authkey      : non-interactive auth using the secret
# --hostname     : deterministic, findable name
# --accept-routes: honour any subnet routes advertised on the tailnet
# --ssh          : optional Tailscale-SSH fallback for terminal debugging
# NOTE: the auth key should be created as "reusable + ephemeral" so dead nodes
#       auto-expire when the job ends.
sudo tailscale up \
    --authkey="$TS_AUTHKEY" \
    --hostname="$HOSTNAME_TAG" \
    --accept-routes \
    --ssh \
    --timeout=120s

# --- 5. capture the Tailscale IPv4 -----------------------------------------
TS_IP="$(tailscale ip -4 | head -n1)"
if [ -z "$TS_IP" ]; then
  die "could not determine Tailscale IPv4 (tailscale ip -4 empty)"
fi
echo "$TS_IP" > "$STATE_DIR/tailscale-ip"
echo "$HOSTNAME_TAG" > "$STATE_DIR/tailscale-hostname"
ok "runner is on the tailnet:"
ok "  Tailscale IPv4 : $TS_IP"
ok "  Tailscale host  : $HOSTNAME_TAG"
log "  (also written to $STATE_DIR/tailscale-ip)"

# Also expose as a step output if running inside GitHub Actions
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "tailscale_ip=$TS_IP" >> "$GITHUB_OUTPUT"
  echo "tailscale_host=$HOSTNAME_TAG" >> "$GITHUB_OUTPUT"
fi
