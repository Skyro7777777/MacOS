# 4-c — Force-fill scaling, orientation helpers, Reels-on-top detection

**Agent:** Explore (Task ID 4-c)
**Scope:** Three sub-questions blocking Features A and D:
- (Q1) Does `setForceFillTextureScaling(true)` make a 9:16 video fill the full
  screen height independently of the black-bar fix?
- (Q2) Are the orientation helpers (`C99744f1m`, `AbstractC186396mW`) safe to
  call from the clips viewer? Side effects?
- (Q3) Is `IgFragmentActivity.A1g()` a reliable "Reels is on top" check?
- (Q4) Config-change resilience — will our transparent-nav patches survive a
  `setRequestedOrientation(LANDSCAPE)` rotation?

All file:line refs are under `/home/z/insta-src/jadx-out/sources/` unless noted.

---

## Q1. Force-fill scaling behavior

### Q1.a. What `A01 = 1.0d` (force-fill) does in `C25U.A00`

`AbstractC210917ky.setForceFillTextureScaling(boolean z)` at
**`p002X/AbstractC210917ky.java:77-79`**:
```java
public final void setForceFillTextureScaling(boolean z) {
    this.A01 = z ? 1.0d : this.A00;
}
```
Constructor defaults (lines 85-86, 218-219, 241-242):
```java
this.A00 = 0.25d;
this.A01 = 0.25d;
```
So `setForceFillTextureScaling(true)` flips `A01` from `0.25d` to `1.0d`;
`setForceFillTextureScaling(false)` restores it to `0.25d`.

`AbstractC210917ky.onSizeChanged` at **`p002X/AbstractC210917ky.java:146-212`**
calls `C25U.A00(...)` with `(float) this.A01` as the `f2` threshold arg
(cited at lines 166 and 193). Quoting the relevant call (line 166):
```java
final C2474796u c2474796uA00 =
    C25U.A00(C25U.A01(f, i3, i4, textureView.getWidth(), textureView.getHeight()),
             f, (float) this.A01, i, i2);
```
Args (from `C25U.A00` signature at **`p002X/C25U.java:11`**):
- `num` — Integer mode flag from `C25U.A01` (FIT = `AnonymousClass006.A00`, ZOOM = `AnonymousClass006.A01`, undefined = `AnonymousClass006.A0C`)
- `f`  — video aspect ratio (videoWidth / videoHeight)
- `f2` — `this.A01` (threshold ratio: 0.25 default vs 1.0 force-fill)
- `i`  — container width
- `i2` — container height

The branch that consumes `f2` is at **`p002X/C25U.java:29-44`**:
```java
if (num == AnonymousClass006.A01 || num == AnonymousClass006.A0C) {
    // ZOOM mode — scale to FILL container, may overflow
    if (f > f5) {
        iA02 = C107593ii.A01(f4 * f);   // width  = round(container_h * video_aspect)
        iA01 = i2;                       // height = container_h
    } else {
        iA01 = C107593ii.A01(f3 / f);   // height = round(container_w / video_aspect)
        iA02 = i;                        // width  = container_w
    }
    float f6 = (iA01 - i2) / iA01;       // height-overflow fraction
    if ((iA02 - i) / iA02 > f2 || f6 > f2) {
        z = true;                        // overflow > threshold → fall back to FIT
    }
} else {
    iA02 = 0;
    iA01 = 0;
}
if (num == AnonymousClass006.A00 || z) {
    // FIT mode — scale to FIT inside container (letterbox)
    if (f > f5) {
        iA01 = C107593ii.A01(f3 / f);   // height = round(container_w / video_aspect)
        iA02 = i;                        // width  = container_w
    } else {
        iA02 = C107593ii.A01(f4 * f);   // width  = round(container_h * video_aspect)
        iA01 = i2;                       // height = container_h
    }
}
```
Then translations are computed at **`p002X/C25U.java:54-63`** to center the
scaled texture:
```java
float f7 = (i - iA02) / 2.0f;            // translationX (centers horizontally, crops overflow)
...
Float fValueOf3 = Float.valueOf((i2 - iA01) / 2.0f);  // translationY
```
Final layout applied to the TextureView in `onSizeChanged` at
`AbstractC210917ky.java:167-176` / `194-203`:
```java
final FrameLayout.LayoutParams layoutParams =
    new FrameLayout.LayoutParams(((Number) c2474796uA00.A00).intValue(),
                                 ((Number) c2474796uA00.A02).intValue());
...
textureView2.setLayoutParams(layoutParams);
AbstractC27310cW.A0F(textureView2, AnonymousClass084.A03(c2474796u.A03), -803297847);  // translationX
AbstractC27310cW.A0G(textureView2, AnonymousClass084.A03(c2474796u.A01), -343943711);  // translationY
```

