# 3-d — Comment Overlay/Sheet for Reels (Feature C)

**Goal:** find the opaque black comment sheet and understand how to make it a
translucent frosted overlay (video visible behind).

**Source root:** `/home/z/insta-src/jadx-out/sources/`

---

## TL;DR — the picture

Reels comments are NOT a `BottomSheetDialogFragment`. They are a regular
`androidx.fragment.app.Fragment` whose view tree is hosted inside the activity
in a special container (`R.id.layout_container_bottom_sheet`). The visible
"sheet panel" is a `TouchInterceptorFrameLayout` whose background is set in
code to either `R.drawable.igds_bottom_sheet_background_prism` or a
`GradientDrawable` colored with the theme attr `igds_color_elevated_background`
(= opaque dark grey/black in dark mode). That panel — plus a separate
`clips_media_dimming_view` that fades black over the video when the sheet
opens — is what blocks the video.

IG already ships a reusable GPU blur view, `FrostedOverlayView`, that uses
`RenderEffect.createBlurEffect(15f, 15f, CLAMP)` on Android 31+ with a CPU
fallback for older devices.

The sheet **overlays** the video (does NOT push/resize it). Confirmed by the
existence of the `isCommentSheetOpenInWatchAndComment` flag in `ClipsItemState`
(C11R) — watch-and-comment mode lets the video keep playing behind the sheet.

---

## 1. The comment sheet class

There are three concrete fragments (all in `p002X/` after jadx deobfuscation):

| Original IG name | jadx class | path |
|---|---|---|
| `CommentListBottomsheetBaseFragment` (abstract base) | `QF1` | `p002X/QF1.java` |
| `CommentListBottomsheetFragment` (legacy Litho UI — what we see) | `C54625Krc` | `p002X/C54625Krc.java` |
| `CommentListBottomsheetComposeFragment` (newer Compose UI) | `C86682YfD` | `p002X/C86682YfD.java` |

Class hierarchy (follow `extends`):
```
Fragment
  └─ AbstractC74952Tg           (IgFragment base)
       └─ AbstractC91822yN      (IGDS fragment w/ session + lifecycle)
            └─ AbstractC27985AXi (comment-sheet base mixins)
                 └─ QF1         (CommentListBottomsheetBaseFragment)
                      ├─ C54625Krc  (CommentListBottomsheetFragment)
                      └─ C86682YfD  (CommentListBottomsheetComposeFragment)
```

`QF1` itself `extends AbstractC27985AXi implements InterfaceC109844mci, FIL,
InterfaceC84385Xai, InterfaceC51765Jma, InterfaceC41550zU, InterfaceC31596Bq1,
InterfaceC112680nmn, InterfaceC82932WlP` — see
`/home/z/insta-src/jadx-out/sources/p002X/QF1.java:26`:
```java
public abstract class QF1 extends AbstractC27985AXi implements InterfaceC109844mci, FIL, InterfaceC84385Xai, InterfaceC51765Jma, InterfaceC41550zU, InterfaceC31596Bq1, InterfaceC112680nmn, InterfaceC82932WlP {
    public static final String __redex_internal_original_name = "CommentListBottomsheetBaseFragment";
```

Route → fragment mapping (entry point) —
`/home/z/insta-src/jadx-out/sources/p002X/AbstractC78782dL.java:5820-5827`:
```java
case 906147982:
    str2 = "comment_clips_viewer";
    if (str.equals(str2)) {
        C90202vl.A01(114713);
        C7DK.A00();
        p7j = new C54625Krc();         // <-- creates the bottom-sheet fragment
        p7j.setArguments(bundle);
        fragmentA01 = p7j;
```

So the route `"comment_clips_viewer"` (launched from the clips/reels viewer
when the user taps the comment icon) instantiates `C54625Krc`.

For tablet/large-screen layouts, `CommentsTwoPaneLayout`
(`/home/z/insta-src/jadx-out/sources/com/instagram/comments/twopane/CommentsTwoPaneLayout.java`)
uses a `SlidingPaneLayout` instead — out of scope for our phone patch.

---

## 2. How the sheet is displayed

