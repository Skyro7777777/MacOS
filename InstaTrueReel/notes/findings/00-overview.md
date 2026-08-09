# 00 — Findings Overview (from decompiled source, file:line evidence)

This is the master index of what the 5 parallel exploration agents found by
reading the actual decompiled Instagram source (175,407 Java files). All
hypotheses from `06-design-brainstorm.md` are now replaced by confirmed facts
below. Per-feature detail lives in `3-a`..`3-e`.

Source root: `/home/z/insta-src/jadx-out/sources/`
⚠️ jadx run used `--no-res` → layout XML / themes / drawables / strings are
NOT in this dump. Code-side calls (setStatusBarColor, setBackgroundColor, etc.)
ARE. XML-level patches will need an apktool decode (open work item).

---

## ROOT CAUSES (why Reels look broken today)

### Top black strip (status bar area)
Two layers paint it black:
1. `com/instagram/mainactivity/InstagramMainActivity.java:3256` (dup `:7234`)
   → `AbstractC54451fC.A03(this, igds_color_primary_background)` =
   `window.setStatusBarColor(BLACK)`.
2. `p002X/C2ZS.java:102` (the clips-tab window-chrome controller, `C2ZS.A01`)
   → `AbstractC54451fC.A04(activity, iA0W)` sets status bar COLOR =
   `igds_color_primary_background` (opaque black) — this **undoes** the
   transparent-status-bar call at `C2ZS.java:99`
   (`AbstractC54451fC.A06(decorView, window, true)`).
3. `p002X/C2ZS.java:86` paints `decorView` black; `:131` paints
   `android.R.id.content` black.

### Bottom black strip (nav bar area) + the gap below the video
1. `com/instagram/mainactivity/InstagramMainActivity.java:3261` (dup `:7239`)
   → `C54511fI.A01(this)` = `window.setNavigationBarColor(BLACK)`.
2. `p002X/C26630bQ.A04` (`p002X/C26630bQ.java:120-138`) paints `R.id.tab_bar`
   + `R.id.ls_nav_bar` with `igds_color_clips_tab_bar_background` (opaque).
   Lines 124/127/132/137. Called from `InstagramMainActivity:4112` and
   `C2ZS.A01:42-44`.
3. **THE GAP itself:** `com/instagram/mainactivity/InstagramMainActivity.java:1421`
   (`A0V(int i)`) — when the bottom nav is VISIBLE, sets
   `swipeable_tab_view_pager.bottomMargin = tabBarHeight`. This bottom margin
   IS the black strip below the reel video. (`swipeable_tab_view_pager` =
   `0x7f0b3f45`, the ViewPager2 host, set up at `p002X/C0ZS.java:226-262`.)

### Why the video doesn't extend under the status bar
`com/instagram/base/activity/IgFragmentActivity.java:735` registers
`C6BM(this, 0)` as the WindowInsets listener. `p002X/C6BM.java:34-49` (case 0
of `Fji`) calls `C192756wm.A0w(contentChild, topInset, bottomInset)` =
`setPadding(left, top, right, bottom)` — applying the system insets as padding
to the content. Plus `IgFragmentActivity.A1j()` at `:727` pre-paints decorView
black.

ClipsViewerFragment (`p002X/C254289Wz.java`) makes **zero** direct
window/inset/system-bar calls — it inherits the activity's window state. So a
per-fragment fix alone is insufficient; the activity's `C6BM` listener keeps
re-applying padding.

### Comment sheet opaque black
`CommentListBottomsheetFragment` = `p002X/C54625Krc.java` (route
`"comment_clips_viewer"` at `AbstractC78782dL.java:5820-5827`). Plain Fragment
overlaid via `IgBottomSheetNavigator` (`C109193lI`) into
`R.id.layout_container_bottom_sheet`. Three opaque layers:
1. Sheet panel: `com/instagram/igds/components/bottomsheet/BottomSheetFragment.java:1562`
   (`R.drawable.igds_bottom_sheet_background_prism`) or `:1608` (GradientDrawable
   colored `igds_color_elevated_background`) — both opaque in dark theme.
