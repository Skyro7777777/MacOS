# Connecting from Android

This guide assumes the workflow has already run and printed a connection-info
block containing the **Tailscale IPv4**, **RustDesk password**, etc.

---

## 1. Install Tailscale on Android

1. Install **Tailscale** from Google Play: <https://play.google.com/store/apps/details?id=com.tailscale.ipn>
2. Open it and sign in with the **same** account as the auth key in `TS_AUTHKEY`.
3. Tap the switch to **Connect**. Confirm when Android asks for VPN permission.

> You can verify the runner is reachable by pinging it from Termux or by
> checking the Tailscale app's "Devices" list — the runner shows up as
> `gh-mac-<run-id>`.

---

## 2. Install RustDesk on Android

1. Install **RustDesk** from Google Play: <https://play.google.com/store/apps/details?id=com.carriez.flutter_hbb>
   (or get the APK from <https://rustdesk.com/download>).

---

## 3. (Recommended) Lock RustDesk to direct-IP only

1. Open RustDesk → tap the **menu** (≡) → **Settings** → **Network** (or
   **ID/Relay server**).
2. Leave **ID Server**, **Relay Server**, **API Server** all **blank**.
3. Go back.

> With all three blank, the client only does direct-IP — exactly what we want
> over Tailscale. No traffic ever touches RustDesk's public infrastructure.

---

## 4. Connect

1. Copy the **Tailscale IPv4** from the workflow log (e.g. `100.96.123.45`).
2. On the RustDesk main screen, paste into the ID field, with port:
   ```
   100.96.123.45:21118
   ```
3. Tap **Connect**.
4. When prompted, enter the **RustDesk password** from the workflow log.
5. You should now see the macOS 15 desktop. Pinch to zoom; drag to pan.

---

## 5. Android-specific tips

| Need | How |
|---|---|
| **Right-click** | Long-press. |
| **Drag** | Tap-and-hold, then drag. |
| **Scroll** | Two-finger drag. |
| **Type** | Tap the keyboard icon in the RustDesk toolbar; Android keyboard pops up. |
| **Copy/paste** | RustDesk syncs the clipboard on recent versions — copy on Android, paste on Mac with ⌘V. |
| **Switch to mouse mode** | Tap the cursor icon in the toolbar for a virtual trackpad. |

---

## 6. Common Android client issues

| Symptom | Fix |
|---|---|
| `Connection failed` / timeout | Tailscale isn't connected (check the Tailscale app), or you're on a different tailnet. Android may have killed Tailscale in the background — disable battery optimization for Tailscale. |
| `Wrong password` | Re-copy from the workflow log. |
| Black screen | Screen Recording wasn't granted to RustDesk on the Mac. Re-run the workflow; watch step 03's logs. |
| Very laggy | Lower quality: RustDesk menu → **Display → Quality → Best speed**. Or switch your phone to Wi-Fi. |
| RustDesk shows a "relay" warning | You didn't blank the server fields in step 3. Go back and blank them. |

---

## 7. Ending the session cleanly

From the Mac desktop (via RustDesk), open Terminal and run:
```bash
touch /tmp/apple-project/remote-done
```

Or, if you have Termux + an SSH client on Android (macOS Remote Login is
enabled by the workflow in step 04):
```bash
ssh cihelper@100.96.123.45 "touch /tmp/apple-project/remote-done"
```
(Password is the `MAC_USER_PASSWORD` secret.)

The hold script exits the job within ~1 s. (If you forget, the job ends
automatically at `hold_minutes`.)
