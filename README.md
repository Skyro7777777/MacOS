# The_Apple_Project

> **Temporary GUI control of a GitHub Actions `macos-15` runner from Windows 11
> or Android — over Tailscale, via RustDesk direct-IP, with no relay server
> and no AI API key.**

---

## Why this exists

GitHub gives you a real macOS 15 (Sequoia, Apple Silicon) VM as a runner. It
has an **active Aqua/GUI session**, ~14 GB RAM, and — critically — the
binaries `bash`, `hosted-compute-agent` and `provisioner` are **pre-granted
Screen Recording** in System Settings (see `upload/02_after_popup_clear.png`).

That means you *can* drive this Mac like a real desktop for the lifetime of a
workflow job — for faster file transfer, running things on a TV, debugging a
build interactively, etc. The catch is that macOS 15's security model makes
**granting Screen Recording to a third-party remote-desktop app** genuinely
hard:

| Approach | Verdict on the GitHub `macos-15` runner |
|---|---|
| **VNC / Apple Screen Sharing** | ☠️ Dead end — black screen. Headless runner has no real framebuffer; VNC reads an empty buffer. Confirmed across every VNC variant. |
| **Direct `TCC.db` write for `kTCCServiceScreenCapture`** | ❌ SIP blocks the system TCC.db; Sequoia's `tccd` also validates the `csreq` blob. Works only for some user-level services. |
| **PPPC (MDM) profile** | ❌ No MDM on the runner, so `mdmclient` can't apply a profile. |
| **`tccutil grant`** | ❌ Doesn't exist — `tccutil` only `reset`s. |

This project uses the one combination that **does** work end-to-end:

```
   ┌──────────────┐    Tailscale (WireGuard)    ┌──────────────────────────┐
   │ Windows 11 / │  ─────────────────────────  │ GitHub macos-15 runner    │
   │   Android    │   direct IP :21118 (TCP)    │  RustDesk (direct-server) │
   │  RustDesk    │  ◄────────────────────────► │  Screen Recording granted │
   └──────────────┘     NO relay server          └──────────────────────────┘
```

The permission is granted by a **three-layer pipeline** (single method,
defence-in-depth):

1. **Layer 1 — `sqlite3` INSERT** into the system `TCC.db` + `killall tccd`.
   Fast, non-UI. Works reliably for *Accessibility*; *ScreenCapture* is often
   rejected by Sequoia's `csreq` validation, but it's cheap to try first.
2. **Layer 2 — `osascript` deterministic click-through** (PRIMARY for
   ScreenCapture). `bash`+`osascript` already have Accessibility + AppleEvents
   on the runner, so we open each privacy pane by deep-link URL, recursively
   search the AX tree for RustDesk's toggle, and click it. No AI, fully
   deterministic.
3. **Layer 3 — `ShowUI-2B` local vision agent** (AI FALLBACK). If the UI
   hierarchy has drifted, or RustDesk isn't yet in the list and the `+`
   file-picker needs driving, we boot the `showlab/ShowUI-2B` model **locally**
   (~4.2 GB, MPS fp16, no API key), feed it `screencapture` frames, and click
   with `cliclick`.

> **The "responsible process" trick that makes the AI layer possible:**
> `screencapture`, `osascript` and `cliclick` spawned by `bash` are
> TCC-attributed to `bash`, which already has Screen Recording + Accessibility.
> So the Python agent can **see** the screen and **click** without ever needing
> its own TCC grant. (We deliberately avoid `mss` / `PIL.ImageGrab` /
> `pyautogui`, which make the API call *inside* the Python binary and would
> need their own permission.)

---

## Repo layout (paste these at the root of your GitHub repo)