### Q1.b. STRETCH (distort) or ZOOM-CROP (preserve aspect)?

**Verdict: ZOOM-CROP (preserves aspect ratio).** The math always scales the
TextureView by a single uniform factor derived from the video aspect ratio
`f` — it never sets width and height independently. The overflow is then
CROPPED via the negative translation (center-crop), NOT distorted.

Concretely:
- ZOOM branch: scales so the SMALLER dimension fills the container; the larger
  dimension overflows and is cropped by `(i - iA02) / 2` (negative → shifts
  view so equal overflow on both sides is clipped by the parent).
- FIT branch: scales so the LARGER dimension fits the container; the smaller
  dimension is letterboxed (translation centers it).
- The `f2` threshold decides whether ZOOM's overflow is "too much" and falls
  back to FIT.

With **default** `A01 = 0.25d`: ZOOM falls back to FIT if crop > 25% of either
dimension. With **force-fill** `A01 = 1.0d`: the threshold is 100% — i.e.
"allow any crop up to doubling the dimension", which in practice means
**always ZOOM, never fall back to FIT**.

This matches the user's intent ("stretch to fill" in TikTok terms = scale to
fill the screen, even if it means cropping; TikTok does NOT distort aspect).

### Q1.c. 9:16 video in a screen-height container — will it fill the height?

Tracing `C25U.A00` for a typical reels-viewer scenario:
- Container (VideoFrameLayout) = full screen, e.g. `i=1080, i2=2400`
  (status+nav already removed by the Feature A patch).
- Video: 9:16 → `f = 0.5625`.
- `f5 = i / i2 = 1080 / 2400 = 0.45`. So `f > f5` → 0.5625 > 0.45 → TRUE
  → ZOOM branch enters the "video wider than container" sub-branch:
  - `iA02 = round(i2 * f) = round(2400 * 0.5625) = 1350` (TextureView width)
  - `iA01 = i2 = 2400` (TextureView height = **container height**)
- Overflow check (force-fill `f2 = 1.0`):
  - `(iA02 - i) / iA02 = (1350 - 1080) / 1350 = 0.222` → < 1.0 ✓
  - `f6 = (iA01 - i2) / iA01 = 0` → < 1.0 ✓
  - → `z` stays false → STAYS in ZOOM mode (no FIT fallback).
- translationX = `(i - iA02) / 2 = (1080 - 1350) / 2 = -135`
  → TextureView is centered horizontally, 135px cropped on each side.
- translationY = `(i2 - iA01) / 2 = 0` → no vertical crop.

**Result:** TextureView is sized 1350×2400, positioned at (-135, 0). The video
fills the full container height (2400px = screen height) and is cropped 135px
on each side horizontally. **YES, the video reaches the top and bottom of the
screen** when force-fill is enabled.

**With default 0.25d instead:** Same trace, but if overflow > 0.25, FIT kicks
in. For 9:16 in 9:21.78 (1080:2400) container, overflow = 0.222 < 0.25 → stays
ZOOM, also fills height. So for an EXACT 9:16 video in an EXACT 9:16 screen,
both modes fill. The difference appears for 9:16 video in a TALLER container
(e.g. 9:21.78 from a 1080×2400 phone with status+nav removed), where the ZOOM
overflow (0.222) is below the 0.25 threshold so both modes fill — but for a
9:16 video in an even taller container (e.g. 9:22), overflow > 0.25 → default
falls back to FIT (letterbox with black bars top/bottom) while force-fill
keeps ZOOM (full fill).

**Conclusion:** Force-fill ALONE solves the "video doesn't reach top/bottom"
issue **whenever the container itself extends edge-to-edge**. If the container
has padding for status/nav bars (the current state per 3-b), force-fill can't
help — the black strips come from the container bounds, not the TextureView
scaling. The two fixes are COMPLEMENTARY:
1. Feature A (transparent status/nav + `setDecorFitsSystemWindows(false)`)
   makes the VideoFrameLayout container extend to the screen edges.
2. Force-fill ON (this patch) makes the TextureView fill that container.

The clips viewer currently leaves `A01 = 0.25d` (per 3-a). To enable
force-fill on the clips viewer, the simplest smali hook is to override
`AbstractC210917ky.setForceFillTextureScaling(false)` to be a no-op OR to
patch the constructor to initialize `A01 = 1.0d` for clips-viewer subclasses.
Cleanest is to patch `C3EO` (the clips viewer's VideoFrameLayout subclass —
`p002X/C3EO.java` per 3-a) to call `setForceFillTextureScaling(true)` after
super() in its constructor.

### Q1.d. Feed binder call site (pattern reference)

`p002X/C8NA.java:187` — the FEED binder (uses
`com.instagram.p132ui.widget.framelayout.MediaFrameLayout`, NOT the clips C3EO):
```java
boolean z5 = c3se.A0R;
mediaFrameLayout.setForceFillTextureScaling(z5);
```
The feed toggles force-fill per-feed-config (`c3se.A0R`). The clips viewer
doesn't pass any value — it just inherits the constructor default `0.25d`.

