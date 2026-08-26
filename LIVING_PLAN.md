# The Apple Project — Living Plan

> This is a **living document**. It captures the current understanding, the
> active hypothesis, the decision tree, and the log of what each experiment
> proved. It is updated every time a workflow run teaches us something new.

**Repo:** `Skyro7777777/MacOS`
**Goal:** Remote GUI control of a GitHub Actions `macos-15` runner from
Windows/Android via Tailscale + RustDesk (direct-IP, no relay, no AI API key),
for the lifetime of a workflow job.
**Hard sub-problem:** granting macOS 15 Sequoia `kTCCServiceScreenCapture`
(Screen Recording) to RustDesk so it can capture the screen.

---

## 1. The goal in one diagram

```
 ┌──────────────┐   Tailscale (WireGuard)   ┌──────────────────────────┐
 │ Windows 11 / │ ────────────────────────── │ GitHub macos-15 runner    │
 │   Android    │   direct IP :21118 (TCP)   │  RustDesk (direct-server)  │
 │  RustDesk    │ ◄─────────────────────────►│  Screen Recording GRANTED │
 └──────────────┘     NO relay server        └──────────────────────────┘
```

The ONLY thing standing between us and a working session is the macOS TCC
permission grant to RustDesk. Everything else (Tailscale, RustDesk direct-IP
config, the Aqua session, SSH) is solved and present in the existing scripts.

---

## 2. Why the previous plan didn't work

The README documents a three-layer pipeline (sqlite TCC.db → osascript AX →
local ShowUI-2B vision agent). In practice, on macOS 15 Sequoia:

| Layer | Verdict (from README + code comments) |
|---|---|
| `sqlite3` INSERT into system TCC.db | README claims "SIP blocks the system TCC.db; Sequoia's tccd also validates the csreq blob". |
| `osascript` AX click-through | Works **only** when RustDesk is already in the privacy list. Fails when the `+` file-picker must be driven. |
| Local ShowUI-2B vision agent | 3–8 s per grounding call, flaky grounding, 4.2 GB model, MPS fp16 — too slow to be reliable in a job window. |
| `mac_vision_agent.py` (Apple Vision OCR + AX) | OCR finds text but text positions ≠ button positions (the "Allow" *label* sits above the "Allow" *button*). |
| `mac_tgpt_agent.py` (TCC.db + AX fallback) | TCC.db write reportedly rejected for ScreenCapture. |
| `web_remote.py` (manual browser click control) | **This actually works** (it uses the responsible-process trick) — but needs a human operator to click. The user deleted the workflow because the *automation* kept failing. |

The net effect: every automated layer either hit Sequoia's hardening or was
too slow/flaky, so the only reliable path was the manual web remote — which
defeats the "just run the workflow and connect" goal.

---

## 3. The breakthrough hypothesis (to be verified by `mac-diagnose.yml`)

**actions/runner-images#8162** states that GitHub's `macos-13` runner image
ships with **SIP disabled** (unlike macos-11/12 which had it on). If the
`macos-15` image inherits this, then the README's central premise — *"SIP
blocks the system TCC.db"* — is **false for the GitHub runner specifically**.

If SIP is off on the runner:

- `sudo sqlite3 "/Library/.../TCC.db" "INSERT ..."` is no longer blocked by SIP.
- The only remaining obstacle is `tccd`'s **csreq blob validation** — it checks
  the stored code-requirement blob against the actual binary on read and
  silently ignores rows that don't match. This is solvable: we compile
  RustDesk's real csreq from `codesign -d -r-` (already done in
  `mac_tgpt_agent.py`).
- If the INSERT **persists after `killall tccd`** and tccd accepts it, the
  Screen Recording grant becomes **fully automated — no clicking, no AI, no
  human in the loop.** That is the dream outcome.

### Decision tree (Phase 1 / 2 / 3)

