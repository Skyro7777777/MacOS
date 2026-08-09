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

---

## 2026-08-09 — Step 2: ACTUAL source exploration (corrected course)

### Course correction (from user feedback)
User said I went far off: focused on building a patcher instead of understanding
the decompiled Instagram + the features. Also never downloaded the artifact
(the MAIN thing). Also wrongly leaned on `Screenshot_20260808-145028__01.jpg`
(from a previous failed conversation; its button did nothing). Corrected:
downloaded the 156 MB artifact, unzipped to 175,407 Java files (1.3 GB) at
`/home/z/insta-src/jadx-out/sources/`, dispatched 5 parallel Explore agents.

### What the 5 agents found (file:line evidence, not brainstorm)
See `findings/00-overview.md` for the full master index. Highlights:

**Root causes of the black strips (all confirmed in code):**
- Top: `InstagramMainActivity.java:3256` sets statusBarColor=BLACK;
  `p002X/C2ZS.java:102` re-sets it black (undoing the transparent call at :99);
  `:86`/`:131` paint decorView/content black.
- Bottom: `InstagramMainActivity.java:3261` sets navBarColor=BLACK;
  `p002X/C26630bQ.A04:124,127,132,137` paints tab_bar black.
- THE GAP below the video: `InstagramMainActivity.java:1421` sets
  `swipeable_tab_view_pager.bottomMargin = tabBarHeight`. This margin IS the
  black strip. Setting it to 0 removes the gap.
- Why video doesn't go under status bar: `IgFragmentActivity.java:735`
  registers `C6BM` which applies system insets as padding (`C6BM.java:34-49`).
  ClipsViewerFragment itself makes ZERO window/inset calls — inherits activity
  state. So fix must be at activity level (or gated on "Reels on top" via
  `IgFragmentActivity.A1g():685`).

**Feature B (bottom nav) — best news:** IG does NOT hide the bar on Reels
(`Gvc():7992` keeps VISIBLE; only colors change). So the floating-transparent
approach is a clean fit — just make bg transparent + icons white + zero the
bottomMargin. 3 concrete hooks found.

**Feature C (comment sheet) — best news:** IG already HAS a reusable blur view:
`com/instagram/p132ui/legibilityoverlay/FrostedOverlayView.java` —
`RenderEffect.createBlurEffect(15f,15f,CLAMP)` on API 31+ with a 27%-scale CPU
box-blur fallback. Drop-in for true frosted glass. Plus 3 opaque layers to
neutralize (sheet panel, clips_media_dimming_view, background_dimmer).

**Feature D (existing fullscreen) — confirmed user's description:**
- Existing "fullscreen" = fade-out of side UFI buttons (alpha=0, NOT GONE) via
  `VBP.FSS()`/`VBP.EvT()`, triggered by swipe gesture. Also a "Fullscreen"
  entry in the long-press popup (`VSL.java`).
- NO rotation (no setRequestedOrientation in clips). NO seekbar
  (SimpleVideoLayout has no getDuration/getCurrentPosition/seekTo).
- Hook points for TikTok-style: add setRequestedOrientation(LANDSCAPE) at
  `VBP.java:116` (enter), PORTRAIT at `:47` (exit); add a SeekBar overlay.
  Side-button hide is FREE (reuse the toggle).

### Remaining gaps (for next prompt)
1. Locate the player instance (getCurrentPosition/getDuration/seekTo) for the
   Feature D seekbar — read `C257899eY`, `C3BT`, grep `p002X/` for the player
   interface. SimpleVideoLayout exposes none.
2. Decompile tail of `I34.run()` case 33 — confirm popup menu path calls
   `VBP.FSS` (else hook it separately).
3. apktool decode for resources — layout XMLs, themes, drawables, strings are
   NOT in the jadx dump (--no-res). Required for any XML/drawable/color patch.
4. Runtime-verify the BottomSheetFragment.onViewCreated branch (prism drawable
   vs GradientDrawable) for Reels comments.
5. Confirm activity access from `VBP` (plain object, not Fragment).

### Status
- No code/patches written (still understanding, per user).
- 5 findings docs (3-a..3-e, ~3000 lines total) + 00-overview master index
  committed to repo.
- Next decision point for the user: (a) dispatch a focused agent for the
  remaining gaps (player instance + I34.run case 33 + apktool-res), or
  (b) start designing the actual Smali patches against the confirmed hooks,
  or (c) answer the still-open product questions (Q2 stretch-vs-crop, Q3
  status bar visible-vs-hidden, Q4 scope reels-only, Q7 build approach,
  Q9 Android version).

---

## 2026-08-09 — Step 3: closed all remaining gaps (4 more agents + apktool resources)

