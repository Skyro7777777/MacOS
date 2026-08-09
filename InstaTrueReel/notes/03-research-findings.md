# 03 — Research Findings

Brief web research (z-ai web_search). Key takeaways only.

## A. Android edge-to-edge / immersive mode (the core mechanism)

- **Android 15 (API 35) forces edge-to-edge** for apps targeting API 35: views
  receive window insets and must handle them. Apps targeting lower APIs or that
  explicitly opt out keep the old letterboxed look. Instagram likely targets a
  lower API *and/or* explicitly calls `setDecorFitsSystemWindows(true)` /
  sets `fitsSystemWindows="true"` / paints its root background black.
- **Modern API (AndroidX):**
  - `WindowCompat.setDecorFitsSystemWindows(getWindow(), false)` — let content
    draw behind system bars.
  - `enableEdgeToEdge()` (Activity KTX) — one-call edge-to-edge.
  - `WindowInsetsControllerCompat` — hide/show system bars; set
    `setSystemBarsBehavior(BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE)` for
    immersive (swipe to reveal).
- **Old API (still works, what Instagram may use):**
  - `FLAG_TRANSLUCENT_STATUS` / `FLAG_TRANSLUCENT_NAVIGATION`
  - `FLAG_LAYOUT_NO_LIMITS`
  - `SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | SYSTEM_UI_FLAG_LAYOUT_STABLE |
    SYSTEM_UI_FLAG_IMMERSIVE_STICKY`
- **Per-view:** `fitsSystemWindows="true"` makes a view apply insets as padding
  (this is what creates the black gap). Setting it `false` + manual inset
  handling is the fix. Also watch `android:windowBackground` (often black) and
  `View.setSystemUiVisibility`.
- Useful reads:
  - medium.com/androiddevelopers "Insets handling tips for Android 15's
    edge-to-edge enforcement"
  - proandroiddev "How to support edge-to-edge display in Android apps?"

**Implication for patching:** we don't need to *add* edge-to-edge from scratch;
we need to find where Instagram **disables** it for Reels (or pads its root
black) and flip that off, then make the overlay bars transparent.

## B. ReVanced / Instagram patching ecosystem

- **ReVanced Patches** (gitlab.com/ReVanced/revanced-patches, mirror github)
  has Instagram patches: hide ads, hide reels button, disable reels scrolling,
  anonymous story viewing, disable analytics, etc.
- **No existing ReVanced patch for "edge-to-edge Reels" or "transparent
  bottom bar"** — this is a gap (community has asked: reddit
  r/revancedapp "Could We Take on Instagram Next?").
- **ReVanced patches are written in Kotlin/Java** and target **Smali** via the
  ReVanced Patcher (they don't recompile jadx Java). So our patches should
  either be:
  - **(i) ReVanced-style patch classes** (Kotlin) that the ReVanced Patcher
    applies to the APK, or
  - **(ii) direct Smali edits** via apktool (simpler to iterate, no ReVanced
    toolchain needed).
- The APK in this repo is already "patches-v3.8.0" → already had ReVanced
  patches applied. We patch on top of that.

## C. TikTok horizontal fullscreen feature (Feature D)

- Launched **Dec 2022** (TechCrunch/ZDNet). "Full Screen" button appears on
  horizontal (≥16:9-ish) videos.
- Behavior: tap → video shifts to **horizontal full-screen** (landscape
  orientation), hides the vertical-feed UI (like/comment/share side buttons),
  shows a **seekbar/scrubber** — YouTube-like.
- TikTok Creator Academy has an official "Full Screen Mode Guide":
  tiktok.com/creator-academy/en/article/tool-full-screen-intro
- Posting trick: creators rotate 270° in the editor so a widescreen video is
  treated as horizontal and gets the Full-Screen button.

**Implication:** Instagram v435's expand button (screenshot F) is the analog.
Need to test what it does today. If it just expands within vertical (crops/
zooms) without rotating + seekbar, we enhance/replace it.

## D. Tooling for patch+build pipeline (to run in Actions)

- **apktool** (2.9+) — decode APK to Smali + resources; rebuild. Best for
  direct Smali edits + resource (layout XML) edits.
- **baksmali/smali** — lower-level; apktool wraps these.
- **ReVanced Patcher** — if we go the ReVanced-patch route.
- **uber-apk-signer** or **apksigner** (Android SDK build-tools) — sign the
  rebuilt APK (debug or user-provided keystore).
- **zipalign** — align before signing.
- **jadx** (already used) — read-only decompile for understanding; **cannot
  recompile to a working APK.**
- **Resources matter:** Instagram's bottom-bar layout XMLs and themes are in
  `res/`. The current jadx run used `--no-res`, so to patch layouts/themes we
  must either re-run jadx with resources or (better) use apktool which decodes
  `res/` natively. → note for exploration workflow.

## E. What we likely need to find in the source (preview — full list in 04)

- The **Reels/Clips Activity/Fragment** (e.g. `ClipsFragment`, `ReelsFragment`,
  `ReelViewerFragment`, `ClipsActivity`).
- The **bottom nav** view class + its layout XML + theme (background color).
- The **comment BottomSheet** fragment + its background style.
- Any call to `setDecorFitsSystemWindows`, `setFitsSystemWindows`,
  `setSystemUiVisibility`, `FLAG_TRANSLUCENT_*`, `windowBackground` in the
  Reels scope.
- The **existing expand/fullscreen button** for horizontal videos — its
  click handler and what it invokes.
- The **video player view** (likely ExoPlayer-backed `PlayerView` /
  `ClipsPlayerView`) and its container's layout params / aspect-ratio mode
  (RESIZE_MODE_*).