2. `clips_media_dimming_view` — separate dim layer, opaque
   `igds_color_media_background`, alpha-animated at `p002X/EPN.java:534`.
3. `background_dimmer` — IGDS scrim, alpha-animated at
   `p002X/C109193lI.java:546, 602, 724, 1873, 1878`.

### Existing "fullscreen" (Feature D base)
NOT a separate Fragment/Activity. It is a **fade-out of the side UFI buttons**
triggered by a swipe gesture. Handler: `VBP.FSS(i,i2)` enters (`p002X/VBP.java:116-170`),
`VBP.EvT()` exits (`:47-88`). Sets **alpha = 0.0f** on `R.id.clips_ufi_component`
(NOT View.GONE) + media-info + `ClipsViewerNavigationBar`. Fade animator = `EPN`
("WatchAndCommentViewManager"). There is also a "Fullscreen" entry in the
long-press/three-dot popup (`VSL.java:26-44` adds `MediaOption$Option.FULLSCREEN_VIEW`).
**Confirmed:** no `setRequestedOrientation` anywhere in clips → no rotation;
`SimpleVideoLayout` exposes no getDuration/getCurrentPosition/seekTo → no seekbar.

---

## KEY CLASS MAP (obfuscated → real)

| Obfuscated | Real name / role | Path |
|------------|------------------|------|
| `C27528AFt` | ClipsTabFragment (outer Reels host) | p002X/C27528AFt.java |
| `C254289Wz` | ClipsViewerFragment (swipeable feed, 113k lines) | p002X/C254289Wz.java |
| `C3EO` | VideoFrameLayout (SimpleVideoLayout + TextureView) | p002X/C3EO.java |
| `AbstractC210917ky` | VideoFrameLayout base (sizing: FIT 0.25d / fill 1.0d) | p002X/AbstractC210917ky.java |
| `C25U` | TextureView layout math (FIT vs ZOOM) | p002X/C25U.java |
| `C2ZS` | Clips-tab window-chrome controller | p002X/C2ZS.java |
| `C26630bQ` | Bottom-nav painter (bg + icon tint) | p002X/C26630bQ.java |
| `C34210ne` | MainTab (holds R.id.tab_bar, field A0F) | p002X/C34210ne.java |
| `C6BM` | WindowInsets listener (applies inset padding) | p002X/C6BM.java |
| `C54625Krc` | CommentListBottomsheetFragment | p002X/C54625Krc.java |
| `QF1` | CommentListBottomsheetBaseFragment | p002X/QF1.java |
| `BottomSheetFragment` | IGDS shared sheet (panel bg) | com/instagram/igds/components/bottomsheet/BottomSheetFragment.java |
| `C109193lI` | IgBottomSheetNavigator (scrim) | p002X/C109193lI.java |
| `EPN` | WatchAndCommentViewManager (ufi fade + dim) | p002X/EPN.java |
| `VBP` | Clips-viewer gesture listener (fullscreen toggle) | p002X/VBP.java |
| `C11R` | ClipsItemState (isFullscreenViewActive etc.) | p002X/C11R.java |
| `FrostedOverlayView` | REUSABLE blur (RenderEffect, API 31+, CPU fallback) | com/instagram/p132ui/legibilityoverlay/FrostedOverlayView.java |
| `AbstractC54451fC` | status-bar helpers (transparent/setcolor/layout-fullscreen) | p002X/AbstractC54451fC.java |
| `C54511fI` | nav-bar helpers (A01 opaque / A02 translucent) | p002X/C54511fI.java |

---

## PER-FEATURE PATCH HOOK POINTS (file:line, confirmed)

### Feature A — transparent status bar (video behind it)
- Force the transparent branch at `InstagramMainActivity.java:3258`/`:7236`
  (it already calls `AbstractC54451fC.A05(this, false)` = light icons at
  `:3259`/`:7237` — good, white icons over video).