### What was done
Dispatched 4 more parallel Explore agents (4-a..4-d) over the decompiled source
AND did an apktool resource decode of the actual APK (downloaded via GitHub raw
URL since git-lfs wasn't installed; 240 MB APK → 574 MB resources in 14 sec).
All 5 original gaps + several bonus items are now closed.

### Agent 4-a (player instance + seekbar) — BIG win
- Located the full player chain: ClipsViewerFragment → C257899eY
  (ClipsVideoPlayerController) → C3HU interface → C89843a5W (ClipsVideoPlayer)
  → C50741Yd (VideoPlayerImpl) → C50301Wl (IgGrootPlayer) → C52701cN
  (FB Groot/ExoPlayer fork).
- Player API EXISTS: C50741Yd has BbK()=getCurrentPositionMs, A0P()=getDurationMs,
  A0V(float,int)=seekToNormalized, A0r()=isPlaying, A0h(boolean)=play/pause.
  C3HU has setScrubbingModeEnabled + GzY(float,int)=seekTo normalized.
- **IG ALREADY SHIPS a TikTok-style seekbar**: `VideoScrubberSeekBar`
  (com.instagram.p132ui.mediaactions.VideoScrubberSeekBar) with keyframe markers
  + thumbnail preview + chapter text. It's mounted via Litho component
  `C30423BTc` (LegacyClipsAttachedScrubberComponent), gated behind MobileConfig
  flag 36320867680860001L + a duration gate (ClipsProgressUiState).
- **Feature D seekbar verdict:** REUSE the existing scrubber — force-show it by
  flipping the MobileConfig flag / duration gate. NO custom SeekBar needed.
- Bonus: listener FV2(width,height,isPortrait) = video-size-changed event →
  use width>height as the landscape gate for Feature D rotation.

### Agent 4-b (popup menu path + VBP activity access)
- I34.run() case 33 does NOT call VBP.FSS — it calls C14U.FGC (stores fullscreen
  target + analytics). The newer IA5.F6G path lands at C15T:1211 (case LAGOS/114)
  which just logs. So the popup "Fullscreen" entry is currently a NO-OP visually
  (matches user's "did nothing on click"). VBP.FSS is invoked ONLY by gesture
  broadcasters (AnonymousClass940:548, C106638kpe:131).
- VBP gets Activity via: VBP.A02 (RE7) → re7.A0B (C257899eY) → c257899eY.A04
  (FragmentActivity = InstagramMainActivity). Clean.
- **Orientation helper to use:** AbstractC186396mW.A00(activity, int) — pure
  static, catches the "Only fullscreen activities can request orientation"
  IllegalStateException. NOT C99744f1m (3-e was mislabeled; that one mutates
  LinearLayouts for FB Horizon cloud gaming).
- Feature D rotation one-liners confirmed at VBP.java:116 (enter, LANDSCAPE=0)
  and VBP.java:47 (exit, USER=14). Plus optional second hook at C15T:1211 for
  the popup-menu path.

### Agent 4-c (force-fill + orientation + Reels detection)
- **setForceFillTextureScaling(true) = ZOOM-CROP (preserves aspect), NOT
  stretch-distort.** For a 9:16 video in a 1080×2400 container → TextureView
  becomes 1350×2400, crops 135px each side, fills full height. So force-fill
  makes the video reach top+bottom IF the container is edge-to-edge (Feature A).
  The two fixes are complementary. Currently clips viewer uses default 0.25d
  (FIT); only feed binder C8NA:187 calls setForceFillTextureScaling.
- **Reels-on-top detection:** A1g() is NOT reliable (returns top-level tab host,
  not ClipsTabFragment). Better: patch C2ZS.A01 directly — its call site
  (ClipsTabFragment.onResume:860) IS already the "Reels on top" gate. No extra
  runtime check needed for window-chrome patches.
- **Config-change resilience:** InstagramMainActivity.onConfigurationChanged
  (A1p:4078-4180) re-paints tab_bar via C26630bQ.A04:4112 — undoes transparent-
  nav patches on rotation. So patch C26630bQ.A04 ITSELF (single chokepoint
  called from both C2ZS.A01:42 and A1p:4112) to survive rotation. Window-level
  patches (setStatusBarColor etc.) survive rotation (not re-touched by A1p).

### Agent 4-d (comment sheet runtime branch + dimming)
- BottomSheetFragment runtime branch for Reels: Branch C → setColorFilter at
  BottomSheetFragment.java:1646 (color2 = igds_color_elevated_background,
  opaque). So the ColorFilter is the final paint — patch line 1646.
- EPN.java:534 sets clips_media_dimming_view alpha = 1.0 - fA05; when sheet
  open, fA05=0 → alpha=1.0 (opaque black). Patch → 0.0f to kill dimming.
- C109193lI (scrim): background_dimmer is a full-screen TouchInterceptorFrameLayout,
  alpha = slide fraction (1.0 when open), color 0xFF000000. Patch lines 546+724
  → multiply alpha by 0.4 for translucency.
- clips_media_dimming_view = plain View (not blur), ON TOP of video, BEHIND
  sheet. Three opaque layers all block video.
- FrostedOverlayView: setupFrom(View, IgProgressImageView) snapshots any source
  view via view.draw(canvas) + RenderEffect blur (API 31+) / CPU fallback.
  Can blur the clips ViewPager from inside the comment sheet container.
  One-shot snapshot; live blur needs Choreographer loop.

### apktool resource decode (4-e) — the missing half
- MainActivity manifest: configChanges includes orientation|screenSize (rotation
  doesn't recreate activity — patches survive ✅) + screenOrientation="locked"
  (overridden by runtime setRequestedOrientation ✅).
- Runtime theme: Theme.Instagram → Base.Theme.Instagram sets windowBackground +
  statusBarColor = ?igds_color_primary_background (= igds_prism_black = #ff0c1014,
  dark blue-gray not pure black).
- igds_color_clips_tab_bar_background = igds_prism_black = #ff0c1014.
  igds_color_clips_tab_bar_icon = igds_prism_gray_00 = #fff8f9f9 — **icons
  ALREADY white** ✅ (only bg needs fixing).
- tabBarHeight = theme attr → @dimen/tab_bar_height_panorama = 44dp(hdpi)/48dp(xxhdpi).
- tab_bar = TouchInterceptorLinearLayout in layout_activity_main_internal_viewpager2.xml,
  layout_gravity=bottom, height=?tabBarHeight. swipeable_tab_view_pager (Reels host)
  = fill_parent with NO XML bottomMargin (code adds it at :1421).
- **CRITICAL:** layout_clips_tab_fragment, layout_clips_viewer_fragment,
  bottom_sheet_fragment do NOT exist as XML → they're Bloks/Litho (code-defined).
  So Reels viewer + comment sheet + scrubber patches MUST be Smali (no XML).
  Only tab_bar bg (Feature B) and the prism drawable (Feature C partial) can be
  resource-patched.
- igds_bottom_sheet_background_prism.xml EXISTS (shape, solid=?igds_color_elevated_background).
  Trivial to make translucent, BUT runtime uses ColorFilter (line 1646) on top —
  must patch the code path too.

### Status after step 3
- All 5 original gaps CLOSED. Player found. Popup path traced. Force-fill
  understood. Comment sheet branch confirmed. Resources decoded.
- New minor open items (non-blocking, for the eventual patching phase):
  1. Verify production prism state (determines ColorFilter patch location).
  2. Find exact MobileConfig values to flip for the scrubber (36320867680860001L).
  3. Confirm C30423BTc is mounted in the clips Litho tree (vs needing to mount).
  4. Decide one-shot vs live blur for Feature C frosted glass.
- STILL no code/patches written (per user: explore only). Next prompt = decide
  whether to start designing/writing Smali patches, or explore more.

---

## 2026-08-09 — Step 4: CODING — patches written + verified + workflow ready

### What was done
- Downloaded the actual APK (240MB) via GitHub raw URL.
- Full apktool decode (smali + manifest, 1.9GB, ~1 min).
- Mapped all jadx-deobfuscated class names to original smali names:
  C2ZS→X/2ZS, C26630bQ→X/0bQ, C6BM→X/6BM, VBP→X/VBP, EPN→X/EPN, etc.
  (jadx --deobf prepends a hash prefix; the SUFFIX matches the original name.)
- Read the exact smali for each patch target (VBP FSS/EvT, 2ZS A01, 6BM Fji,
  0bQ A04, InstagramMainActivity A0V, EPN dimming, BottomSheetFragment).
- Wrote `apply_patches.py` with 9 patches covering all 4 features.
- Tested locally: all 9 patterns found, all 9 patches applied successfully.
- Verified patched smali looks correct (VBP FSS/EvT rotation code clean).
- Wrote `insta-truereel-build.yml` workflow (decode → patch → build → sign → upload).

### Patches summary (9 total)
- A1: 2ZS.smali — decorView bg → transparent (v3→0 before 0cW.A0R)
- A2: 2ZS.smali — android.R.id.content bg → transparent (p2→0)
- A3: 6BM.smali — zero top inset (p1→0 before setPadding)
- B1: InstagramMainActivity.smali — zero swipeable_tab_view_pager bottomMargin (3 sites)
- B2: styles.xml — igds_color_clips_tab_bar_background → #00000000 (4 theme variants)
- C1: EPN.smali — zero ALL dimming alpha calls (8 0cW.A05 calls)
- C2: BottomSheetFragment.smali — setColorFilter color → 0xCC000000 (80% black, 2 sites)
- D1: VBP.smali FSS — setRequestedOrientation(LANDSCAPE=0) at method start
- D2: VBP.smali EvT — setRequestedOrientation(USER=14) at method start

### Key smali details verified
- VBP.A02 (RE7) → RE7.A0B (X/9eY) → 9eY.A04 (FragmentActivity) — confirmed field chain
- 6mW.A00(Activity, int) — confirmed: calls setRequestedOrientation, catches IllegalStateException
- Manifest: configChanges includes orientation|screenSize (no recreate on rotation) ✅
- screenOrientation="locked" — overridden by runtime setRequestedOrientation ✅
- Icons already white (igds_prism_gray_00 = #fff8f9f9) — only bg needs fixing ✅

### Not yet implemented (future iterations)
- Feature D seekbar (force-show VideoScrubberSeekBar via MobileConfig flip)
- Feature C true frosted blur (FrostedOverlayView)
- Force-fill scaling (setForceFillTextureScaling)
- Reels-only gating for A3 (currently global)

### Next step
User triggers the workflow → downloads patched APK → tests on Android 10+.
Iterate based on what works/breaks.