```
csrutil status on macos-15 runner
        │
        ├── "disabled"  ──► SIP is OFF (matches runner-images#8162)
        │       │
        │       ├── TCC.db INSERT for ScreenCapture PERSISTS after killall tccd
        │       │       └──► PHASE 1: fully automated granter (ideal)
        │       │             rewrite mac_03 as: sqlite3 INSERT ×3 services →
        │       │             killall tccd → launch RustDesk → verify 21118 → hold
        │       │             NO osascript, NO cliclick, NO AI, NO human.
        │       │
        │       └── INSERT runs but tccd REJECTS the row (csreq mismatch /
        │           wrong policy_id / wrong flags)
        │               └──► PHASE 2: AI outer-loop (uses VLM skill from cloud)
        │                     workflow captures screenshots + uploads as artifact;
        │                     orchestrator downloads artifact, VLM analyses the UI,
        │                     computes next click, commits a `commands.json`;
        │                     workflow polls + executes the command, re-captures.
        │                     (Responsible-process trick means screencapture +
        │                     cliclick already work via bash's pre-grant.)
        │
        └── "enabled"  ──► SIP is ON (unexpected)
                └──► PHASE 3: polish the manual web_remote (it works, just needs UX)
                      + investigate MDM-free PPPC alternatives.
```

---

## 4. What each skill is used for

| Skill / Tool | Where it's used |
|---|---|
| **web-search** | Research SIP, TCC.db Sequoia schema, csreq, runner-images quirks (ongoing). |
| **VLM (vision)** | Analyse screenshots uploaded as workflow ARTIFACTS — read the System Settings privacy pane, verify toggle state, find RustDesk's row, debug any black-screen. The orchestrator runs VLM in the cloud; the Mac only captures. |
| **GitHub API (fine-grained PAT)** | Push code, trigger `workflow_dispatch`, poll run status, download artifacts — all from the cloud sandbox. |
| **LLM** | Synthesise findings + draft refined scripts between runs. |
| `osascript` / AX / `cliclick` / `sqlite3` / `screencapture` | On-Mac primitives, already present in the repo. |

The "responsible process" trick (bash is pre-granted Screen Recording;
`screencapture`/`cliclick`/`osascript` children inherit it) is what makes the
AI-outer-loop path viable even without a TCC grant for Python itself.

---

## 5. Execution timeline + log

### Phase 0 — Ground-truth diagnostic  ✅ DONE (run 32998309247, 2026-08-26)
- Workflow: `.github/workflows/mac-diagnose.yml` (no secrets needed).
- Script: `mac_diagnose.py` — captured SIP status, TCC.db schema, existing
  ScreenCapture/Accessibility/InputMonitoring rows, attempted the real grant,
  launched RustDesk, checked port 21118, screenshotted the System Settings
  Screen Recording pane, dumped the AX tree.
- Artifacts: `mac-diagnose` (JSON summary + 2 PNGs) — downloaded + analysed.

### Findings — CONFIRMED

| Field | Value | Meaning |
|---|---|---|
| macOS | 15.7.7 (Build 24G720), arm64 | Sequoia, Apple Silicon |
| `csrutil status` | **"System Integrity Protection status: disabled."** | ✅ SIP OFF — TCC.db is root-writable |
| user | `runner` | the Aqua-session owner |
| RustDesk | 1.4.9 (brew cask) | `com.carriez.rustdesk`, team HZF9JMC8YN |
| known-good ScreenCapture rows | `bash`, `hosted-compute-agent`, `provisioner` — **all auth_value=2, csreq EMPTY** | tccd does NOT validate csreq on this image |
| TCC.db schema (Sequoia 15.7) | `service, client, client_type, auth_value, auth_reason, auth_version, csreq, policy_id, indirect_object_identifier_type, indirect_object_identifier, indirect_object_code_identity, flags, last_modified, pid, pid_version, boot_uuid, last_reminded` | NO `expired_at`; my generic INSERT handled it correctly via `PRAGMA table_info` introspection |
| grant INSERT | rc=0 | ✅ INSERT OR REPLACE succeeded |
| `killall tccd` | rc=0 | ✅ tccd restarted |
| readback | `auth_value=2, csreq_hex=""` | ✅ row PERSISTED after tccd restart |
| **AX read of System Settings** | `SWITCH name=RustDesk value=1` | ✅✓✓ **macOS itself shows RustDesk's toggle ON — grant is REAL + HONOURED** |
| port 21118 | `RustDesk ... TCP *:21118 (LISTEN)` | ✅ RustDesk server running |
| screencapture | rc=0, 195 KB PNG | ✅ bash's own Screen Recording works |