NOT a `BottomSheetDialogFragment`, NOT a `BottomSheetBehavior`. It is a
regular Fragment added to a container in the activity via a custom
"IG Bottom Sheet Navigator" (`C109193lI` aka `IgBottomSheetNavigator`).

### Container in the activity

`/home/z/insta-src/jadx-out/sources/com/instagram/base/activity/IgFragmentActivity.java:1858-1863`:
```java
if (viewA1f.findViewById(R.id.bottom_sheet_container) == null || viewA1f.findViewById(R.id.bottom_sheet_container_stub) != null) {
    View viewA1f2 = A1f();
    AbstractC30520hh abstractC30520hhA1a = A1a();
    C109193lI c109193lI = new C109193lI(this, viewA1f2, abstractC30520hhA1a, abstractC66481ybA1i, "BottomSheetConstants.FRAGMENT_TAG", R.id.layout_container_bottom_sheet, true);
    this.A00 = c109193lI;
    return c109193lI;
```
So the host container ID is `R.id.layout_container_bottom_sheet` and the
fragment tag is `"BottomSheetConstants.FRAGMENT_TAG"`.

### Sheet root layout

`/home/z/insta-src/jadx-out/sources/com/instagram/igds/components/bottomsheet/BottomSheetFragment.java:2392-2402`:
```java
@Override // androidx.fragment.app.Fragment
public final View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
    int iA02 = C3TF.A02(1282599313);
    C109103l9.A0U(layoutInflater, 0);
    C50186J5g c50186J5g = this.A03;
    if (c50186J5g != null && c50186J5g.A1O) {
        this.A0G.A02(viewGroup);
    }
    View viewInflate = layoutInflater.inflate(R.layout.bottom_sheet_fragment, viewGroup, false);
    C3TF.A09(-881852558, iA02);
    return viewInflate;
}
```
Sheet root layout = `R.layout.bottom_sheet_fragment` (res id `0x7f0e0158`).

### Inner views of the sheet (looked up in `onViewCreated`)

`BottomSheetFragment.java:2490-2502`:
```java
this.bottomSheetContainer        = (ViewGroup) view.requireViewById(R.id.bottom_sheet_container);
this.contentView                 = (TouchInterceptorFrameLayout) view.requireViewById(R.id.bottom_sheet_container_view);
this.navButtonStartGuideline     = (Guideline) view.requireViewById(R.id.nav_button_start_guide_line);
this.navButtonEndGuideline       = (Guideline) view.requireViewById(R.id.nav_button_end_guide_line);
this.dragHandleFrame             = (IgFrameLayout) view.requireViewById(R.id.bottom_sheet_drag_handle_frame);
ViewStub viewStub                = (ViewStub) view.requireViewById(R.id.bottom_sheet_drag_handle_prism_stub);
...
viewStub.setLayoutResource(i);   // R.layout.bottom_sheet_drag_handle_prism or _lightweight
viewStub.inflate();
```
So the layout tree is roughly:
```
R.layout.bottom_sheet_fragment  (root — full-screen)
 ├─ R.id.background_dimmer               (TouchInterceptorFrameLayout — scrim/dim)
 └─ R.id.bottom_sheet_container          (the visible rounded panel)
      ├─ R.id.bottom_sheet_drag_handle_frame
      │    └─ R.id.bottom_sheet_drag_handle_prism
      ├─ R.id.nav_buttons_and_title_container
      └─ R.id.bottom_sheet_container_view  (TouchInterceptorFrameLayout — content slot)
           └─ <fragment-specific content>  // for comments: R.layout.layout_comment_list
```

### Sheet panel content

For the comment sheet specifically,
`/home/z/insta-src/jadx-out/sources/p002X/C54625Krc.java:202-217`:
```java
@Override // androidx.fragment.app.Fragment
public final View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
    View viewInflate;
    int iA02 = C3TF.A02(-1914183886);
    C109103l9.A0U(layoutInflater, 0);
    boolean zA1C = C01C.A1C(this.A0M);
    int iA07 = A03(this) ? C01C.A07(this.A0G.getValue()) : 0;
    if (zA1C) {
        viewInflate = C31620jT.A00(layoutInflater, viewGroup, R.layout.layout_comment_list, iA07, false, true);
    } else {
        viewInflate = layoutInflater.inflate(R.layout.layout_comment_list, viewGroup, false);
        C109103l9.A0D(viewInflate);
    }
    C3TF.A09(903267940, iA02);
    return viewInflate;
}
```
Inner content layout = `R.layout.layout_comment_list` (res id `0x7f0e0a72`).

