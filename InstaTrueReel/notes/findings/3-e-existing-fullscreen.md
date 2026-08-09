# 3-e — Existing IG "fullscreen" feature + Feature D hook points

**Scope:** Existing Instagram "fullscreen" feature on Reels (which only hides
the side action buttons) and the hook points for Feature D (TikTok-style:
rotate-to-landscape + hide side buttons + show seekbar).

**Decompiled source root:** `/home/z/insta-src/jadx-out/sources/`
**Prior context:** Read worklog.md sections 3-a, 3-b, 3-c, 3-d first.

---

## TL;DR

- IG's existing "fullscreen" is **NOT a separate Fragment/Activity**. It is a
  **fade-out of the side UFI buttons** triggered by a swipe gesture on the
  reel. The fade animator is `EPN` (same class 3-d found for watch-and-comment).
  Handler: `VBP.FSS()` enters, `VBP.EvT()` exits. They set **alpha = 0.0f** on
  `R.id.clips_ufi_component` (NOT View.GONE) and on `ClipsViewerNavigationBar`,
  media-info, etc.
- State flags live on `C11R` (ClipsItemState): `A0v` = `isFullscreenViewActive`,
  `A0u` = `isFillToScreenActive`, `A0w` = `isFullscreenViewNuxActive`. All
  `final boolean` set in the constructor (immutable Builder pattern — they
  describe the per-item config, not a runtime toggle).
- There is also a **menu entry** `"Fullscreen"` in the long-press / three-dot
  popup built by `VSL.java`. Tapping it invokes `IA3.F6G()` → `C2OR.A07(c2or,
  new I34(c2or, 33))`. The user-visible "expand icon" on landscape reels in the
  screenshot is almost certainly THIS popup-menu entry (no always-visible
  inline expand-button found in code).
- IG does NOT rotate the device on fullscreen — confirmed no
  `setRequestedOrientation` anywhere in `ClipsTabFragment` / `ClipsViewerFragment`.
  Multiple `setRequestedOrientation` helpers DO exist elsewhere in IG
  (`C99744f1m`, `AbstractC186396mW`, `AbstractC104253ij1`, `SF7`, `C45773HVn`).
- No landscape/aspect-ratio accessor exists on `com.instagram.feed.media.Media`
  for the playback path. The only `isLandscape` flag is the creation-side
  `feedmetadata_isLandscape` column in the drafts DB (`C28721Akk.java:342`,
  parsed by `C28856Amv.java:261`). Runtime aspect-ratio is computed from the
  TextureView's measured dimensions in `C25U.A00` (see prior agent 3-a).
- `SimpleVideoLayout` / `AbstractC210917ky` expose **NO** `getDuration()` /
  `getCurrentPosition()` / `seekTo()` / `setController()` and **NO** built-in
  SeekBar/TimeBar/PlayerControlView. The `com.instagram.common.clips.player`
  package contains only `VideoInferenceUtil.java` — the actual player
  interface lives elsewhere (gap, see Q4).
- FB media3 `PlayerView` (which HAS a built-in controller + TimeBar) exists at
  `p146fb/androidx/media3/p147ui/PlayerView.java:4623` but is **NOT** wired
  into the clips viewer.

---

## Q1 — The fullscreen / hide-ufi state

### State flag (immutable Builder field on ClipsItemState)

**File:** `/home/z/insta-src/jadx-out/sources/p002X/C11R.java`
(Original name: `ClipsItemState` — confirmed by 3-a)

```java
// C11R.java:78-80  (field declarations)
public final boolean A0u;   // = isFillToScreenActive
public final boolean A0v;   // = isFullscreenViewActive
public final boolean A0w;   // = isFullscreenViewNuxActive
```

```java
// C11R.java:131-134  (constructor assignments — Builder-style, immutable)
this.A0v = z20;
this.A0u = z21;
// ...
this.A0w = z23;
```

```java
// C11R.java:544-551  (toString — proves the field-name mapping)
sb.append(", isFullscreenViewActive=");
sb.append(this.A0v);
sb.append(", isFillToScreenActive=");
sb.append(this.A0u);
// ...
sb.append(", isFullscreenViewNuxActive=");
sb.append(this.A0w);
```

Read-accessor MethodHandles (reflection-style getters used by other classes):
- `/home/z/insta-src/jadx-out/sources/p002X/RL0.java:8` →
  `super(C11R.class, "isFullscreenViewActive", "isFullscreenViewActive()Z", 0);`