### Verdict: PHASE 1 IS VIABLE ✅

The fully-automated TCC.db granter works on the GitHub `macos-15` runner.
No clicking, no AI, no human in the loop required. The breakthrough was
realising the README's "SIP blocks the system TCC.db" premise is **false for
the GitHub runner** (SIP is off per actions/runner-images#8162), and that the
pre-granted entries carry **empty csreq blobs** so we don't need the fragile
`csreq` compilation step at all — `csreq=NULL` matches the proven pattern.

---

## 6. Next actions

### Phase 1 — production granter  ✅ BUILT (verifying now)
- `mac_grant_tcc.py` — clean, schema-introspecting, pure-sqlite3 granter.
  Writes `csreq=NULL` (matching the known-good pattern), `auth_value=2`,
  `auth_reason=4`, restarts tccd, then **AX-verifies** each toggle = ON.
- `mac_03_grant_permissions.sh` — rewritten to just call the granter
  (with `FALLBACK_WEB_REMOTE=1` opt-in for the manual web remote if a future
  macOS breaks the automated path).
- `mac-grant-verify.yml` — no-secrets workflow that proves the granter
  end-to-end (install RustDesk → grant → AX-verify → screenshot all 3 panes →
  upload). Run this BEFORE setting up Tailscale secrets.
- `mac-remote-control.yml` — full end-to-end workflow (00→01→02→03→04→05).

### Phase 1b — end-to-end live test (needs secrets)
Requires 3 repo secrets (see README §"One-time setup"):
- `TS_AUTHKEY` — Tailscale reusable+ephemeral auth key
- `RUSTDESK_PASSWORD` — the password the client types
- `MAC_USER_PASSWORD` — password for the `cihelper` helper admin user

Then: Actions → "macOS 15 Remote Control" → Run workflow. The grant is now
automated, so after ~5 min the connection-info block prints and the operator
connects via RustDesk client to `<tailscale-ip>:21118`.

### Phase 2 / 3 — held in reserve
Only needed if a future macOS image bumps SIP back on or re-introduces csreq
validation. The `web_remote.py` manual fallback + the AI outer-loop design
(artifact round-trip with cloud VLM) remain available behind `FALLBACK_WEB_REMOTE`.

---

## 7. Open questions — answered by Phase 0

1. ✅ Is SIP actually off on `macos-15`? **YES — "System Integrity Protection status: disabled."**
2. ✅ Does `tccd` re-validate csreq on read? **No** — the pre-granted entries have empty csreq, and our `csreq=NULL` row was honoured (AX toggle = ON).
3. ✅ Does RustDesk need a first launch to register in the list? **No** — the TCC.db row alone puts RustDesk in the Screen Recording list (AX saw it after INSERT, before any RustDesk launch in step 8).
4. ✅ Does the runner still pre-grant bash/hosted-compute-agent/provisioner? **YES** — all three present with auth_value=2. `screencapture` works (195 KB PNG captured).
5. ✅ Sequoia-specific `policy_id`/`flags`? **policy_id=0, flags=0** (matches the pre-granted rows). `last_modified`/`boot_uuid`/`last_reminded` use SQLite defaults when NULL is inserted.

### Remaining open question
6. **Functional end-to-end**: does a RustDesk *client* actually receive a
   non-black screen after this grant? The AX toggle=ON is conclusive at the OS
   level, but the only 100%-proof test is a live client connection over
   Tailscale — that's Phase 1b (needs the 3 secrets).
