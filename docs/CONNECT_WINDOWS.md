# Connecting from Windows 11

This guide assumes the workflow has already run and printed a connection-info
block containing the **Tailscale IPv4**, **RustDesk password**, etc.

---

## 1. Install Tailscale on Windows

1. Download from <https://tailscale.com/download/windows> and install.
2. Sign in with the **same** account (or an account on the same tailnet) as the
   auth key you put in the `TS_AUTHKEY` secret.
3. Click the Tailscale tray icon → confirm you're **Connected**.

> The GitHub runner appears in your Tailscale admin console
> (<https://login.tailscale.com/admin/machines>) as `gh-mac-<run-id>`.

---

## 2. Install RustDesk on Windows

1. Download from <https://rustdesk.com/download> (the Windows `.exe` installer).
2. Install with default options.

---

## 3. (Recommended) Lock RustDesk to direct-IP only

So the client never tries RustDesk's public rendezvous/relay servers:

1. RustDesk → **Settings** (gear icon) → **Network**.
2. Under **ID Server / Relay Server / API Server**, leave all fields **blank**.
3. Save.

> With all three blank, RustDesk will only ever attempt direct-IP connections —
> exactly what we want over Tailscale.

---

## 4. Connect

1. Copy the **Tailscale IPv4** from the workflow log (e.g. `100.96.123.45`).
2. In RustDesk's main window, paste it into the **ID** field, with the port:
   ```
   100.96.123.45:21118
   ```
   (If you omit `:21118`, RustDesk uses the default direct-IP port 21118
   anyway — but being explicit avoids ambiguity.)
3. Click **Connect**.
4. When prompted, enter the **RustDesk password** from the workflow log.
5. You should now see the macOS 15 desktop. 🎉

---

## 5. Common Windows client issues

| Symptom | Fix |
|---|---|
| `Failed to connect` / timeout | Tailscale isn't connected, or you're on a different tailnet than the auth key. Check the tray icon. |
| `Wrong password` | Re-copy the password from the workflow log — it's in `connection-info.txt`. |
| Black screen on the Mac side | Screen Recording wasn't granted to RustDesk. Re-run the workflow and watch the Layer-2/Layer-3 logs in step 03. |
| Can move mouse but screen frozen | Network is congested. In RustDesk, lower the quality: **Display → Quality → Best speed**. |
| RustDesk says "relay" / shows a relay warning | You didn't blank the server fields in step 3. Go back and blank them. Over Tailscale there is never a reason to use a relay. |

---

## 6. File transfer

Once connected, RustDesk supports drag-and-drop file transfer **Windows → Mac**
on recent versions. For **Mac → Windows**, use the RustDesk **File transfer**
mode (click the folder icon in the RustDesk toolbar), or `scp` over SSH
(the workflow enables macOS Remote Login on the Tailscale IP):

```powershell
# from Windows PowerShell (macOS Remote Login is enabled by the workflow)
scp cihelper@100.96.123.45:/Users/runner/some-file.txt .
```

(Password is the `MAC_USER_PASSWORD` secret.)

---

## 7. Ending the session cleanly

When you're done, end the GitHub Actions job so the runner is released:

**Option A — from the Mac desktop (easiest):**
Open Terminal on the Mac (via RustDesk) and run:
```bash
touch /tmp/apple-project/remote-done
```

**Option B — from Windows via SSH over Tailscale:**
```powershell
ssh cihelper@100.96.123.45 "touch /tmp/apple-project/remote-done"
```
(Password is the `MAC_USER_PASSWORD` secret. macOS Remote Login is enabled
by the workflow in step 04.)

The hold script polls for that file every second and exits the job within ~1 s
of it appearing. (If you forget, the job ends automatically at `hold_minutes`.)
