#!/usr/bin/env bash
# =============================================================================
#  mac_00_setup_user.sh — create a fresh admin user with a known password.
#
#  WHY:  the default `runner` user on the GitHub macOS image is SecureToken-
#  enabled and its password is NOT known / not resettable, even by root.
#  Some permission flows and login prompts need a password we actually know.
#  We therefore provision a second admin user (default: cihelper) whose
#  password we control, and tell the ShowUI-2B agent about it so it can type
#  it into any password prompt that appears while granting permissions.
#
#  The new user is NOT auto-logged-in; the existing `runner` Aqua session
#  stays active and is what RustDesk will capture.  The helper user exists
#  for authentication prompts + as an SSH/Tailscale-SSH fallback.
# =============================================================================
set -euo pipefail
source "$(dirname "$0")/mac_lib.sh"

log "Step 00 — provisioning helper admin user '$MAC_USER'"

require_env MAC_USER_PASSWORD

# idempotent: if the user already exists, just make sure it is an admin
if id "$MAC_USER" >/dev/null 2>&1; then
  warn "user '$MAC_USER' already exists — ensuring admin membership"
else
  log "creating user '$MAC_USER'"
  # sysadminctl is the supported, SecureToken-friendly way to add a user on
  # modern macOS.  -admin makes the new user a member of the admin group.
  sudo sysadminctl -addUser "$MAC_USER" \
      -fullName "CI Helper" \
      -password "$MAC_USER_PASSWORD" \
      -home "/Users/$MAC_USER" \
      -shell /bin/bash \
      -admin
  sudo createhomedict -c -u "$MAC_USER" || true
fi

# belt + suspenders: ensure admin group membership
sudo dscl . -append /Groups/admin GroupMembership "$MAC_USER" 2>/dev/null || true

# allow the helper user sudo without password (handy for SSH debugging)
sudo mkdir -p /etc/sudoers.d
echo "$MAC_USER ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/"$MAC_USER" >/dev/null
sudo chmod 0440 /etc/sudoers.d/"$MAC_USER"

# stash the creds where later steps (ShowUI agent) can read them
umask 077
sudo tee "$STATE_DIR/helper-user.env" >/dev/null <<EOF
MAC_USER=$MAC_USER
MAC_USER_PASSWORD=$MAC_USER_PASSWORD
EOF
sudo chown "$RUNNER_USER" "$STATE_DIR/helper-user.env"

ok "helper user '$MAC_USER' ready (admin, passwordless sudo)"
