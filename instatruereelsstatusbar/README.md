# InstaTrueReelStatusBar

Patch project for Instagram Android APK v435.0.0.37.76 — makes Reels play
edge-to-edge with transparent status bar, transparent bottom navigation bar,
and **transparent navigation bar for bottom sheets** (fixes the comments bar
black strip).

This is a fork of `InstaTrueReel/` with the new **CS1** patch that fixes the
"black strip beneath the Add Comments... box" issue.

## The Fix (CS1)

### Root Cause

When you open a Reel from the home feed / history / liked videos, the comments
bar appears at the bottom with an "Add Comments..." EditText and a **black
strip** beneath it. The black strip is the **MainActivity window's
`navigationBarColor` (BLACK)** showing through a bottom-padding gap.

Verified call chain (from decompiled jadx Java source):

1. `C7DN.A04()` creates `C54625Krc` (CommentListBottomsheetFragment) with a
   `C50186J5g` config that has **no explicit color** set (A07/A08 = 0).
2. `BottomSheetFragment.onResume()` calls `A05()`.
3. `A05()` computes `color = 255` (sentinel, since A07=A08=0) and calls
   `navigator.A0R(255)`.
4. `AbstractC109183lH.A0R(255)` checks `C109193lI.A0I(...)` → returns **FALSE**
   for the comments sheet → **early return** → nav bar is NEVER set transparent
   → stays BLACK.
5. Separately, `G28` inset listener adds bottom padding = nav-bar-height to
   `bottomSheetContainer`, creating a gap. The BLACK nav bar shows through.

### The Patch

**CS1** patches `BottomSheetFragment.A05()` to call `A0R(0)` (transparent)
instead of `A0R(color)`. When `A0R` receives `i=0` (not the sentinel 255), it
skips the early-return and calls `C54511fI.A04(activity, 0)` →
`window.setNavigationBarColor(0)` → **TRANSPARENT**.

This is analogous to the existing A5 patch (which forces transparent status bar
in `1fC.A04`), but for the navigation bar in bottom sheets.

## Patches

| Feature | Patch | Target | Effect |
|---------|-------|--------|--------|
| A1-A7 | Transparent status bar | `2ZS.smali`, `1fC.smali`, `6BM.smali` | Video behind floating status bar icons |
| B1-B4 | Floating bottom nav | `InstagramMainActivity.smali`, `0bQ.smali`, `6BM.smali` | Transparent bottom nav + comment composer bar |
| C1-C2 | Translucent comment sheet | `EPN.smali`, `BottomSheetFragment.smali` | 80% black sheet panel (readable) |
| **CS1** | **Transparent nav bar for sheets** | **`BottomSheetFragment.smali` A05()** | **Fixes comments bar black strip** |
| D1-D3 | TikTok fullscreen | `VBP.smali`, `33g.smali` | Landscape rotation + scrubber |

## Build

The GitHub Actions workflow `.github/workflows/insta-truereelsstatusbar-build.yml`
builds the patched APK:

1. Checks out the repo (with LFS for the APK)
2. Decodes with `apktool d -r` (smali only, resources kept binary)
3. Runs `python3 instatruereelsstatusbar/patches/apply_patches.py decoded`
4. Rebuilds with `apktool b`
5. Signs with `uber-apk-signer` (debug key)
6. Uploads `InstaTrueReelStatusBar-patched.apk` artifact

Trigger via GitHub Actions UI (Run workflow) or API:
```
POST /repos/Skyro7777777/MacOS/actions/workflows/insta-truereelsstatusbar-build.yml/dispatches
{"ref":"main","inputs":{"features":"all"}}
```

## Install

Uninstall the current Instagram first (signature changed), then install the
patched APK.
