#!/usr/bin/env bash
# =============================================================================
#  mac_01_install_tailscale.sh
#  Install Tailscale via the Homebrew FORMULA (not the .pkg / not the cask),
#  start the tailscaled daemon as root, and bring the runner onto the tailnet
#  with an ephemeral auth key.
#
#  WHY HOMEBREW FORMULA INSTEAD OF THE .pkg:
#     The standalone .pkg installs a GUI .app whose CLI binary crashes with
#       "Tailscale/BundleIdentifiers.swift:47: Fatal error: The current
#        bundleIdentifier is unknown to the registry"
#     when invoked via `sudo tailscale up` before the .app has been registered
#     with LaunchServices (root's LS context doesn't know the bundle).
#     The Homebrew FORMULA (`brew install tailscale`) installs `tailscale`
#     (CLI) + `tailscaled` (daemon) as plain standalone binaries — no GUI app,
#     no LaunchServices, no bundle-identifier crash.  Perfect for CI.
#
#  Tailscale is the ONLY transport.  No relay / rendezvous server is used
#  anywhere in this project — the RustDesk client will dial the runner's
#  Tailscale IP directly.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 01 — Tailscale install (Homebrew formula) + connect"

require_env TS_AUTHKEY

# --- 1. install via Homebrew formula ----------------------------------------
# `brew install tailscale`  → formula (CLI + tailscaled daemon)
# `brew install --cask tailscale` → GUI .app (we do NOT want this)
if ! command -v tailscale >/dev/null 2>&1; then
  log "installing tailscale via Homebrew formula (not cask)"
  brew install tailscale
else
  ok "tailscale already on PATH"
fi

# Locate the binaries.  On Apple Silicon: /opt/homebrew/{bin,sbin}
# On Intel: /usr/local/{bin,sbin}.  Use brew --prefix for portability.
BREW_PREFIX="$(brew --prefix)"
TS_BIN="${BREW_PREFIX}/bin/tailscale"
TSD_BIN="${BREW_PREFIX}/sbin/tailscaled"
[ -x "$TS_BIN" ]  || die "tailscale CLI not found at $TS_BIN after brew install"
[ -x "$TSD_BIN" ] || die "tailscaled daemon not found at $TSD_BIN after brew install"
ok "tailscale: $("$TS_BIN" version 2>/dev/null | head -n1)"

# --- 2. start tailscaled as root (needed for the TUN network device) ---------
log "starting tailscaled daemon (root, background)"
sudo mkdir -p /var/lib/tailscale /var/run/tailscale

# kill any stale tailscaled from a previous attempt
sudo pkill -x tailscaled 2>/dev/null || true
sleep 1

# launch tailscaled in the background as root
#   --state  : persistent state file (node identity)
#   --socket : the UNIX socket the CLI talks to
sudo nohup "$TSD_BIN" \
  --state=/var/lib/tailscale/tailscaled.state \
  --socket=/var/run/tailscale/tailscaled.sock \
  > /tmp/tailscaled.log 2>&1 &
TSD_PID=$!
log "tailscaled PID=$TSD_PID  (log: /tmp/tailscaled.log)"

# wait for the socket to appear (up to 15 s)
SOCKET_READY=false
for i in $(seq 1 15); do
  if [ -S /var/run/tailscale/tailscaled.sock ]; then
    SOCKET_READY=true
    break
  fi
  sleep 1
done
if [ "$SOCKET_READY" = "false" ]; then
  err "tailscaled did not create its socket in 15 s.  Log tail:"
  tail -n 20 /tmp/tailscaled.log 2>/dev/null || true
  die "tailscaled startup failed"
fi
ok "tailscaled socket ready at /var/run/tailscale/tailscaled.sock"

# --- 3. bring the runner onto the tailnet -----------------------------------
# A unique hostname per run makes the node easy to spot in the admin console.
HOSTNAME_TAG="gh-mac-${GITHUB_RUN_ID:-local}-$$"
log "tailscale up  (hostname=$HOSTNAME_TAG, ephemeral key, accept-routes, ssh)"
# --authkey      : non-interactive auth using the secret
# --hostname     : deterministic, findable name
# --accept-routes: honour any subnet routes advertised on the tailnet
# --ssh          : enables Tailscale-SSH inbound (so the operator can
#                  `ssh cihelper@<ts-ip>` to touch the done-flag file)
# NOTE: the auth key should be created as "reusable + ephemeral" so dead nodes
#       auto-expire when the job ends.
sudo "$TS_BIN" up \
    --authkey="$TS_AUTHKEY" \
    --hostname="$HOSTNAME_TAG" \
    --accept-routes \
    --ssh \
    --timeout=120s

# --- 4. capture the Tailscale IPv4 -----------------------------------------
TS_IP="$(sudo "$TS_BIN" ip -4 | head -n1)"
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
