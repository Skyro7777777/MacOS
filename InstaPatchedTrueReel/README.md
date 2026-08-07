# InstaPatchedTrueReel

Patches the ReVanced Instagram APK (`Instagram-v435.0.0.37.76-patches-v3.8.0.apk`) so Reels
play at **true full-screen 9:16 — stretch, no crop, video behind the bars — like TikTok.**

This folder + the workflow in `.github/workflows/insta-patched-true-reel.yml` build the patched
APK in GitHub Actions and upload it as an artifact. Download it from the **Actions** tab →
latest run → **Instagram-true916-patched** artifact.

## What the patch does

Instagram's reels viewer (`instagram/features/clips/viewer/*`, a.k.a. "Clips") wraps each reel's
video in a media3 `AspectRatioFrameLayout` and clamps it to **9:16** with `setAspectRatio(0.5625)`.
On a phone taller than 9:16 (most modern phones are ~9:19.5), the clamped frame is centered,
leaving empty bars top & bottom — and the video never reaches the physical screen edges.

The fix has three parts, all applied directly to the decompiled smali:

| # | Patch | Smali change | Effect |
|---|-------|--------------|--------|
| 1 | **Defeat the aspect clamp** | `setAspectRatio(F)V` → no-op (`.locals 0` / `return-void`) on every class that declares it | The reels frame can now grow to fill its parent (MATCH_PARENT) instead of being locked to 9:16 |
| 2 | **Force stretch (no crop)** | `setResizeMode(I)V` → inject `const/4 p1, 3` after `.locals` | `RESIZE_MODE_FILL` (3) stretches the video to fill the frame. **No cropping** — the video is vertically stretched to fill the screen, exactly as requested. (The previous build wrongly used `4` = ZOOM = crop; this is corrected to `3` = FILL = stretch.) |
| 3 | **Immersive edge-to-edge** | In the media3 `AspectRatioFrameLayout.setAspectRatio` no-op, also call `setSystemUiVisibility(0x16ff)` | Hides the status bar + nav bar and lays out edge-to-edge, so the video reaches the physical top & bottom of the display |

Because IG's reels page root is already a **FrameLayout** (the bars are overlaid siblings, not
in a vertical layout reserving space), defeating the aspect clamp + stretching makes the video
fill the **entire screen behind the bars** — the bars (bottom nav, comment bar, right action
column, top header) become transparent/overlaid on top of the full-screen video, exactly like
TikTok. No layout restructure is needed.

## Fullscreen button for horizontal videos (TikTok-style)

TikTok shows a "fullscreen" button on horizontal (16:9) videos. This patch adds the same:

- `TrueReelsHelper.java` is compiled to a separate `classesN.dex` and merged into the APK.
- `PlayerView.onAttachedToWindow` is patched to call `TrueReelsHelper.onPlayerAttached(view)`.
- The helper polls the player's `getVideoSize()`; if `width > height` (horizontal), it shows a
  fullscreen toggle button (top-right).
- Tapping the button toggles the reels frame between `RESIZE_MODE_FILL` (stretch, default) and
  `RESIZE_MODE_ZOOM` (crop-to-fill) — so you can switch between "show whole video, stretched"
  and "crop to fill" for horizontal content.

> Note: TikTok's native fullscreen mode launches a landscape player + rotate prompt. That
> requires a new Activity and is out of reach of static smali patching. This patch implements
> the portrait-screen fullscreen toggle (crop-fill on/off) instead.

## Files

- `patch.py` — main patcher script (apktool decompile → ripgrep → smali patches → recompile →
  merge helper.dex → sign).
- `TrueReelsHelper.java` — runtime helper for the fullscreen button (compiled to dex, merged).
- `../.github/workflows/insta-patched-true-reel.yml` — GitHub Actions workflow.

## How to build

The workflow runs automatically on push to this folder, or manually via the Actions tab
(**InstaPatchedTrueReel** → **Run workflow**). The patched, signed APK is uploaded as the
`Instagram-true916-patched` artifact (30-day retention).

To run locally:
```bash
java -jar apktool.jar ...   # see patch.py args
python3 patch.py --apk Instagram-v435.0.0.37.76-patches-v3.8.0.apk --out out \
                 --helper-dex helper.dex --apktool apktool.jar --signer uber-apk-signer.jar
```

## Install

1. The patched APK is re-signed with a debug key, so **uninstall the stock Instagram first**
   (signatures differ; Android won't allow install-over).
2. Allow "Install unknown apps" for your browser/Files app.
3. Install the APK. Log in (try a secondary account first — modded clients can trip Meta's checks).
4. Open Reels — the video now fills edge-to-edge behind the bars.

## Honesty / limitations

- The patching pipeline is fully verified (apktool + smali + sign produces a valid installable APK).
- The on-device visual result (video behind bars, stretch, fullscreen button) is technically sound
  per the reverse-engineering of IG's reels viewer, but must be confirmed on a real phone.
- `ClipsViewerFragment` is renamed/obfuscated in this IG build, so the immersive injection targets
  the media3 `AspectRatioFrameLayout` (which is reliably named) instead. The fullscreen-button
  helper hooks `PlayerView.onAttachedToWindow` (also reliably named).
