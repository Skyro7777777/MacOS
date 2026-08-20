# Task 3-a — Reels viewer surface + video player (READ-ONLY exploration)

Scope: the swipeable Reels feed (bottom-nav "Reels" tab), the view that
renders the reel video, how that view is sized, the system-bar / inset
handling that produces the visible black strips, and the bottom-nav bar
that sits under the feed.

All file paths are relative to `/home/z/insta-src/jadx-out/sources/`
unless otherwise noted. Line numbers are 1-based as printed by the
`Read` tool (which is `cat -n` style).

---

## 1. Reels tab → fragment factory chain

The bottom-nav "Reels" tab is one of the entries in `EnumC108993ky`:

- `p002X/EnumC108993ky.java:83`
  ```
  A08 = new EnumC108993ky("CLIPS", "fragment_clips", ...,
                           "clips_viewer_clips_tab", 6, R.id.clips_tab, ...);
  ```
  So the tab's "fragment tag" string is **`"fragment_clips"`** and the
  analytics module name is `"clips_viewer_clips_tab"`.

The main activity hosts a `ViewPager2` (`p002X/C0ZS` / `c0zs.A00`) whose
adapter is `C39060vT`. Each page is wrapped in an
`IgSwipeableTabHostFragment` (`p002X/C37670tE.java`,
`__redex_internal_original_name = "IgSwipeableTabHostFragment"`). When a
page becomes visible, `C37670tE.A01(...)` looks up the tag string and
delegates to **`IgTabHostFragmentFactory`**:

- `p002X/C55071gC.java:47` — for `"fragment_clips"` it calls
  `AbstractC80182fb.A0E(userSession)` to create the actual fragment.

`AbstractC80182fb.A0E(...)` at `p002X/AbstractC80182fb.java:771-797`
selects between **three** fragment classes for the Reels tab:

```java
771: public static AbstractC91822yN A0E(UserSession userSession) {
...
778:     ClipsViewerSource clipsViewerSourceA02 = (...) ? ClipsViewerSource.A0L : ClipsViewerSource.A02(userSession);
...
790:     if (zA01) {
791:         c27528AFt = new C177006Tt();              // homecoming variant
792:     } else {
793:         c27528AFt = C38420uR.A03(userSession) ? new C27528AFt() : c254089Wf.A07(bundle, userSession);
794:     }
```

- `zA01 = C91332xa.A01(userSession)` is the "homecoming feed" gate. When
  true → `C177006Tt`, whose `__redex_internal_original_name` is
  `"HomeTabFragment"` (`p002X/C177006Tt.java:8`) — NOT the reels
  viewer; this is the new home/test surface. Out of scope.
- `C38420uR.A03(userSession)` at `p002X/C38420uR.java:28-31`:
  ```java
  return !C91332xa.A01(userSession) && ((MobileConfigUnsafeContext)...).BHQ(36321232755571055L);
  ```
  When this MobileConfig flag is on (the typical production case) →
  **`C27528AFt` = `ClipsTabFragment`** (modern host).
- Otherwise → `C254089Wf.A07(bundle, userSession)` at
  `p002X/C254089Wf.java:76-97`, which itself picks between
  `C27528AFt` (`ClipsTabFragment`) and `C254289Wz` (`ClipsViewerFragment`)
  based on a parent-tab check (`C260299iQ.A00.A02(...)`).

### Verdict
On v435.0.0.37.76 the bottom-nav Reels tab uses
**`ClipsTabFragment` (`p002X/C27528AFt`)** as the outer host. Each of
its sub-tabs (e.g. "For You" / "Following") is a
**`ClipsViewerFragment` (`p002X/C254289Wz`)** — the legacy single-feed
fragment (113,710 lines). The sub-tab adapter is
`C28800Am1` (`p002X/C28800Am1.java:36-87`, `A00(...)` calls
`C254089Wf.A00.A07(bundle, userSession)`).

> **What this means for the patch:** the patch only needs to touch
> `ClipsTabFragment` and `ClipsViewerFragment` (both obfuscated as
> `C27528AFt` and `C254289Wz`). The "fragment_clips" tag in
> `EnumC108993ky` and the `IgTabHostFragmentFactory` switch at
> `C55071gC.A00(...)` do not need changes.

---

## 2. ClipsTabFragment (`C27528AFt`) — outer host

File: `p002X/C27528AFt.java`
Original name: `ClipsTabFragment` (line 31)

Key lifecycle / view setup:

- `onCreateView` — `p002X/C27528AFt.java:806-820`
  ```java
  811: View viewInflate = layoutInflater.inflate(R.layout.layout_clips_tab_fragment, viewGroup, false);
  ```
  Layout resource: **`R.layout.layout_clips_tab_fragment`**
  (`com/instagram/android/R.java:37925` → `0x7f0e0a39`).

