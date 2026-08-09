# 01 — Task Understanding

## What the user actually wants (in plain words)

Instagram does **not** let Reels play at their full potential. Even a native 9:16
vertical Reel is not shown at true 9:16 — it is squished between black bars so it
doesn't reach the phone's status bar (top) or the app's bottom navigation bar.
The user wants Reels to play **edge-to-edge, like TikTok**, with the bar icons
"floating" as thin white lines over the video instead of sitting on solid black.

Three concrete UI problems to fix, plus one feature to add:

### Problem A — Status bar (top)
- **Now:** solid black strip at the very top holds the time/wifi/battery icons;
  the video starts *below* this strip.
- **Want:** video reaches the top edge; status-bar icons drawn as floating white
  lines over the video (Android "edge-to-edge" / transparent status bar /
  immersive mode).

### Problem B — Main bottom navigation bar (Home / Reels / Create / Search / Profile)
- **Now:** a solid black bar at the bottom; video ends *above* it.
- **Want:** video reaches the bottom; nav icons float as white-line outlines over
  the video (like TikTok's Home/Friends/Inbox/Profile row).

### Problem C — Comment overlay (when comments are open)
- **Now:** an **opaque black sheet** rises from the bottom, sitting in front of
  the video and *blocking* it; the "Add comment..." box and the area beneath it
  are on solid black.
- **Want:** a **translucent frosted-glass** overlay (glassmorphism) where the
  video is still visible behind the comments and the input box — like TikTok.

### Feature D — Horizontal (16:9) video fullscreen (TikTok-style)
- On TikTok, when a reel is landscape (~16:9), a "Full Screen" button appears
  (middle-bottom). Tapping it rotates the phone to landscape, hides the
  like/comment/share side buttons, and shows a seekbar — basically YouTube-style
  fullscreen.
- ⚠️ **Twist:** Instagram v435 already shows an "expand" icon (upper-right) on
  horizontal videos (see screenshot F / `Screenshot_20260808-145028__01.jpg`).
  We need to verify what that button currently does, and decide whether to
  (a) enhance it to match TikTok (rotate + hide side buttons + seekbar), or
  (b) the user simply hadn't noticed it. → see `05-open-questions.md`.

## What "edge-to-edge / immersive" means technically
- Android lets an app draw behind the system status bar and navigation bar.
- Modern way: `WindowCompat.setDecorFitsSystemWindows(window, false)` /
  `enableEdgeToEdge()` (AndroidX) + `WindowInsetsControllerCompat` for immersive
  (hide-on-swipe) behavior.
- Old way: `FLAG_LAYOUT_NO_LIMITS`, `FLAG_TRANSLUCENT_STATUS/NAVIGATION`,
  `SYSTEM_UI_FLAG_*`.
- Instagram currently does the *opposite*: it sets `fitsSystemWindows=true`
  (or pads its root view by the system insets) and paints the padded areas
  black. The patch must undo that for the Reels surface specifically.

## Constraints from the user
- The APK is **already patched once** (ReVanced v3.8.0) and **already
  decompiled** by jadx (artifact `instagram-decompiled-java`).
- Do decompilation/compilation **in GitHub Actions** (sandbox too limited).
- Use the provided GitHub fine-grained token for repo operations.
- This is **hard** — 150k+ Java files; expect heavy exploration; plans will
  change mid-flight; keep living notes.
- **For this prompt: understand + explore + brief web search + write thinking
  docs. Do NOT code patches yet, do NOT make a final plan.**

## What "recreation of bottom bars" likely means
The user said the main bar's icons (Home/Reels/DM/Profile) need to "FLOAT" and
this "will require recreation and heavy coding." Interpretation: Instagram's
existing bottom nav is probably an opaque `BottomNavigationView` / custom view
with a black background. To make it float transparently over a video that now
extends under it, we likely need to either:
- make that view's background transparent/null and recolor its icons white, or
- if it can't be made transparent cleanly, overlay a *new* minimal floating
  icon strip and hide the original.
Same idea for the comment bar's input box + the black panel beneath it.
We won't know which until we read the source. → `04-source-exploration-roadmap.md`.
