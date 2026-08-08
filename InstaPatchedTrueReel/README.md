# InstaPatchedTrueReel (clean rewrite)

Patches the ReVanced Instagram APK (`Instagram-v435.0.0.37.76-patches-v3.8.0.apk`) so Reels
play **TikTok-style**: edge-to-edge video behind transparent overlay bars + a working
fullscreen button for 16:9 videos.

This is a **complete clean rewrite** — the previous versions (v2–v8) accumulated harmful
smali patches that crashed the comment bar and hid status-bar icons. This version does the
**minimum in smali** (2 verified patches) and pushes **all bar-transparency + fullscreen
logic into the runtime helper**, which can walk the live view tree and handle Litho
re-mounts dynamically.

## What was wrong before (and why this rewrite)

| Old problem | Root cause | Fix in this rewrite |
|---|---|---|
| Comment bar "Add comment…" vanished | v8 nulled resource `0x7f08042f` → `LX/4rT;->A0N(ctx, 0)` throws → XIU Litho component replaced with error placeholder | **Removed** all bar-resource nulling. Helper detects `GradientDrawable` and calls `setColor(TRANSPARENT)` to kill the black fill **while preserving the white stroke** |
| Status bar "only wifi info hidden" | v8 injected `setSystemUiVisibility(0x16ff)` which includes `FULLSCREEN`/`HIDE_NAVIGATION`/`IMMERSIVE` flags | **Removed** all immersive-flag injection. Helper uses layout-only flags `0x700` (bars stay VISIBLE + TRANSPARENT, video renders behind) |
| Status bar black strip | `InstagramMainActivity.onResume` sets status bar color to BLACK, overriding the helper's transparent | Helper **re-applies** `setStatusBarColor(TRANSPARENT)` on every layout pass + every 200ms rescan → defeats the onResume override within ~200ms |
| Main bottom nav bar ~80% black | Tab bar is a plain `FrameLayout` (id `0x7f0b3f67`) with `setBackgroundColor(~80% black)`. Old helper missed it (not a known class name + alpha threshold 150 skipped the ~51-alpha color) | Helper adds **explicit ID-based lookup** for `tab_bar`/`ls_nav_bar` + lowers alpha threshold from 150 → 1 |
| Fullscreen button "does nothing" | `setRequestedOrientation(LANDSCAPE)` was ignored (activity portrait-locked in manifest) / broke the layout | **No activity rotation.** Helper transforms the `TextureView` in-place: `setRotation(90)` + `setScaleX/Y` fills the portrait screen with landscape video. ViewPager2 swipe locked. Overlay with exit + prev/next tap zones added to decorView |

## The 2 smali patches (both evidence-backed from jadx source)

### Patch A — `LX/7ky;->onSizeChanged(IIII)V` → TextureView MATCH_PARENT  [KEY]

**Root cause** (confirmed in `AbstractC210917ky.java` line 146, jadx class =
`AbstractC210917ky`, smali `X/7ky`):
- IG's reels video surface is `SimpleVideoLayout` (extends `LX/7ky`).
- `LX/7ky` has field `A02: TextureView` (the actual video surface) and field
  `A04: C160765mH` (mediaInfo with aspect-ratio field `A03: Double`).
- `onSizeChanged` computes the TextureView size via `C25U.A00` based on the video
  aspect ratio → letterboxed view (e.g. 1080×1920 centered on 1080×2400 screen →
  240px gaps top + bottom).
- This patch rewrites `onSizeChanged` to set `A02` layout params to
  `FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT)` with translation X/Y = 0,
  bypassing the aspect math → video stretches edge-to-edge.

### Patch B — `LX/7ky;->onAttachedToWindow()V` → helper hook  [KEY]

Injects `invoke-static TrueReelsHelper->onPlayerAttached(Landroid/view/View;)V` at
the start of `onAttachedToWindow`. The helper checks `findReelsRoot()` and returns
early if not in the reels context (safe for feed/stories/ads).

## What the runtime helper does (`TrueReelsHelper.java`)

Compiled to a separate `classesN.dex` and merged into the APK. On every video
surface attach (in reels context):