- `onViewCreated` — `p002X/C27528AFt.java:897-1019`
  ```java
  927: this.A05 = new C28800Am1(childFragmentManager, lifecycle, clipsViewerConfig, userSession3, c266549sV, str, list2);
  ...
  939: viewPager2 = (ViewPager2) view.findViewById(R.id.clips_tab_view_pager);
  940: viewPager2.setAdapter(this.A05);
  941: viewPager2.setUserInputEnabled(false);   // inner sub-tab swipe DISABLED here
  ...
  945:     viewPager2.setOffscreenPageLimit(1);
  947: this.A00 = viewPager2;
  ```
  The outer pager is **`R.id.clips_tab_view_pager`**
  (`com/instagram/android/R.java:20356` → `0x7f0b0c49`).
  `setUserInputEnabled(false)` means the outer pager does NOT scroll —
  sub-tab switching is driven programmatically (by `C28825AmQ`
  tabController) and the actual vertical swipe happens inside the
  `ClipsViewerFragment`.

- `onResume` — `p002X/C27528AFt.java:855-867`
  ```java
  859: super.onResume();
  860: C2ZS.A02(requireActivity(), this, (UserSession) this.A0A.getValue(), true, false);
  ```
  This `C2ZS.A02(...)` call is the single entry point that paints the
  system bars / window chrome for the Reels tab. See §5.

- `onStop` — `p002X/C27528AFt.java:870-881`
  ```java
  875: C2ZS.A00.A0B(requireActivity(), this, (UserSession) this.A0A.getValue(), true, false);
  ```
  Restores the "normal" (non-clips) chrome when leaving the tab.

> **What this means for the patch:** the entry point for changing the
> Reels tab's window chrome is `C2ZS.A02(...)` in `onResume` (line 860)
> and `C2ZS.A00.A0B(...)` in `onStop` (line 875). The layout XML
> `layout_clips_tab_fragment` is not in this jadx dump (jadx was run
> with `--no-res`); for any XML-level change (e.g. fitsSystemWindows)
> we will need to decompile `resources/` via apktool.

---

## 3. ClipsViewerFragment (`C254289Wz`) — the actual reel feed

File: `p002X/C254289Wz.java` (113,710 lines — jadx struggled)
Original name: `ClipsViewerFragment` (line 130).

### 3a. onCreateView

`p002X/C254289Wz.java:49371-49415`:
```java
49371: public final View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
...
49386: int i = R.layout.layout_clips_viewer_fragment;
49387: if (zA0H) {
49388:     i = R.layout.layout_clips_viewer_fragment_two_pane_comments;
49389: }
49390: View viewA00 = C31620jT.A00(layoutInflater, viewGroup, i, 0, false, false);
49391: C255769b7 c255769b7 = (C255769b7) this.A3B.getValue();
49392: if (c255769b7.A05()) {
49393:     View viewFindViewById = viewA00.findViewById(R.id.root_clips_layout);
49394:     int iA00 = C114583tz.A03() ? c255769b7.A00() : c255769b7.A01();
49395:     if (viewFindViewById != null) {
49396:         AbstractC27310cW.A0R(viewFindViewById, iA00, 1931589072);  // setBackgroundColor
49397:     }
49398: }
```
Layout: **`R.layout.layout_clips_viewer_fragment`** (or its two-pane
comments variant). Resource IDs found in code that are inside this
layout:

| R.id                              | hex         | R.java line |
|-----------------------------------|-------------|-------------|
| `root_clips_layout`               | `0x7f0b35ae`| 30815       |
| `clips_linear_layout_container`   | `0x7f0b0bbd`| 20217       |
| `clips_navigation_bar_container`  | `0x7f0b0bc6`| 20226       | (ViewStub)
| `clips_top_of_feed_container`     | `0x7f0b0c5b`| 20374       | (ViewStub)
| `clips_stories_tray_container`    | `0x7f0b0c43`| 20350       |
| `clips_ptr_spinner_overlay_stub`  | (ViewStub)  | used at 42309 |
| `clips_viewer_action_bar`         | `0x7f0b0c6b`| 20390       |
| `clips_bottom_sheet_container_stub`| `0x7f0b0b43`| 20095      | (ViewStub, comment sheet)
| `clips_autoscroll_recently_viewed_button_stub` | (ViewStub) | used at 49402 |

The `root_clips_layout` view is what gets its background repainted
through the `c255769b7` color source (line 49394-49396). This is one of
the color sources for the "black background" seen behind the video.

### 3b. onViewCreated — **NOT DECOMPILABLE**

`p002X/C254289Wz.java:113683-113708`:
```java
113683: public final void onViewCreated(final android.view.View r83, android.os.Bundle r84) {
113684:     /*  JADX ERROR: JadxOverflowException in pass: RegionMakerVisitor
...
113704:     Method dump skipped, instruction units count: 8845
113707: throw new UnsupportedOperationException("Method not decompiled: ...C254289Wz.onViewCreated(...):void");
```
The 8,845-instruction `onViewCreated` could not be decompiled. This is
where the inner `ViewPager2`/`RecyclerView` (the actual vertical reel
feed) is wired up. The local variable names in the surrounding
`onDestroyView` (lines 49955-49995 — `RecyclerView recyclerViewA01`,
`ViewPager2 viewPager3`, `viewPager4`, `recyclerViewA02`, `recyclerViewA03`)
prove that BOTH a `ViewPager2` AND several `RecyclerView` instances are
created here, but their `findViewById` calls are inside the un-decompiled
block. We do NOT have the inner pager's `R.id.*` from this file.