```
The_Apple_Project/
├── .github/workflows/
│   └── mac-remote-control.yml        # the only workflow — runs on macos-15
├── mac_lib.sh                        # shared shell helpers (sourcing library)
├── mac_00_setup_user.sh              # create helper admin user (known password)
├── mac_01_install_tailscale.sh       # download .pkg, verify SHA256, connect
├── mac_02_install_rustdesk.sh        # install RustDesk, write direct-IP config
├── mac_03_grant_permissions.sh       # THE pipeline: sqlite3 -> osascript -> ShowUI
├── mac_grant_permissions.applescript # deterministic AX click-through
├── mac_showui_agent.py               # local ShowUI-2B vision agent (fallback)
├── mac_04_start_rustdesk.sh          # launch in GUI session, verify port 21118
├── mac_05_hold_session.sh            # keep job alive until done-flag or timeout
├── mac_requirements.txt              # Python deps for the ShowUI agent
├── docs/
│   ├── CONNECT_WINDOWS.md            # step-by-step from a Windows 11 client
│   └── CONNECT_ANDROID.md            # step-by-step from an Android client
└── README.md                         # this file
```

---

## One-time setup

### 1. Tailscale account + auth key

1. Create a free Tailscale account at <https://login.tailscale.com>.
2. Go to **Settings → Keys → Generate auth key**.
3. Choose:
   - **Reusable** ✓ (so one key registers many runner instances)
   - **Ephemeral** ✓ (dead nodes auto-expire when the job ends)
   - **Tags** (optional, e.g. `tag:gh-runner` — lets you scope ACLs)
4. Copy the key. It looks like `tskey-auth-xxxxx...`.

### 2. GitHub repo secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name | Value | Required |
|---|---|---|
| `TS_AUTHKEY` | your Tailscale auth key (`tskey-auth-...`) | ✅ |
| `RUSTDESK_PASSWORD` | a strong password the client will type to connect | ✅ |
| `MAC_USER_PASSWORD` | password for the freshly-created helper admin user | ✅ |
| `MAC_USER` | helper username (default `cihelper`) | optional |

### 3. Install Tailscale on your client device(s)

- **Windows 11:** <https://tailscale.com/download/windows>
- **Android:** <https://tailscale.com/download/android>

Sign in to the **same** tailnet as the auth key.

### 4. Install the RustDesk client

- **Windows 11:** <https://rustdesk.com/download>
- **Android:** Google Play → "RustDesk"

(No server setup needed — we use direct-IP mode.)

---

## Running it

1. In your repo, go to **Actions → "macOS 15 Remote Control" → Run workflow**.
2. Pick **hold_minutes** (default 120, max 240) and click **Run**.
3. Watch the job log. After a few minutes you'll see a connection-info block:

```
  Tailscale IPv4 ... 100.x.y.z
  RustDesk port .... 21118
  RustDesk password  ********
```

4. On your client, open RustDesk and enter `100.x.y.z:21118` in the Connect
   field. Type the password. You're driving the Mac. 🎉
5. When finished, end the job cleanly by creating the done-flag:
   ```
   touch /tmp/apple-project/remote-done
   ```
   (Open Terminal on the Mac via the RustDesk session, or SSH over the
   Tailscale IP — the workflow enables macOS Remote Login in step 04:
   `ssh cihelper@100.x.y.z`.)

See [`docs/CONNECT_WINDOWS.md`](docs/CONNECT_WINDOWS.md) and
[`docs/CONNECT_ANDROID.md`](docs/CONNECT_ANDROID.md) for screenshots-level
walkthroughs.

---

## How the permission pipeline works (deep dive)

`mac_03_grant_permissions.sh` runs for each of three TCC services:

| Service | TCC key | Pane deep-link |
|---|---|---|
| Screen Recording | `kTCCServiceScreenCapture` | `x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture` |
| Accessibility | `kTCCServiceAccessibility` | `…?Privacy_Accessibility` |
| Input Monitoring | `kTCCServiceListenEvent` | `…?Privacy_ListenEvent` |

For each, it tries the layers in order and stops at the first success:

### Layer 1 — `sqlite3` INSERT
- Extracts RustDesk's designated code requirement via `codesign -d -r-`.
- Compiles it to a binary blob with `csreq`, hex-encodes it.
- Introspects the live `access` table schema (`PRAGMA table_info`) and builds a
  matching `INSERT OR REPLACE` so it never fails on a missing column.
- `sudo killall tccd` to force a re-read.
- **Outcome:** usually works for Accessibility; often silently rejected for
  ScreenCapture on Sequoia (tccd validates `csreq`). We accept that and move on.

