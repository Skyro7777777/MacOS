# 05 — Open Questions

Things to resolve before/while coding. Some need the user; some need source.

## Q1 — RESOLVED (by source exploration, agent 3-e)
The user clarified: Instagram already has a "fullscreen" feature that **only
hides the side like/comment/share buttons and does nothing else** — no rotation,
no seekbar. Source confirms exactly this:
- The existing "fullscreen" is **NOT** a separate Fragment/Activity. It is a
  **fade-out of the side UFI buttons** via alpha=0.0f, triggered by a swipe
  gesture. Handler: `VBP.FSS(i,i2)` enters (`p002X/VBP.java:116-170`),
  `VBP.EvT()` exits (`:47-88`). Fade animator = `EPN`.
- State flags on `ClipsItemState` (`C11R.java:78-80`): `isFullscreenViewActive`,
  `isFillToScreenActive`, `isFullscreenViewNuxActive` (immutable Builder fields).
- There is a "Fullscreen" entry in the long-press/three-dot popup
  (`VSL.java:26-44` → `MediaOption$Option.FULLSCREEN_VIEW`, label
  `R.string 2131984733`). The "expand icon" seen on landscape reels in the old
  screenshot is almost certainly this popup-menu entry (no always-visible inline
  expand-button exists in code).
- **Confirmed:** NO `setRequestedOrientation` anywhere in clips → no rotation.
  `SimpleVideoLayout` exposes no getDuration/getCurrentPosition/seekTo → no seekbar.
- **Verdict for Feature D:** enhance `VBP.FSS`/`VBP.EvT` — ADD
  `setRequestedOrientation(LANDSCAPE/PORTRAIT)` + ADD a seekbar overlay. The
  side-button hide is already free (reuse the toggle).
- ⚠️ NOTE: the screenshot `Screenshot_20260808-145028__01.jpg` (and its
  "expand button") was from a **previous failed conversation** and the button
  there did nothing on click — per the user. Disregard it as a reference.
  See `findings/00-overview.md` Feature D section for the real hook points.
- **Still-open sub-item:** the player instance exposing
  getCurrentPosition/getDuration/seekTo is NOT yet located
  (`SimpleVideoLayout`/`AbstractC210917ky` expose none). Needs follow-up
  exploration (read `C257899eY`, `C3BT`; grep `p002X/` for the player interface).

## Q2 — Stretch vs crop?
The user said: "I haven't much idea that on instagram whether insta crops upper
and lowermost reel's part or it stretches, but I want you to stretch 9:16 reels
vertically both upto status and main/comment bar."
- Confirm: the desired behavior is **stretch to fill** (video reaches status bar
  top and bottom bar bottom), NOT crop. For a true 9:16 source this is lossless
  fill; for the black bars, the patch removes the bars so the video's container
  grows. Need to confirm we are not expected to *vertically stretch a sub-9:16
  video* (which would distort). Likely: container becomes full-screen; video
  uses `RESIZE_MODE_ZOOM`/`FILL` only if needed. → confirm with user.

## Q3 — Keep status bar visible (floating) or fully hide it (immersive)?
TikTok keeps the status bar visible but transparent (floating icons). The user's
description matches "floating white lines," i.e. **transparent status bar, not
hidden**. Confirm we keep it visible (not `IMMERSIVE_STICKY` hide-on-swipe).
- Probably: transparent status bar + transparent nav bar, both always visible
  as floating icons. Match TikTok exactly.

## Q4 — Scope: Reels only, or also Feed/Story/Explore?
The screenshots are all **Reels**. The black-bar issue may also affect the main
feed and Stories. Confirm scope = **Reels viewer only** for now (lowest risk).
Expanding to feed/story later is possible.

## Q5 — Main bottom nav: make-transparent vs replace?
User hinted "recreation and heavy coding" may be needed for the floating nav.
Two approaches (decide after reading source):
- **(a) Minimal:** set the existing nav view's background to transparent/null,
  tint icons white. Lowest risk if the view supports it.
- **(b) Recreate:** hide original nav, overlay a new minimal floating icon strip.
  Higher risk, more code, but guaranteed TikTok look.
Defer decision until we see the nav view class & layout.

## Q6 — Comment overlay: glassmorphism on Instagram's existing sheet, or replace?
Same minimal-vs-recreate dilemma as Q5 but for the comment BottomSheet. TikTok
uses a frosted translucent sheet; Instagram uses opaque black. Likely fix =
change the sheet's background to a translucent blur drawable. Need to find the
sheet class + its background style. Also: the "black thing beneath the input
box" (screenshot 4) is part of the same sheet — must become translucent too.

## Q7 — Build/sign approach: direct Smali (apktool) vs ReVanced Patcher?
- Direct Smali via apktool = simpler to iterate, full control, no ReVanced
  toolchain. Good for a one-off custom patch.
- ReVanced Patcher = more reproducible, integrates with existing v3.8.0 patches,
  but adds toolchain complexity.
Recommendation pending: probably **apktool direct Smali** for speed, since we're
not publishing reusable patches. Confirm with user.

## Q8 — Signing key
Patched APK must be signed to install. Use a debug key (auto-generated, signs
out the original signature → user must uninstall official Instagram first) or a
user-provided keystore? The existing "patches-v3.8.0" APK is already
re-signed — confirm we can re-sign again on top. Likely: debug/CI key is fine.

## Q9 — Target Android version / device
Patches may behave differently across Android versions (esp. Android 15
edge-to-edge enforcement). What Android version + device does the user test on?
Affects which inset API path matters.

## Q10 — Resources: re-decode with apktool (not just jadx)?
Current jadx run used `--no-res` (Java only). To patch layouts/themes/drawables
we **must** have `res/`. Plan: apktool decode gives proper Smali + res. Confirm
we add an apktool step to the build pipeline (it's required, not optional, for
features B/C which touch backgrounds).
