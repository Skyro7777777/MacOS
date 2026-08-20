# 07 — Patch Implementation (first iteration)

**Status:** Patches written + verified locally against decoded smali.
Build workflow ready. NOT yet built/tested on-device.

## Patch script
`InstaTrueReel/patches/apply_patches.py` — runs after apktool decode,
before apktool build. Applies all patches via targeted find-and-replace.

## Build workflow
`.github/workflows/insta-truereel-build.yml` — `workflow_dispatch`:
1. Checkout repo (LFS for APK)
2. apktool decode (full: smali + resources)
3. `python3 InstaTrueReel/patches/apply_patches.py decoded`
4. apktool build → zipalign → sign (uber-apk-signer, debug key)
5. Upload `InstaTrueReel-patched-apk` artifact

## Patches implemented (9 total)

### Feature A — transparent status bar (video behind floating icons)
| ID | File (smali) | What | Verified |
|----|-------------|------|----------|
| A1 | `X/2ZS.smali` (C2ZS.A01) | Zero decorView background color (v3→0 before `0cW.A0R`) | ✅ pattern found + applied |
| A2 | `X/2ZS.smali` (C2ZS.A02) | Zero `android.R.id.content` background (p2→0 before `0cW.A0R`) | ✅ pattern found + applied |
| A3 | `X/6BM.smali` (C6BM.Fji) | Zero top inset (p1→0 before `6wm.A0w` = setPadding) | ✅ pattern found + applied |

**Effect:** decorView + content view transparent, top inset zeroed → video
extends under the transparent status bar. Status bar icons already drawn
white by `AbstractC54451fC.A05(activity, false)` (existing IG code).

### Feature B — floating bottom nav (transparent + no gap)
| ID | File (smali) | What | Verified |
|----|-------------|------|----------|
| B1 | `InstagramMainActivity.smali` | Zero `swipeable_tab_view_pager.bottomMargin` (3 occurrences, filtered by `0x7f0b3f45` proximity) | ✅ 3 patched |
| B2 | `res/values/styles.xml` | `igds_color_clips_tab_bar_background` → `#00000000` (4 theme variants) | ✅ pattern confirmed (resource patch runs in workflow) |

**Effect:** bottom nav bg transparent (icons already white = `igds_prism_gray_00`
= `#fff8f9f9`), zero bottomMargin → video extends to bottom edge behind nav.

### Feature C — translucent comment sheet
| ID | File (smali) | What | Verified |
|----|-------------|------|----------|
| C1 | `X/EPN.smali` | Zero ALL `0cW.A05(View;F;I)` dimming alpha calls (8 occurrences) | ✅ 8 zeroed |
| C2 | `BottomSheetFragment.smali` | Replace `setColorFilter` color with `0xCC000000` (80% black, 2 occurrences) | ✅ 2 patched |

**Effect:** dimming view no longer blacks out the video; sheet panel is 80%
translucent black → video visible behind comments. (True frosted blur via
`FrostedOverlayView` is a future enhancement.)

### Feature D — TikTok-style horizontal fullscreen
| ID | File (smali) | What | Verified |
|----|-------------|------|----------|
| D1 | `X/VBP.smali` (FSS) | Insert `6mW.A00(activity, 0)` = `setRequestedOrientation(LANDSCAPE)` at method start | ✅ applied |
| D2 | `X/VBP.smali` (EvT) | Insert `6mW.A00(activity, 14)` = `setRequestedOrientation(USER)` at method start | ✅ applied |

**Path:** `VBP.A02` (RE7) → `RE7.A0B` (X/9eY) → `9eY.A04` (FragmentActivity) →
`6mW.A00(activity, orientation)`. The `6mW.A00` helper catches the
`IllegalStateException("Only fullscreen activities can request orientation")`.

**Effect:** swiping into fullscreen rotates to landscape; exiting restores USER
orientation. Side UFI buttons already hidden by existing `VBP.FSS` (alpha=0).
Seekbar (force-show existing `VideoScrubberSeekBar` via MobileConfig flip) is
a future enhancement for this iteration.

## Smali class name mapping (jadx → original)
| jadx name | Original smali | smali_classes dir |
|-----------|---------------|-------------------|
| C2ZS | X/2ZS | smali_classes17 |
| C26630bQ | X/0bQ | smali_classes13 |
| C54511fI | X/1fI | smali_classes13 |
| C109193lI | X/3lI | smali_classes13 |
| C6BM | X/6BM | smali_classes15 |
| AbstractC186396mW | X/6mW | smali_classes13 |
| AbstractC54451fC | X/1fC | smali_classes13 |
| AbstractC210917ky | X/7ky | smali_classes2 |
| AbstractC27310cW | X/0cW | smali_classes13 |
| VBP | X/VBP | smali_classes8 |
| EPN | X/EPN | smali_classes18 |
| C257899eY | X/9eY | smali_classes16 |
| BottomSheetFragment | com.instagram.igds... | smali_classes17 |

## Android 10 compatibility
- `setRequestedOrientation` — all APIs ✅
- `6mW.A00` catches Android 8+ `IllegalStateException` ✅
- Legacy `setSystemUiVisibility` (used by IG) — works on API 29 ✅
- `const/high16 vN, 0x0` for 0.0f dimming — all APIs ✅
- Resource color `#00000000` — all APIs ✅
- Manifest `configChanges` includes `orientation|screenSize` → no activity recreate ✅

## What's NOT in this iteration (future)
1. **Feature D seekbar** — force-show existing `VideoScrubberSeekBar` via
   MobileConfig flag flip (needs the flag value + Litho section patching).
2. **Feature C true frosted blur** — insert `FrostedOverlayView` for real
   RenderEffect blur (API 31+) with CPU fallback (API 29-30).
3. **Force-fill scaling** — `setForceFillTextureScaling(true)` on clips viewer
   to zoom-crop wider videos to fill height.
4. **Reels-only gating** — currently A3 (top inset zeroing) affects all screens.
   If it breaks other screens, add a Reels-on-top check.
5. **C2 color register** — the `setColorFilter` patch uses `const` which may
   need register widening if the original used a different opcode.

## How to build
1. Go to GitHub Actions → "InstaTrueReel Build" → Run workflow.
2. Wait ~10-15 min for decode + patch + build + sign.
3. Download the `InstaTrueReel-patched-apk` artifact.
4. Uninstall current Instagram (signature changed).
5. Install the patched APK.
6. Open Reels → test each feature.