---

## Q2. Orientation helpers — side effects

### Q2.a. `C99744f1m` — has heavy side effects, also NOT used by Reels

Full class at **`p002X/C99744f1m.java`** (140 lines). Three methods:

**`A00()` (lines 20-34):** Queries `activity.getRequestedOrientation()` and
returns an int (0=portrait, 1=landscape, -1=reverse-landscape). Read-only.

**`A01(String str, Collection collection)` (lines 36-87):** LAYOUT-orientation
toggler. Walks a Collection of ViewGroups, finds LinearLayouts, and:
- For "portrait" → sets `linearLayout.setOrientation(1)` (vertical) AND
  modifies `topMargin` of each child (saving the original in a WeakHashMap
  first). Lines 51-69.
- Otherwise → restores the saved `topMargin` values and sets
  `setOrientation(0)` (horizontal). Lines 70-83.

**SIDE EFFECTS:** Mutates view layout params + orientation of arbitrary
LinearLayouts. Calling this on Reels would scramble the UFI side-button
layout. **DO NOT call A01 from VBP.**

**`A02(String str)` (lines 95-139):** The actual `setRequestedOrientation`
helper. Quoting the LANDSCAPE branch (lines 101-108):
```java
if (str.equalsIgnoreCase("LANDSCAPE")) {
    Activity activity = this.A00;
    if (activity.getRequestedOrientation() != 0 && 6 != activity.getRequestedOrientation()) {
        this.A00.setRequestedOrientation(0);  // SCREEN_ORIENTATION_LANDSCAPE
    } else if (str.equalsIgnoreCase("PORTRAIT") && 1 != this.A00.getRequestedOrientation() && this.A01 != null) {
        this.A00.setRequestedOrientation(1);  // unreachable: outer if is LANDSCAPE
    }
    z = true;
    interfaceC116596ua2 = this.A02;
    if (interfaceC116596ua2 != null) {
        iA00 = A00();
        if (iA00 != 0) {
            i = 2131981495;
        } else if (iA00 != 1) {
            i = 2131981494;
        } else {
            i = 2131981496;
        }
        interfaceC116596ua2.GTw(i);  // callbacks the UI controller with an R.string label
    }
}
```
PORTRAIT branch (lines 121-135) is similar:
```java
} else if (str.equalsIgnoreCase("PORTRAIT")) {
    this.A00.setRequestedOrientation(1);  // SCREEN_ORIENTATION_PORTRAIT
    z = true;
    interfaceC116596ua2 = this.A02;
    if (interfaceC116596ua2 != null) {
        ...
        interfaceC116596ua2.GTw(i);
    }
}
```

**Side effects of `A02`:**
1. Calls `activity.setRequestedOrientation(int)` — desired.
2. Calls `interfaceC116596ua2.GTw(int)` — invokes a UI-controller callback
   (InterfaceC116596ua2 — see `p002X/InterfaceC116596ua2.java:18`). `GTw` takes
   an R.string id (2131981494/1495/1496) — looks like a tab-bar tooltip /
   accessibility announcement ("Rotate to landscape" etc.). The interface
   also declares 20+ other UI-control methods (`DNP`, `GR2`, `GUG`, `Gxa`,
   `H3K`, click-listener setters `GkC`..`GkM`).

**Critical: `C99744f1m` is NOT used by Instagram Reels at all.** The ONLY
constructing caller is the Facebook cloud-gaming activity
`com/facebook/cloudstreaming/backends/BaseHorizon2DActivity.java:452`:
```java
C99744f1m c99744f1m = new C99744f1m();
```
(verified by `rg "C99744f1m\("` — single hit). So `C99744f1m` was built for
Horizon cloud-game UI rotation; `A02` works but the surrounding state
(`this.A02` InterfaceC116596ua2, `this.A01` InterfaceC116563twl,
`this.A04` WeakHashMap) is wired by Horizon. Calling `C99744f1m.A02` from VBP
would either NPE on `this.A00` (Activity, never set if we just `new` it) or
silently no-op the `interfaceC116596ua2.GTw(i)` callback since `this.A02` is
null.

**Verdict for Q2.a:** `C99744f1m.A02` is functionally usable but requires
constructing the helper with an Activity, AND its side-effect callback
`interfaceC116596ua2.GTw(i)` would be skipped (null `this.A02` — fine, no
crash, no UI side-effect). However, the worklog 3-e reference
"`C99744f1m.A01 (lines 104,106,122)`" is **mis-labeled** — lines 104, 106,
122 are inside `A02`, not `A01`. `A01` is the layout-orientation toggler
(with heavy view-mutation side effects) and MUST NOT be called.