### The IG bottom-sheet navigator

`/home/z/insta-src/jadx-out/sources/p002X/C109193lI.java` (1963 lines).
Two helpers it exposes:
- `A0u()` (line 1818) → returns the **scrim** `TouchInterceptorFrameLayout`
  (looked up via `R.id.background_dimmer`, line 236). Alpha is animated.
- `A0v()` (line 1827) → returns the **sheet panel** `TouchInterceptorFrameLayout`
  (looked up via `this.A1P`, set to the panel container id).

The sheet is committed via standard fragment transaction
(`/home/z/insta-src/jadx-out/sources/p002X/C109193lI.java:1624-1638`):
```java
c28180dv = new C28180dv(abstractC30520hh);              // C28180dv = FragmentTransaction wrapper
...
c28180dv.A0M(fragment, str, i6);                        // .add(containerId, fragment, tag)
c28180dv.A0S(str);                                      // .addToBackStack(tag)
if (zBooleanValue) c28180dv.A04(); else c28180dv.A01(); // .commit()/commitAllowingStateLoss()
abstractC30520hh.A0a();                                 // .executePendingTransactions()
```

### Does it OVERLAY or PUSH the video?

OVERLAYS. Two pieces of evidence:

1. `ClipsItemState.isCommentSheetOpenInWatchAndComment` —
   `/home/z/insta-src/jadx-out/sources/p002X/C11R.java:572`:
   ```java
   sb.append(", isCommentSheetOpenInWatchAndComment=");
   sb.append(this.A0N);
   ```
   This flag exists specifically because the video keeps playing while the
   comment sheet is open. The clips viewer does not resize.

2. `WatchAndCommentViewManager` (jadx `EPN`) —
   `/home/z/insta-src/jadx-out/sources/p002X/EPN.java:125-137`:
   ```java
   sb.append("WatchAndCommentViewManager, media ");
   ...
   sb.append(", commentSheetOpeningHeightRatio ");
   sb.append(this.A03);
   sb.append(", availableScreenHeight ");
   sb.append(A03(this));
   sb.append(", mediaViewHeight ");
   sb.append(A00());
   ```
   `EPN` manages the slide-up of the sheet over the media view (no resize).

So the screenshot evidence (sheet over opaque-black panel blocking the
video) is consistent with code: the sheet floats on top.

---

## 3. The black background — where it comes from

There are THREE distinct opaque layers between the video and the user's eye:

### (a) Sheet panel background — set in code in `BottomSheetFragment`

`/home/z/insta-src/jadx-out/sources/com/instagram/igds/components/bottomsheet/BottomSheetFragment.java:1559-1648`
(three branches depending on theme/style):

```java
// Branch 1: default prism drawable
} else {
    drawable = A00(this).A0H;
    if (drawable == null) {
        drawable = context.getDrawable(R.drawable.igds_bottom_sheet_background_prism);  // line 1562
    }
    AbstractC27310cW.A03(drawable, viewGroup, i2);                                     // setBackground(drawable)
    ...
```

```java
// Branch 2: GradientDrawable with theme "elevated_background" color
} else if (A00(this).A0h == AnonymousClass006.A0C) {
    float dimension = context.getResources().getDimension(R.dimen.abc_dropdownitem_icon_width);
    C32055BxQ c32055BxQ = new C32055BxQ();
    c32055BxQ.A00 = dimension;
    ...
    ViewGroup viewGroup10 = this.bottomSheetContainer;
    if (viewGroup10 != null) {
        GradientDrawable gradientDrawable = new GradientDrawable();
        gradientDrawable.setColor(AbstractC26520bF.A00(context));   // = igds_color_elevated_background
        gradientDrawable.setCornerRadius(dimension);
        AbstractC27310cW.A03(gradientDrawable, viewGroup10, -415685939);  // setBackground
        ...
    }
}
```