- Stop re-painting the status bar black: neutralize the
  `AbstractC54451fC.A04(activity, iA0W)` call at `p002X/C2ZS.java:102` (or
  make `iA0W` resolve to transparent when Reels is on top).
- Stop applying top inset as padding: skip `C6BM.Fji` case 0 at
  `p002X/C6BM.java:34-49` when Reels is on top (or neutralize
  `IgFragmentActivity.A1j()` at `:727`).
- Stop painting decorView/content black: `p002X/C2ZS.java:86` and `:131`.
- "Reels on top" detection: `IgFragmentActivity.A1g()` at `:685`.

### Feature B — floating bottom nav (transparent + white icons + no gap)
1. `p002X/C26630bQ.java:124,127,132,137` (`A04`) — substitute `0` (TRANSPARENT)
   for the color arg in clips mode. (Resource alternative: edit
   `igds_color_clips_tab_bar_background` + `igds_color_reels_tab_bar_separator`
   in `res/values/colors.xml` → `#00000000`.)
2. `p002X/C26630bQ.java:200` (`A09`) — substitute `0xFFFFFFFF` for
   `activity.getColor(i)` to force white icons. (Resource alternative: edit
   `igds_color_clips_tab_bar_icon` → `#FFFFFFFF`. Default is already
   white-ish, may only need confirming.)
3. `com/instagram/mainactivity/InstagramMainActivity.java:1421` (`A0V`) —
   change `marginLayoutParams.bottomMargin = dimensionPixelOffset` → `= 0`.
   **REQUIRED** even with resource-only fallback (zeroing the dimen would
   collapse bar height). This removes the gap so video extends behind the nav.
- Lifecycle is already TikTok-like: IG does NOT hide the bar on Reels
  (`Gvc(int i)` at `InstagramMainActivity.java:7992` keeps it VISIBLE; only
  colors change via `C2ZS.A01/A02/A03` enter, `C2ZS.A0B` exit). Perfect for
  floating-transparent.
- Nav bar color: replace `C54511fI.A01(this)` at `InstagramMainActivity.java:3261`/`:7239`
  with `C54511fI.A02(this)` (translucent nav bar) when Reels on top.
- Optional true API-30+ edge-to-edge: replace `setSystemUiVisibility(1792)` at
  `:1969`/`:2290`/`:2738`/`:3069` with `AbstractC24660Vv.A00(window, false)`.

### Feature C — translucent frosted comment sheet
1. Make the sheet panel translucent — change `igds_bottom_sheet_background_prism`
   drawable in `res/drawable/` to a semi-transparent color (resource patch via
   apktool), OR override `igds_color_elevated_background` in `themes.xml`.
2. Reduce dim layers — smali-patch `p002X/EPN.java:534` to skip dimming the
   video, and/or multiply alpha by ~0.3 at `p002X/C109193lI.java:546`.
3. **True frosted blur (drop-in):** insert `FrostedOverlayView`
   (`com/instagram/p132ui/legibilityoverlay/FrostedOverlayView.java`) as the
   first child of the bottomSheetContainer and call `setupFrom(clipsViewPager, null)`
   in `C54625Krc.onViewCreated`. That class already does GPU
   `RenderEffect.createBlurEffect(15f,15f,CLAMP)` on API 31+ (line 114) with a
   27%-scale CPU box-blur fallback for older devices (lines 68-92).
- Note: the runtime branch in `BottomSheetFragment.onViewCreated` (prism drawable
  vs GradientDrawable) depends on theme + caller config → needs runtime
  verification before patching.

### Feature D — TikTok-style horizontal fullscreen (enhance existing)
Hook into the existing fullscreen toggle (`VBP`):
- **Landscape rotation:** at the start of `VBP.FSS` (`p002X/VBP.java:116`) add
  `setRequestedOrientation(LANDSCAPE)`; at the start of `VBP.EvT` (`:47`) add
  `setRequestedOrientation(PORTRAIT/USER)`. Reuse IG helpers `C99744f1m.A01`
  (`p002X/C99744f1m.java:104,106,122`) or `AbstractC186396mW.A00`
  (`p002X/AbstractC186396mW.java:11`).
