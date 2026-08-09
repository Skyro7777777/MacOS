# Task 3-b — System bar / window insets / edge-to-edge (Features A & B)

Exploration of Instagram v435.0.0.37.76 decompiled at `/home/z/insta-src/jadx-out/sources/`.
READ-ONLY. All line numbers refer to that decompile tree.

## TL;DR — what creates the black strips

1. `InstagramMainActivity` does NOT call `setDecorFitsSystemWindows(false)` and does NOT
   set its own window colors directly. It only sets `decorView.setSystemUiVisibility(1792)`
   (legacy LAYOUT_STABLE | LAYOUT_FULLSCREEN | LAYOUT_HIDE_NAVIGATION) at four places and
   delegates status-bar/nav-bar coloring to two helper classes:
   - `AbstractC54451fC` (status bar color + light/dark status-bar icons)
   - `C54511fI` (navigation bar color + light/dark nav-bar icons)
2. **The black strip above Reels is the status-bar background painted by
   `AbstractC54451fC.A03(activity, color)` where `color = igds_color_primary_background`
   (= BLACK in IG's dark theme).** The exact call is at
   `InstagramMainActivity.java:3256` and the duplicate `:7234`.
3. **The black strip below Reels is the navigation-bar background painted by
   `C54511fI.A04(activity, color)` where `color` is the theme `R.attr.navigationBarColor`
   (= BLACK) for `InstagramMainActivity`.** Wired in `C54511fI.A01(activity)` from
   `InstagramMainActivity.java:3261` and `:7239`.
4. **The visible "padding" that pushes the video down/up (so the system bars are not
   covered by video) comes from `IgFragmentActivity.A1k()` → registers `C6BM(this, 0)`
   as a WindowInsets listener; on every inset change `C6BM.Fji(top, bottom)` calls
   `C192756wm.A0w(contentChild, top, bottom)` = `setPadding(left, top, right, bottom)`.**
   See `IgFragmentActivity.java:735`, `C6BM.java:34-49`, `C192756wm.java:401-404`.
5. The `ClipsViewerFragment` (Reels tab; obfuscated as `p002X/C254289Wz`, original name
   `"ClipsViewerFragment"` per `__redex_internal_original_name` at line 130) does **NOT**
   touch the window at all: zero hits for `setStatusBarColor|setNavigationBarColor|
   setSystemUiVisibility|setDecorFitsSystemWindows|setFitsSystemWindows|WindowInsets|
   requestApplyInsets|setOnApplyWindowInsetsListener|getInsetsController|enableEdgeToEdge`.
   Same for `instagram/features/stories/fragment/ReelViewerFragment.java` (Stories).
6. The only "edge-to-edge setup" helper that IG uses internally for Reels-adjacent UI
   (`AbstractC72042Ib.A01(window, z)` — clears `FLAG_TRANSLUCENT_*`, adds
   `FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS`, `setDecorFitsSystemWindows(false)`, transparent
   status + nav bar, no contrast enforcement) is wired only through the **splash screen
   helper** `C123814Le` ("FbMainActivitySplashHelper") and is RESET to fitsSystemWindows
   by `AIQ` once the real activity is created. So at runtime, IG runs NON-edge-to-edge.

The `getStatusBarType()` enum on `AbstractC91822yN` (IgFragment) is overridden by
ClipsViewerFragment and ReelViewerFragment to `EnumC41080yj.FORCED_DARK_MODE` but is
**never read** by any caller in the decompiled tree — it appears to be dead/vestigial
or consumed via reflection elsewhere. Don't rely on it for the patch.

---

## IG-side hits — every match in IG code

| file:line | quoted call | what it does |
|---|---|---|
| `com/instagram/mainactivity/InstagramMainActivity.java:1969` | `decorView.setSystemUiVisibility(1792);` | MainActivity onCreate: legacy edge-to-edge layout bits (LAYOUT_STABLE\|LAYOUT_FULLSCREEN\|LAYOUT_HIDE_NAVIGATION). Pushes content under status + nav bars but does NOT make bars transparent. |
| `com/instagram/mainactivity/InstagramMainActivity.java:2290` | `decorView2.setSystemUiVisibility(1792);` | duplicate path (cold-start Reels tab branch) |
| `com/instagram/mainactivity/InstagramMainActivity.java:2738` | `decorView.setSystemUiVisibility(1792);` | duplicate path |
| `com/instagram/mainactivity/InstagramMainActivity.java:3069` | `decorView2.setSystemUiVisibility(1792);` | duplicate path |
| `com/instagram/mainactivity/InstagramMainActivity.java:3256` | `AbstractC54451fC.A03(instagramMainActivity, instagramMainActivity.getColor(AbstractC26520bF.A0O(instagramMainActivity)));` | **THE BLACK TOP STRIP.** Sets status bar color to `igds_color_primary_background` (BLACK in dark theme) when action bar visible. |
| `com/instagram/mainactivity/InstagramMainActivity.java:3258` | `AbstractC54451fC.A03(instagramMainActivity, instagramMainActivity.getColor(R.color.bds_transparent));` | alternate branch: status bar transparent (used when camera-overlay mode) |
| `com/instagram/mainactivity/InstagramMainActivity.java:3259` | `AbstractC54451fC.A05(instagramMainActivity, false);` | in transparent branch: dark icons (z=false → AbstractC54451fC.A05 → A01(false)) |
| `com/instagram/mainactivity/InstagramMainActivity.java:3261` | `C54511fI.A01(instagramMainActivity);` | **THE BLACK BOTTOM STRIP.** Sets nav-bar color to theme `R.attr.navigationBarColor` (BLACK) for InstagramMainActivity. |
| `com/instagram/mainactivity/InstagramMainActivity.java:7234-7239` | same calls as 3256-3261 | duplicate of above in a second lifecycle entry point (likely `onResume`/re-attach) |
| `com/instagram/base/activity/IgFragmentActivity.java:735` | `C242418ug.A05(this, new C6BM(this, 0), false);` | registers the per-activity WindowInsets listener that applies status/nav bar inset as `setPadding` to the content view (creates the "pushed-down" layout) |
| `com/instagram/base/activity/IgFragmentActivity.java:718-728` | `A1j()` body | reads `igds_color_primary_background`, calls `AbstractC54451fC.A03/A04` (status bar color + flags) + `AbstractC27310cW.A0R(decorView, color, …)` = `decorView.setBackgroundColor(color)` (paints decor BLACK behind the system bars) |
| `com/instagram/base/activity/IgFragmentActivity.java:915` | `final int iA0X = AbstractC26520bF.A0X(this, android.R.attr.statusBarColor) \| (-16777216);` | reads theme `android:statusBarColor`, forces alpha=0xFF, uses it for `setTaskDescription` (recent-apps bar). Not the live status bar. |
| `com/instagram/base/activity/IgFragmentActivity.java:1652` | `getTheme().resolveAttribute(android.R.attr.windowBackground, typedValue, true);` | `A26()` — used to detect whether window has a solid background. Gates `A1j()` call in C6BM (line 48). |
| `p002X/C6BM.java:34-49` | `C192756wm.A0w(childAt, i, i2);` … `igFragmentActivity.A1j();` | the WindowInsets dispatcher callback (case 0): applies `setPadding(left, top, right, bottom)` on the activity content's first child, then re-applies status bar color via A1j when the window is opaque. |
| `p002X/C192756wm.java:401-404` | `view.setPadding(view.getPaddingLeft(), i, view.getPaddingRight(), i2);` | `A0w(view, top, bottom)` — the actual `setPadding` call. `i`=top inset (status bar), `i2`=bottom inset (nav bar). |
| `p002X/C242418ug.java:102-126` | `interfaceC27600AIn.Fji(i2, i);` | `WindowInsetsManager.A05(activity, listener, z)` — registers and dispatches system-bar insets to listeners. Original class name `com.instagram.ui.windowinsets.WindowInsetsManager` (see A0B comment line 41). |
| `p002X/AbstractC54451fC.java:69-80` | `A03(activity, i)` body | sets status bar color: calls `A04(activity, i)` and resolves `windowLightStatusBar` from theme to toggle icons. |
| `p002X/AbstractC54451fC.java:82-116` | `A04(activity, i)` body | the actual `window.addFlags(0x80000000); window.setStatusBarColor(i);` (FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS + color). |
| `p002X/AbstractC54451fC.java:119-133` | `A05(activity, z)` body | toggles light status bar via `new C25090Xm(decorView, window).A01(z2)` (z2 depends on dark/light mode). |
| `p002X/AbstractC54451fC.java:65-67` | `A02(activity)` | one-liner: `A03(activity, transparent)`. Convenience for "make status bar transparent". |
| `p002X/AbstractC54451fC.java:135-147` | `A06(view, window, z)` | legacy light-status-bar toggle using `setSystemUiVisibility` bits 4/256 + `window.setFlags(1024, 1024)` (FLAG_FORCE_NOT_FULLSCREEN). |
| `p002X/AbstractC54451fC.java:149-154` | `A07(window, z)` | registers an `OnApplyWindowInsetsListener` on decorView via `AbstractC24250Ug.A02` + `requestApplyInsets()`. |
| `p002X/C54511fI.java:35-47` | `A01(activity)` body | reads theme `R.attr.navigationBarColor` (for InstagramMainActivity) or `igds_color_primary_background` (for other activities), then `A04(activity, color)` + `A05(activity, true)`. |
| `p002X/C54511fI.java:77-121` | `A04(activity, i)` body | `window.addFlags(0x80000000); window.setNavigationBarColor(i);` + contrast enforcement. |
| `p002X/C54511fI.java:124-138` | `A05(activity, z)` body | toggles light nav bar via `new C25090Xm(decorView, window).A00(z2)`. |
| `p002X/C54511fI.java:49-56` | `A02(activity)` | `window.addFlags(0x08000000); window.addFlags(0x80000000);` — translucent nav bar (FLAG_TRANSLUCENT_NAVIGATION + FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS). |
| `p002X/C25070Xk.java:21` | `this.A01.setSystemBarsBehavior(2);` | `BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE` (=2) for immersive mode (only used when window==null branch). |
| `p002X/C25070Xk.java:26-28` | `decorView.setSystemUiVisibility((-2049) & …);` then `setSystemUiVisibility(4096 \| …)` | clears SYSTEM_UI_FLAG_IMMERSIVE (2048), sets SYSTEM_UI_FLAG_IMMERSIVE_STICKY (4096). |
| `p002X/C25070Xk.java:53` | `decorView.setSystemUiVisibility(\| 16);` + `setSystemBarsAppearance(16, 16)` | SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR (16) + WindowInsetsController APPEARANCE_LIGHT_NAVIGATION_BARS. |
| `p002X/C25070Xk.java:71` | `decorView.setSystemUiVisibility(8192 \| …);` + `setSystemBarsAppearance(8, 8)` | SYSTEM_UI_FLAG_LIGHT_STATUS_BAR (8192) + WindowInsetsController APPEARANCE_LIGHT_STATUS_BARS (8). |
| `p002X/C25070Xk.java:99` | `WindowInsetsController insetsController = window.getInsetsController();` | constructor: obtains modern controller. |
| `p002X/C25090Xm.java:21-78` | `C25090Xm(view, window)` constructor | bridge: SDK≥35 uses C25070Xk (with overridden immersive behavior); SDK 30-34 uses C25070Xk; SDK<30 uses legacy `AbstractC25030Xg` subclass that calls `setSystemUiVisibility` bits 16/8192 + `window.addFlags(0x80000000)` + `clearFlags(0x04000000 / 0x08000000)`. |
| `p002X/AbstractC24660Vv.java:12-29` | `A00(window, z)` | versioned `setDecorFitsSystemWindows(z)` wrapper (SDK≥35: just `setDecorFitsSystemWindows(z)`; SDK 30-34: + LAYOUT_STABLE bit 256; SDK<30: bits 1792). Used by AbstractC106088ked and SJ6 (React Native). NOT used by MainActivity. |
| `p002X/AbstractC24630Vs.java:11-20` | `A00(window, z)` | SDK 30-34 path: `setSystemUiVisibility` bit 256 + `setDecorFitsSystemWindows(z)`. |
| `p002X/AbstractC24650Vu.java:8-10` | `A00(window, z)` | SDK≥35 path: just `setDecorFitsSystemWindows(z)`. |
| `p002X/AbstractC106088ked.java:20-58` | `A00(window)` body | React Native fullscreen setup: `AbstractC24660Vv.A00(window, false)` + `setStatusBarColor(0)` + `setNavigationBarColor(0)` + `setStatusBarContrastEnforced(false)` + `setNavigationBarContrastEnforced(theme)` + `layoutInDisplayCutoutMode = 3 (ALWAYS)` (or 1 SHORT_EDGES for SDK<30). Then paints nav bar translucent black (A00=128 alpha, A01=230 alpha). |
| `p002X/AbstractC106088ked.java:60-79` | `A01(window, str)` | sets status bar icon tint: `"dark-content"` → `setSystemBarsAppearance(8, 8)` (light status bar / dark icons); else → `setSystemBarsAppearance(0, 8)` (default / light icons). |
| `p002X/AbstractC106088ked.java:81-100` | `A02(window, z)` body | fullscreen toggle: z=true → `setDecorFitsSystemWindows(false)` + `layoutInDisplayCutoutMode=1 (SHORT_EDGES)` + `addFlags(1024) (FLAG_FULLSCREEN)`. z=false → `setDecorFitsSystemWindows(true)` + `layoutInDisplayCutoutMode=0` + `clearFlags(1024)`. |
| `p002X/AbstractC72042Ib.java:10-17` | `A00(activity)` | reset to non-edge-to-edge: `setSystemBarsAppearance(0, 24)` (clears both light bits) + `setDecorFitsSystemWindows(true)`. Called by `AIQ` once MainActivity is created (i.e., splash teardown). |
| `p002X/AbstractC72042Ib.java:19-31` | `A01(window, z)` body | full edge-to-edge setup: `clearFlags(0x0C000000)` (FLAG_TRANSLUCENT_STATUS\|FLAG_TRANSLUCENT_NAVIGATION) + `addFlags(0x80000000)` + `setDecorFitsSystemWindows(false)` + `setStatusBarColor(0)` + `setNavigationBarColor(0)` + `setStatusBarContrastEnforced(false)` + `setNavigationBarContrastEnforced(false)` + `setSystemBarsAppearance(z?0:24, 24)` (z=true → default light icons; z=false → dark icons). Called ONLY by `C123814Le.A01` (splash). |
| `p002X/C123814Le.java:74-98` | `A01(activity, c123814Le)` | `FbMainActivitySplashHelper`: sets up splash content view + edge-to-edge via AbstractC72042Ib.A01. |
| `p002X/AIQ.java:465-482` | `onActivityCreated` lifecycle callback | splash teardown: if activity is not the splash, calls `AbstractC72042Ib.A00(activity2)` (resets DecorFitsSystemWindows=true). |
| `com/instagram/modal/ModalActivity.java:118` | `C54511fI.A02(this);` | translucent nav bar when intent extra `translucent_navigation_bar` is true |
| `com/instagram/modal/ModalActivity.java:128` | `C242418ug.A05(this, new C6BM(this, 4), false);` | registers insets listener for ModalActivity (case 4 applies padding to bottom_sheet_container) |
| `com/instagram/modal/ModalActivity.java:133-138` | `int i = this.A06 ? 1792 : 1280; window.getDecorView().setSystemUiVisibility(i);` | ModalActivity window flags: 1792 (full edge-to-edge layout) if A06 true, else 1280 (LAYOUT_STABLE\|LAYOUT_FULLSCREEN — no layout under nav bar). |
| `com/instagram/modal/ModalActivity.java:140-148` | `window2.setStatusBarColor(intExtra);` / `AbstractC54451fC.A03(this, getColor(AbstractC26520bF.A0O(this)));` | status bar color: from intent extra `status_bar_color` (default -16777216 = BLACK) or theme `igds_color_primary_background` (BLACK). |
| `com/instagram/modal/ModalActivity.java:124` | `viewFindViewById.setFitsSystemWindows(this.A05);` | layout_container_parent gets fitsSystemWindows=true (default) |
| `p002X/C37870tY.java:14-266` | `SwipeNavigationStatusBarManager` (per log at line 88) | manages status bar transition during swipe-between-tabs in MainActivity. Toggles `setSystemUiVisibility` bit 4 (SYSTEM_UI_FLAG_FULLSCREEN) + decorView background BLACK (R.color.bds_black at line 125) when swipe state=1 or 2 (going to/from camera); transparent + light icons otherwise. Also `addFlags(1024)` / `clearFlags(1024)` (FLAG_FULLSCREEN). |
| `p002X/C37870tY.java:130` | `window.getDecorView().setSystemUiVisibility(i);` | the swipe-nav status bar visibility setter |
| `p002X/C37870tY.java:143` | `AbstractC254749Yt.A01(activity, AbstractC26520bF.A0a(activity, R.attr.igds_color_transparent, R.color.bds_transparent));` | during swipe: forces status bar transparent + dark icons (when cutout present). |
| `p002X/AbstractC254749Yt.java:9-19` | `A00(activity)` | cutout-aware: if cutout present, calls `AbstractC54451fC.A06(decorView, window, true)` (legacy light status bar bit) + `AbstractC54451fC.A05(activity, false)` (dark icons). |
| `p002X/AbstractC254749Yt.java:21-32` | `A01(activity, i)` | same + `AbstractC54451fC.A03(activity, i)` (status bar color = i). |
| `p002X/C254289Wz.java:325, 491, 45828-45830` | `public final EnumC41080yj A3O;` … `this.A3O = EnumC41080yj.FORCED_DARK_MODE;` … `public final EnumC41080yj getStatusBarType() { return this.A3O; }` | ClipsViewerFragment declares its status-bar type as `FORCED_DARK_MODE`. The enum (`p002X/EnumC41080yj.java`) values: DEFAULT, TRANSPARENT, FORCED_DARK_MODE, PERSIST, GONE. **But no caller invokes `getStatusBarType()` outside the fragments themselves** — this property appears vestigial / unused at runtime. |
| `instagram/features/stories/fragment/ReelViewerFragment.java:15749-15750` | `public final EnumC41080yj getStatusBarType() { return EnumC41080yj.FORCED_DARK_MODE; }` | same pattern in Stories ReelViewerFragment |
| `p002X/AbstractC38450uU.java:80-95` | `A05(view)` | reads `view.getRootWindowInsets().getDisplayCutout().getBoundingRects()` — used by `AbstractC254749Yt` to decide whether to apply transparent status bar during swipe. |
| `p002X/AbstractC38450uU.java:60-71` | `A03(context)` | reads `display.getCutout().getSafeInsetTop()` — top safe inset. |

### Search-term coverage matrix

| search term | matches in IG code | notes |
|---|---|---|
| `setDecorFitsSystemWindows` | 6 files (AbstractC106088ked, AbstractC72042Ib, AbstractC24630Vs, AbstractC94188bWl, AbstractC24650Vu, AbstractC104285ijz) — all in `p002X/` helpers | never called by ClipsViewerFragment or InstagramMainActivity directly |
| `enableEdgeToEdge` | 0 in code (4 false positives: R.java, RCZ, C99255ejv, SIW) | IG does NOT use androidx `enableEdgeToEdge` |
| `FLAG_TRANSLUCENT_STATUS` / `FLAG_TRANSLUCENT_NAVIGATION` / `FLAG_LAYOUT_NO_LIMITS` | 0 literal matches | IG uses the int constants `0x04000000` / `0x08000000` directly in `AbstractC72042Ib.A01` (clearFlags 201326592) and `C54511fI.A02` (addFlags 0x08000000) |
| `SYSTEM_UI_FLAG_*` symbolic | 0 literal matches | IG uses raw ints: 1792, 1280, 8192, 16, 4, 256, 2048, 4096 (see `InstagramMainActivity.java:1969`, `AbstractC54451fC.java:140-144`, `AbstractC24660Vv.java:24-28`, `C25070Xk.java:26-71`, `AbstractC106088ked.java:62-67`, `ModalActivity.java:133`) |
| `setSystemUiVisibility` | 32 files; IG-relevant: InstagramMainActivity, IgFragmentActivity (none), ModalActivity, AbstractC54451fC, AbstractC24660Vv, AbstractC24630Vs, AbstractC106088ked, AbstractC72042Ib (via flag manipulation), C37870tY (SwipeNavStatusBarManager), C25070Xk | covered above |
| `WindowInsetsControllerCompat` / `WindowCompat` | 0 | IG uses raw `WindowInsetsController` (Android API 30+) via `window.getInsetsController()` and `decorView.getWindowInsetsController()`. androidx/window/ package is NOT used by IG. |
| `BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE` | 0 literal | IG uses the int `2` directly (`C25070Xk.java:21`, `C25090Xm.java:27`) |
| `statusBarColor` / `navigationBarColor` / `windowBackground` | resolvable in code via theme attr at `IgFragmentActivity.java:915, 1007, 1652` and `C54511fI.java:42` | actual RGB values live in `res/values/styles.xml` (NOT decompiled — `--no-res`) |
| `WindowInsets` / `getSystemWindowInsetTop` / `getInsets` / `systemBars` | only in `C242418ug` (WindowInsetsManager) and `AbstractC38450uU` (cutout reader) | the runtime inset pipeline |
| `setAppearanceLightStatusBars` / `setAppearanceLightNavigationBars` / `setSystemBarsAppearance` | 3 files: C25070Xk (the wrapper), AbstractC106088ked (RN), AbstractC72042Ib (splash) | the modern API 30+ entry points |

---

## Reels/Clips viewer — does it touch the window?

**No.** The ClipsViewerFragment (`p002X/C254289Wz.java`, 113,710 lines, original name
`"ClipsViewerFragment"`) has ZERO direct calls to any window/system-bar/inset API. It
inherits the activity's window state.

What it DOES declare:
- `public final EnumC41080yj A3O;` initialized to `EnumC41080yj.FORCED_DARK_MODE`
  (line 491) and exposed via `getStatusBarType()` (line 45828). This enum value is
  NEVER consumed elsewhere in the codebase (verified by rg on `EnumC41080yj` and
  `getStatusBarType`).
- It implements `InterfaceC27572AHl` (the swipe-nav status bar listener interface
  used by `C37870tY`), so it may receive `FNy(C25870aC)` callbacks during swipe
  transitions — but `C37870tY` is the one manipulating the window, not the fragment.

Same finding for `instagram/features/stories/fragment/ReelViewerFragment.java`
(Stories): zero direct window/inset/system-bar API calls. It also returns
`EnumC41080yj.FORCED_DARK_MODE` from `getStatusBarType()` (line 15750).

This means: **the Reels viewer inherits the MainActivity's window setup**, and the
MainActivity paints the status bar and nav bar BLACK (per `igds_color_primary_background`
and theme `navigationBarColor`). The Reels fragment is laid out INSIDE the activity's
padded content view (paddingTop = statusBarHeight, paddingBottom = navBarHeight), so
the video plays in a rectangle that does NOT touch the system bars — leaving the black
strips visible above and below.

## MainActivity — global or per-screen window setup?

The window setup is **global to the activity**, applied in two lifecycle entry points
(both at `:3256-3261` and the duplicate `:7234-7239`, suggesting one is `onCreate` and
the other is `onResume`/re-attach). There is no per-tab override of the window colors
when the user switches to the Reels tab — only the swipe-transition animator
(`C37870tY`) manipulates the window during the actual gesture, and it restores the
default (black) state after the gesture completes.

Therefore: **a per-Reels-fragment fix is insufficient**. Even if the Reels fragment
tried to override the status bar color, the activity's `WindowInsetsManager` (C6BM)
keeps re-applying the padding and `A1j()` keeps re-painting the status bar color on
every inset change. The fix must run at the activity level (or hook into the activity's
insets listener).

## Status bar icon tint — how does IG set it?

Two paths:

1. **Modern (API 30+)** via `WindowInsetsController.setSystemBarsAppearance`:
   - Bit 8 = `APPEARANCE_LIGHT_STATUS_BARS` (dark icons on light status bar)
   - Bit 16 = `APPEARANCE_LIGHT_NAVIGATION_BARS` (dark icons on light nav bar)
   - Wrapper: `C25090Xm.A01(z)` → `C25070Xk.A04(z)` (sets/clears bit 8) and
     `C25090Xm.A00(z)` → `C25070Xk.A03(z)` (sets/clears bit 16).
   - Called by `AbstractC54451fC.A05(activity, z)` (status bar) and
     `C54511fI.A05(activity, z)` (nav bar).

2. **Legacy (API < 30)** via `setSystemUiVisibility`:
   - Bit 8192 = `SYSTEM_UI_FLAG_LIGHT_STATUS_BAR`
   - Bit 16 = `SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR`
   - Bit 4 = `SYSTEM_UI_FLAG_FULLSCREEN` (used by `C37870tY`)
   - Bit 256 = `SYSTEM_UI_FLAG_LAYOUT_STABLE`
   - Bit 1024 = `SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN`
   - Bit 512 = `SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION`
   - Implemented in `AbstractC25030Xg` subclass inside `C25090Xm` constructor
     (anonymous class `X.0Xh`).

The decision of light vs. dark icons is driven by `C114583tz.A03()` (a dark-mode
detector). When dark mode is on, IG wants LIGHT icons (default = bit cleared). When
light mode is on, IG wants DARK icons (bit set).

For our patch (force white icons over video), we need to call
`AbstractC54451fC.A05(activity, false)` (= clear light-status-bar bit = light icons)
when entering Reels — which is exactly what MainActivity already does in its
transparent branch (line 3259).

---

## Patch implications (where we'd hook to make Reels edge-to-edge + transparent status bar)

To make Reels behave like TikTok (video edge-to-edge behind a transparent status bar
with white floating icons, and the bottom nav floating over the video), the minimal
smali-level patch would target these specific lines:

### (A) Transparent status bar + white icons when Reels is visible

**Target**: `com/instagram/mainactivity/InstagramMainActivity.java:3256` and `:7234`

Currently:
```java
AbstractC54451fC.A03(instagramMainActivity, instagramMainActivity.getColor(AbstractC26520bF.A0O(instagramMainActivity)));
```

We want this branch to ALWAYS take the transparent path (currently only taken when
`B4p(false).A0D` is true). Simplest smali patch: force `c31610jS.A0D` true when the
current top fragment is `ClipsViewerFragment` (or simply always take the
`bds_transparent` branch). The transparent branch is already wired:
```java
AbstractC54451fC.A03(instagramMainActivity, instagramMainActivity.getColor(R.color.bds_transparent));  // line 3258 / 7236
AbstractC54451fC.A05(instagramMainActivity, false);  // line 3259 / 7237 — dark icons (LIGHT icons on dark bg)
```
`AbstractC54451fC.A03(activity, transparent)` calls `A04(activity, 0)` which sets
`window.setStatusBarColor(0)` (transparent) + `addFlags(0x80000000)`.

### (B) Stop the activity from pushing the content view down by status-bar height

**Target**: `com/instagram/base/activity/IgFragmentActivity.java:735`

Currently:
```java
C242418ug.A05(this, new C6BM(this, 0), false);
```
This registers `C6BM(this, 0)` whose `Fji(top, bottom)` does
`C192756wm.A0w(contentChild, top, bottom)` = `setPadding(left, top, right, bottom)`.

When Reels is the top fragment, we want top padding = 0 (video plays under status bar)
and bottom padding = 0 (video plays under nav bar; bottom nav floats).

Options (any of these works; pick least invasive at smali time):
1. **Make `C6BM.Fji` case 0 skip the padding when the top fragment is ClipsViewerFragment.**
   Modify `p002X/C6BM.java:34-49` to check `((IgFragmentActivity)this.A00).A1g()`
   (returns the current top fragment) — if instanceof `C254289Wz`, return early without
   calling `C192756wm.A0w` or `A1j()`.
2. **Make `C192756wm.A0w` a no-op when Reels is on top** — riskier (called elsewhere).
3. **Override `getViewsToInset()` in ClipsViewerFragment** — already returns
   `Collections.singletonList(this.mView)` by default; doesn't help with the activity's
   content padding. The activity-level padding is the issue, not the fragment's own
   inset.
4. **Re-paint the decorView background to transparent** by neutralizing
   `IgFragmentActivity.A1j()` (`com/instagram/base/activity/IgFragmentActivity.java:718-728`)
   so the area behind the status bar is not pre-painted BLACK. Currently
   `A1j()` calls `AbstractC27310cW.A0R(getWindow().getDecorView(), color, 1338506672)`
   which is `decorView.setBackgroundColor(igds_color_primary_background)`. Setting this
   to transparent (0) when Reels is on top lets the video show through.

The cleanest hook is option (1) at `p002X/C6BM.java:34` (case 0 of `Fji`).

### (C) Make the bottom nav FLOAT over the video

The bottom nav is hosted in `com/instagram/mainactivity/maintab/` (per worklog).
The C6BM padding pushes the activity content up by `navBarHeight`. To float the bottom
nav, the nav bar background must be transparent and the bottom nav must overlay the
content with its own bottom padding = navBarHeight (so its icons aren't covered by the
gesture area).

**Targets**:
- `com/instagram/mainactivity/InstagramMainActivity.java:3261` and `:7239`:
  `C54511fI.A01(this)` → calls `C54511fI.A04(this, navigationBarColor)` →
  `window.setNavigationBarColor(BLACK)`. Replace with `C54511fI.A02(this)` (which
  calls `window.addFlags(0x08000000 | 0x80000000)` = translucent nav bar) when Reels
  is on top. (See `p002X/C54511fI.java:49-56`.)
- The bottom-nav container itself (in `com/instagram/mainactivity/maintab/` — covered
  by another agent's task) needs to be elevated above the video and given transparent
  background.

### (D) Optional: enable true `setDecorFitsSystemWindows(false)` for edge-to-edge

For full Android-15 compliance / proper edge-to-edge behavior on API 30+, also call
`AbstractC24660Vv.A00(window, false)` (which delegates to `setDecorFitsSystemWindows(false)`
+ `setSystemUiVisibility` LAYOUT_STABLE). The helper already exists at
`p002X/AbstractC24660Vv.java:12`. Currently NOT called by MainActivity; only by
`AbstractC106088ked.A00` (React Native) and `SJ6.A00` (React Native modal).

Could be inserted at `InstagramMainActivity.java:1969` (replacing the
`setSystemUiVisibility(1792)` call) and similarly at `:2290, :2738, :3069`.

### (E) Status bar icon tint when over video

`AbstractC54451fC.A05(activity, false)` (already called at line 3259/7237 in the
transparent branch) is what we want — `false` means "don't set light status bar" →
default light/white icons over the dark video. No additional change needed IF we
force the transparent branch.

For finer per-video-frame control (e.g., switching to dark icons when the video frame
behind the status bar is bright), we'd need a new hook — but TikTok's behavior is
"always white floating icons", so `A05(activity, false)` is sufficient.

---

## Summary of patch anchor points

| concern | file | line | current | desired |
|---|---|---|---|---|
| Status bar color (black → transparent) | `com/instagram/mainactivity/InstagramMainActivity.java` | 3256, 7234 | `AbstractC54451fC.A03(this, igds_color_primary_background)` | take the `bds_transparent` branch (lines 3258/7236) |
| Status bar icon tint | `com/instagram/mainactivity/InstagramMainActivity.java` | 3259, 7237 | `AbstractC54451fC.A05(this, false)` | OK as-is (white icons) |
| DecorView pre-paint (black → transparent) | `com/instagram/base/activity/IgFragmentActivity.java` | 727 (`A1j` body) | `decorView.setBackgroundColor(igds_color_primary_background)` | skip when Reels on top, or set to transparent |
| Content-view padding (status bar inset) | `p002X/C6BM.java` | 34-49 (`Fji` case 0) | `setPadding(left, top, right, bottom)` always | skip when Reels on top |
| Nav bar color (black → transparent) | `com/instagram/mainactivity/InstagramMainActivity.java` | 3261, 7239 | `C54511fI.A01(this)` (sets BLACK) | replace with `C54511fI.A02(this)` (translucent) when Reels on top |
| Bottom nav container background/elevation | `com/instagram/mainactivity/maintab/*` | TBD (other agent) | solid black bar | transparent + floating overlay |
| Optional: true edge-to-edge on API 30+ | `com/instagram/mainactivity/InstagramMainActivity.java` | 1969, 2290, 2738, 3069 | `setSystemUiVisibility(1792)` | replace with `AbstractC24660Vv.A00(window, false)` |

### "Is Reels on top?" detection

Use `IgFragmentActivity.A1g()` (`com/instagram/base/activity/IgFragmentActivity.java:685-687`)
which returns `A1a().A0O(R.id.layout_container_main)` (the current top fragment). Compare
its class against `p002X/C254289Wz` (the obfuscated `ClipsViewerFragment`).

Alternative: check `__redex_internal_original_name` field on the fragment instance —
but the class identity check is cleaner at smali level.

### res/ dependencies (NOT in this decompile)

- `R.attr.igds_color_primary_background` (BLACK in dark theme) — need to confirm via
  `res/values/colors.xml` + `res/values/themes.xml` after running apktool.
- `R.attr.navigationBarColor` — same.
- `R.color.bds_transparent` — should be 0x00000000.
- `R.color.bds_black` — 0xFF000000.
- Theme `android:windowBackground` / `android:statusBarColor` /
  `android:navigationBarColor` / `android:windowLightStatusBar` /
  `android:enforceNavigationBarContrast` — all referenced via `getTheme().resolveAttribute`
  in IG code; final values live in `res/`.