1. **Window transparency** — `setStatusBarColor(TRANSPARENT)` +
   `setNavigationBarColor(TRANSPARENT)` + `setSystemUiVisibility(0x700)` +
   `setDecorFitsSystemWindows(false)`. **Re-applied on every layout pass + every
   200ms** to defeat IG's `onResume` override.
2. **Video chain fill** — walks up from the TextureView to the reels root, sets
   every ancestor to `MATCH_PARENT` + `setFitsSystemWindows(false)` +
   `setClipChildren(false)` so the video extends behind the system bars.
3. **Bar transparency** — walks the entire decorView tree:
   - Explicit ID lookup for `tab_bar` (0x7f0b3f67), `ls_nav_bar` (0x7f0b248e) + shadows.
   - Class-name matching for known bar classes (`ClipsViewerNavigationBar`, etc.).
   - Position+opacity heuristic for unknown bars (top/bottom of screen + alpha ≥ 1).
   - **GradientDrawable** backgrounds: `setColor(TRANSPARENT)` kills the fill,
     **keeps the stroke** (the white outline of the comment box).
   - Other backgrounds: `mutate().setAlpha(0)` + `setBackgroundColor(TRANSPARENT)`.
4. **Fullscreen button** — added to the Activity's `decorView` (above all IG touch
   interceptors). Polls `getVideoSize()` (reflects on `A04` mediaInfo → `A03`
   aspect Double). Shows only for landscape videos (aspect > 1.15).
5. **Fullscreen transform** (on button tap):
   - `sIsLandscape = true`, lock ViewPager2 (`setUserInputEnabled(false)` via reflection).
   - `TextureView.setRotation(90)` + `setScaleX(screenH/screenW)` +
     `setScaleY(screenW/screenH)` → video fills the portrait screen in landscape
     orientation (math verified: the rotated+scaled quad fills exactly).
   - Hide IG overlay bars (INVISIBLE) so the fullscreen is clean.
   - Add overlay to decorView: exit button (top-right) + left 40% tap zone (prev
     reel) + right 40% tap zone (next reel) → scrollable landscape feed.
   - On swipe-advance (`onPlayerAttached` fires for new video): re-apply transform
     to new TextureView; auto-exit if new video isn't 16:9.

## Files

- `patch.py` — patcher (apktool decompile → 2 smali patches → recompile → merge
  helper.dex → sign).
- `TrueReelsHelper.java` — runtime helper (window transparency, bar transparency,
  fullscreen button + transform). Compiled to dex, merged.
- `../.github/workflows/insta-patched-true-reel.yml` — GitHub Actions workflow.

## How to build

The workflow runs automatically on push to this folder, or manually via the
Actions tab (**InstaPatchedTrueReel** → **Run workflow**). The patched, signed APK
is uploaded as the `Instagram-true916-patched` artifact (30-day retention).

## Install

1. The patched APK is re-signed with a debug key, so **uninstall the stock
   Instagram first** (signatures differ; Android won't allow install-over).
2. Allow "Install unknown apps" for your browser/Files app.
3. Install the APK. Log in (try a secondary account first — modded clients can
   trip Meta's checks).
4. Open Reels — the video now fills edge-to-edge behind the (transparent) bars.
   For 16:9 videos, a fullscreen button appears top-right; tap it for landscape
   fullscreen with prev/next tap zones.

## Honesty / limitations

- The 2 smali patches are fully verified against the jadx-decompiled source
  (`AbstractC210917ky.java` confirms `A02: TextureView`, `onSizeChanged`,
  `onAttachedToWindow`).
- The fullscreen transform uses `TextureView.setRotation(90)` + scale. This is
  verified math (the quad fills the screen exactly) but the video will have a
  mild horizontal stretch on phones wider than 16:9 (e.g. 20:9 screens show a
  16:9 video stretched ~1.25× horizontally) — similar to TikTok's "fill" mode.
- The bar transparency relies on runtime view-tree walking + rescan. If IG adds
  new bar classes in a future version, they may not be caught until
  `BAR_CLASS_NAMES` is updated — but the position+opacity heuristic catches most.
- d8 compiler limitation: only single-level anonymous inner classes are used
  (no anonymous class nested inside another anonymous class).
