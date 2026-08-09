# THINK_LOG — running scratchpad (append-only)

A place for mid-flight reasoning. Newest at the bottom. Each entry: date +
step + thought. Plans WILL change; that's fine.

---

## 2026-08-09 — Step 1: understand + explore + brief search

### What I learned from the repo
- Repo "MacOS" is really "The_Apple_Project" (macOS remote control via
  RustDesk/Tailscale) — the Instagram work is being added on the side.
- `Instagram-v435.0.0.37.76-patches-v3.8.0.apk` is a Git-LFS file (~251 MB):
  an Instagram APK **already patched once** with ReVanced patches v3.8.0.
- `.github/workflows/jadx-decompile.yml` decompiles it with jadx 1.5.6,
  best quality, **--no-res** (Java only, no resources). Artifact
  `instagram-decompiled-java` = ~150k Java files.

### VLM analysis of the 4 key screenshots — confirmed the user's description
- TikTok (target): video edge-to-edge behind status bar AND bottom nav AND
  comment overlay; icons are floating white lines; comment bar = translucent
  frosted glass. No black strips.
- Instagram (current): video sandwiched between top black strip (status bar)
  and bottom black strip (nav bar); comment overlay = opaque black sheet that
  BLOCKS the video. Exactly as user described.

### Surprise: Instagram v435 already has an expand/fullscreen button
- Screenshot F (`Screenshot_20260808-145028__01.jpg`) shows a landscape car
  video letterboxed in a vertical Reel, with an "expand" icon (rectangle +
  corner brackets + arrow) in the UPPER-RIGHT, next to a blue progress bar.
- Implication: Feature D may be "enhance existing" not "build new." Must
  verify what the button currently does. → open question Q1. This is exactly
  the kind of mid-flight plan change the user warned about.

### Web research takeaways
- Android 15 forces edge-to-edge for API-35 targets; Instagram likely opts out
  via fitsSystemWindows/padding + black windowBackground. Fix = undo that for
  Reels scope (setDecorFitsSystemWindows(false), transparent statusBarColor,
  fitsSystemWindows(false) on root).
- ReVanced has many Instagram patches but NONE for edge-to-edge Reels — this
  is genuinely novel. ReVanced patches edit Smali (not jadx Java).
- TikTok horizontal fullscreen launched Dec 2022: tap → landscape + hide side
  buttons + seekbar (YouTube-like). Official TikTok Creator Academy guide
  exists.

### Toolchain decision (tentative)
- Use **apktool** (not jadx) for patching — gives Smali + res (layouts/themes/
  drawables). jadx output is read-only. Current jadx run has no res, so we
  need apktool decode anyway for Features B/C/D (they touch backgrounds/
  layouts).
- Build = apktool b → zipalign → sign (debug key) in a GitHub Actions workflow.
- Patches stored as overlay files in `InstaTrueReel/patches/<feature>/`
  mirroring apktool's decoded tree, applied by a small `apply.sh`.

### Why I'm NOT coding yet
- 150k files; I haven't read a single one yet. Any patch written now would be
  a guess. The user explicitly said don't code yet + don't finalize a plan.
- Right move: ship the thinking docs (this commit), then in the NEXT prompt
  either (a) build the exploration workflow + grep the source for the Reels/
  nav/comment/inset classes, or (b) the user steers.

### Next-step options to offer the user
1. **Explore source** — create `workflows/explore-source.yml` that re-runs jadx
   (with res this time, or apktool decode) and runs the grep battery from
   `04-source-exploration-roadmap.md`; commit findings. This is the highest-
   value next step — it turns hypotheses into file:line facts.
2. **On-device test Q1** — user taps the existing expand button (screenshot F)
   on their phone and reports: does it rotate to landscape + hide side buttons
   + show seekbar? Resolves Feature D scope cheaply without any code.
3. **Clarify Q2–Q10** — user answers the open questions (stretch vs crop,
   scope, nav recreate vs tint, sign key, Android version, etc.).

Recommendation: do (1) and (2) in parallel. (1) is automated; (2) needs the
user's phone. (3) can trickle in.

### Open uncertainties to revisit
- Exact Reels Activity/Fragment class name (ClipsFragment? ReelsFragment?
  ReelViewerFragment?) — unknown until grep.
- Whether the bottom nav is a stock BottomNavigationView or a custom IG view.
- Whether the comment sheet is a BottomSheetDialogFragment or custom.
- Whether Instagram's expand button already does TikTok-style fullscreen.
- Android version of the user's test device (affects inset API path).
