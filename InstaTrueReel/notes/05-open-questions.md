# 05 — Open Questions

Things to resolve before/while coding. Some need the user; some need source.

## Q1 — Does Instagram v435's existing "expand" button already do TikTok-style fullscreen?
Screenshot F (`Screenshot_20260808-145028__01.jpg`) shows an expand icon
(upper-right) on a letterboxed horizontal Reel. We need to know:
- Does tapping it **rotate to landscape** and hide the side buttons + show a
  seekbar (TikTok-like)? Or does it just zoom/crop within the vertical frame?
- **Action:** explore the source (Feature D target) AND/OR the user tests the
  button on-device and reports behavior.
- If it already does the right thing → Feature D is "done," we just confirm.
- If it does a lesser thing → we enhance its handler (force landscape
  orientation, hide side-action column, add/show a seekbar).
- If the user wasn't aware of it → clarify whether they still want changes.

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