### 3c. Evidence the inner feed is a ViewPager2 / RecyclerView

`p002X/C254289Wz.java:42-43`:
```
import androidx.recyclerview.widget.RecyclerView;
import androidx.viewpager2.widget.ViewPager2;
```
And `onDestroyView` references (lines 49955-50000+):
`ViewPager2 viewPager2; ... ViewPager2 viewPager3; RecyclerView recyclerViewA01;
ViewPager2 viewPager4; RecyclerView recyclerViewA02; RecyclerView recyclerViewA03;`
plus ~22 occurrences of `viewPager2.setAdapter(null);` (the cleanup at
the end of `onDestroyView`).

### 3d. The "ClipsViewerRecyclerAdapter"

The inner adapter / data source is `ACN`
(`p002X/ACN.java`):
- `__redex_internal_original_name` is not set, but its Systrace tags
  are `"ClipsViewerAdapter.onItemChangedInternal"` (line 306),
  `"ClipsViewerAdapter.addClipsItems"` (line 799),
  `"ClipsViewerAdapter.prewarmSponsoredItem"` (line 1059), and it
  implements `InterfaceC31369BmM`, `InterfaceC51465Jhk`, `WMX` — i.e.
  a Litho `SectionTree` data source, not a `RecyclerView.Adapter`.
- Confirms **the per-reel UI is rendered via Litho** (see also
  `import com.facebook.litho.LithoView;` at `C254289Wz.java:45`).

> **What this means for the patch:** because the actual feed UI is
> Litho-driven and `onViewCreated` is un-decompiled, we should patch
> the window-chrome / inset behavior in `ClipsTabFragment` (which is
> fully decompiled) rather than try to edit `ClipsViewerFragment`'s
> `onViewCreated`. The container view we care about for "video fills
> the screen" is `R.id.root_clips_layout` (repainted at line 49396).

---

## 4. The video view — `C3EO` (=`VideoFrameLayout` wrapper) + `SimpleVideoLayout`

The actual view that renders a reel video is **`C3EO`**.

File: `p002X/C3EO.java` (73 lines, fully decompiled)
```java
15: public final class C3EO extends AbstractC210917ky {
16:     public SimpleVideoLayout A00;
17:     public final IgImageView A01;     // cover/placeholder image
18:     public final IgImageView A02;     // mute-or-pause icon
...
21:     public C3EO(Context context, UserSession userSession) {
...
27:         this.A00 = new SimpleVideoLayout(context, null, 0);
...
32:         this.A00.setId(R.id.clips_video_container);
33:         setId(R.id.clips_viewer_video_layout);
34:         FrameLayout.LayoutParams layoutParams = new FrameLayout.LayoutParams(-1, -1);   // MATCH_PARENT × MATCH_PARENT
35:         layoutParams.gravity = 17;     // Gravity.CENTER
36:         this.A01.setLayoutParams(layoutParams);
37:         this.A00.setLayoutParams(layoutParams);
38:         if (...BHQ(36317663636234538L) || C0X1.A01(userSession)) {
39:             addView(this.A00);
40:             view = igImageView;
41:         } else {
42:             addView(igImageView);
43:             view = this.A00;
44:         }
45:         addView(view);
46:         addView(igImageView2);
47:     }
```
Layout params are `(-1, -1)` (MATCH_PARENT × MATCH_PARENT) with
`Gravity.CENTER` — so **the video view itself wants to fill its
parent**. If the video doesn't fill the screen, the cause is NOT the
video view's own layout params; it is the parent's bounds (see §5 and
§6) and the TextureView's matrix scaling inside `AbstractC210917ky`.

### 4a. C3EO is created by Litho

`p002X/C3BT.java:63`:
```java
return new C3EO(context, this.A00.A01);
```
`C3BT extends AbstractC76222Yd` — a Litho component binder.

### 4b. AbstractC210917ky = `VideoFrameLayout` (the actual video surface owner)

File: `p002X/AbstractC210917ky.java` (252 lines)
- `__redex_internal_original_name` not set, but Systrace tag at
  line 37: `"VideoFrameLayout.setVideoSource"`.
- extends `FrameLayout` (line 16)
- holds a `TextureView A02` (line 21), captured automatically when a
  child `TextureView` is added (`addView(...)` at lines 97-107).
