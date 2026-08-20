# Task 4-d — Comment Sheet Runtime Branch + Dimming Refinement

**Scope:** Confirm exactly which `BottomSheetFragment.onViewCreated` branch runs for
the Reels comment sheet, read `EPN` (dimming animator) + `C109193lI` (scrim) +
`AbstractC95704cDl` (dimming view def) + `FrostedOverlayView` (reuse for true blur),
and produce a precise list of patch points for Feature C (translucent comment sheet).

Decompiled source root: `/home/z/insta-src/jadx-out/sources/`

---

## Q1 — `BottomSheetFragment.onViewCreated` runtime branch for Reels

File: `com/instagram/igds/components/bottomsheet/BottomSheetFragment.java`

### Branch structure (lines 1524–1660)

The sheet panel background is chosen by a 4-way conditional. Key lines:

```java
// line 1524
if (!C0PQ.A06(context, getSession())) {
    // ----- BRANCH A: prism DISABLED -----
    viewGroup = this.bottomSheetContainer;
    // (inverted-null-check; enters body when viewGroup != null)
    ...
    // line 1559 (the `else` of `if (A00(this).A0M != null)`)
    drawable = A00(this).A0H;                       // line 1560
    if (drawable == null) {
        drawable = context.getDrawable(R.drawable.igds_bottom_sheet_background_prism);  // line 1562
    }
    AbstractC27310cW.A03(drawable, viewGroup, i2);   // line 1565 = setBackground(drawable)
    ...
} else if (A00(this).A0h == AnonymousClass006.A0C) { // line 1599 (A0h==2)
    // ----- BRANCH B: elevated_background GradientDrawable -----
    GradientDrawable gradientDrawable = new GradientDrawable();           // line 1607
    gradientDrawable.setColor(AbstractC26520bF.A00(context));             // line 1608 = igds_color_elevated_background
    gradientDrawable.setCornerRadius(dimension);                          // line 1609
    AbstractC27310cW.A03(gradientDrawable, viewGroup10, -415685939);      // line 1610 = setBackground(gradientDrawable)
    ...
} else if (A00(this).A0H == null || (viewGroup = this.bottomSheetContainer) == null) {  // line 1615
    // ----- BRANCH C: custom-view OR mutate-existing-background -----
    view2 = A00(this).A0M;                                                // line 1616
    if (view2 != null) { /* V1l wrapper path */ }
    else {
        viewGroup2 = this.bottomSheetContainer;                          // line 1636
        background = viewGroup2.getBackground();                         // line 1640
        Drawable drawableMutate3 = background.mutate();                  // line 1644
        C109103l9.A0D(drawableMutate3);
        drawableMutate3.setColorFilter(color2, PorterDuff.Mode.SRC_IN);  // line 1646 = tint with color2
    }
} else {
    // ----- BRANCH D: custom Drawable A0H -----
    drawable = A00(this).A0H;                                            // line 1649
    AbstractC27310cW.A03(drawable, viewGroup, i2);                       // line 1651
    ...
}
```

### Defaults that decide which branch

`C50186J5g` constructor (`p002X/C50186J5g.java:160`):

```java
this.A0h = AnonymousClass006.A00;   // = Integer 0  (see AnonymousClass006.java:76)
```

Field defaults on `C50186J5g`:
- `A0h` (Integer style enum) = `0` (`AnonymousClass006.A00`)
- `A0H` (Drawable custom bg) = `null`
- `A0M` (View custom bg) = `null`
- `A05` (int color2) = `0` → resolved at runtime to `context.getColor(AbstractC26520bF.A0D(context))` at line 1494 (= `igds_color_elevated_background`, opaque dark)

`AnonymousClass006` constants (`p002X/AnonymousClass006.java:76-78`):
- `A00 = 0` (default)
- `A01 = 1` (prism?)
- `A0C = 2` (elevated_background GradientDrawable style)

### Does C54625Krc / QF1 override any of these?

