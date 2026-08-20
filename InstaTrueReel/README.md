# InstaTrueReel — README

> Make Instagram Reels play in **true full-screen, edge-to-edge** (like TikTok),
> and add a TikTok-style **horizontal-video fullscreen** experience.
> Implemented by patching the Instagram Android APK.

**Status:** 🧭 EXPLORATION / UNDERSTANDING phase. No patches written yet.
This is a hard reverse-engineering task (150k+ decompiled Java files). We move
carefully: understand → explore source → design → patch → build → verify.

---

## What we want (the goal)

Instagram currently letterboxes Reels between two **solid black strips**:
- a top black strip holding the status bar, and
- a bottom black strip holding the main nav bar (Home/Reels/Create/Search/Profile)
  or, when comments are open, an opaque black comment sheet.

The video does **not** reach the status bar or the bottom bar.

TikTok does it differently — the video plays **edge-to-edge behind** the status
bar and the bottom bar; the bar icons are drawn as thin **floating white lines
over the video**, and the comment overlay is a **translucent frosted-glass**
sheet with the video still visible behind it.

We want Instagram Reels to behave like TikTok:

| # | Feature | TikTok (target) | Instagram (current) |
|---|---------|-----------------|---------------------|
| 1 | **Status bar** | video behind it; icons = floating white lines | solid black strip, video cut off |
| 2 | **Main bottom nav** (Home/Reels/...) | floating white-line icons over video | solid black bar, video cut off |
| 3 | **Comment overlay** | translucent frosted glass, video visible behind | opaque black sheet blocks video |
| 4 | **Horizontal (16:9) video fullscreen** | "Full Screen" button → rotate landscape, hide side buttons, show seekbar (YouTube-like) | ⚠️ Instagram v435 **already has** an expand button (upper-right) — need to verify its behavior (see open questions) |

See `notes/02-visual-analysis.md` for screenshot-by-screenshot evidence.

---

## The starting point (already in this repo)

- `Instagram-v435.0.0.37.76-patches-v3.8.0.apk` (Git-LFS, ~251 MB)
  → an Instagram APK **already patched once** with ReVanced patches v3.8.0.
- `.github/workflows/jadx-decompile.yml`
  → decompiles the APK with **jadx 1.5.6** (best quality, `--deobf`,
  `--decompilation-mode restructure`, `--show-bad-code`, no resources).
  Output artifact: `instagram-decompiled-java` (~150,000 Java files).
  Latest artifact: https://github.com/Skyro7777777/MacOS/actions/runs/31267254016/artifacts/9024779037

> ⚠️ jadx Java output is **for reading/understanding only**. To actually PATCH
> the APK we must use **apktool** (Smali) or **ReVanced Patcher** (which edits
> Smali via Kotlin patch classes). jadx output cannot be recompiled into a
> working APK. See `notes/06-design-brainstorm.md`.

---

## Repo layout (InstaTrueReel)

```
InstaTrueReel/
├── README.md                          ← this file (overview + status)
├── notes/
│   ├── 01-task-understanding.md       ← what the user wants, in plain words
│   ├── 02-visual-analysis.md          ← screenshot-by-screenshot (target vs current)
│   ├── 03-research-findings.md        ← web research: Android APIs, ReVanced, TikTok
│   ├── 04-source-exploration-roadmap.md ← what classes/patterns to hunt in 150k files
│   ├── 05-open-questions.md           ← things to clarify before/while coding
│   ├── 06-design-brainstorm.md        ← preliminary patch ideas (NOT a final plan)
│   └── THINK_LOG.md                   ← running scratchpad (append-only)
├── workflows/                         ← (to be added) GitHub Actions workflows
└── patches/                           ← (to be added) actual smali/ReVanced patches
```

`workflows/` and `patches/` are empty for now — we add them once we know exactly
what to patch (after source exploration).

---

## How we work (process)

1. **Understand** ✅ (this commit)
2. **Explore source** — use a GitHub Actions workflow that re-runs jadx (or
   downloads the existing artifact) and greps for the Reels UI classes,
   `fitsSystemWindows`, `setDecorFitsSystemWindows`, BottomSheet/Comment
   fragments, the existing fullscreen button, etc. Findings committed to repo.
3. **Design patches** — decide exact smali/method changes per feature.
4. **Patch + build** — apktool decode → smali edits → build → zipalign → sign,
   all in a workflow (sandbox too small). Upload patched APK as artifact.
5. **Verify** — install on device, screenshot, compare to target.

Decompilation/compilation is done **in GitHub Actions**, not in the local
sandbox (sandbox has size/time limits). The GitHub token is used for repo ops.

---

## Working notes / conventions

- All heavy work (jadx, apktool, build, sign) happens in **GitHub Actions
  workflows**. The sandbox is only for thinking, doc-writing, and small greps.
- Each exploration step writes its findings into `notes/` so context is never
  lost between prompts.
- `THINK_LOG.md` is an append-only scratchpad for mid-flight reasoning.