`AbstractC26520bF.A00(context)` resolves to `R.attr.igds_color_elevated_background` —
`/home/z/insta-src/jadx-out/sources/p002X/AbstractC26520bF.java:16-17`:
```java
public static final int A00(Context context) {
    return A0W(context, R.attr.igds_color_elevated_background);
}
```
In IG's dark theme, `igds_color_elevated_background` is an opaque very dark
grey (#121212-ish). In light theme it's white.

Either way: **the sheet panel itself is opaque.** This is the dominant
"black thing" the user sees behind the comment list and above the composer.

### (b) `clips_media_dimming_view` — separate dim view over the video

A second opaque layer is created by the **Clips viewer**, not the sheet.

`/home/z/insta-src/jadx-out/sources/p002X/AbstractC95704cDl.java:7-10`:
```java
public abstract class AbstractC95704cDl {
    public static final C139704tP A00(C137884qT c137884qT) {
        return new C139704tP(AbstractC138564rZ.A09(
            AbstractC138564rZ.A0C(
                AbstractC138564rZ.A06(
                    C3C.A0X(AnonymousClass295.A0q(null, AbstractC29121ArC.A0j()),
                            EnumC139134sU.HEIGHT_PERCENT), 0.0f),
                R.id.clips_media_dimming_view),
            AbstractC138504rT.A05(c137884qT, R.attr.igds_color_media_background)),
            null, null, null, null, null, null, null, null, false);
    }
}
```
This is a Litho component whose background color is
`R.attr.igds_color_media_background` (opaque black in dark theme) and whose
id is `R.id.clips_media_dimming_view` (res id `0x7f0b0bc0`).

Its alpha is animated by the `WatchAndCommentViewManager` —
`/home/z/insta-src/jadx-out/sources/p002X/EPN.java:532-535`:
```java
View viewA04 = epn.A04();    // finds R.id.clips_media_dimming_view (line 202)
if (viewA04 != null) {
    AbstractC27310cW.A05(viewA04, 1.0f - fA05, -2048684427);   // view.setAlpha(1.0 - slideOffset)
}
```
(`AbstractC27310cW.A05` = `view.setAlpha(f)`, confirmed at
`/home/z/insta-src/jadx-out/sources/p002X/AbstractC27310cW.java:44-46`.)

### (c) Standard IGDS bottom-sheet `background_dimmer` scrim

A third layer is the standard IGDS dim view `R.id.background_dimmer` —
`/home/z/insta-src/jadx-out/sources/p002X/C109193lI.java:235-243`:
```java
private final TouchInterceptorFrameLayout A04() {
    TouchInterceptorFrameLayout touchInterceptorFrameLayout =
        (TouchInterceptorFrameLayout) A0w().getView().findViewById(R.id.background_dimmer);
    if (touchInterceptorFrameLayout == null) return null;
    AbstractC27310cW.A0K(touchInterceptorFrameLayout, 983989413);
    AbstractC27120cD.A03(touchInterceptorFrameLayout, AnonymousClass006.A01);
    return touchInterceptorFrameLayout;
}
```
Alpha animated at e.g. line 546:
```java
AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u, f, 1035830398);
```

### (d) Status bar color set when sheet opens

`/home/z/insta-src/jadx-out/sources/com/instagram/igds/components/bottomsheet/BottomSheetFragment.java:2459-2462`:
```java
C109193lI c109193lI = (C109193lI) abstractC109183lHBI9;
if (c109193lI.A15 && this.A03 != null) {
    AbstractC54451fC.A03(requireActivity(),
        getThemedContext().getColor(A00(this).A09 != 0 ? A00(this).A09
                                                       : R.color.bds_black_50_transparent));
}
```
`AbstractC54451fC.A03(activity, color)` —
`/home/z/insta-src/jadx-out/sources/p002X/AbstractC54451fC.java:69-80` — only
sets `window.setStatusBarColor(color)` and adjusts
`FLAG_SYSTEM_UI_FLAG_LIGHT_STATUS_BAR`. So the status bar becomes 50%
transparent black while the sheet is open. Minor — not the main issue.

Also in `C109193lI` — `/home/z/insta-src/jadx-out/sources/p002X/C109193lI.java:1644-1650`:
```java
} else if (z2 && AbstractC54451fC.A00(activity) != activity.getColor(R.color.bds_black)) {
    color = activity.getColor(R.color.bds_black_50_transparent);
    if (color != 255) {
        this.A05 = AbstractC54451fC.A00(activity);
        this.A03 = color;
        this.A11 = AbstractC54451fC.A08(activity);
    }
}
```
Same `bds_black_50_transparent` color used as the default scrim color when
none is specified. (`color == 255` is the sentinel for "no color".)

---

## 4. The "Add comment..." input box

The composer lives inside `R.layout.layout_comment_list`. Looked up in
`C54625Krc.onViewCreated` —
`/home/z/insta-src/jadx-out/sources/p002X/C54625Krc.java:400-635`:

```java
?? r0 = (IgFrameLayout) C109103l9.A04(view, R.id.list_view_container);          // line 400
LithoView lithoView  = (LithoView) C109103l9.A04(view, R.id.main_list_view);    // line 401  (comment list)
LithoView lithoView2 = (LithoView) C109103l9.A04(view, R.id.above_composer_views);
ComposeView composeView = (ComposeView) view.findViewById(R.id.ai_bulk_reply_view);
...
InterfaceC44504Gsk interfaceC44504GskA01 =
    AbstractC30330hO.A01(view.findViewById(R.id.comment_composer_container_updated_stub), false, false, false);  // line 410
...
int[] iArr = {0, 0, 0,
    R.id.layout_comment_thread_post_button_icon,
    R.id.comment_composer_media_picker_button,
    R.id.comment_composer_animated_image_picker_button,
    R.id.comment_composer_appreciation_gift_button,
    R.id.comment_composer_sticker_suggestion};
View viewFindViewById = view.findViewById(R.id.comment_composer_parent_updated);   // line 414
```

The EditText itself — line 618 & 621:
```java
composerAutoCompleteTextView =
    (ComposerAutoCompleteTextView) C109103l9.A04(view3, R.id.layout_comment_thread_edittext_multiline);
...
composerAutoCompleteTextView =
    (ComposerAutoCompleteTextView) C109103l9.A04(view3, R.id.layout_comment_thread_edittext);
```

Key resource IDs (all confirmed in `R.java`):
| id | hex | purpose |
|---|---|---|
| `list_view_container` | `0x7f0b23a8` | outer IgFrameLayout holding list + composer |
| `main_list_view` | `0x7f0b24db` | LithoView — the scrolling comment list |
| `above_composer_views` | — | LithoView rendered above the composer |
| `comment_composer_container_updated_stub` | — | ViewStub that inflates the composer |
| `comment_composer_parent_updated` | `0x7f0b0d76` | composer parent container |
| `comment_composer_text_parent` | — | text input parent |
| `layout_comment_thread_edittext` | `0x7f0b223a` | single-line EditText ("Add a comment…") |
| `layout_comment_thread_edittext_multiline` | `0x7f0b223b` | multi-line EditText |
| `comment_composer_left_image_view` | — | profile avatar |
| `layout_comment_thread_post_button_icon` | — | "Post" button |
| `comment_composer_media_picker_button` | — | photo picker |
| `comment_composer_animated_image_picker_button` | — | GIF picker |
| `comment_composer_appreciation_gift_button` | — | gift button |
| `comment_composer_sticker_suggestion` | — | sticker picker |
| `story_comment_composer_divider` | — | divider above composer |
| `comment_overswipe_dismiss_container` | — | swipe-to-dismiss wrapper |
| `comment_overswipe_affordance` | — | affordance handle |

The composer widget class is `com.instagram.p132ui.widget.textview.ComposerAutoCompleteTextView`
(imported at `C54625Krc.java:46`) — a custom `IgAutoCompleteTextView` that
handles @-mentions.

The user's "black thing beneath the input" is the area between the bottom of
the comment list and the top of the composer — this is the sheet's own panel
background (`igds_bottom_sheet_background_prism` / `igds_color_elevated_background`,
see §3a) showing through.

---

## 5. Existing blur / translucent mechanism in IG — YES, reusable

`/home/z/insta-src/jadx-out/sources/com/instagram/p132ui/legibilityoverlay/FrostedOverlayView.java`

This is exactly what we need. It's a `View` subclass that draws a blurred
snapshot of an arbitrary "source" view behind itself. Highlights:

- API check + dual path:
  ```java
  this.A06 = C01C.A18(Build.VERSION.SDK_INT, 31);   // line 46  -> isAndroidSPlus
  ...
  if (frostedOverlayView.A06) {
      frostedOverlayView.setupRenderEffectBlur(view);     // GPU path
  } else {
      frostedOverlayView.setupCpuBlur(view);              // CPU fallback
  }
  ```

- GPU path (Android 12+) uses `RenderEffect`:
  ```java
  // line 94-116
  private final void setupRenderEffectBlur(View view) {
      ...
      Bitmap bitmapCreateBitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
      Canvas canvasA0P = AbstractC29185AsE.A0P(bitmapCreateBitmap);
      canvasA0P.translate(-i, -i2);
      view.draw(canvasA0P);
      ...
      this.A00 = bitmapCreateBitmap;
      ...
      setRenderEffect(RenderEffect.createBlurEffect(15.0f, 15.0f, Shader.TileMode.CLAMP));
      invalidate();
  }
  ```

- CPU fallback (pre-Android 12) scales the bitmap down for cheap box blur:
  ```java
  // line 68-92
  private final void setupCpuBlur(View view) {
      ...
      int iA04 = C2V.A04(AnonymousClass116.A04(this), 0.27f, 1);   // 27% scale
      int iA05 = C2V.A04(AnonymousClass116.A05(this), 0.27f, 1);
      Bitmap bitmapA00 = AbstractC233038fY.A00(bitmapCreateBitmap, iA04, iA05, true);
      ...
  }
  ```

- Slightly darkens the blurred snapshot (0.85 brightness):
  ```java
  ColorMatrix colorMatrix = new ColorMatrix();
  colorMatrix.setScale(0.85f, 0.85f, 0.85f, 1.0f);
  paintA0M.setColorFilter(new ColorMatrixColorFilter(colorMatrix));
  this.A02 = paintA0M;
  ```

- Public entry: `setupFrom(View sourceView, IgProgressImageView optional)` —
  ```java
  // line 160-173
  public final void setupFrom(View view, IgProgressImageView igProgressImageView) {
      ...
      if (igProgressImageView == null || igProgressImageView.A09()) {
          A00(view, this);
      } else {
          this.A01 = igProgressImageView;
          igProgressImageView.A07(new C104552iwM(1, view, this), 1112298834);
      }
  }
  ```

Sibling class `ColorOverlayView` in the same package
(`/home/z/insta-src/jadx-out/sources/com/instagram/p132ui/legibilityoverlay/ColorOverlayView.java`)
is a simpler semi-transparent color overlay (no blur) — useful if we want a
plain translucent tint without blur:
```java
// line 40-48
public final void A00(int i, double d) {
    if (d <= 0.0d) d = 0.699999988079071d;            // default alpha = 0.7
    this.A01.setColor(B99.A0D(i, (int) (d * 255.0d)));  // modulate alpha
    this.A00 = true;
    invalidate();
}
```

`FrostedOverlayView` is already wired into Stories (the "legibility overlay"
behind story captions). It's a drop-in reusable component.

---

## 6. Comment list (RecyclerView equivalent) inside the sheet

Confirmed at `/home/z/insta-src/jadx-out/sources/p002X/C54625Krc.java:71`:
```java
public RecyclerView A04;
```

Field `A04` is the comment list. It's assigned from the inflated layout at
`onDestroyView` line 232 (`this.A04 = null;` — cleared on teardown). The
visible comment list is rendered via LithoView `R.id.main_list_view`
(`C54625Krc.java:401`) — Litho uses an internal `RecyclerView`-equivalent
`BaseMountingView`. The `RecyclerView` field is also stored on the fragment
for scroll-position tracking.

Pull-to-refresh is via `RefreshableNestedScrollingParent`
`R.id.comment_overswipe_dismiss_container` (`C54625Krc.java:445, 484`).

So: yes, comments scroll vertically inside the sheet's content slot.

---

## Patch implications

To turn the opaque black comment sheet into a translucent frosted overlay
with the video visible behind, the changes fall into three buckets.

### Bucket 1 — make the sheet panel translucent (EASIEST, biggest visual win)

The sheet panel background is set in
`/home/z/insta-src/jadx-out/sources/com/instagram/igds/components/bottomsheet/BottomSheetFragment.java`.
Two code paths to patch (pick whichever branch is actually taken for the
comment sheet at runtime — likely the prism drawable branch at line 1562):

1. **Drawable branch** — line 1562:
   ```java
   drawable = context.getDrawable(R.drawable.igds_bottom_sheet_background_prism);
   ```
   Patch the `igds_bottom_sheet_background_prism` drawable in `res/drawable/`
   to use a semi-transparent color (e.g. `#CC000000` — 80% alpha black).
   This is a resource-only change via apktool — no smali needed.

2. **GradientDrawable branch** — lines 1607-1609:
   ```java
   GradientDrawable gradientDrawable = new GradientDrawable();
   gradientDrawable.setColor(AbstractC26520bF.A00(context));   // igds_color_elevated_background
   gradientDrawable.setCornerRadius(dimension);
   ```
   Either (a) override `igds_color_elevated_background` in `res/values/themes.xml`
   to a semi-transparent color, or (b) smali-patch line 1608 to insert an
   alpha channel into the color (e.g. `gradientDrawable.setColor(0xCC000000)`).

### Bucket 2 — reduce/remove the dim layer over the video (also easy)

Two dim layers always darken the video when the sheet is open:

1. **`clips_media_dimming_view`** — opaque `igds_color_media_background` view
   in the clips viewer, alpha-animated by `EPN.A04()` (line 532-535 of
   `EPN.java`). Options:
   - Override `igds_color_media_background` theme attr to be transparent
     (affects all media backgrounds, side effects).
   - Smali-patch `EPN.java:534` to set the dimming view's alpha to 0 (or a
     small value) so it never darkens the video.
   - Smali-patch `AbstractC95704cDl.java:10` to swap
     `R.attr.igds_color_media_background` for `R.attr.igds_color_transparent`.