Grep results — no override found:
- `C54625Krc.java`: only `if (A0A().A0M == null)` read at line 500 (no setter for A0h/A0H/A0M).
- `QF1.java`: only `c97707dfu.A06 = AnonymousClass006.A00` (different field `A06`, unrelated to sheet style).
- `AbstractC27985AXi.java` (QF1's superclass): no setter.

Conclusion: **the Reels comment sheet uses default `A0h=0`, `A0H=null`, `A0M=null`.**

### Which branch executes for Reels?

Depends on `C0PQ.A06(context, getSession())` (`p002X/C0PQ.java:91`):

```java
public static final boolean A06(Context context, AbstractC95633Au abstractC95633Au) {
    if (abstractC95633Au instanceof UserSession && C64121un.A0D(context)) {
        UserSession userSession = (UserSession) abstractC95633Au;
        if (C102743at.A05(userSession) || C102743at.A06(userSession)) {
            return true;   // prism ENABLED
        }
    }
    return false;
}
```

- **If prism ENABLED (returns true → `!true = false` at line 1524):** Falls to `else if (A0h == A0C)` (line 1599). `0 != 2` → false. Falls to `else if (A0H == null || ...)` (line 1615) → TRUE. Enters **BRANCH C**. `A0M == null` → goes to mutate-existing-background path (lines 1635-1646): `setColorFilter(color2, SRC_IN)` where `color2 = igds_color_elevated_background` (opaque dark). Sheet panel = opaque dark tint over XML's default background.
- **If prism DISABLED (returns false → `!false = true` at line 1524):** Enters **BRANCH A**. `A0H == null` → falls back to `context.getDrawable(R.drawable.igds_bottom_sheet_background_prism)` (line 1562) → `setBackground(drawable)` (line 1565). Sheet panel = prism drawable (likely opaque).

**Production IG v435.0.0.37.76 almost certainly has prism ENABLED** (it's the modern IgdsBottomSheet default), so the runtime branch is **BRANCH C** → `setColorFilter(color2, SRC_IN)` at `BottomSheetFragment.java:1646`.

### Q1 patch points for translucency

Three layered patch options (any one suffices for branch C; covers all branches if applied to `color2`):

1. **Universal (preferred):** Set `C50186J5g.A05` (= `color2`) to a translucent color when constructing the Reels comment sheet's builder (e.g. `0xCC000000` for 80% black). Affects lines 1557, 1596, 1646 (all `setColorFilter(color2, SRC_IN)` calls). Does NOT affect Branch A's prism drawable path (line 1565) — for that we'd also need patch #3.
2. **Targeted (line 1646):** Replace `color2` literal in `setColorFilter(color2, PorterDuff.Mode.SRC_IN)` with `(color2 & 0x00FFFFFF) | 0xCC000000` (force 80% alpha). Only Branch C (Reels production path).
3. **Branch A fallback (line 1562):** Replace `R.drawable.igds_bottom_sheet_background_prism` lookup with a translucent drawable, OR intercept `AbstractC27310cW.A03(drawable, viewGroup, i2)` at line 1565 to wrap `drawable` in a translucent layer.

**Code vs resource:** Line 1562 is a **resource drawable** lookup. Line 1608 (GradientDrawable color) and line 1646 (`setColorFilter`) are **code-level color assignments**. Branch C (Reels production) is code-level.

---

## Q2 — `EPN` dimming animator (read fully)

File: `p002X/EPN.java` (1169 lines).

`EPN` is the "WatchAndCommentViewManager" — handles ALL visual side-effects of opening the comment sheet on a clips/Reels viewer: shrinks the video, repositions the ufi/avatar/caption, fades the navigation bar, AND animates `clips_media_dimming_view`.

### Key methods

| Method | Line | Purpose |
|---|---|---|
| `A0A(EPN epn, int i)` (static) | 293 | Slide handler — applies all per-frame visual updates for sheet position `i` (= sheet top Y). Called from `EhI` (line 1095) and `EhC` (line 809). |
| `A04()` (private) | 198 | Returns the `clips_media_dimming_view` via `findViewById(R.id.clips_media_dimming_view)` on the current ReboundViewPager page (fallback to root view). |
| `A05(EPN)` (static) | 205 | Returns the current clips item root view. |
| `A0C(float f)` | 599 | Stores target slide ratio. |
| `EhB(EnumC109213lK)` | 624 | "Begin open" callback — restores hidden views. |
| `EhC()` | 655 | **"Close" callback** — called from `VBP.EvT:80` when sheet closes. Restores video to full visibility. |
| `EhI(int i)` | 837 | **"Open/slide" callback** — called from `VBP.FSS:143` on every slide frame. Drives the dimming animation. |

### What `EPN` does to the video when comment sheet opens

When the sheet opens, `EPN`:
1. **Shrinks/repositions the video** (lines 412-543 in `A0A`): computes a clip rect via `C37971EPk` (line 438) and applies it to `epn.A0C` (the media container) via `AbstractC27310cW.A0c(view18, c37974EPn, ...)` (line 566). The video shrinks to make room for the sheet.
2. **Fades the ufi/avatar/navigation bar** (lines 485-510): scales and translates the like/comment/share buttons, audio attribution, etc.
3. **Animates `clips_media_dimming_view` alpha** (line 534 — see below). The dimming view is a **plain View** between the video and the sheet panel.

### Quote of line 534 (the dimming alpha animation)

```java
// p002X/EPN.java:532-535  (inside A0A(EPN epn, int i))
View viewA04 = epn.A04();                                  // returns clips_media_dimming_view
if (viewA04 != null) {
    AbstractC27310cW.A05(viewA04, 1.0f - fA05, -2048684427);  // = viewA04.setAlpha(1.0f - fA05)
}
```

`AbstractC27310cW.A05` is verified at `p002X/AbstractC27310cW.java:44-47`:

```java
public static void A05(View view, float f, int i) {
    A0d(view, "setAlpha", i);
    view.setAlpha(f);
}
```

### What alpha does it set? (0 = invisible, 1 = opaque)

`fA05` is computed at lines 359-368:

```java
float f5 = i;                                              // line 349 (i = sheet top Y, passed from VBP.FSS)
...
float fA05 = 1.0f;                                         // line 360
if (iA07 - f7 != 0.0f) {                                   // line 361 (iA07 = epn.A0A = screen height; f7 = epn.A02 = expanded/resting Y)
    float f8 = f5 - f7;
    int iA08 = epn.A0A;
    if (iA08 <= 0) { iA08 = A03(epn); }
    fA05 = AbstractC131904gp.A03(f8 / (iA08 - epn.A02), 0.0f, 1.0f);   // clamp(0,1)
}
```

- `i` = sheet top Y position (from `VBP.FSS` → `AnonymousClass940.Fjg:548` `iA05 = A05(this) - slide_offset`)
- `epn.A02` = expanded/resting Y offset = `screen_height * (1 - 0.6)` = `0.4 * screen_height` (since `EPN` is constructed at `VBP.java:131` with `0.6f` as max opening ratio)
- `epn.A0A` = full screen height

**Result:**
- Sheet **fully OPEN** (`i = epn.A02`): `fA05 = 0` → `1 - fA05 = 1.0` → **dimming view alpha = 1.0 (FULLY OPAQUE BLACK)**
- Sheet **fully CLOSED** (`i = epn.A0A`): `fA05 = 1` → `1 - fA05 = 0.0` → **dimming view alpha = 0.0 (TRANSPARENT)**

**Confirmed by `EhC()` (close callback) line 803:** explicitly sets dimming view alpha to `0.0f` (defensive reset on close):

```java
// p002X/EPN.java:801-804
View viewA04 = A04();
if (viewA04 != null) {
    AbstractC27310cW.A05(viewA04, 0.0f, -383499978);   // setAlpha(0.0f)
}
```

So when comment sheet is fully open, the `clips_media_dimming_view` IS a fully opaque black layer between the video and the sheet panel. 3-d's finding was correct.

### `EhI` and `EhC` (called from VBP.FSS:143 / VBP.EvT:80)

`VBP.java` (`p002X/VBP.java`):

- `VBP.EvT(AnonymousClass950)` at line 47: called when the comment sheet **closes**. Restores visibility (ufi alpha 1, navigation bar alpha 1, etc.) at lines 59-77, then calls `epn.EhC()` at line 80 (which clears the dimming view).
- `VBP.FSS(int i, int i2)` at line 116: called when the comment sheet **opens/slides**. Constructs a new `EPN` at line 131 (`new EPN(viewA06, ..., 0.6f, false)`) if needed, then calls `epn.EhI(i)` at line 143 with `i = sheet top Y`.

### Q2 patch points (keep video visible behind comment sheet)

To neutralize the dimming view when comment sheet opens:

**Primary patch — `EPN.java:534`:**
```java
AbstractC27310cW.A05(viewA04, 1.0f - fA05, -2048684427);
```
Change to:
```java
AbstractC27310cW.A05(viewA04, 0.0f, -2048684427);   // always transparent
```
(or wrap in `if (false)` to skip; or short-circuit `viewA04.setVisibility(View.GONE)` once.)

**Secondary (defensive) — `EPN.java:803`** is already `0.0f` (no change needed).

Note: this patch alone does NOT make the sheet translucent — it just removes the dimming layer. The sheet panel itself (`BottomSheetFragment` Branch C `setColorFilter`) and the `background_dimmer` scrim (see Q3) are still opaque and must also be patched.

---

## Q3 — `C109193lI` (IgBottomSheetNavigator) scrim

File: `p002X/C109193lI.java` (1964 lines).

### Scrim view identification

- `A0u()` at line 1818: returns the cached `A1J` field, lazily populated by `A04()` (line 235):
  ```java
  // p002X/C109193lI.java:235-243
  private final TouchInterceptorFrameLayout A04() {
      TouchInterceptorFrameLayout touchInterceptorFrameLayout =
          (TouchInterceptorFrameLayout) A0w().getView().findViewById(R.id.background_dimmer);
      ...
      return touchInterceptorFrameLayout;
  }
  ```
- `A0v()` at line 1827: returns the cached `A0C` field (the bottom sheet CONTAINER, a separate TouchInterceptorFrameLayout).
- **The scrim is a separate full-screen `TouchInterceptorFrameLayout` with id `R.id.background_dimmer`, sitting BEHIND the sheet panel.** It is NOT part of the sheet itself.
- The Reels comment sheet IS hosted by `C109193lI` — confirmed at line 640: `if (c109193lI.A1F == null || C109103l9.areEqual(c109193lI.A1W, "clips_bottom_sheet_fragment_tag"))`. (Tag name from `C00B.java:5979`.)

### Scrim setup (`A0C`)

`p002X/C109193lI.java:593-604`:

```java
public static final void A0C(C109193lI c109193lI) {
    ColorDrawable colorDrawable = new ColorDrawable(-16777216);                    // line 594 = 0xFF000000 = OPAQUE BLACK
    TouchInterceptorFrameLayout touchInterceptorFrameLayoutA0u = c109193lI.A0u();  // line 595 = background_dimmer
    if (touchInterceptorFrameLayoutA0u != null) {
        AbstractC27310cW.A03(colorDrawable, touchInterceptorFrameLayoutA0u, 1318304944);  // line 597 = setBackground(opaque_black)
    }
    TouchInterceptorFrameLayout touchInterceptorFrameLayoutA0u2 = c109193lI.A0u();
    if (touchInterceptorFrameLayoutA0u2 != null) {
        Float f = c109193lI.A0R;                                                   // line 601 (Float, default null)
        AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u2, f != null ? f.floatValue() : 0.0f, 1749511683);  // line 602 = setAlpha(A0R or 0)
    }
}
```

Called from `AbstractC109183lH.java:195, 366` when `c256199bo.A00(activity, ...)` is true (prism eligible) AND `A0R != null`. For the Reels comment sheet, `A0R` is null (never assigned in `C109193lI.java` — grep confirmed), so `A0C()` does NOT execute; instead `A0A()` is called (see `AbstractC109183lH.java:191-193`).

### Scrim slide animation (`A0A`)

`p002X/C109193lI.java:535-565`:

```java
public static final void A0A(C37850tW c37850tW, C109193lI c109193lI) {
    int i;
    float f = (float) c37850tW.A09.A00;                                            // line 537 = slide fraction (0..1)
    C256199bo c256199bo = c109193lI.A0J;
    if (c256199bo != null) {
        Activity activity = c109193lI.A1Q;
        if (c256199bo.A00(activity, c109193lI.A1U)) {
            double d = c37850tW.A01;
            if ((d == 0.0d || d == 1.0d) && !c109193lI.A0u) {
                TouchInterceptorFrameLayout touchInterceptorFrameLayoutA0u = c109193lI.A0u();  // line 544
                if (touchInterceptorFrameLayoutA0u != null) {
                    AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u, f, 1035830398);        // line 546 = setAlpha(f)
                }
                ...
            }
        }
    }
}
```

**Alpha value:** `f` = `c37850tW.A09.A00` = the sheet's slide fraction (0=collapsed, 1=expanded).
- Sheet fully OPEN → `f = 1.0` → scrim alpha = **1.0 (FULLY OPAQUE BLACK)**
- Sheet fully CLOSED → `f = 0.0` → scrim alpha = **0.0 (transparent)**

### Second slide handler (`A0E`)

`p002X/C109193lI.java:695-732` — a more complex slide handler that also animates the scrim:

```java
public static final void A0E(C109193lI c109193lI, float f, int i) {
    ...
    float f3 = 1.0f;
    if (c109193lI.A0u) {
        float f4 = i;
        float height2 = (f4 - f2) / (touchInterceptorFrameLayoutA0v.getHeight() - f2);
        if (f4 > f2) {
            f3 = 1.0f - height2;
            if (f3 < 0.0f) f3 = 0.0f;
        }
    }
    TouchInterceptorFrameLayout touchInterceptorFrameLayoutA0u = c109193lI.A0u();   // line 722
    if (touchInterceptorFrameLayoutA0u != null) {
        AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u, f3, -1791038417);      // line 724 = setAlpha(f3)
    }
    ...
}
```

Called from `AnonymousClass940.Fjg:551` (`C109193lI.A0E(c109193lI, anonymousClass942.A01.Dsn(c109193lI.A1U), iA05)`). `f3` is clamped to [0, 1] — when sheet fully open, `f3` approaches 0 in this formula (different from `A0A`). The two handlers run on different code paths; both must be considered.

### Q3 patch points (translucent scrim)

Two complementary approaches:

**A. Reduce alpha (preferred — preserves scrim visibility for legibility):**
- `C109193lI.java:546`: change `AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u, f, 1035830398)` → use `f * 0.4f` (40% opacity). Result: scrim alpha = 0.4 when sheet fully open (translucent dark, video still partially visible).
- `C109193lI.java:724`: change `AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u, f3, -1791038417)` → use `f3 * 0.4f`.

**B. Replace scrim color with translucent (alternative):**
- `C109193lI.java:594`: change `new ColorDrawable(-16777216)` (= `0xFF000000`) → `new ColorDrawable(0x66000000)` (40% black). Affects the A0C path (only runs when `A0R != null`, which is rare for Reels — so patch A is the effective one).

**C. Remove scrim entirely (most aggressive):**
- Set `c109193lI.A0u` (the boolean flag at line 712 `if (c109193lI.A0u)` which gates `A0E`'s scrim animation) — but this flag has other semantic meaning, risky.

For Feature C with FrostedOverlayView providing the blur, the scrim can be set to alpha 0 (patch A with multiplier 0.0) since the frosted blur itself provides the visual separation.

---

## Q4 — `clips_media_dimming_view` definition

### What is it?

File: `p002X/AbstractC95704cDl.java` (full file, 12 lines):

```java
package p002X;

import com.instagram.android.R;

public abstract class AbstractC95704cDl {
    public static final C139704tP A00(C137884qT c137884qT) {
        C137714qC c137714qC = C0XB.A02;
        return new C139704tP(
            AbstractC138564rZ.A09(
                AbstractC138564rZ.A0C(
                    AbstractC138564rZ.A06(
                        C3C.A0X(AnonymousClass295.A0q(null, AbstractC29121ArC.A0j()),
                                EnumC139134sU.HEIGHT_PERCENT),
                        0.0f),
                    R.id.clips_media_dimming_view),
                AbstractC138504rT.A05(c137884qT, R.attr.igds_color_media_background)),
            null, null, null, null, null, null, null, null, false);
    }
}
```

**It is a plain `View`** (constructed via the Bloks layout spec `C139704tP` with `HEIGHT_PERCENT` sizing):
- ID: `R.id.clips_media_dimming_view` (resource id `0x7f0b0bc0` per `R.java:20220`)
- Background color: `R.attr.igds_color_media_background` (attr id `0x7f040796` per `R.java:1859`) — a near-black solid color (used elsewhere for video player backgrounds, e.g. `H0V.java:51`, `C48247ISr.java:234`).
- NOT a blur view. NOT a RenderEffect view. Just a plain colored rectangle.
- Layout: `HEIGHT_PERCENT` (full-height of parent, 100% if no ratio specified — the `0.0f` arg is a margin offset).

### Where is it added to the clips viewer layout?

Added via `AbstractC95704cDl.A00(c137884qT)` at multiple call sites in `p002X/C50283J9a.java` (lines 255, 365, 529, 669, 871, 1011, 1175, 1315) and `p002X/J59.java:146`. Both files are clips-viewer layout builders (the `arrayListA0E` argument is the list of children added to a container `C139704tP`).

`C50283J9a` and `J59` build the per-page clips item layout (the `ReboundViewPager.A0F` page). So `clips_media_dimming_view` is a **sibling of the video player inside each clips page**.

### Z-order: ON TOP of video, BEHIND sheet

- The dimming view is added AFTER the video media component in the clips page (verified: `C50283J9a` adds media components first, then `clips_media_dimming_view` later in the `arrayListA0E`).
- Z-order in the same parent: later children = higher Z. So dimming view is **ON TOP of the video**.
- The comment sheet panel (BottomSheetFragment) lives in a SEPARATE container (`IgBottomSheetNavigator`'s `bottom_sheet_container_view` at `R.id.bottom_sheet_container`, overlaid on the whole activity). So the sheet panel is **ON TOP of the dimming view** (and on top of the entire clips viewer).

**Layer stack (bottom → top) when Reels comment sheet is open:**
1. Video (clips player)
2. `clips_media_dimming_view` (plain View, opaque black, alpha=1.0 when sheet open) ← EPN:534
3. `background_dimmer` TouchInterceptorFrameLayout (full-screen, opaque black, alpha=1.0 when sheet open) ← C109193lI:546
4. `bottomSheetContainer` panel (opaque dark via setColorFilter) ← BottomSheetFragment:1646

Three opaque layers block the video. All three must be neutralized for translucency.

### Q4 patch points

Simplest: **set `clips_media_dimming_view` alpha to 0** when comment sheet opens. The exact line is `EPN.java:534` (already covered in Q2):

```java
// Change:
AbstractC27310cW.A05(viewA04, 1.0f - fA05, -2048684427);
// To:
AbstractC27310cW.A05(viewA04, 0.0f, -2048684427);
```

Alternative: in `AbstractC95704cDl.A00`, set the view's visibility to `INVISIBLE` by default. But the dimming view is also used during other transitions (e.g. horizontal fullscreen — Feature D), so a global GONE might break those. The targeted patch at `EPN.java:534` is safer (only affects comment-sheet slide).

---

## Q5 — `FrostedOverlayView` reuse for true blur

File: `com/instagram/p132ui/legibilityoverlay/FrostedOverlayView.java` (190 lines, full read).

### Class summary

`FrostedOverlayView extends View` — a custom view that renders a blurred snapshot of another view (or an `IgProgressImageView`'s loaded bitmap) as its own background. Uses Android 12+ `RenderEffect` for hardware blur, falls back to a CPU blur (`AbstractC233038fY.A00`) on older API.

### Constructor

```java
// line 43
public FrostedOverlayView(Context context, AttributeSet attributeSet, int i) {
    super(context, attributeSet, i);
    C109103l9.A0Q(context);
    this.A06 = C01C.A18(Build.VERSION.SDK_INT, 31);   // true on Android 12+
    Paint paintA0M = AnonymousClass133.A0M(3);
    ColorMatrix colorMatrix = new ColorMatrix();
    colorMatrix.setScale(0.85f, 0.85f, 0.85f, 1.0f);  // dimming: 85% brightness
    paintA0M.setColorFilter(new ColorMatrixColorFilter(colorMatrix));
    this.A02 = paintA0M;
    this.A04 = AbstractC29184AsD.A0M();
    this.A03 = AbstractC29184AsD.A0M();
    this.A05 = new C97662dex();
}

// line 176 — convenience
public FrostedOverlayView(Context context) { this(context, null, 0); ... }

// line 186 — convenience
public FrostedOverlayView(Context context, AttributeSet attributeSet) { this(context, attributeSet, 0); ... }
```

### `setupFrom` API

```java
// line 160
public final void setupFrom(View view, IgProgressImageView igProgressImageView) {
    C109103l9.A0Q(view);
    IgProgressImageView igProgressImageView2 = this.A01;
    if (igProgressImageView2 != null) {
        igProgressImageView2.A04(1112298834);   // detach old callback
    }
    this.A01 = null;
    if (igProgressImageView == null || igProgressImageView.A09()) {   // image already loaded OR no image
        A00(view, this);                       // blur immediately
    } else {
        this.A01 = igProgressImageView;        // defer blur until image loads
        igProgressImageView.A07(new C104552iwM(1, view, this), 1112298834);
    }
}
```

- **`view`**: the source view to snapshot+blur. Can be any view in the same window — `setupCpuBlur`/`setupRenderEffectBlur` use `getLocationOnScreen()` to compute the offset between source and FrostedOverlayView (lines 71-74, 95-100), so they need NOT be siblings.
- **`igProgressImageView`**: optional — if non-null and image not yet loaded, defers the blur until the image loads (via `A07` callback). Pass `null` to blur immediately.

### `A00` (gate)

```java
// line 57
public static final void A00(View view, FrostedOverlayView frostedOverlayView) {
    if (!frostedOverlayView.isAttachedToWindow()
            || frostedOverlayView.getWidth() <= 0
            || frostedOverlayView.getHeight() <= 0
            || view.getWidth() <= 0
            || view.getHeight() <= 0) {
        return;   // not laid out yet — skip
    }
    if (frostedOverlayView.A06) {                       // Android 12+
        frostedOverlayView.setupRenderEffectBlur(view);
    } else {
        frostedOverlayView.setupCpuBlur(view);
    }
}
```

### `setupRenderEffectBlur` (Android 12+, fast path)

```java
// line 94
private final void setupRenderEffectBlur(View view) {
    int[] iArr = new int[2];
    int[] iArr2 = new int[2];
    getLocationOnScreen(iArr);
    view.getLocationOnScreen(iArr2);
    int i = iArr[0] - iArr2[0];
    int i2 = iArr[1] - iArr2[1];
    int width = getWidth();
    int height = getHeight();
    Bitmap bitmapCreateBitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
    Canvas canvasA0P = AbstractC29185AsE.A0P(bitmapCreateBitmap);
    canvasA0P.translate(-i, -i2);
    view.draw(canvasA0P);                                    // snapshot source view
    Bitmap bitmap = this.A00;
    if (bitmap != null) bitmap.recycle();
    this.A00 = bitmapCreateBitmap;
    this.A04.set(0, 0, width, height);
    this.A03.set(0, 0, width, height);
    setRenderEffect(RenderEffect.createBlurEffect(15.0f, 15.0f, Shader.TileMode.CLAMP));   // 15px hardware blur
    invalidate();
}
```

### `setupCpuBlur` (pre-Android 12, slow path)

```java
// line 68
private final void setupCpuBlur(View view) {
    int[] iArr = new int[2];
    int[] iArr2 = new int[2];
    getLocationOnScreen(iArr);
    view.getLocationOnScreen(iArr2);
    int i = iArr[0] - iArr2[0];
    int i2 = iArr[1] - iArr2[1];
    Bitmap bitmapCreateBitmap = Bitmap.createBitmap(getWidth(), getHeight(), Bitmap.Config.ARGB_8888);
    Canvas canvasA0P = AbstractC29185AsE.A0P(bitmapCreateBitmap);
    canvasA0P.translate(-i, -i2);
    view.draw(canvasA0P);
    int iA04 = C2V.A04(AnonymousClass116.A04(this), 0.27f, 1);   // 27% scale
    int iA05 = C2V.A04(AnonymousClass116.A05(this), 0.27f, 1);
    Bitmap bitmapA00 = AbstractC233038fY.A00(bitmapCreateBitmap, iA04, iA05, true);   // CPU blur
    C109103l9.A0D(bitmapA00);
    bitmapCreateBitmap.recycle();
    Bitmap bitmap = this.A00;
    if (bitmap != null) bitmap.recycle();
    this.A00 = bitmapA00;
    this.A04.set(0, 0, iA04, iA05);
    this.A03.set(0, 0, getWidth(), getHeight());
    invalidate();
}
```

### `draw` (renders the blurred bitmap)

```java
// line 136
@Override
public final void draw(Canvas canvas) {
    int iA00 = C00F.A00(canvas, -2117444157);
    Bitmap bitmap = this.A00;
    if (bitmap != null) {
        Rect rect = this.A04;
        if (!rect.isEmpty()) {
            Rect rect2 = this.A03;
            if (!rect2.isEmpty()) {
                float fA04 = AnonymousClass116.A04(this);
                float fA05 = AnonymousClass116.A05(this);
                if (fA04 > 0.0f && fA05 > 0.0f) {
                    int iSaveLayer = canvas.saveLayer(0.0f, 0.0f, fA04, fA05, null);
                    canvas.drawBitmap(bitmap, rect, rect2, this.A02);   // draw blurred bitmap with 85%-brightness color filter
                    this.A05.A00(canvas, fA04, fA05);                   // optional overlay (C97662dex)
                    canvas.restoreToCount(iSaveLayer);
                }
            }
        }
    } else {
        super.draw(canvas);   // no snapshot — transparent
    }
    C3TF.A0A(1367186605, iA00);
}
```

### `A01` (cleanup)

```java
// line 118
public final void A01() {
    IgProgressImageView igProgressImageView = this.A01;
    if (igProgressImageView != null) igProgressImageView.A04(1112298834);
    this.A01 = null;
    Bitmap bitmap = this.A00;
    if (bitmap != null) bitmap.recycle();
    this.A00 = null;
    setBackground(null);
    if (Build.VERSION.SDK_INT >= 31) setRenderEffect(null);
}
```

### Can it blur the clips ViewPager (the video) from inside the comment sheet container?

**Yes**, with caveats:

1. **Same-window requirement:** Both the source (clips ViewPager or its current page) and the `FrostedOverlayView` must be in the same window. The comment sheet is hosted by `IgBottomSheetNavigator` whose container is overlaid on the same Activity window as the clips viewer — so they share a window. ✓
2. **Layout gate:** `A00` checks both views have width > 0 and height > 0. Must call `setupFrom` AFTER layout (e.g. in `onGlobalLayout` or post-sheet-show callback). The comment sheet's `onViewCreated` runs before layout — too early.
3. **Snapshot semantics:** `view.draw(canvas)` captures a single still frame at the moment of the call. For a playing video, this is a frozen frame — the blur does NOT update as the video plays. For a true "live frosted" TikTok-style effect, we'd need to call `setupFrom` periodically (e.g. on a `Choreographer.FrameCallback` at 30-60 fps), which is expensive on CPU-blur devices.
4. **Performance:**
   - Android 12+ (`RenderEffect`): ~1-2ms per snapshot+blur, suitable for periodic refresh (e.g. 30fps).
   - Pre-Android 12 (CPU blur via `AbstractC233038fY.A00` at 0.27 scale): ~10-30ms per snapshot, too slow for live refresh — use one-shot blur only.
5. **IgProgressImageView parameter:** For video, pass `null` (no async image load to wait for).

### Threading / lifecycle caveats

- `setupFrom` must be called on the UI thread (touches View state).
- Must call `A01()` on sheet dismiss to recycle the bitmap and clear the RenderEffect (otherwise memory leak).
- For live blur, schedule `setupFrom` on `Choreographer.getInstance().postFrameCallback` — but cancel when sheet starts closing.

### Recommended integration for Feature C

**One-shot blur (simpler, acceptable UX):**
- Insert a `FrostedOverlayView` as the bottom-most child of the comment sheet's root container.
- In `BottomSheetFragment.onViewCreated` (or a `OnPreDrawListener`), call `frostedOverlayView.setupFrom(clipsViewPager.getCurrentItemView(), null)`.
- Patch the three opaque layers (sheet panel, scrim, dimming view) to alpha 0 — the FrostedOverlayView provides the visual separation.

**Live blur (TikTok-style, more complex):**
- Same as above, but additionally register a `Choreographer.FrameCallback` that re-calls `setupFrom` every frame while the sheet is open.
- Only viable on Android 12+ (gate on `C01C.A18(Build.VERSION.SDK_INT, 31)` — the same check `FrostedOverlayView` uses at line 46).
- Cost: ~2ms/frame on modern devices; might cause jank on low-end.

---

## Feature C precise patch points (consolidated)

Three opaque layers must be neutralized. Each patch is independent — applying all three gives full translucency; applying FrostedOverlayView on top gives true TikTok-style frosted blur.

### Layer 1: `clips_media_dimming_view` (between video and sheet)

**File:** `p002X/EPN.java`
**Line:** 534
**Change:**
```java
// Before
AbstractC27310cW.A05(viewA04, 1.0f - fA05, -2048684427);
// After (translucent — keep slight dimming for legibility)
AbstractC27310cW.A05(viewA04, (1.0f - fA05) * 0.3f, -2048684427);
// OR (fully transparent — let FrostedOverlayView handle the blur)
AbstractC27310cW.A05(viewA04, 0.0f, -2048684427);
```

### Layer 2: `background_dimmer` scrim (full-screen behind sheet)

**File:** `p002X/C109193lI.java`
**Lines:** 546 and 724
**Change:**
```java
// Line 546 (in A0A):
// Before
AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u, f, 1035830398);
// After
AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u, f * 0.4f, 1035830398);

// Line 724 (in A0E):
// Before
AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u, f3, -1791038417);
// After
AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u, f3 * 0.4f, -1791038417);
```

**Alternative (single-line, color-based):** `C109193lI.java:594`
```java
// Before
ColorDrawable colorDrawable = new ColorDrawable(-16777216);   // 0xFF000000
// After
ColorDrawable colorDrawable = new ColorDrawable(0x66000000);   // 40% black
```
(Only effective when `A0R != null`, which is rare for Reels — patch at 546/724 is the actual runtime path.)

### Layer 3: Sheet panel background (BottomSheetFragment)

**File:** `com/instagram/igds/components/bottomsheet/BottomSheetFragment.java`

For Reels (Branch C, production prism-enabled path):

**Line 1646 (setColorFilter with `color2`):**
```java
// Before
drawableMutate3.setColorFilter(color2, PorterDuff.Mode.SRC_IN);
// After (force 80% alpha on the tint color)
int translucentColor2 = (color2 & 0x00FFFFFF) | 0xCC000000;
drawableMutate3.setColorFilter(translucentColor2, PorterDuff.Mode.SRC_IN);
```

**Universal alternative (set `C50186J5g.A05` at builder time):**
Find where the Reels comment sheet's `C50186J5g` builder is constructed (likely in `QF1` or a `C47644I5m` factory) and set `A05 = 0xCC000000` (80% black) before `A00()` is called. This covers all three `setColorFilter` paths (lines 1557, 1596, 1646) but NOT the prism drawable fallback (line 1565) — so combine with the next patch if Branch A may execute.

**Branch A fallback (line 1562):** if prism is disabled at runtime:
```java
// Before
drawable = context.getDrawable(R.drawable.igds_bottom_sheet_background_prism);
// After — wrap in a translucent layer (or replace with a custom translucent drawable)
Drawable prism = context.getDrawable(R.drawable.igds_bottom_sheet_background_prism);
prism.setAlpha(204);   // 80% opacity
drawable = prism;
```

### Layer 4 (optional): Add `FrostedOverlayView` for true blur

**Insertion point:** Inside the comment sheet's root container (`BottomSheetFragment.bottomSheetContainer` or its first child), add a `FrostedOverlayView` as the bottom-most child (Z-order: behind sheet content, above the now-translucent panel background).

**Setup call:**
```java
FrostedOverlayView frosted = new FrostedOverlayView(requireContext());
// Add to sheet container at index 0
bottomSheetContainer.addView(frosted, 0);
// After layout, blur the clips ViewPager:
frosted.getViewTreeObserver().addOnGlobalLayoutListener(new OnGlobalLayoutListener() {
    @Override public void onGlobalLayout() {
        if (frosted.getWidth() > 0 && clipsViewPager.getWidth() > 0) {
            frosted.setupFrom(clipsViewPager, null);   // null = blur immediately (video, not async image)
            frosted.getViewTreeObserver().removeOnGlobalLayoutListener(this);
        }
    }
});
// On sheet dismiss: frosted.A01();  (cleanup)
```

**Live blur (Android 12+ only):** Wrap `setupFrom` in a `Choreographer.FrameCallback` loop while sheet is open; cancel on dismiss.

---

## Open questions / next actions

1. **Verify runtime prism state:** Confirm `C0PQ.A06` returns true in production v435.0.0.37.76 (smali-level runtime log or by reading `C102743at.A05/A06` mobile-config defaults). If false, Branch A executes instead of Branch C — patch Layer 3 differently.
2. **Locate the Reels comment sheet's `C50186J5g` builder construction site:** Likely in a `C47644I5m` factory or in `QF1` itself. Find it to set `A05` (translucent color2) at builder time (universal Layer 3 patch). Grep `C54625Krc`/`QF1` for `new C50186J5g(` or `C50186J5g.A00` calls.
3. **Decide one-shot vs live blur:** Live blur requires Choreographer loop and Android 12+ gate. One-shot blur is simpler but the frosted image won't update as the video plays. For TikTok-style behavior, live blur is required.
4. **Coordinate with 3-d/4-a/4-b:** This task confirms the dimming architecture; the actual patch implementation should be coordinated with whatever smali-patching approach 4-a/4-b are using for their respective features.