- `setVideoSource(...)` at line 30 (the main entry point for loading a
  reel's video into the surface).
- `setForceFillTextureScaling(boolean z)` at line 77-79:
  ```java
  77: public final void setForceFillTextureScaling(boolean z) {
  78:     this.A01 = z ? 1.0d : this.A00;
  79: }
  ```
  The `A01` field is the "fill ratio" used by `onSizeChanged`. Default
  value of `A00` (the "fit" ratio) is `0.25d` (lines 85, 218, 242). So
  by default `A01 = 0.25d` (NOT 1.0d) — meaning **the default is FIT
  mode, not FILL**.

### 4c. Aspect-ratio / scaling computation

`AbstractC210917ky.onSizeChanged(...)` at lines 146-212:
```java
152: if (... && (textureView = this.A02) != null) {
153:     boolean z = this.A06;     // (from BHQ 36328783306316227L) "use A02() aspect"
...
157:     dA03 = c160765mH.A02();    // video's aspect ratio (width/height)
...
166: final C2474796u c2474796uA00 = C25U.A00(
167:     C25U.A01(f, i3, i4, textureView.getWidth(), textureView.getHeight()),
168:     f, (float) this.A01,    // <-- uses A01 (the fill ratio) here
169:     i, i2);
170: final FrameLayout.LayoutParams layoutParams =
171:     new FrameLayout.LayoutParams(((Number) c2474796uA00.A00).intValue(),
172:                                  ((Number) c2474796uA00.A02).intValue());
...
172 (runnable): textureView2.setLayoutParams(layoutParams);
```
The matrix builder is `C25U.A00(...)`:
```java
11: public static final C2474796u A00(Integer num, float f, float f2, int i, int i2) {
...
29:     if (num == AnonymousClass006.A01 || num == AnonymousClass006.A0C) {
30:         if (f > f5) {                 // video wider than container
31:             iA02 = C107593ii.A01(f4 * f);   // height = containerW / aspect (FIT height)
32:             iA01 = i2;
33:         } else {                       // video taller than container
34:             iA01 = C107593ii.A01(f3 / f);   // width = containerH * aspect (FIT width)
35:             iA02 = i;
36:         }
37:         float f6 = (iA01 - i2) / iA01;
38:         if ((iA02 - i) / iA02 > f2 || f6 > f2) {   // overflow > fillRatio → switch to ZOOM
39:             z = true;
40:         }
...
45:     if (num == AnonymousClass006.A00 || z) {       // ZOOM mode
46:         if (f > f5) { iA01 = ...; iA02 = i; }      // height fills, width cropped
47:         else { iA02 = ...; iA01 = i2; }            // width fills, height cropped
48:     }
49: }
```
`num` is an `Integer` mode token from `AnonymousClass006.A00/A01/A0C`
(likely ZOOM / FIT / FIXED). `f2` is `(float) this.A01` — the fill ratio
(0.25 by default, 1.0 when `setForceFillTextureScaling(true)`).

**So: in FIT mode (`A01 = 0.25d`), if the video aspect ratio differs
from the container by more than 25%, IG switches to ZOOM. With
`setForceFillTextureScaling(true)` (`A01 = 1.0d`), IG never zooms — it
always letterboxes (FIT).**

Note: `setForceFillTextureScaling` is currently called only from
`p002X/C8NA.java:187` (`mediaFrameLayout.setForceFillTextureScaling(z5)`)
which is the **feed** video binder (`C8NA`), NOT the clips viewer. The
clips viewer path leaves `A01 = 0.25d`, i.e. the default
"FIT-but-switch-to-ZOOM-if-overflow>25%" behavior.

### 4d. SimpleVideoLayout

File: `com/instagram/p132ui/simplevideolayout/SimpleVideoLayout.java`
- Just `extends AbstractC210917ky implements InterfaceC36365Dkk, CAJ`.
- Adds `setEnforceTextureView(boolean)` / `getEnforceTextureView()` so
  the ClipsViewerFragment can force a `TextureView` (vs `SurfaceView`).
- All actual video rendering is in the parent (`AbstractC210917ky`).

### 4e. FB media3 PlayerView & AspectRatioFrameLayout — NOT used by clips viewer

For reference (the project's task description mentioned ExoPlayer):

- `p146fb/androidx/media3/p147ui/PlayerView.java` — `setResizeMode(int)`
  at line 4623. Internally calls `aspectRatioFrameLayout.setResizeMode(i)`.
- `p146fb/androidx/media3/p147ui/AspectRatioFrameLayout.java` —
  `setResizeMode(int)` at line 86; `onMeasure` (lines 30-73) supports
  modes 0 (FIT, default), 1 (FIXED_WIDTH), 2 (FIXED_HEIGHT), 4 (ZOOM).
- A repo-wide search for `setResizeMode|RESIZE_MODE_FIT|RESIZE_MODE_FILL`
  returns only **10** files, none of which are in the clips viewer
  package. The clips viewer does **not** use media3 `PlayerView` at all;
  it uses IG's own `VideoFrameLayout` (`AbstractC210917ky`) +
  `TextureView` and computes layout manually via `C25U`.

> **What this means for the patch:** to make 16:9 horizontal reels
> fill the screen TikTok-style (goal D), we have two possible hooks:
>
> 1. Force `setForceFillTextureScaling(true)` (i.e. set `A01 = 1.0d`)
>    from the clips viewer — but that produces FIT (letterbox), the
>    OPPOSITE of fill. So this is the wrong knob.
> 2. Override `C25U.A00(...)` to always use ZOOM mode (set `num` to
>    `AnonymousClass006.A00`) for clips — this would crop-and-fill.
> 3. The TikTok behavior the mission wants is actually the opposite:
>    for 16:9 videos, **rotate to landscape + show a seekbar**, NOT
>    crop-and-fill. That requires `Activity.setRequestedOrientation`
>    + a seekbar UI. Note: **neither `ClipsTabFragment` nor
>    `ClipsViewerFragment` ever calls `setRequestedOrientation`**
>    (confirmed via grep — no matches for
>    `setRequestedOrientation|requestedOrientation|SCREEN_ORIENTATION`).
>    So landscape rotation must be ADDED by the patch.

---

## 5. Window chrome / system-bar controller — `C2ZS` (root cause of black strips)

File: `p002X/C2ZS.java` (284 lines)

Called from `ClipsTabFragment.onResume` (line 860):
```java
C2ZS.A02(requireActivity(), this, (UserSession) this.A0A.getValue(), true, false);
```
Which delegates to `C2ZS.A01(activity, fragment, userSession,
igds_color_clips_tab_bar_icon, z=true, z2=false, z3=false)` at line
108-111. The full body of `A01` (lines 36-105) is the master switch for
the Reels screen chrome:

```java
40: int iA0W = AbstractC26520bF.A0W(C26560bJ.A01(activity), R.attr.igds_color_primary_background);
41: if (z) {       // z=true (called from onResume with z=true)
42:     C26630bQ.A04(activity, userSession,
43:         AbstractC26520bF.A0Z(activity, R.attr.igds_color_clips_tab_bar_background),
44:         AbstractC26520bF.A0Z(activity, R.attr.igds_color_reels_tab_bar_separator));
45:     C26630bQ c26630bQ = C26630bQ.A00;
46:     c26630bQ.A09(activity, i);
47:     c26630bQ.A0A(activity, userSession, i);
48: }
...
66: Window window = parent.getWindow();
70: window.addFlags(Integer.MIN_VALUE);                      // FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS
72: window.setNavigationBarColor(iA0W);                      // nav bar = primary background
...
85: if (A08(activity)) {                                     // true if no swipe_navigation_container
86:     AbstractC27310cW.A0R(decorView, iA0W, -154045110);   // decorView.setBackgroundColor(primary_bg)
87:     A05(activity, userSession, iA0W);                     // see line 126-132
88:     if (C64121un.A00) { A00(activity, iA0W); }            // large-screen only
89: } else {
90:     A00(activity, iA0W);
91: }
...
94: if (z2) {                                                // z2=false here, so SKIPPED
95:     AbstractC54451fC.A06(decorView, window2, false);      // (would make status bar OPAQUE)
96:     return;
97: }
98: if (!AbstractC54451fC.A09(decorView, window2)) {          // if status bar currently opaque
99:     AbstractC54451fC.A06(decorView, window2, true);       //   make it transparent (LAYOUT_FULLSCREEN)
100: }
101: if (!z3) {                                              // z3=false here, so EXECUTED
102:     AbstractC54451fC.A04(activity, iA0W);                // ** sets status bar COLOR = primary_bg **
103: }
104: AbstractC54451fC.A05(activity, false);                   // icon-color helper
```

### What `A05(activity, userSession, iA0W)` does
`p002X/C2ZS.java:126-132`:
```java
126: public static final void A05(Activity activity, UserSession userSession, int i) {
127:     View viewFindViewById;
128:     if (!C102743at.A0I(userSession) || (viewFindViewById = activity.findViewById(android.R.id.content)) == null) {
129:         return;
130:     }
131:     AbstractC27310cW.A0R(viewFindViewById, i, -2146982397);   // content.setBackgroundColor(primary_bg)
132: }
```
Sets `android.R.id.content` background to `igds_color_primary_background`
(typically opaque black on dark theme).

### Key observation — the bug pattern
Line 99 makes the status bar transparent (sets
`SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN` so content draws under it), BUT
line 102 then sets `setStatusBarColor(igds_color_primary_background)`
which is an **opaque** color. With `FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS`
already set (line 70), the system paints the status-bar area with that
opaque color, producing the visible "black strip" above the video.

### `AbstractC54451fC` — the status-bar color helper
File: `p002X/AbstractC54451fC.java` (167 lines)

Public API (all static):
- `A02(activity)` line 65-67: sets status bar color to
  `bds_transparent` (color = 0). Use this to make the bar fully
  transparent.
- `A04(activity, int i)` line 82-116: sets status bar color to `i`
  (adds `FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS`, may defer via
  `WindowChromeColorDeferer`).
- `A05(activity, boolean z)` line 119-133: sets `windowLightStatusBar`
  (icon brightness). Wraps `C25090Xm` = `WindowInsetsControllerCompat`.
- `A06(view, window, boolean z)` line 136-147:
  - `z=true` → `view.setSystemUiVisibility(... | 256)` and
    `window.clearFlags(1024)`. `256 = SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN`,
    `1024 = FLAG_FORCE_NOT_FULLSCREEN`. So `z=true` = content extends
    under status bar + transparent bar.
  - `z=false` → `view.setSystemUiVisibility(... | 4)` and
    `window.setFlags(1024, 1024)`. `4 = SYSTEM_UI_FLAG_FULLSCREEN`-
    adjacent; this restores the "below status bar" layout.
- `A07(window, boolean z)` line 149-154: calls
  `decorView.requestApplyInsets()`.
- `A09(view, window)` line 164-166: returns true if the status bar is
  currently in transparent/layout-fullscreen mode.

### `C54511fI` — the navigation-bar color helper
File: `p002X/C54511fI.java` (201 lines)
- `A04(activity, int i)` line 77-121: sets **navigation bar** color to
  `i` (with contrast enforcement via `A06`).
- `A05(activity, boolean z)` line 124-138: sets
  `windowLightNavigationBar`.
- `A06(activity, boolean z, int i)` line 141-160:
  `setNavigationBarContrastEnforced`.

### `AbstractC27310cW.A0R` — `setBackgroundColor`
File: `p002X/AbstractC27310cW.java:147-150`:
```java
147: public static void A0R(View view, int i, int i2) {
148:     A0d(view, "setBackgroundColor", i2);
149:     view.setBackgroundColor(i);
150: }
```

> **What this means for the patch (goal A — video behind status bar):**
> The single root cause is `C2ZS.A01` calling
> `AbstractC54451fC.A04(activity, iA0W)` at line 102 with
> `iA0W = igds_color_primary_background` (opaque). The minimal patch is
> to either:
> - Replace the `iA0W` argument at line 102 with the transparent color
>   (`AbstractC54451fC.A02(activity)` instead of `A04(activity, iA0W)`),
>   OR
> - Skip line 102 entirely when entering the Reels tab (so the
>   transparent status bar set at line 99 stays transparent), AND
> - Also drop the `decorView.setBackgroundColor(iA0W)` at line 86 and
>   the `content.setBackgroundColor(iA0W)` at line 131 so the video
>   actually shows through the previously-black area.
>
> All changes are inside `C2ZS.A01` (one method, one file). No XML /
> resource decompilation needed for this part.

---

## 6. Bottom navigation bar — `C26630bQ` (root cause of bottom black strip)

File: `p002X/C26630bQ.java` (223 lines)

Called from `InstagramMainActivity.onConfigurationChanged` at
`com/instagram/mainactivity/InstagramMainActivity.java:4112`:
```java
C26630bQ.A04(this, userSession2,
    AbstractC26520bF.A0Z(this, R.attr.igds_color_clips_tab_bar_background),
    AbstractC26520bF.A0Z(this, R.attr.igds_color_reels_tab_bar_separator));
```

`C26630bQ.A04` body at lines 120-138:
```java
120: public static final void A04(Activity activity, UserSession userSession, int i, int i2) {
121:     View viewFindViewById = activity.findViewById(R.id.tab_bar);
122:     View viewFindViewById2 = activity.findViewById(R.id.ls_nav_bar);
123:     if (viewFindViewById != null) {
124:         AbstractC27310cW.A0R(viewFindViewById, activity.getColor(i), -1293857592);  // tab_bar.setBackgroundColor(clips_tab_bar_bg)
125:     }
126:     if (viewFindViewById2 != null) {
127:         AbstractC27310cW.A0R(viewFindViewById2, activity.getColor(i), 829964805);   // ls_nav_bar.setBackgroundColor(clips_tab_bar_bg)
128:     }
129:     View viewFindViewById3 = activity.findViewById(R.id.tab_bar_shadow);
130:     View viewFindViewById4 = activity.findViewById(R.id.ls_nav_bar_shadow);
131:     if (viewFindViewById3 != null) {
132:         AbstractC27310cW.A0R(viewFindViewById3, activity.getColor(i2), -502183527);
133:     }
...
137:     AbstractC27310cW.A0R(viewFindViewById4, activity.getColor(i2), 1118723360);
138: }
```

Also called from `C2ZS.A01` at line 42-44 (every time the Reels tab
becomes visible). So:
- `R.id.tab_bar` (and `R.id.ls_nav_bar`) gets
  `R.attr.igds_color_clips_tab_bar_background` — an **opaque** color,
  typically black on dark theme. This is the bottom black strip.
- `R.id.tab_bar_shadow` (and `R.id.ls_nav_bar_shadow`) gets
  `R.attr.igds_color_reels_tab_bar_separator`.

The relevant resource IDs (from `com/instagram/android/R.java`):
```
26490:  public static final int ls_nav_bar = 0x7f0b248e;
33280:  public static final int tab_bar = 0x7f0b3f67;
```
plus `tab_bar_shadow` and `ls_nav_bar_shadow` (not shown but referenced).

> **What this means for the patch (goal B — floating bottom nav):**
> The minimal patch is to override `C26630bQ.A04` so that on the Reels
> tab, `tab_bar` / `ls_nav_bar` get `Color.TRANSPARENT` (or
> `bds_transparent`) instead of `igds_color_clips_tab_bar_background`.
> That alone makes the bar visually float over the video (the bar's
> child icons already are independent drawables). If we also want the
> video to extend UNDER the nav bar, we need to additionally:
> - Disable `setDecorFitsSystemWindows(true)` (or call
>   `WindowCompat.setDecorFitsSystemWindows(window, false)` so content
>   extends under the nav bar.
> - Currently `C2ZS.A01` calls `window.setNavigationBarColor(iA0W)` at
>   line 72 (opaque). For full transparency we'd change that to
>   `C54511fI.A04(activity, transparentColor)` and
>   `C54511fI.A06(activity, false, transparentColor)` to disable
>   contrast enforcement.

---

## 7. Comment sheet — `IgBottomSheetNavigator` + `BottomSheetFragment`

### 7a. Navigator

`ClipsViewerFragment` lazily creates its comment-sheet navigator at
`p002X/C254289Wz.java:540-570`:
```java
548: View viewRequireView = c254289Wz.requireView();
553: ViewStub viewStub = (ViewStub) viewRequireView.findViewById(R.id.clips_bottom_sheet_container_stub);
...
562: viewFindViewById = viewStub.inflate();
563: View viewFindViewById2 = viewFindViewById.findViewById(R.id.layout_container_bottom_sheet);
564: if (viewFindViewById2 != null) {
565:     viewFindViewById2.setId(R.id.clips_bottom_sheet_fragment_transaction_view);
566: }
567: c109193lI = new C109193lI(fragmentActivityRequireActivity, viewFindViewById, childFragmentManager, userSessionA1x, C00B.A00(2973), R.id.clips_bottom_sheet_fragment_transaction_view, false);
```
- `C109193lI` = `IgBottomSheetNavigator` (extends
  `AbstractC109183lH`; see `p002X/C109193lI.java:48`). It hosts an
  `com.instagram.igds.components.bottomsheet.BottomSheetFragment`.
- Stub container: `R.id.clips_bottom_sheet_container_stub` (`0x7f0b0b43`).
- Inflated container: `R.id.layout_container_bottom_sheet` (`0x7f0b2242`),
  re-id'd to `R.id.clips_bottom_sheet_fragment_transaction_view`.

### 7b. BottomSheetFragment

File: `com/instagram/igds/components/bottomsheet/BottomSheetFragment.java`
- `onCreateView` line 2392-2402: inflates
  `R.layout.bottom_sheet_fragment`.
- `onResume` line 2453-2471 — the critical lines for "is the sheet
  translucent?":
  ```java
  2461: AbstractC54451fC.A03(requireActivity(),
          getThemedContext().getColor(
            A00(this).A09 != 0 ? A00(this).A09 : R.color.bds_black_50_transparent));
  ```
  `AbstractC54451fC.A03` (line 69-80) sets the status bar color to the
  given color and also calls `A05(activity, z)` for icon brightness.
  The scrim/overlay color is `A00(this).A09` (a per-sheet configured
  color) or defaults to `R.color.bds_black_50_transparent` (50% black).

> **What this means for the patch (goal C — translucent comment sheet):**
> The `BottomSheetFragment` is the IGDS shared bottom-sheet used across
> the app; making it translucent for clips only requires either:
> - A clips-specific override that sets the sheet's root background to
>   `bds_transparent` (or a frosted translucent drawable) instead of
>   `igds_color_primary_background`, AND
> - Lets the underlying video keep playing & visible — which means the
>   sheet must NOT cover the video. Currently `layout_container_bottom_sheet`
>   is a child of `root_clips_layout` (the same view that gets repainted
>   at `C254289Wz:49396`); the sheet sits ON TOP of the video.
>   The minimal hack is to set the sheet's container background to
>   transparent + apply a blur/frost drawable.

---

## 8. Existing IG "fullscreen" / hide-side-buttons feature

The mission note says IG already has a "fullscreen" feature that hides
the side like/comment/share buttons. Searched broadly:

- Side action buttons live in `R.id.clips_ufi_component`
  (`0x7f0b0c62`) — has children `clips_ufi_like_button`,
  `clips_ufi_comments_button`, `clips_ufi_share_button`,
  `clips_ufi_more_button` (`R.java:20380-20385`).
- The media-info / caption area is `R.id.clips_media_info_component`
  (`0x7f0b0bc1`) / `R.id.clips_viewer_media_info` (`0x7f0b0c8d`).
- I could NOT find an explicit "fullscreen_button" or "fullscreen_mode"
  class in the clips viewer. The likely entry point for the existing
  hide-ufi behavior is the per-reel tap handler inside the
  **un-decompiled** `ClipsViewerFragment.onViewCreated` (§3b), which
  toggles `clips_ufi_component` and `clips_media_info_component`
  visibility. Reference: `C6BD.java:52` shows the
  `R.id.clips_ufi_component` lookup helper.
- Confirmed: **NO `setRequestedOrientation` / `SCREEN_ORIENTATION_*`
  reference exists in `C27528AFt` or `C254289Wz`** (grep returned no
  matches). So whatever IG currently calls "fullscreen" does NOT rotate
  the device, matching the mission description.

> **What this means for the patch (goal D — TikTok-style fullscreen for
> 16:9 videos):** the existing "fullscreen" hook (whatever calls
> `clips_ufi_component.setVisibility(GONE)`) is inside the un-decompiled
> `onViewCreated` block. Rather than try to enhance it in place, a
> cleaner patch is to:
> 1. Add an `OnClickListener` to a new "fullscreen" button (or hook the
>    existing one) on the `ClipsViewerFragment` view tree.
> 2. On click, call `requireActivity().setRequestedOrientation(
>    ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE)` and reveal a seekbar
>    (`PlayerView`/`ExoPlayer` controller) bound to the same
>    `TextureView`'s player.
> 3. The seekbar can be a `androidx.media3.ui.PlayerView`-style
>    controller overlaid on `R.id.clips_viewer_video_layout`.

---

## 9. Summary table of file:line evidence

| Concern | File | Line(s) |
|---|---|---|
| Reels tab enum entry | `p002X/EnumC108993ky.java` | 83 |
| Tab host fragment factory | `p002X/C55071gC.java` | 47, 50 |
| Reels-tab fragment picker | `p002X/AbstractC80182fb.java` | 771-797 |
| `ClipsTabFragment` (modern host) | `p002X/C27528AFt.java` | 31, 806-820 (onCreateView), 897-1019 (onViewCreated), 855-867 (onResume), 870-881 (onStop) |
| Sub-tab adapter | `p002X/C28800Am1.java` | 36-87 |
| `ClipsViewerFragment` (legacy feed) | `p002X/C254289Wz.java` | 130, 49371-49415 (onCreateView), 113683-113708 (onViewCreated FAILED) |
| Reels-tab layout | `R.layout.layout_clips_tab_fragment` (`0x7f0e0a39`) | R.java:37925 |
| Reels-feed layout | `R.layout.layout_clips_viewer_fragment` (`0x7f0e0a4c`) | R.java:37944 |
| Outer ViewPager2 id | `R.id.clips_tab_view_pager` (`0x7f0b0c49`) | R.java:20356 |
| Root container id | `R.id.root_clips_layout` (`0x7f0b35ae`) | R.java:30815 |
| Video view class | `p002X/C3EO.java` | 15-47 (constructor sets MATCH_PARENT×MATCH_PARENT, `R.id.clips_viewer_video_layout`) |
| Video view creator (Litho) | `p002X/C3BT.java` | 63 |
| Video surface base class | `p002X/AbstractC210917ky.java` | 16, 30 (setVideoSource), 77-79 (setForceFillTextureScaling), 146-212 (onSizeChanged) |
| Video aspect-ratio calculator | `p002X/C25U.java` | 11-67 (`A00(...)` computes width/height/x/y for TextureView) |
| Window chrome controller | `p002X/C2ZS.java` | 36-105 (`A01`), 108-111 (`A02` entry), 126-132 (`A05` paints `android.R.id.content`) |
| Status-bar color helper | `p002X/AbstractC54451fC.java` | 65-67 (A02 transparent), 82-116 (A04 set color), 119-133 (A05 icon color), 136-147 (A06 layout-fullscreen toggle), 164-166 (A09 query) |
| Nav-bar color helper | `p002X/C54511fI.java` | 77-121 (A04), 124-138 (A05), 141-160 (A06 contrast) |
| Bottom-nav bar painter | `p002X/C26630bQ.java` | 120-138 (A04) |
| Bottom-nav call site | `com/instagram/mainactivity/InstagramMainActivity.java` | 4112-4114 |
| `setBackgroundColor` impl | `p002X/AbstractC27310cW.java` | 147-150 (A0R) |
| Comment sheet navigator | `p002X/C109193lI.java` (`IgBottomSheetNavigator`) | 48, 158 |
| Comment sheet host setup | `p002X/C254289Wz.java` | 540-570 |
| `BottomSheetFragment` (IGDS) | `com/instagram/igds/components/bottomsheet/BottomSheetFragment.java` | 154 (class), 2392-2402 (onCreateView), 2461 (scrim color) |
| Side action buttons | `R.id.clips_ufi_component` (`0x7f0b0c62`) | R.java:20381 |
| Media info / caption | `R.id.clips_media_info_component` (`0x7f0b0bc1`) | R.java:20221 |
| media3 PlayerView (NOT used by clips) | `p146fb/androidx/media3/p147ui/PlayerView.java` | 4623 (setResizeMode) |
| media3 AspectRatioFrameLayout | `p146fb/androidx/media3/p147ui/AspectRatioFrameLayout.java` | 86 (setResizeMode), 30-73 (onMeasure modes 0=FIT/1=FIXED_W/2=FIXED_H/4=ZOOM) |

---

## 10. Open questions / things this turn did NOT resolve

1. The actual inner feed's `R.id.*` (the `ViewPager2` or `RecyclerView`
   that swipes between reels) is inside the **un-decompiled
   `ClipsViewerFragment.onViewCreated`** (`C254289Wz:113683-113708`).
   We confirmed via imports and `onDestroyView` locals that BOTH
   `ViewPager2` and `RecyclerView` are used, but we cannot quote the
   `findViewById` line. Will need apktool / smali to inspect, OR run
   jadx with `--comments-level debug` on this file.
2. The exact "tap-to-hide-ufi" handler that the existing IG
   "fullscreen" feature uses is also inside the un-decompiled
   `onViewCreated` block. Same recommendation.
3. The `layout_clips_tab_fragment` / `layout_clips_viewer_fragment`
   XMLs are NOT in this jadx dump (jadx was run with `--no-res`). For
   any patch that needs to change `fitsSystemWindows`, paddings, or
   layout containers in XML, we will need to decompile `resources/`
   separately via apktool.
4. The `c255769b7` color source used at `C254289Wz:49391-49398` to
   repaint `root_clips_layout` was not fully traced (would need to
   follow `C255769b7.A05()/A00()/A01()` to see which color is
   applied). It is one of the sources of the opaque background behind
   the video.