- `/home/z/insta-src/jadx-out/sources/p002X/R70.java:8` →
  `super(C11R.class, "isFullscreenViewActive", "isFullscreenViewActive()Z", 0);`
- `/home/z/insta-src/jadx-out/sources/p002X/RK1.java:8` →
  `super(C11R.class, "isFullscreenViewNuxActive", "isFullscreenViewNuxActive()Z", 0);`

NOTE: Because `A0v`/`A0u`/`A0w` are `final`, they CANNOT be flipped at runtime
via these accessors — they describe the per-reel configuration (e.g. "this reel
was opened via the fullscreen CTA"). The runtime "currently-hiding-ufi" state
is held inside `EPN` (see below).

### Toggle method — `VBP` (the gesture listener that hides UFI)

**File:** `/home/z/insta-src/jadx-out/sources/p002X/VBP.java`
Implements `InterfaceC113320nxx` (clips viewer swipe/transition listener).

**Enter fullscreen** = `VBP.FSS(int i, int i2)` at lines 116-170:

```java
// VBP.java:153-156  — hides clips_ufi_component via alpha 0
View viewA08 = AnonymousClass955.A06(c27468ADl);
if (viewA08 != null && (viewFindViewById = viewA08.findViewById(R.id.clips_ufi_component)) != null) {
    AbstractC27310cW.A0K(viewFindViewById, 1583392527);
}

// VBP.java:147-152  — fades out media-info (C2TW)
if (viewA07 != null) {
    Object tag = viewA07.getTag();
    if ((tag instanceof C2TW) && (c2tw = (C2TW) tag) != null) {
        c2tw.A0J(0.0f);
    }
}

// VBP.java:157-160  — fades out C31610jS
C31610jS c31610jS2 = re8.A00;
if (c31610jS2 != null) {
    c31610jS2.A0y(0.0f);
}

// VBP.java:161-169  — fades out C2LU + ClipsViewerNavigationBar
C2LU c2lu2 = re8.A01;
if (c2lu2 != null) { c2lu2.A00.HEK(0.0f); }
C2LU c2lu3 = re8.A01;
if (c2lu3 == null || (clipsViewerNavigationBar = c2lu3.A00.A0U) == null) { return; }
AbstractC27310cW.A05(clipsViewerNavigationBar, 0.0f, 708129985);

// VBP.java:130-138  — creates the EPN ufi-fade animator if not already active
EPN epn2 = new EPN(viewA06, re7.A04, re7.A05, re7.A06, re7.A07, re7.A08,
                   re7.A09, c255759b6, re7.A0B, null, null, null, null, null,
                   0.6f, false);
re7.A02 = epn2;
epn2.A0J = true;
// VBP.java:142-144  — pushes the slide offset to the animator
epn3.EhI(i);
```

**Exit fullscreen** = `VBP.EvT()` at lines 47-88:

```java
// VBP.java:62-65  — restores clips_ufi_component via alpha 1
View viewA07 = AnonymousClass955.A06(c27468ADl);
if (viewA07 != null && (viewFindViewById = viewA07.findViewById(R.id.clips_ufi_component)) != null) {
    AbstractC27310cW.A0L(viewFindViewById, -2119118394);
}
// VBP.java:57-60   — restores C2TW (media-info) alpha
// VBP.java:67-69   — restores C31610jS alpha
// VBP.java:71-73   — restores C2LU alpha
// VBP.java:74-77   — restores ClipsViewerNavigationBar alpha
// VBP.java:78-83   — tears down EPN: epn.EhC(); re7.A02 = null; re7.A03 = null;
```

**Confirmed: alpha-based, NOT visibility-based.** From
`/home/z/insta-src/jadx-out/sources/p002X/AbstractC27310cW.java`:

```java
// AbstractC27310cW.java:119-125
public static void A0K(View view, int i) { A05(view, 0.0f, i); }  // alpha 0  = hide
public static void A0L(View view, int i) { A05(view, 1.0f, i); }  // alpha 1  = show
```

### The actual ufi-fade animator: `EPN` ("WatchAndCommentViewManager")

**File:** `/home/z/insta-src/jadx-out/sources/p002X/EPN.java`
(Original name: `WatchAndCommentViewManager` — confirmed by 3-d.)

```java
// EPN.java:23
public final class EPN implements InterfaceC113370nyp {

// EPN.java:94  — full constructor (16+ deps; built by VBP.FSS line 131)
public EPN(View view, ClipsViewerSource clipsViewerSource, UserSession userSession,
           AbstractC28606Ait abstractC28606Ait, ACN acn, InterfaceC51284Jep interfaceC51284Jep,
           InterfaceC43615GeP interfaceC43615GeP, C255759b6 c255759b6, C257899eY c257899eY,
           Float f, Float f2, Function0 function0, Function0 function1, Function0 function2,
           float f3, boolean z) { ... }

// EPN.java:655  — exit-fullscreen teardown
public final void EhC() { ... }

// EPN.java:837  — apply slide-offset to fade UFI
public final void EhI(int i) { ... }
```

Also note from 3-d's findings: `EPN.java:534` animates `clips_media_dimming_view`
alpha (`view.setAlpha(1.0f - slideOffset)`). So EPN is the single class that
governs the entire "fullscreen = hide UFI side buttons + dim media" state.

### What `VBP` does NOT do

- Does NOT call `setRequestedOrientation` (no rotation).
- Does NOT add or show a SeekBar / TimeBar / progress bar.
- Does NOT change the video scaling mode (`AbstractC210917ky.setForceFillTextureScaling` is NOT invoked — that path is only in the FEED binder `C8NA.java:187` per 3-a).
- Does NOT set `View.GONE` — only `setAlpha(0.0f)`. The buttons are still
 触摸-capable (their `onTouch` is bypassed via the `EPN` `A0J=true` flag and a
 swipe-down gesture — but they're not gone).

---

## Q2 — The expand-button click handler

### The popup-menu path (the "expand icon" the screenshot shows)

The expand/fullscreen affordance for Reels is an entry in the **long-press /
three-dot popup menu** built by `VSL.java`, NOT an always-visible inline
button on the reel.

**File:** `/home/z/insta-src/jadx-out/sources/p002X/VSL.java`

```java
// VSL.java:26-44  — builds the popup menu
C62141rb c62141rbA01 = AbstractC107883jB.A01();
c62141rbA01.add(MediaOption$Option.PLAYBACK_SPEED);
c62141rbA01.add(MediaOption$Option.FULLSCREEN_VIEW);          // <-- the fullscreen entry
if (zH2V) { c62141rbA01.add(MediaOption$Option.VIDEO_CAPTIONS); }
if (zH2W) { c62141rbA01.add(MediaOption$Option.VIDEO_TRANSLATIONS); }
// ...
// VSL.java:37  — PLAYBACK_SPEED item with label R.string 2131974874
c74504Sm5.A00(new C29117Ar8(...));
// VSL.java:38  — FULLSCREEN_VIEW item
c74504Sm5.A00(C2OR.A00(c11r, MediaOption$Option.FULLSCREEN_VIEW, c2or, null,
                        new C111754nQz(20, c11r, c2or), 0));
```

The label string for FULLSCREEN_VIEW is resolved in `C2OR.A00`:

```java
// C2OR.java:65-80  — string-resolution switch on ordinal
public static final C29117Ar8 A00(C11R c11r, MediaOption$Option mediaOption$Option, ...) {
    int iOrdinal = mediaOption$Option.ordinal();
    if (iOrdinal == 1)   { i2 = 2131977720; }
    else if (iOrdinal == 2)   { i2 = R.string.piko_disable_comments; }
    else if (iOrdinal == 5)   { i2 = 2131968684; }
    else if (iOrdinal == 6)   { i2 = 2131973824; }
    else if (iOrdinal == 114) { i2 = 2131984733; }   // <-- FULLSCREEN_VIEW label
    else if (iOrdinal == 116) { i2 = 2131978197; }
    // ...
}
```

(`MediaOption$Option.FULLSCREEN_VIEW` ordinal == 114 — inferred from the
switch above; also note `EnumC43392Gao.java:25` shows
`FULL_SCREEN_PLAYER("full_screen")` which is a sibling enum, different feature.)

### The tap callback — `IA3.F6G()` / `IA5.F6G()`

Two parallel surfaces (old `C2OR`-based and newer `C15T`-based) both implement
`InterfaceC82075WOt` (the media-option callback interface) with a `F6G()`
method for FULLSCREEN_VIEW.

**File:** `/home/z/insta-src/jadx-out/sources/p002X/IA3.java`

```java
// IA3.java:30-35  — old C2OR-based path
@Override public final void F6G() {
    C2OR c2or = this.A00;
    C2OR.A03(c2or.A08.A08(c2or.A05), MediaOption$Option.FULLSCREEN_VIEW, c2or);  // logging
    C2OR.A07(c2or, new I34(c2or, 33));                                            // enqueue action
}
```

**File:** `/home/z/insta-src/jadx-out/sources/p002X/IA5.java`

```java
// IA5.java:26-29  — newer C15T-based path
@Override public final void F6G() {
    C15T.A09(MediaOption$Option.FULLSCREEN_VIEW, this.A00);
}
```

### What the action does

`I34(c2or, 33)` is a `Function0` (extends `AbstractC109253lO implements
Function0`). File `/home/z/insta-src/jadx-out/sources/p002X/I34.java`:

```java
// I34.java:13-21
public final class I34 extends AbstractC109253lO implements Function0 {
    public I34(Object obj, int i) { ... }
    // run() switch cases visible only 0..16 — case 33 not present in decompile
    // (decompile gap: either falls to default, or the int dispatches elsewhere)
}
```

**GAP / open question:** the decompile of `I34.run()` only shows cases 0..16 —
case 33 (the FULLSCREEN_VIEW action) is in the un-decompiled tail. We
**cannot confirm from code alone** whether the existing FULLSCREEN_VIEW menu
action actually triggers `VBP.FSS` (the hide-ufi animator) or whether it does
something else (e.g. just logs / NUX). Likely candidates from the architecture:

- `VBP.FSS` / `VBP.EvT` are normally invoked by **swipe gesture** (a
  `InterfaceC113320nxx` listener) — so the menu item MAY go through a
  different code path that ends up calling the same `EPN.EhI` animator.
- Or the menu item may simply SET `C11R.A0v` (isFullscreenViewActive) on the
  NEXT rebuild — but since `A0v` is `final`, it's set via the Builder when the
  item is constructed (so the menu tap probably just triggers a state
  invalidation + rebuild).
- **Patching implication:** regardless of the existing menu path, our Feature D
  hook is best placed directly in `VBP.FSS` / `VBP.EvT` (or in `EPN.EhI` /
  `EPN.EhC`) so BOTH the gesture path AND the menu path get the
  rotation + seekbar enhancement.

### Does the menu call the hide-ufi toggle from Q1?

**Likely yes, indirectly.** The menu action's purpose IS to enter fullscreen
(hide UFI), and the only "hide UFI" code in the clips viewer is `VBP.FSS` /
`EPN.EhI`. But the literal call chain `IA3.F6G → C2OR.A07 → I34(33).run()` is
not fully decompiled — the smali edit will need to verify.

---

## Q3 — Aspect-ratio / horizontal-video detection

### No runtime accessor on `Media`

Grep of `/home/z/insta-src/jadx-out/sources/com/instagram/feed/media/` for
`isLandscape|isHorizontal|aspectRatio|getVideoWidth|getVideoHeight|isFullscreen|getDuration|getCurrentPosition`
returned **zero matches**. So the playback `Media` model has no built-in
landscape accessor.

### Only creation-side `feedmetadata_isLandscape` flag exists

**File:** `/home/z/insta-src/jadx-out/sources/p002X/C28721Akk.java:342-343`

```sql
CREATE TABLE IF NOT EXISTS `drafts_backup` (
  ...
  `feedmetadata_isLandscape` INTEGER,
  `videocrop_width`  INTEGER,
  `videocrop_height` INTEGER,
  `videocrop_rectF`  TEXT,
  ...
)
```

Parsed at:

**File:** `/home/z/insta-src/jadx-out/sources/p002X/C28856Amv.java:261`

```java
int iA0121 = AbstractC187276nw.A00(rgxG6D, "feedmetadata_isLandscape");
```

This is the **drafts backup** path (used during creation / save). NOT exposed
on the playback Media API.

### Runtime aspect ratio is computed in `C25U.A00` (TextureView sizing)

Per prior agent 3-a:
- `AbstractC210917ky.onSizeChanged` (lines 146-212) → `C25U.A00` (file
  `p002X/C25U.java:11-67`) which computes TextureView width/height/x/y and
  picks FIT vs ZOOM based on the overflow ratio vs `A01` (the force-fill
  factor, default 0.25d).
- The clips viewer leaves `A01 = 0.25d` (default FIT).

So the runtime "is this video wider than tall?" check exists implicitly inside
`C25U.A00`'s math, but isn't exposed as a boolean. **For Feature D, the
cleanest landscape gate** is to compute it inside
`AbstractC210917ky.onSizeChanged` (or in our own wrapper around C3EO):

```java
// Pseudo: detect landscape from the decoded video dimensions, NOT the TextureView dimensions
boolean isLandscape = (videoWidth > videoHeight);
```

The actual `videoWidth` / `videoHeight` come from the underlying player (which
we have NOT yet located — see Q4 gap). A pragmatic fallback is to check the
`TextureView`'s measured bitmap dimensions in `onSizeChanged`, or to read the
Media's crop coordinates (`videocrop_width` / `videocrop_height` if exposed).

### Implication for Feature D

- IG currently shows the FULLSCREEN_VIEW menu entry unconditionally (VSL.java:28
  always adds it). So **no existing "only show on landscape reels" gate** to
  hook into.
- For TikTok-style behavior we must ADD our own gate (e.g. only rotate +
  seekbar when `videoWidth > videoHeight`); portrait reels just hide UFI as today.

---

## Q4 — Seekbar / player controller availability

### `SimpleVideoLayout` — NO built-in controller

**File:** `/home/z/insta-src/jadx-out/sources/com/instagram/p132ui/simplevideolayout/SimpleVideoLayout.java`

```java
// SimpleVideoLayout.java:15
public class SimpleVideoLayout extends AbstractC210917ky
        implements InterfaceC36365Dkk, CAJ { ... }
```

Grep of the entire `com.instagram/p132ui/simplevideolayout/` package for
`SeekBar|TimeBar|PlayerControlView|setUseController|setControllerShowTimeoutMs|Controller|progressBar|scrub|getDuration|getCurrentPosition|seekTo|MediaPlayer|Player`:

- **Zero matches** in `SimpleVideoLayout.java`.
- **Zero matches** in `AbstractC210917ky.java` either (it's the VideoFrameLayout
  base class — just the TextureView + sizing math; no playback control).

So IG's clips viewer has **NO existing seekbar / scrub UI to enable**. One must
be added.

### `com.instagram.common.clips.player` — only inference util

**Path:** `/home/z/insta-src/jadx-out/sources/com/instagram/common/clips/player/`

Contains a single file: `VideoInferenceUtil.java`. NO `Player` interface, NO
`getCurrentPosition()` / `getDuration()` / `seekTo()` here. The actual player
interface is elsewhere (gap, see below).

### FB media3 `PlayerView` — exists but unused

Per prior agent 3-a:
- `p146fb/androidx/media3/p147ui/PlayerView.java:4623` — the FB media3 PlayerView
  class, which has a built-in `PlayerControlView` + `TimeBar` (scrub bar).
- `AspectRatioFrameLayout` at line 86.
- Confirmed NOT used by the clips viewer (clips viewer uses IG's own
  `AbstractC210917ky` + `SimpleVideoLayout` + `TextureView`).

### Which approach is more feasible?

| Approach | Feasibility | Cost |
|---|---|---|
| **(A) Add a custom SeekBar overlay** bound to the player via `Handler.postDelayed` polling `getCurrentPosition()` / `getDuration()` | **MORE FEASIBLE** — minimal blast radius, no pipeline change. Just need to locate the player instance (see gap). | Low. Add a `android.widget.SeekBar` (or compose one) as a sibling of `R.id.clips_viewer_video_layout`; toggle visibility in `VBP.FSS` / `VBP.EvT`. |
| **(B) Overlay a media3 `PlayerView` controller** (swap `SimpleVideoLayout` for `PlayerView`, or wrap it) | Less feasible — would require swapping the entire video pipeline (`C3EO` → `C3BT` binder → Litho section). IG's `SimpleVideoLayout` is hard-wired to `TextureView` + custom `C25U` sizing math. | Very high — risk of breaking playback. Not recommended. |

**Recommendation: Approach A.** Add a custom SeekBar overlay, visible only in
fullscreen mode (i.e. when `VBP.FSS` runs), bound to the player via a Handler.

### Gap — locate the player instance

`SimpleVideoLayout` and `AbstractC210917ky` do not expose
`getCurrentPosition()` / `getDuration()` / `seekTo()`. The actual player
interface (likely something like `VideoPlayer` / `ClipsVideoPlayer` /
`MediaPlayer` wrapper) is referenced from the Litho binder `C3BT` (which
creates `C3EO`, per 3-a) or from `C257899eY` (the `c257899eY` field on `RE7`,
used in `VBP.F6I` line 104 to check `A17(media.C7D())` and call
`A0u(AbstractC114203tN.A00(...), false, false)` — that `A0u` is likely a
"play/pause" method).

**Next agent action:** read `p002X/C257899eY.java` and `p002X/C3BT.java` to
find the player instance field and confirm whether it exposes
`getCurrentPosition()` / `getDuration()` / `seekTo()`. If not, the patch must
reach into the underlying `MediaPlayer` (Android framework) via reflection or
via an existing IG wrapper (search for `IMediaPlayer` / `VideoPlayer`
interfaces across `p002X/`).

---

## Feature D hook points (concrete file:line anchors)

### Where to ADD `setRequestedOrientation(LANDSCAPE)`

**Enter-landscape (paired with hide-ufi):**
- **Primary hook:** `VBP.FSS(int i, int i2)` at
  `/home/z/insta-src/jadx-out/sources/p002X/VBP.java:116` (start of method).
  Add at the top: `re7.A0B.A0r("resume");` already exists at line 28 — insert
  our rotation call adjacent. Get the activity via `re7.A0C` (a `C27468ADl`
  Fragment holder) → `requireActivity().setRequestedOrientation(0)` (0 =
  `SCREEN_ORIENTATION_LANDSCAPE`). Gate on `isLandscape` (Q3).
- **Alternative hook:** `EPN.EhI(int i)` at
  `/home/z/insta-src/jadx-out/sources/p002X/EPN.java:837` — but EPN doesn't
  hold an Activity reference, so VBP is cleaner.

**Exit-landscape (paired with show-ufi):**
- **Primary hook:** `VBP.EvT()` at
  `/home/z/insta-src/jadx-out/sources/p002X/VBP.java:47` (start of method).
  Add `requireActivity().setRequestedOrientation(1)` (1 = PORTRAIT) — or
  better, `ActivityInfo.SCREEN_ORIENTATION_USER` to respect user rotation lock.

**Existing helpers to reuse (NOT in clips viewer currently):**
- `C99744f1m.A00()` at `/home/z/insta-src/jadx-out/sources/p002X/C99744f1m.java:20`
  returns the current orientation (0=landscape, 1=portrait, 6=sensor).
- `C99744f1m.A01(...)` toggles orientation (calls `setRequestedOrientation(0)`
  at line 104, `setRequestedOrientation(1)` at line 106/122).
- `AbstractC186396mW.A00(activity, i)` at line 11 — generic wrapper.
- `AbstractC104253ij1.java:77` — `activityA00.setRequestedOrientation(i3);`

### Where to ADD a seekbar

**Show on enter fullscreen:**
- In `VBP.FSS(int i, int i2)` at `VBP.java:116` — after creating `EPN` (line
  131), look up our custom SeekBar view by id and set its visibility /
  register a Handler callback. The SeekBar should be a sibling of
  `R.id.clips_viewer_video_layout` (added via the layout XML).

**Hide on exit fullscreen:**
- In `VBP.EvT()` at `VBP.java:47` — hide the SeekBar, remove Handler callback.

**Progress polling:**
- Use `android.os.Handler` + `postDelayed(this, 33)` (30 fps update) calling
  `player.getCurrentPosition()` and `player.getDuration()` (player instance
  TBD per Q4 gap). Update `SeekBar.setProgress((int)(pos * 1000 / dur))`.
- On `SeekBar.onStopTrackingTouch` → `player.seekTo(progress * dur / 1000)`.

### Where to ADD the landscape gate

- Best place: inside `VBP.FSS` before the rotation call — check the current
  reel's video dimensions (need player instance from Q4 gap). If portrait,
  skip the rotation but STILL hide the UFI (current behavior).
- Alternative: in the menu-item construction `VSL.run()` at
  `/home/z/insta-src/jadx-out/sources/p002X/VSL.java:18-50` — only add
  `MediaOption$Option.FULLSCREEN_VIEW` when `isLandscape`. But this only
  affects the popup-menu visibility, not the gesture path.

---

## Summary table — file:line evidence

| Concern | File:line | What |
|---|---|---|
| State flag (immutable) | `p002X/C11R.java:78-80, 131-134, 544-551` | `A0v=isFullscreenViewActive`, `A0u=isFillToScreenActive`, `A0w=isFullscreenViewNuxActive` |
| State getters | `p002X/RL0.java:8`, `R70.java:8`, `RK1.java:8` | MethodHandle accessors |
| Enter-fullscreen (hide UFI) | `p002X/VBP.java:116-170` | `FSS()` sets alpha 0 on `clips_ufi_component` + media-info + nav-bar; creates `EPN` |
| Exit-fullscreen (show UFI) | `p002X/VBP.java:47-88` | `EvT()` sets alpha 1, tears down `EPN` |
| Alpha helpers | `p002X/AbstractC27310cW.java:119-125` | `A0K(view,i)=alpha 0`, `A0L(view,i)=alpha 1` |
| UFI fade animator | `p002X/EPN.java:23, 94, 655, 837` | `EPN` (WatchAndCommentViewManager); `EhI(i)` enter, `EhC()` exit |
| Expand menu builder | `p002X/VSL.java:26-44` | Adds `FULLSCREEN_VIEW` to popup |
| Expand menu label | `p002X/C2OR.java:77-79` | ordinal 114 → R.string 2131984733 |
| Expand tap callback (old) | `p002X/IA3.java:30-35` | `F6G()` → `C2OR.A07(c2or, new I34(c2or, 33))` |
| Expand tap callback (new) | `p002X/IA5.java:26-29` | `F6G()` → `C15T.A09(FULLSCREEN_VIEW, ...)` |
| Action runner | `p002X/I34.java:13-21` | `Function0`; case 33 not decompiled (gap) |
| Landscape DB column | `p002X/C28721Akk.java:342-343` | `feedmetadata_isLandscape` in drafts DB |
| Landscape parser | `p002X/C28856Amv.java:261` | `AbstractC187276nw.A00(rgxG6D, "feedmetadata_isLandscape")` |
| Runtime sizing math | `p002X/C25U.java:11-67` | `C25U.A00` computes aspect ratio (no boolean exposed) |
| Video view (no controller) | `com/instagram/p132ui/simplevideolayout/SimpleVideoLayout.java:15` | extends `AbstractC210917ky`; NO SeekBar/TimeBar/Controller |
| Base video layout | `p002X/AbstractC210917ky.java` | NO `getDuration/getCurrentPosition/seekTo` |
| FB media3 PlayerView (unused) | `p146fb/androidx/media3/p147ui/PlayerView.java:4623` | has built-in controller + TimeBar; NOT wired to clips |
| `setRequestedOrientation` helpers | `p002X/C99744f1m.java:20, 104, 106, 122` `p002X/AbstractC186396mW.java:11` `p002X/AbstractC104253ij1.java:77` `p002X/SF7.java:239, 249` `p002X/C45773HVn.java:138, 434` | Existing orientation helpers to reuse |

## Open gaps for next agent

1. **Player instance for SeekBar binding** — read `p002X/C257899eY.java` and
   `p002X/C3BT.java` to find the player field. Check if it exposes
   `getCurrentPosition()` / `getDuration()` / `seekTo()`. If not, find the
   underlying `MediaPlayer` (search `p002X/` for `IMediaPlayer` /
   `VideoPlayer` interfaces).
2. **`I34(c2or, 33).run()` body** — confirm what the FULLSCREEN_VIEW menu
   action actually does (decompile tail). If it does NOT call `VBP.FSS`, our
   Feature D hook in `VBP.FSS` would miss the menu-tap path; we'd also need
   to hook into `I34`'s case 33 or `C2OR.A07`.
3. **Resources** — `R.string 2131984733` (FULLSCREEN_VIEW label) and the
   `R.drawable` for the expand icon need apktool lookup (not in this --no-res
   jadx dump).
4. **Verify `RE7.A0C` activity access** — confirm `re7.A0C` is a Fragment
   holder and `requireActivity()` works from `VBP` (which is a plain object,
   not a Fragment). If not, pass the activity via `RE7` constructor or use
   `AnonymousClass955.A06(c27468ADl).getContext()`.
