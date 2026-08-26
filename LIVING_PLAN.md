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

### Phase 0 — Ground-truth diagnostic  (IN PROGRESS)
- Workflow: `.github/workflows/mac-diagnose.yml` (no secrets needed).
- Script: `mac_diagnose.py` — captures SIP status, TCC.db schema, all existing
  ScreenCapture/Accessibility/InputMonitoring rows, attempts the real grant
  (clone a known-good row → rewrite client to RustDesk → INSERT → killall tccd
  → read back), launches RustDesk, checks port 21118, screenshots the System
  Settings Screen Recording pane, dumps the AX tree.
- Artifacts: `mac-diagnose` (JSON summary + 2 PNGs).
- **Expected duration:** ~8–12 min.

### Findings
*(updated after each run)*

| Run | SIP | can_write_tcc | grant_persisted | rustdesk_listening | Verdict |
|---|---|---|---|---|---|
| _pending_ | _?_ | _?_ | _?_ | _?_ | _awaiting first run_ |

---

## 6. Next actions (after diagnostic verdict)

- **If Phase 1 viable (SIP off + grant persists):** rewrite `mac_03_grant_permissions.sh`
  as a pure TCC.db granter (delete the osascript/ShowUI/web-remote code paths),
  add `mac-remote-control.yml` end-to-end workflow, document the 3 required
  secrets, and run a live end-to-end test (operator connects from RustDesk).
- **If Phase 2 needed (SIP off, tccd rejects):** build the artifact round-trip
  agent — a small `mac_ai_runner.py` on the Mac that loops `screencapture →
  upload-artifact-via-poll → read commands.json → cliclick → repeat`, and an
  orchestrator in the cloud that VLM-analyses each screenshot and pushes the
  next command.
- **If Phase 3 needed (SIP on):** keep `web_remote.py`, add guided "click
  these exact coordinates" presets derived from the diagnostic AX dump, and
  document the 90-second manual grant procedure.

---

## 7. Open questions

1. Is SIP actually off on `macos-15`? (diagnostic answers this)
2. Does `tccd` re-validate csreq on read, and if so does our compiled blob pass?
3. Does RustDesk need a **first launch** to register itself in the Screen
   Recording list before the TCC.db row is meaningful? (the diagnostic launches
   it after the INSERT to test this)
4. Does the GitHub `macos-15` runner still ship `hosted-compute-agent` +
   `provisioner` pre-granted Screen Recording (so `screencapture` works)?
5. Is there a Sequoia-specific `policy_id` / `flags` value the row needs?
   (the diagnostic clones a known-good row's values to answer this)

Each of these is answerable from the Phase-0 artifact; no guessing required.
