# InstaPatchedTrueReel

Patches the ReVanced Instagram APK (`Instagram-v435.0.0.37.76-patches-v3.8.0.apk`) so Reels
play at **true full-screen 9:16 — stretch, no crop, video behind the bars — like TikTok.**

This folder + the workflow in `.github/workflows/insta-patched-true-reel.yml` build the patched
APK in GitHub Actions and upload it as an artifact. Download it from the **Actions** tab →
latest run → **Instagram-true916-patched** artifact.

## Root cause (found by reading jadx-decompiled Java source)

The previous patch versions (runs #1–#4) targeted the WRONG classes. The actual mechanism:

- IG's reels video surface is `Lcom/instagram/ui/simplevideolayout/SimpleVideoLayout;`
  (id `clips_video_layout` / `clips_video_container`), which extends `LX/7ky;`
  (jadx name: `AbstractC210917ky`, internally called "VideoFrameLayout").
- `LX/7ky;` extends `FrameLayout` and contains a `TextureView A02` field — the actual
  video surface.
- `LX/7ky;->onSizeChanged(IIII)V` overrides the default to compute the TextureView's
  width/height via `LX/25U;->A00(...)` based on the VIDEO ASPECT RATIO, then sets
  `FrameLayout.LayoutParams(w, h)` + translation X/Y on the TextureView.
- For a 9:16 video (aspect 0.5625) on a 9:19.5 screen (aspect 0.4615), the "fit" mode
  returns width=1080, height=1920 — centered on a 1080×2400 screen, leaving 240px gaps
  top + bottom. **THIS is the visible gap above & below the reel.**

Previous patches (media3 PlayerView, IgProgressImageView.onMeasure) had no effect because:
- `IgProgressImageView` is just the poster image (extends FrameLayout containing an
  IgImageView + ProgressBar), NOT the video surface.
- media3 `PlayerView` / `AspectRatioFrameLayout` are not used by the swipeable reels feed.

## The fix (v2)

| # | Patch | Smali change | Effect |
|---|-------|--------------|--------|
| 1 | **Stretch TextureView to fill** (KEY) | `LX/7ky;->onSizeChanged(IIII)V` rewritten to set `A02` (TextureView) layout params to `FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT)` with translation X/Y = 0 | Bypasses the aspect-ratio math; video stretches to fill the SimpleVideoLayout (which already fills C3EO → ReelViewGroup → screen) edge-to-edge. **Stretch, no crop, no letterbox.** |
| 2 | **Immersive on real video surface** (KEY) | `LX/7ky;->onAttachedToWindow()V` injects `setSystemUiVisibility(0x16ff)` | Hides status + nav bars when the actual reels video surface attaches (not media3 PlayerView, which reels doesn't use). |
| 3 | setAspectRatio no-op (legacy, harmless) | `setAspectRatio(F)V` → no-op on media3 AspectRatioFrameLayout | Neutralises the aspect clamp on media3 surfaces (reels doesn't use these, but other IG surfaces might). |
| 4 | setResizeMode FILL (legacy, harmless) | `setResizeMode(I)V` → `const/4 p1, 3` | Forces RESIZE_MODE_FILL (stretch) on media3 surfaces. |
| 5 | IgProgressImageView.onMeasure super (legacy, harmless) | `onMeasure(II)V` → `super.onMeasure(p1, p2)` | Makes the poster image fill its parent (doesn't affect video, but consistent). |
| 6 | PlayerView helper hook (for fullscreen button) | `media3/ui/PlayerView.onAttachedToWindow` → `TrueReelsHelper.onPlayerAttached(view)` | Hooks the fullscreen-button helper (PlayerView isn't used by reels feed, but may exist in other IG surfaces). |

## Fullscreen button for horizontal videos (TikTok-style)

`TrueReelsHelper.java` is compiled to a separate `classesN.dex` and merged into the APK.
It hooks `PlayerView.onAttachedToWindow`, polls the player's `getVideoSize()`, and when it
detects a horizontal video (width > height), shows a fullscreen toggle button (top-right).
Tapping it toggles the reels frame between `RESIZE_MODE_FILL` (stretch) and `RESIZE_MODE_ZOOM`
(crop-to-fill).

> Note: PlayerView isn't used by the swipeable reels feed, so this button may not appear on
> reels — it's primarily for other IG video surfaces. The core stretch fix (patch #1) applies
> to all videos regardless.

## Files

- `patch.py` — main patcher script (apktool decompile → smali patches → recompile →
  merge helper.dex → sign).
- `TrueReelsHelper.java` — runtime helper for the fullscreen button (compiled to dex, merged).
- `../.github/workflows/insta-patched-true-reel.yml` — GitHub Actions workflow.

## How to build

The workflow runs automatically on push to this folder, or manually via the Actions tab
(**InstaPatchedTrueReel** → **Run workflow**). The patched, signed APK is uploaded as the
`Instagram-true916-patched` artifact (30-day retention).

## Install

1. The patched APK is re-signed with a debug key, so **uninstall the stock Instagram first**
   (signatures differ; Android won't allow install-over).
2. Allow "Install unknown apps" for your browser/Files app.
3. Install the APK. Log in (try a secondary account first — modded clients can trip Meta's checks).
4. Open Reels — the video now fills edge-to-edge behind the bars.

## Honesty / limitations

- The patching pipeline is fully verified (apktool + smali + sign produces a valid installable APK).
- The on-device visual result depends on whether `LX/7ky;` is truly the only class controlling
  the reels video surface size. If the video still doesn't fill the screen, there may be
  additional clamping in `C3EO` (the wrapper around SimpleVideoLayout) or in the Litho
  component tree that hosts C3EO. The next debugging step would be to also patch
  `LX/3EO;` (C3EO) onMeasure/onSizeChanged, or trace the Litho layout.