- **Landscape gate:** inside `VBP.FSS` before rotation, check the player's video
  dimensions (`videoWidth > videoHeight`). No runtime `isLandscape` accessor
  exists (only the creation-side `feedmetadata_isLandscape` in drafts DB) — add
  our own check.
- **Side buttons already hidden** by `VBP.FSS` (alpha=0 on `clips_ufi_component`
  etc.) — so Feature D's "hide side buttons" is FREE; just reuse the toggle.
- **Seekbar:** `SimpleVideoLayout` has none. Options:
  - (a) Add a custom `SeekBar` overlay bound to the player via
    `Handler.postDelayed(33ms)` polling `getCurrentPosition/getDuration` —
    least invasive.
  - (b) Overlay a media3 `PlayerView` controller — would need the player
    instance; more invasive.
  - Show/hide the seekbar in `VBP.FSS` after `EPN` creation (line 131) and
    hide in `VBP.EvT` (line 47).
- **Open gap:** the player instance (exposing getCurrentPosition/getDuration/
  seekTo) is NOT yet located. `SimpleVideoLayout`/`AbstractC210917ky` expose
  none. Next exploration: read `p002X/C257899eY.java` + `p002X/C3BT.java`
  (Litho binder creating `C3EO`) and hunt for the underlying
  `MediaPlayer`/`IMediaPlayer`/`VideoPlayer` interface across `p002X/`.

---

## REMAINING GAPS (need follow-up exploration)

1. **Player instance for Feature D seekbar** — locate the object exposing
   getCurrentPosition/getDuration/seekTo. Read `C257899eY`, `C3BT`, and grep
   `p002X/` for `getCurrentPosition|getDuration|seekTo|MediaPlayer|VideoPlayer`.
2. **`I34.run()` case 33** — decompile the tail to confirm whether the popup
   menu's "Fullscreen" entry actually calls `VBP.FSS` (or needs its own hook).
3. **Resources via apktool** — the layout XMLs (`layout_clips_tab_fragment`,
   `layout_clips_viewer_fragment`, `bottom_sheet_fragment`,
   `layout_activity_main_coordinator_layout`), themes (`statusBarColor`,
   `navigationBarColor`, `windowBackground`), drawables
   (`igds_bottom_sheet_background_prism`), and strings (`R.string 2131984733` =
   FULLSCREEN_VIEW label) are NOT in the jadx dump. An apktool decode is
   required before any XML/drawable/color patch.
4. **Runtime verification** of the `BottomSheetFragment.onViewCreated` branch
   (prism drawable vs GradientDrawable) — which path runs for Reels comments.
5. **Confirm `RE7.A0C` activity access** from `VBP` (VBP is a plain object, not
   a Fragment — may need a context cast to Activity, or pass activity via `RE7`).

---

## SUMMARY TABLE — what each feature needs

| Feature | Code patch (Smali) | Resource patch (apktool) | Verdict |
|---------|--------------------|--------------------------|---------|
| A status bar | C2ZS.java:86,99,102,131; C6BM.java:34-49; IgFragmentActivity:727 | statusBarColor/windowBackground in themes | Feasible — all hooks found |
| B bottom nav | C26630bQ.java:124,127,132,137,200; InstagramMainActivity.java:1421,3261,7239 | igds_color_clips_tab_bar_background/icon in colors.xml | Feasible — all hooks found |
| C comment sheet | EPN.java:534; C109193lI.java:546 | igds_bottom_sheet_background_prism drawable; igds_color_elevated_background | Feasible — FrostedOverlayView is reusable for true blur |
| D fullscreen | VBP.java:47,116 (+ seekbar overlay) | R.string 2131984733 label; expand drawable | Feasible for rotation; seekbar needs player-instance exploration |