2. **`background_dimmer`** (IGDS standard) — `C109193lI.A0u()` at line 1818.
   Its alpha is animated at `C109193lI.java:546, 602, 724, 1873, 1878`. The
   color itself comes from the layout XML (`R.layout.bottom_sheet_fragment`'s
   `background_dimmer` view background — not in this jadx dump, would need
   apktool to inspect). Options:
   - Smali-patch one of the `AbstractC27310cW.A05(touchInterceptorFrameLayoutA0u, f, ...)`
     call sites to pass `f * 0.3f` (multiply dim by 30%).
   - Or override the `background_dimmer` view's background drawable in
     `res/layout/bottom_sheet_fragment.xml` to a more transparent color.

### Bucket 3 — true frosted blur (medium effort, looks like TikTok)

Two feasible approaches:

**Approach A — Reuse `FrostedOverlayView` directly** (preferred):
- Insert a `FrostedOverlayView` as the first child of the sheet's
  `bottomSheetContainer` (sibling to the content view), z-ordered below the
  content but above the video.
- In the comment fragment's `onViewCreated` (`C54625Krc.java`), call
  `frostedOverlayView.setupFrom(clipsViewPager, null)` to bind it to the
  video surface.
- The class already handles Android 12+ `RenderEffect` and falls back to a
  27%-scale CPU blur for older devices. Re-render trigger is implicit via
  `invalidate()` — may need to invalidate on every video frame, or accept a
  static blurred snapshot.