### Q2.b. `AbstractC186396mW` — clean, pure static, RECOMMENDED

Full class at **`p002X/AbstractC186396mW.java`** (21 lines):
```java
public abstract class AbstractC186396mW {
    public static final void A00(Activity activity, int i) {
        if (activity != null) {
            try {
                activity.setRequestedOrientation(i);
            } catch (IllegalStateException e) {
                if (!"Only fullscreen activities can request orientation".equals(e.getMessage())) {
                    throw e;
                }
                C21630Ke.A0K("FixedOrientationCompat", "%s hit fixed orientation exception",
                             e, AbstractC178105m.A00(activity.getClass()));
            }
        }
    }
}
```

**Side effects:** Only `activity.setRequestedOrientation(i)`. The catch
handles Android 12+ "Only fullscreen activities can request orientation"
IllegalStateException (thrown when an activity has
`android:resizeableActivity="true"` AND is in multi-window / not fullscreen).
On that exception, it logs via `C21630Ke.A0K` (QPL/buck logger — fire-and-
forget, no UI side effect) and swallows. No persistence, no analytics event,
no view mutation, no Fragment requirement.

**Safe to call from a non-Fragment (VBP) given an Activity.** No Fragment
context needed. Just pass `Activity` + the orientation int.

### Q2.c. Recommendation

**Use `AbstractC186396mW.A00(activity, orientation)`** — cleanest, no side
effects, has the Android-12 multi-window guard built in.

From `VBP.FSS` (enter fullscreen, line 116 of `p002X/VBP.java`):
```java
AbstractC186396mW.A00(this.A02.A0B.A04, 0);  // SCREEN_ORIENTATION_LANDSCAPE
```
From `VBP.EvT` (exit fullscreen, line 47):
```java
AbstractC186396mW.A00(this.A02.A0B.A04, 2);  // SCREEN_ORIENTATION_USER (allow rotation)
// or 1 for SCREEN_ORIENTATION_PORTRAIT to force portrait
```

**Activity access path verified:** `VBP.A02` (RE7, `p002X/RE7.java:11-25`) →
`re7.A0B` (C257899eY, `p002X/C257899eY.java:48-53`) → `c257899eY.A04`
(`FragmentActivity`, line 53). So `this.A02.A0B.A04` IS the hosting
`InstagramMainActivity` instance.

(Note: prior worklog 3-e also listed `AbstractC104253ij1` and `SF7` as
candidate helpers — neither file exists in the jadx output. Likely name
drift between ReVanced versions. `AbstractC186396mW` is the right one to
use.)

---

## Q3. `IgFragmentActivity.A1g()` — Reels-on-top detection

### Q3.a. What `A1g()` returns

**`com/instagram/base/activity/IgFragmentActivity.java:685-687`:**
```java
public Fragment A1g() {
    return A1a().A0O(R.id.layout_container_main);
}
```
Returns the **top-level Fragment** hosted in `R.id.layout_container_main` —
the activity's main fragment-container slot. NOT a Reels-specific check.

In `InstagramMainActivity`, the main container hosts the **tab host fragment**
(`C0ZS`-managed `IgSwipeableTabHostFragment` / `MainTabActivity`-equivalent —
`this.A06 = new C0ZS(...)` at `InstagramMainActivity.java:1823, 2149, 2596,
2926`). The Reels/Clips viewer (`ClipsTabFragment` = `p002X/C27528AFt.java`)
is a CHILD fragment of the tab host, hosted in a nested ViewPager2 — NOT in
`R.id.layout_container_main` directly.

**Therefore `A1g() instanceof ClipsTabFragment` is ALWAYS FALSE in
InstagramMainActivity.** `A1g()` returns the tab host (e.g. an
`IgSwipeableTabHostFragment` instance), not ClipsTabFragment.

### Q3.b. Existing callers of `A1g()` — none use it for Reels detection

Grepping `A1g\(\)` in IgFragmentActivity itself:
- **line 316:** `InterfaceC164100c interfaceC164100cA1g = igFragmentActivity.A1g();`
  → used for key-event dispatch (`((AAS) ...).DjM(i, keyEvent)`).
- **line 1087:** `Fragment fragmentA1g = A1g();` → used for back-press
  dispatch (`((InterfaceC109844mci) fragmentA1g).onBackPressed()`).

Both are generic "current top fragment" dispatchers, neither Reels-specific.
Cross-file matches for `A1g()` (rg over `/sources/`) hit unrelated classes
(`LiveTreeUserDict`, `Media`, `ImmutablePando*`, `C15R`) — none of them are
the IgFragmentActivity.A1g (different `this` receiver).

**Verdict for Q3.a:** `A1g()` is NOT a reliable "Reels is on top" check.
It returns the wrong fragment layer (tab host, not the reels subtab).