### Layer 2 — `osascript` click-through (`mac_grant_permissions.applescript`)
- Opens the pane by deep-link URL.
- Waits for the System Settings window.
- **Recursively** walks the AX tree (`findSwitchForApp`) looking for an
  `AXGroup`/`AXRow` that contains *both* an `AXSwitch` and a matching
  `AXStaticText`. This is robust against minor hierarchy drift.
- Reads the switch value; if `0`, clicks it (set value, fallback to `click`).
- Dismisses the "Quit & Reopen" sheet by clicking **Later**.
- Returns `GRANTED` / `ALREADY_ON` / `NOT_IN_LIST` / `ERROR`.
- **Outcome:** works whenever RustDesk is already in the list (it registers
  itself the first time it tries to capture the screen). Fails only if the `+`
  file-picker needs driving — that's the AI's job.

### Layer 3 — ShowUI-2B local vision agent (`mac_showui_agent.py`)
- Installs `cliclick` + `transformers` + `torch` + `qwen-vl-utils` if missing.
- Loads `showlab/ShowUI-2B` (~4.2 GB) on MPS (fp16) — runs entirely locally,
  **no API key, no OpenAI, no relay**.
- Opens the pane, then loops up to 25 steps:
  1. `screencapture -x` → PNG (inherits bash's Screen Recording)
  2. ShowUI-2B grounds *"the toggle switch next to RustDesk"* → `[x, y]`
  3. `cliclick c:x,y` (inherits bash's Accessibility)
  4. If RustDesk isn't in the list: grounds *"the plus + button"*, clicks it,
     drives the file picker via **Cmd+Shift+G** → types `/Applications/RustDesk.app`
     → Enter → Open.
  5. Verifies the toggle is ON by sampling the pixel colour at the toggle
     centre (blue ≈ `#0A84FF` on Sequoia → ON).
  6. Dismisses "Quit & Reopen" → "Later".

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `tailscale up` hangs | The auth key may be expired or non-reusable. Regenerate as reusable+ephemeral. |
| RustDesk shows black screen | Screen Recording wasn't granted. Re-run the job; check the Layer-3 log for ShowUI grounding errors. |
| Port 21118 not listening | RustDesk didn't start in the GUI session. Check `pgrep -lf RustDesk`. The LaunchAgent may need `launchctl load` re-run. |
| osascript returns `NOT_IN_LIST` | Expected on the very first run — Layer 3 (ShowUI) should kick in and drive the `+` file picker. |
| ShowUI is too slow | It's a 2B model on MPS; ~3–8 s per grounding call. Fine for a one-shot permission grant. Increase `SHOWUI_MAX_STEPS` if needed. |
| Job dies before I connect | GitHub kills jobs with no log output for 10 min. The hold script heartbeats every 30 s — but don't minimize the Actions tab. |
| Sequoia monthly re-auth banner | Can't be silenced without MDM. Rarely fires on short-lived runners; if it does, dismiss it manually via RustDesk. |

---

## Security notes

- The runner is on your tailnet for the **duration of the job only**. With an
  ephemeral auth key, Tailscale auto-removes the node when the job ends.
- `RUSTDESK_PASSWORD` and `MAC_USER_PASSWORD` are GitHub secrets — they never
  appear in logs (the scripts redact them).
- The helper user (`cihelper`) has passwordless sudo — convenient for SSH
  debugging, but **revoke it** (delete `/etc/sudoers.d/cihelper`) if you're
  paranoid. The runner is ephemeral anyway.
- RustDesk runs in **direct-IP mode with empty rendezvous/relay/API servers**,
  so no traffic ever touches RustDesk's public infrastructure. The only network
  path is your Tailscale WireGuard tunnel.

---

## Why not just `tmate` / `ngrok RDP`?

- `action-tmate` gives you a **terminal** only — no GUI. Useless when you need
  to click through macOS permission dialogs or run a GUI app.
- `ngrok + VNC` to a Windows runner works, but on macOS you hit the black-screen
  VNC problem described above. This project exists precisely because VNC is a
  dead end on the macOS runner.

---

## License

MIT. The bundled third-party tools (Tailscale, RustDesk, ShowUI-2B, cliclick)
retain their own licenses.