**Approach B — Apply `RenderEffect` directly to the sheet panel**:
- In `BottomSheetFragment.onViewCreated` (line 2474+), after
  `bottomSheetContainer` is resolved, call:
    ```java
    if (Build.VERSION.SDK_INT >= 31) {
        bottomSheetContainer.setRenderEffect(
            RenderEffect.createBlurEffect(20f, 20f, Shader.TileMode.CLAMP));
    }
    ```
- This blurs everything drawn INTO the sheet (not what's behind it) — wrong
  direction. To blur the video behind the sheet, you need a child view that
  captures and re-draws the video (exactly what `FrostedOverlayView` does).

**Verdict:** Approach A using the existing `FrostedOverlayView` is the right
path. A simple alpha-only translucent sheet (Bucket 1 + Bucket 2) is much
easier and gets 80% of the visual effect; a true frosted blur needs Approach A.

### Concrete file:line targets for patching (smali-level)

| What | File (Java) | Line | Patch action |
|---|---|---|---|
| Sheet panel drawable (default branch) | `com/instagram/igds/components/bottomsheet/BottomSheetFragment.java` | 1562 | Replace `R.drawable.igds_bottom_sheet_background_prism` drawable in `res/drawable-*/igds_bottom_sheet_background_prism.xml` to semi-transparent color |
| Sheet panel GradientDrawable color | `com/instagram/igds/components/bottomsheet/BottomSheetFragment.java` | 1607-1609 | Either override `igds_color_elevated_background` in themes.xml OR smali-patch `setColor(...)` to add alpha |
| `clips_media_dimming_view` color | `p002X/AbstractC95704cDl.java` | 10 | Replace `R.attr.igds_color_media_background` with `R.attr.igds_color_transparent` |
| `clips_media_dimming_view` alpha animation | `p002X/EPN.java` | 534 | Change `1.0f - fA05` → `0.0f` (never dim) |
| IGDS `background_dimmer` alpha | `p002X/C109193lI.java` | 546, 602, 724 | Multiply `f` by `0.3f` |
| Status bar color when sheet open | `com/instagram/igds/components/bottomsheet/BottomSheetFragment.java` | 2461 | Use `R.color.bds_transparent` instead of `bds_black_50_transparent` |
| Blur view (if doing true frost) | `com/instagram/p132ui/legibilityoverlay/FrostedOverlayView.java` | 33 (class) | Add an instance to `R.layout.layout_comment_list` (via res patch) and call `setupFrom(clipsViewPager, null)` in `C54625Krc.onViewCreated` |

### Resource (XML) targets (will need apktool to inspect/patch)

The following resources are referenced by the code but NOT in the jadx dump
(`--no-res` was used). They must be inspected via apktool on the actual APK:

- `res/drawable/igds_bottom_sheet_background_prism.xml` — the sheet panel
  background drawable. Most likely an `<inset>` wrapping a `<shape>` with
  solid `?igds_color_elevated_background` fill and rounded top corners.
- `res/layout/bottom_sheet_fragment.xml` — sheet root layout; contains
  `background_dimmer`, `bottom_sheet_container`, `bottom_sheet_container_view`,
  drag handle stubs.
- `res/layout/layout_comment_list.xml` — comment list + composer layout.
- `res/layout/layout_clips_viewer_fragment.xml` — clips viewer root; contains
  `clips_media_dimming_view`.
- `res/values/themes.xml` (or `res/values-night/themes.xml`) — defines
  `igds_color_elevated_background`, `igds_color_media_background`,
  `igds_color_transparent`.

---

## Open questions for the patching phase

1. Which branch in `BottomSheetFragment.onViewCreated` (lines 1559-1648) is
   actually executed for the comment sheet at runtime? The branch taken
   depends on `C0PQ.A06(context, getSession())` and the `A00(this).A0h`
   enum. Need a runtime test or trace. Likely the prism-drawable branch
   (line 1562) for the default dark theme — but verify before patching.
2. Does IG's Compose variant (`C86682YfD` / `CommentListBottomsheetComposeFragment`)
   take over from `C54625Krc` on this APK version? If so, the sheet panel
   background is drawn by Compose (in `C7Y` / `C0P5` composables), not by
   `BottomSheetFragment`'s code paths — and the patch target shifts. The
   `comment_clips_viewer` route still maps to `C54625Krc` (line 5825 of
   `AbstractC78782dL.java`), so the Litho/View version is the one used —
   good news.
3. `FrostedOverlayView` triggers a re-blur on `setupFrom()` call. For a
   continuously-playing video we'd want it to re-blur every frame — may need
   to add a `Choreographer`-driven `invalidate()` loop or accept a static
   blurred snapshot taken when the sheet opens.