### Q3.c. Better Reels-on-top checks

**Option 1 (cleanest, IG's own primitive): `C0ZS.A0B() == EnumC108993ky.A08`**

`C0ZS` is the MainTabController held by InstagramMainActivity as `this.A06`.
`p002X/C0ZS.java:536-542`:
```java
public final EnumC108993ky A0B() {
    C25650Zq c25650Zq = this.A02;
    if (c25650Zq != null) {
        return c25650Zq.A06();
    }
    throw new IllegalStateException("Required value was null.");
}
```
Returns the **current top tab enum**. Per **`p002X/EnumC108993ky.java:83`**:
```java
A08 = new EnumC108993ky("CLIPS", "fragment_clips", ..., 6, R.id.clips_tab, R.drawable.tab_clips_drawable, 2131957876);
```
So the check is:
```java
InstagramMainActivity activity = (InstagramMainActivity) this.A02.A0B.A04;
boolean reelsOnTop = (activity.A06 != null) && (activity.A06.A0B() == EnumC108993ky.A08);
```
This is the SAME primitive IG uses internally — see `C0ZS.java:215`:
```java
if (c0zs.A0B() == EnumC108993ky.A0B && enumC108993ky == EnumC108993ky.A0A) {
```
`A06` field declared at `InstagramMainActivity.java:??` — confirmed
constructed at lines 1823, 2149, 2596, 2926.

**Option 2 (UI-state-based, IG's own gate at onConfigurationChanged):
`C26630bQ.A05(activity)`**

**`p002X/C26630bQ.java:140-151`:**
```java
public static final boolean A05(Activity activity) {
    View viewFindViewById = activity.findViewById(R.id.tab_bar);
    View viewFindViewById2 = activity.findViewById(R.id.ls_nav_bar);
    Drawable background = viewFindViewById != null ? viewFindViewById.getBackground() : null;
    ColorDrawable colorDrawable = background instanceof ColorDrawable ? (ColorDrawable) background : null;
    Drawable background2 = viewFindViewById2 != null ? viewFindViewById2.getBackground() : null;
    ColorDrawable colorDrawable2 = background2 instanceof ColorDrawable ? (ColorDrawable) background2 : null;
    if (colorDrawable == null || colorDrawable.getColor() != AbstractC26520bF.A0X(C26560bJ.A01(activity), R.attr.igds_color_primary_background)) {
        return colorDrawable2 != null && colorDrawable2.getColor() == AbstractC26520bF.A0X(C26560bJ.A01(activity), R.attr.igds_color_primary_background);
    }
    return true;
}
```
Returns true if EITHER `R.id.tab_bar` OR `R.id.ls_nav_bar` has its background
color equal to `igds_color_primary_background`. **This is the EXACT gate IG
itself uses at `InstagramMainActivity.A1p` (onConfigurationChanged) line 4111:**
```java
if (C26630bQ.A05(this)) {
    C26630bQ.A04(this, userSession2, ...igds_color_clips_tab_bar_background, ...igds_color_reels_tab_bar_separator);
    c26630bQ.A09(this, ...igds_color_clips_tab_bar_icon);
    c26630bQ.A0A(this, userSession2, ...igds_color_clips_tab_bar_icon);
} else {
    c26630bQ.A08(this);
    c26630bQ.A0A(this, userSession2, AbstractC26520bF.A06(this));
    ...
}
```
**Caveat:** `A05` returns true if tab_bar OR ls_nav_bar color matches
`igds_color_primary_background`. When Reels is active, `C2ZS.A01:42` calls
`C26630bQ.A04` with `igds_color_clips_tab_bar_background` (NOT
`igds_color_primary_background`). So `A05` is reliable ONLY IF
`igds_color_clips_tab_bar_background` resolves to a DIFFERENT color int than
`igds_color_primary_background`. In a standard IG dark theme, both are likely
`#000000` → `A05` returns true in BOTH the home-tab and reels-tab cases. The
`else` branch at 4115 would never fire — which is suspicious. Without res/
access (apktool needed), we cannot confirm whether these two attrs resolve to
distinct ints. **Treat `C26630bQ.A05` as a "tab bar is currently opaque black"
check, not a strict "Reels is on top" check.**

**Option 3 (lifecycle-based, recommended): gate on `ClipsTabFragment.onResume`
→ `C2ZS.A02` is already being called**

Per 3-a and confirmed at **`p002X/C27528AFt.java:855-867`**:
```java
public final void onResume() {
    AbstractC64641vd.A01("ClipsTabFragment.onResume", 1267912090);
    ...
    super.onResume();
    C2ZS.A02(requireActivity(), this, (UserSession) this.A0A.getValue(), true, false);
}
```
And `onStop` at line 870-881:
```java
public final void onStop() {
    AbstractC64641vd.A01("ClipsTabFragment.onStop", -150050157);
    ...
    super.onStop();
    C2ZS.A00.A0B(requireActivity(), this, (UserSession) this.A0A.getValue(), true, false);
}
```
So **`C2ZS.A02(...)` fires exactly when Reels gains focus, and
`C2ZS.A0B(...)` fires exactly when Reels loses focus.** Any patches we apply
inside `C2ZS.A01` (called by A02 at `p002X/C2ZS.java:108-111`) are
ALREADY gated to "Reels is the active tab" by virtue of the lifecycle call
site. We do NOT need an additional runtime "is Reels on top" check for the
window-chrome patches.

**Recommended strategy:**
- For window-chrome patches (Features A, B): patch `C2ZS.A01` directly — its
  call site (`ClipsTabFragment.onResume:860`) is already the "Reels is on top"
  gate. No need for `A1g()` or `A0B()`.
- For runtime gates that fire from non-lifecycle code paths (e.g., our VBP
  orientation hook firing while the user is mid-scroll): use
  `C0ZS.A0B() == EnumC108993ky.A08` via `activity.A06` (Option 1).
- `C26630bQ.A05(activity)` is OK as a fallback but depends on
  `igds_color_clips_tab_bar_background` != `igds_color_primary_background`
  (verify via apktool).
- **DO NOT use `IgFragmentActivity.A1g()` for Reels detection** — returns the
  tab host fragment, not ClipsTabFragment.

---

## Q4. Config-change resilience

### Q4.a. Does `InstagramMainActivity` declare `android:configChanges`?

**Cannot verify from jadx output** — `jadx-out/` contains only `sources/` and
an empty `resources/` directory (no `AndroidManifest.xml`). **Flagged for
apktool.**

**Indirect evidence that `orientation` IS in `configChanges`:**
`IgFragmentActivity.onConfigurationChanged` is implemented at
**`com/instagram/base/activity/IgFragmentActivity.java:1962-1969`**:
```java
@Override // androidx.appcompat.app.AppCompatActivity, androidx.activity.ComponentActivity, android.app.Activity, android.content.ComponentCallbacks
public void onConfigurationChanged(Configuration configuration) {
    C109103l9.A0Q(configuration);
    C0UM c0um = this.A0B;
    I2E i2e = new I2E(1, c0um, configuration);
    Q45 q45 = new Q45(5, configuration, c0um);
    Integer num = AnonymousClass006.A00;
    C0UM.A00(c0um, num, num, "onConfigurationChanged", q45, i2e);
}
```
If `orientation` were NOT in `configChanges`, Android would RECREATE the
activity (`onDestroy` + `onCreate`) instead of calling
`onConfigurationChanged`. Since IG implements `onConfigurationChanged` (and
`InstagramMainActivity.A1p` overrides it at line 4078), the manifest must
declare at least `orientation` (and likely `screenSize|keyboardHidden` per
common IG-style manifests). **apktool must confirm.**

### Q4.b. What `InstagramMainActivity.A1p` (onConfigurationChanged) re-paints

**`com/instagram/mainactivity/InstagramMainActivity.java:4078-4140+`:**
```java
@Override // com.instagram.base.activity.BaseFragmentActivity, com.instagram.base.activity.IgFragmentActivity
public final void A1p(Configuration configuration, AbstractC91672y8 abstractC91672y8) {
    ...
    if (AbstractC56737Lka.A00(configuration2, configuration)) {  // config actually changed
        ...
        AbstractC30520hh abstractC30520hhBbf = Bbf();
        if (userSession2 != null) {
            if (abstractC30520hhBbf != null) {
                C26630bQ c26630bQ = C26630bQ.A00;
                if (C26630bQ.A05(this)) {
                    C26630bQ.A04(this, userSession2,
                        AbstractC26520bF.A0Z(this, R.attr.igds_color_clips_tab_bar_background),
                        AbstractC26520bF.A0Z(this, R.attr.igds_color_reels_tab_bar_separator));
                    c26630bQ.A09(this, AbstractC26520bF.A0Z(this, R.attr.igds_color_clips_tab_bar_icon));
                    c26630bQ.A0A(this, userSession2, AbstractC26520bF.A0Z(this, R.attr.igds_color_clips_tab_bar_icon));
                } else {
                    c26630bQ.A08(this);
                    c26630bQ.A0A(this, userSession2, AbstractC26520bF.A06(this));
                    ...
                }
            }
            ...
        }
    }
    super.A1p(configuration, abstractC91672y8);
    ...
}
```

What gets re-painted on rotation when Reels is on top (`A05 == true`):
1. **`C26630bQ.A04(this, userSession2, igds_color_clips_tab_bar_background, igds_color_reels_tab_bar_separator)`**
   at line 4112 — paints `R.id.tab_bar`, `R.id.ls_nav_bar`,
   `R.id.tab_bar_shadow`, `R.id.ls_nav_bar_shadow` with OPAQUE
   `igds_color_clips_tab_bar_background` (see `C26630bQ.java:120-138`).
   → **UNDOES any transparent-nav-bar patch on those views.**
2. **`C26630bQ.A09(this, igds_color_clips_tab_bar_icon)`** at line 4113 —
   re-paints the tab icons with the (white) clips color.
3. **`C26630bQ.A0A(this, userSession2, igds_color_clips_tab_bar_icon)`** at
   line 4114 — same, gated by `C0ZW.A04(userSession)`.

What is NOT re-painted (verified by reading A1p lines 4078-4180):
- `window.setDecorFitsSystemWindows(...)` — NOT called in A1p. The
  Window's decor-fit flag is a Window property that survives config changes.
  → **Our `setDecorFitsSystemWindows(false)` patch survives rotation.**
- `window.setStatusBarColor(...)` / `window.setNavigationBarColor(...)` —
  NOT directly called in A1p. These Window colors also survive config
  changes.
- `AbstractC54451fC.A04/A06` (status bar transparent / color) — NOT called
  in A1p. Survives.
- `C54511fI.A04/A06` (nav bar color/contrast) — NOT called in A1p.
  Survives.
- `decorView.setBackgroundColor(...)` — NOT called in A1p (only in
  `C2ZS.A01:86`, which is NOT triggered by rotation — only by
  `ClipsTabFragment.onResume`).
- `android.R.id.content.setBackgroundColor(...)` — NOT called in A1p (only
  in `C2ZS.A05:131`, also gated by `ClipsTabFragment.onResume`).

**So the only patches at risk on rotation are the ones touching
`R.id.tab_bar`, `R.id.ls_nav_bar`, `R.id.tab_bar_shadow`,
`R.id.ls_nav_bar_shadow` directly — i.e., the BOTTOM NAV BAR patches
(Feature B).**

### Q4.c. Survival strategy

The patches that need re-application after rotation:
- Any patch that sets `R.id.tab_bar` / `R.id.ls_nav_bar` background to
  transparent (Feature B).

The cleanest fix: **patch `C26630bQ.A04` itself** to use a transparent color
when Reels is on top, instead of patching the caller. Since `A04` is the
single chokepoint called from BOTH `C2ZS.A01:42` (Reels enter) AND
`InstagramMainActivity.A1p:4112` (rotation re-paint), patching it once
covers both paths. Concretely:
- Replace `activity.getColor(i)` (line 124 / 127) with `0` (transparent)
  when `C26630bQ.A05(activity)` is true (or pass a "transparent" flag).
- Or short-circuit the entire method (early return) when Reels is on top.

Alternative: **patch `InstagramMainActivity.A1p` after line 4120** to re-apply
our transparent-nav patches (call `C26630bQ.A04` with a transparent color, or
null out the backgrounds). Less clean — adds a second call site.

The Window-level patches (status bar transparent, nav bar color,
`setDecorFitsSystemWindows(false)`) survive rotation without intervention
— no re-apply needed.

### Q4.d. Rotation lifecycle flow

When VBP.FSS calls `AbstractC186396mW.A00(activity, 0)` (LANDSCAPE):
1. Android fires `onConfigurationChanged` on `IgFragmentActivity` (line 1962).
2. Dispatches through `C0UM` lifecycle to `InstagramMainActivity.A1p` (4078).
3. A1p re-paints the tab bar via `C26630bQ.A04` (4112) — bottom-nav patch
   undone here.
4. A1p calls `super.A1p` (4139) → `AppCompatActivity.onConfigurationChanged`.
5. A1p re-syncs ViewPager2 state (4141+).
6. The ViewFrameLayout's `onSizeChanged` fires (new width/height after
   rotation) → `C25U.A00` recomputes TextureView layout → video re-fills.
7. `ClipsTabFragment.onResume` does NOT re-fire on rotation (only on tab
   switch) — so `C2ZS.A02` is NOT re-called. The window-chrome state set
   by `C2ZS.A01` on tab enter SURVIVES, except for the bottom nav bar which
   A1p re-paints.

So on rotation, the chain of survival:
- ✅ Window flags (decor fits, status/nav color) — survive (Window property).
- ✅ Status bar transparent — survives (Window property).
- ✅ Video TextureView force-fill — re-applied automatically by
  `AbstractC210917ky.onSizeChanged` → `C25U.A00`.
- ❌ Bottom nav bar background — re-painted opaque by A1p:4112. Must
  re-apply via patching `C26630bQ.A04`.
- ✅ Top status-bar color set by `AbstractC54451fC.A04` (in C2ZS.A01:102) —
  this sets `window.setStatusBarColor(primary_bg)` which IS a Window property
  and survives rotation. So our patch to make status bar truly transparent
  (skip A04, or call A02 instead) also survives.

---

## Summary verdicts

| Sub-Q | Verdict |
|-------|---------|
| Q1.a — what `A01=1.0d` does | Sets the ZOOM→FIT fallback threshold to 100% in `C25U.A00` — effectively "always ZOOM, never fall back to letterbox". |
| Q1.b — STRETCH or ZOOM-CROP | **ZOOM-CROP** (preserves aspect ratio, crops overflow via translation). NOT a stretch/distort. |
| Q1.c — 9:16 fills screen height | **YES, if the container extends edge-to-edge.** Traced math: 9:16 video in 1080×2400 container → TextureView sized 1350×2400, cropped 135px each side, fills full height. Force-fill alone does NOT solve black strips — those come from container bounds. |
| Q1.d — feed binder pattern | `C8NA.java:187` calls `mediaFrameLayout.setForceFillTextureScaling(z5)` per-feed-config. Clips viewer (C3EO) inherits default 0.25d. |
| Q2.a — C99744f1m | `A02(str)` works but bundled with cloud-gaming UI (`BaseHorizon2DActivity` is the only constructing caller). `A01(str,coll)` MUTATES view layout params — DO NOT call. Worklog 3-e's "A01 at lines 104/106/122" is mislabeled (those lines are inside A02). |
| Q2.b — AbstractC186396mW | **RECOMMENDED.** Pure static, just calls `activity.setRequestedOrientation(i)` with Android-12 multi-window guard. No side effects. |
| Q2.c — VBP call | `AbstractC186396mW.A00(this.A02.A0B.A04, 0)` for LANDSCAPE in FSS, `(…, 2)` for USER in EvT. Path: VBP→RE7→C257899eY→FragmentActivity A04 (verified). |
| Q3.a — A1g() reliability | **NOT reliable.** Returns the tab host fragment (in `R.id.layout_container_main`), not ClipsTabFragment. `A1g() instanceof ClipsTabFragment` is always false. |
| Q3.b — callers | Only 2 internal callers (key-event dispatch at :316, back-press at :1087). Both generic "top fragment" use. |
| Q3.c — better check | **Use `C0ZS.A0B() == EnumC108993ky.A08`** (via `activity.A06`) for runtime checks. For window-chrome patches, **patch `C2ZS.A01` directly** — its call site `ClipsTabFragment.onResume:860` is already the "Reels on top" gate. |
| Q4.a — configChanges | Cannot verify (jadx has no manifest). Indirect evidence: `onConfigurationChanged` is implemented → `orientation` IS in configChanges. **apktool must confirm.** |
| Q4.b — what's re-painted | A1p:4112 re-paints `R.id.tab_bar` + `R.id.ls_nav_bar` opaque via `C26630bQ.A04`. Window flags / status-bar color / `setDecorFitsSystemWindows` are NOT re-touched. |
| Q4.c — survival strategy | Window-level patches survive. Bottom-nav patches need re-apply — cleanest is to **patch `C26630bQ.A04` itself** (single chokepoint for both C2ZS.A01 and A1p:4112 callers). |
| Q4.d — rotation flow | VBP.FSS → setRequestedOrientation(0) → onConfigurationChanged → A1p re-paints tab bar (undo bottom-nav patch) → onSizeChanged re-fills TextureView. ClipsTabFragment.onResume does NOT re-fire (no C2ZS.A02 re-call). |

## Open gaps for next agent

1. **apktool required:** confirm `android:configChanges` for
   `InstagramMainActivity` in AndroidManifest.xml — must include
   `orientation|screenSize` (else rotation recreates the activity and ALL
   patches are lost, not just bottom-nav).
2. **apktool required:** confirm `igds_color_clips_tab_bar_background` int
   value vs `igds_color_primary_background` int value — if identical,
   `C26630bQ.A05` cannot distinguish "Reels active" from "Home active"
   (Option 2 in Q3).
3. **C3EO constructor:** read `p002X/C3EO.java` fully to find the cleanest
   insertion point for `setForceFillTextureScaling(true)` (after super() in
   constructor OR override `setVideoSource` to flip the flag on each new
   reel).
4. **VBP.FSS landscape gate:** per 3-e, runtime aspect-ratio detection is
   needed (no `Media.isLandscape` accessor). The gate `videoW > videoH` must
   be checked BEFORE calling `AbstractC186396mW.A00(activity, 0)` in FSS —
   otherwise portrait videos would also force-rotate on tap.
5. **C26630bQ.A04 patch shape:** decide between (a) early-return when Reels
   on top (transparent tab bar — icons float over video) or (b) replace the
   color arg with transparent. Option (a) is simpler but loses the tab icon
   re-paint (icons may appear with wrong color after rotation). Option (b)
   preserves icon paint but makes the bar transparent.
