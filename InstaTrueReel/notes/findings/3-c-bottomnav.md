# Task 3-c — Bottom Navigation Bar (Home/Reels/Create/Search/Profile)

Exploration of Instagram's main bottom navigation bar in the decompiled
`jadx-out` sources. Goal: locate the exact view class, its background/tint
calls, layout placement, and Reels lifecycle hooks so we can convert the
solid-black bar to a floating transparent bar with white-line icons.

All paths below are relative to:
`/home/z/insta-src/jadx-out/sources/`

---

## 1. The bottom nav view class — it is NOT FixedTabBar

**The actual main bottom nav is a plain `ViewGroup` with id `R.id.tab_bar`
(= `0x7f0b3f67`).** It is inflated from the activity layout
`R.layout.layout_activity_main_coordinator_layout`
(= `0x7f0e0943`, defined in `com/instagram/android/R.java:37681`).
The activity layout XML is NOT in this jadx dump (run with `--no-res`); it
lives in `res/layout/layout_activity_main_coordinator_layout.xml` in the
APK and must be inspected with apktool later.

The view is wrapped by a small helper holder class:

**`p002X/C34210ne.java`** — originally
`com.instagram.mainactivity.maintab.ui.MainTab`
(confirmed by the cast error message in `InstagramMainActivity.java:3604`:
`"null cannot be cast to non-null type com.instagram.mainactivity.maintab.ui.MainTab"`).

Constructor (lines 38-49) — resolves the views from the activity root:

```java
// p002X/C34210ne.java:38
public C34210ne(View view) {
    this.A0D = view;
    View viewFindViewById = view.findViewById(R.id.tab_bar);          // line 40
    C109103l9.A0D(viewFindViewById);
    this.A0F = (ViewGroup) viewFindViewById;                          // line 42  <-- THE BOTTOM NAV
    View viewFindViewById2 = view.findViewById(R.id.tab_bar_shadow);  // line 43  <-- top divider
    C109103l9.A0D(viewFindViewById2);
    this.A0E = viewFindViewById2;                                     // line 45
    this.A0G = AbstractC30330hO.A01(view.findViewById(R.id.ls_vertical_nav_bar_stub), false, false, false);          // line 46
    this.A0H = AbstractC30330hO.A01(view.findViewById(R.id.ls_vertical_tab_title_container_stub), false, false, false); // line 47
    this.A06 = new ArrayList();
}
```

Field map of `C34210ne` (the MainTab holder):

| Field | View ID | Purpose |
|-------|---------|---------|
| `A0F` (ViewGroup) | `R.id.tab_bar` (`0x7f0b3f67`) | **The bottom nav bar — phone layout** |
| `A0E` (View) | `R.id.tab_bar_shadow` (`0x7f0b3f68`) | 1px separator above the bar |
| `A0G` (InterfaceC44504Gsk) | `R.id.ls_vertical_nav_bar_stub` (`0x7f0b2497`) | Large-screen side-nav stub |
| `A0H` (InterfaceC44504Gsk) | `R.id.ls_vertical_tab_title_container_stub` | Large-screen tab titles stub |
| `A0D` (View) | root | Activity content root |

The MainTab is created lazily and stored on `InstagramMainActivity.A0u`
(see `InstagramMainActivity.A0F(this)` accessor at line 1112). The activity
supplies the layout via `A28()` (line 4393-4395):
`return ... ? R.layout.layout_activity_main_coordinator_layout_viewpager2
           : R.layout.layout_activity_main_coordinator_layout;`

### Related IDs (in `com/instagram/android/R.java`)

```
tab_bar                          = 0x7f0b3f67   (R.java:33280)
tab_bar_shadow                   = 0x7f0b3f68   (R.java:33281)
tab_button_count                 = 0x7f0b3f69   (R.java:33282)
tab_icon                         = 0x7f0b3f6f   (R.java:33288)
tab_avatar                       = 0x7f0b3f66   (R.java:33279)
ls_nav_bar                       = 0x7f0b248e   (R.java:26490)  -- tablet side nav
ls_nav_bar_shadow                = 0x7f0b248f   (R.java:26491)
swipeable_tab_view_pager         = 0x7f0b3f45   (R.java:33247)  -- the reels/feed host
layout_container_main            = 0x7f0b2246   (R.java:25911)
layout_container_main_panel      = 0x7f0b2248   (R.java:25912)
layout_activity_main_coordinator_layout           = 0x7f0e0943  (R.java:37681)
layout_activity_main_coordinator_layout_viewpager2= 0x7f0e0944  (R.java:37682)

igds_color_clips_tab_bar_background = 0x7f040713  (R.java:1728)
igds_color_clips_tab_bar_icon       = 0x7f040714  (R.java:1729)
igds_color_reels_tab_bar_separator  = 0x7f0407d6  (R.java:1923)
igds_color_primary_background       = 0x7f0407af  (R.java:1884)
igds_color_primary_icon             = 0x7f0407b5  (R.java:1890)
igds_color_separator                = (attr, used in C2ZS.A0B)
tabBarHeight                        = 0x7f040d30  (R.java:2998)  -- attr
```

### Per-tab button wrapper

Each tab button (Home / Reels / Create / Search / Profile etc.) is a
`C26570bK` instance (concrete subclass of `AbstractC26550bI`):

- **`p002X/C26570bK.java`** — concrete per-tab button class
  (`X.0bK` original, loaded from `classes13.dex`).
- **`p002X/AbstractC26550bI.java`** — abstract base; has the
  icon-tint and image-resource methods.
- Tab enum: **`p002X/EnumC108993ky.java`** (`X.3ky` original,
  `__redex_internal_original_name = "IgTab"`). Tab identity table:
  ```
  A0B = FEED     fragment_feed       R.id.feed_tab      tab_home_drawable
  A0D = NEWS     fragment_news       R.id.news_tab      tab_activity_heart_drawable
  A0H = SHARE    fragment_share      R.id.share_tab     tab_camera_drawable     (legacy camera/create)
  A09 = CREATION fragment_share      R.id.creation_tab  tab_camera_drawable     (current "+" create)
  A0G = SEARCH   fragment_search     R.id.search_tab    tab_search_drawable
  A0F = PROFILE  fragment_profile    R.id.profile_tab   tab_profile_drawable
  A08 = CLIPS    fragment_clips      R.id.clips_tab     tab_clips_drawable     <-- Reels
  A0A = DIRECT   fragment_direct_tab R.id.direct_tab    tab_direct_drawable
  ```
  (EnumC108993ky.java:72-88)

The tab buttons are created at `InstagramMainActivity.java:1179`
(`A0J()` -> `beginCreateTabButtons$tabViews$1$1` inner class at line 1217)
and then attached to either `A0F` (phone `R.id.tab_bar`) or the tablet
side nav (`A01(userSession, 0)` returns `R.id.ls_nav_bar`).

---

## 2. How the background is set — `C26630bQ` (the TabBar colour controller)

**`p002X/C26630bQ.java`** (`X.0bQ` original) is a singleton
(`A00`) that owns every paint call on the tab bar. Key methods:

### `A04` — paint background + separator (lines 120-138)

```java
// p002X/C26630bQ.java:120
public static final void A04(Activity activity, UserSession userSession, int i, int i2) {
    View viewFindViewById = activity.findViewById(R.id.tab_bar);          // line 121
    View viewFindViewById2 = activity.findViewById(R.id.ls_nav_bar);      // line 122
    if (viewFindViewById != null) {
        AbstractC27310cW.A0R(viewFindViewById, activity.getColor(i), -1293857592); // line 124  <-- bg = i
    }
    if (viewFindViewById2 != null) {
        AbstractC27310cW.A0R(viewFindViewById2, activity.getColor(i), 829964805);   // line 127
    }
    View viewFindViewById3 = activity.findViewById(R.id.tab_bar_shadow);     // line 129
    View viewFindViewById4 = activity.findViewById(R.id.ls_nav_bar_shadow);  // line 130
    if (viewFindViewById3 != null) {
        AbstractC27310cW.A0R(viewFindViewById3, activity.getColor(i2), -502183527); // line 132  <-- shadow = i2
    }
    if ((C64121un.A00 && C0PQ.A0J(userSession)) || viewFindViewById4 == null) {
        return;                                                                                          // line 134-136
    }
    AbstractC27310cW.A0R(viewFindViewById4, activity.getColor(i2), 1118723360); // line 137
}
```

`AbstractC27310cW.A0R` is the setBackgroundColor wrapper
(`p002X/AbstractC27310cW.java:147-150`):

```java
public static void A0R(View view, int i, int i2) {
    A0d(view, "setBackgroundColor", i2);
    view.setBackgroundColor(i);   // line 149  <-- the actual call
}
```

So when Reels is entered, `i = igds_color_clips_tab_bar_background`
(black, `0x7f040713`) and `i2 = igds_color_reels_tab_bar_separator`
(`0x7f0407d6`) — that is exactly the "solid black bar" we see.

### `A05` — predicate "is the bar currently using the primary background?" (lines 140-151)

Returns `true` iff the bar's background `ColorDrawable` colour equals
`igds_color_primary_background`. Used by the rotation handler at
`InstagramMainActivity.java:4111` to decide whether to swap to clips
colours.

### `A02` — bulk layout resize (lines 69-111)

Walks every view whose height/margin depends on the tab bar height and
re-applies `R.attr.tabBarHeight`. Used at activity start. The list of
dependent views (lines 76, 85) is important — these are the views that
need to be aware of any future transparency:

```java
// height = tabBarHeight:
activity.findViewById(R.id.tab_bar)            // line 76
activity.findViewById(R.id.tab_button_count)   // line 76
// bottomMargin = tabBarHeight:
activity.findViewById(R.id.layout_bottom_searchbar)         // line 85
activity.findViewById(R.id.layout_container_main)           // line 85
activity.findViewById(R.id.tab_bar_shadow)                  // line 85
activity.findViewById(R.id.whitehat_indicator_stub)         // line 85
activity.findViewById(R.id.devserver_indicator_stub)        // line 85
// topMargin = tabBarHeight:
activity.findViewById(R.id.qe_tool_overlay_stub)            // line 72
activity.findViewById(R.id.network_shaping_stub)            // line 72
```

### `A08` — reset icon tint to primary (lines 189-194)

```java
public final void A08(Activity activity) {
    for (AbstractC26550bI abstractC26550bI : A01(activity, new AMT(8))) {
        int color = activity.getColor(AbstractC26520bF.A0Z(activity, R.attr.igds_color_primary_icon));
        abstractC26550bI.A0B(color, Integer.valueOf(color));   // line 192
    }
}
```

### `A09` — set icon tint to a custom colour (lines 196-202)

```java
@NeverInline
public final void A09(Activity activity, int i) {
    for (AbstractC26550bI abstractC26550bI : A01(activity, new AMT(8))) {
        int color = activity.getColor(i);
        abstractC26550bI.A0B(color, Integer.valueOf(color));   // line 200
    }
}
```

### `A01` — iterate over all tab button wrappers (lines 40-67)

Walks the children of `R.id.tab_bar` AND `R.id.ls_nav_bar`, applies the
passed `AMT` lambda (which casts each child's tag to
`AbstractC26550bI`) and returns the list. This is the single chokepoint
to reach every tab button regardless of phone/tablet layout.

### `A0B` — swap the Reels icon to "auto-scroll outline" variant (lines 214-222)

```java
public final void A0B(Activity activity, UserSession userSession, boolean z) {
    for (AbstractC26550bI abstractC26550bI : A01(activity, new AMT(8))) {
        EnumC108993ky enumC108993ky = abstractC26550bI.A03;
        if (enumC108993ky == EnumC108993ky.A08) {                          // CLIPS tab
            abstractC26550bI.A0A(z ? R.drawable.instagram_auto_scroll_outline_24
                                   : A06(context, userSession, enumC108993ky));  // line 219
        }
    }
}
```

---

## 3. Icon tinting — `ColorFilterAlphaImageView`

Each tab button's icon view (`R.id.tab_icon`, `0x7f0b3f6f`) is a
**`com.instagram.common.p071ui.colorfilter.ColorFilterAlphaImageView`**
(loaded from `classes13.dex`, marked `@Deprecated` but still in use).
It is inflated from `R.layout.tab_button` (default),
`R.layout.badged_tab_button` (FEED with badge),
`R.layout.toasting_badged_tab_button` (NEWS / PROFILE),
or `R.layout.tab_button_count` (DIRECT).

The icon is wired up in `C26570bK` constructor (lines 282-298):

```java
// p002X/C26570bK.java:282
if (enumC108993ky != EnumC108993ky.A0F) {                                 // everything except PROFILE
    ViewStub viewStub = (ViewStub) this.A04.findViewById(R.id.tab_icon_stub);
    ImageView imageView = (ImageView) (viewStub != null ? viewStub.inflate() : this.A04).requireViewById(R.id.tab_icon);
    imageView.setImageResource(C26630bQ.A00.A06(context, userSession, enumC108993ky));  // line 289
    ...
}
// For PROFILE, an IgImageView (avatar) is added via R.layout.tab_profile_button (line 306)
```

### `AbstractC26550bI.A0B(int activeColor, Integer normalColor)` (lines 199-216)

```java
public void A0B(int i, Integer num) {
    ColorFilterAlphaImageView colorFilterAlphaImageView;
    View viewFindViewById = ((C26570bK) this).A04.findViewById(R.id.tab_icon);   // line 201
    if (viewFindViewById instanceof ColorFilterAlphaImageView) {
        colorFilterAlphaImageView = (ColorFilterAlphaImageView) viewFindViewById;
        if (colorFilterAlphaImageView != null) {
            colorFilterAlphaImageView.setActiveColor(i);                         // line 205  <-- active tint
        }
    } else {
        colorFilterAlphaImageView = null;
    }
    if (num != null) {
        int iIntValue = num.intValue();
        if (colorFilterAlphaImageView != null) {
            colorFilterAlphaImageView.setNormalColor(iIntValue);                 // line 213  <-- normal tint
        }
    }
}
```

### `ColorFilterAlphaImageView` (lines 42-52, 96-128)

```java
// com/instagram/common/p071ui/colorfilter/ColorFilterAlphaImageView.java:42
private final void A01() {
    Integer num = this.A05;                                  // normalColor
    if (num != null) {
        int iIntValue = num.intValue();
        Integer num2 = this.A04;                            // activeColor
        if (num2 == null) {
            num2 = num;
        }
        setImageTintList(AbstractC26610bO.A01(iIntValue, num2.intValue(),
                                              this.A01, this.A02, this.A03, this.A00));  // line 50
    }
}

public final void setActiveColor(int i) { ... this.A04 = numValueOf; A01(); }   // line 96
public final void setNormalColor(int i) { ... this.A05 = numValueOf; A01(); }   // line 122
```

The tint list is built by `AbstractC26610bO.A01(...)` with separate
alpha for normal/active/pressed/disabled states (defaults
`A01=A02=A03 = Rpc$RpcRequest.PROTOCOLVERSION_FIELD_NUMBER = 5`,
`A00 = 77`).

**Implication:** to make every icon "white-line" we set both active and
normal colors to `Color.WHITE` (or the existing
`igds_color_clips_tab_bar_icon` if it is already white). The code path
already does this when entering Reels via `C26630bQ.A09(activity,
igds_color_clips_tab_bar_icon)`.

---

## 4. Layout placement — how the bar is attached and how the gap is created

### The activity layout root

`InstagramMainActivity.A28()` (line 4393) returns
`R.layout.layout_activity_main_coordinator_layout[_viewpager2]`, which
contains both `R.id.layout_container_main_panel` (the fragment host) and
`R.id.tab_bar` (the bottom nav) as siblings inside a `ConstraintLayout`
(see `C34210ne.A03()` at line 134-156 which casts
`A0D.findViewById(R.id.layout_container_main_panel)` to
`ConstraintLayout` and re-applies constraints).

The XML layout file itself is NOT in the jadx dump (`--no-res`); it
must be inspected via apktool at
`res/layout/layout_activity_main_coordinator_layout.xml`.

### The "gap" — `swipeable_tab_view_pager.bottomMargin = tabBarHeight`

The bottom margin that creates the black gap below the Reels video is
applied in **`InstagramMainActivity.A0V(int i)`** (lines 1383-1433):

```java
// com/instagram/mainactivity/InstagramMainActivity.java:1383
private final void A0V(int i) {
    ...
    int dimensionPixelOffset = getResources().getDimensionPixelOffset(
            AbstractC26520bF.A0Z(this, R.attr.tabBarHeight));                       // line 1399
    C0ZS c0zs = this.A06;
    if (i == 8) {                                                                   // GONE
        ...
        ((BaseFragmentActivity) this).A00 = dimensionPixelOffset;                   // line 1405
        BaseFragmentActivity.A19(this, C97373Hm.M62.A00());
        View viewFindViewById = findViewById(R.id.swipeable_tab_view_pager);        // line 1407
        layoutParams = viewFindViewById != null ? viewFindViewById.getLayoutParams() : null;
        if ((layoutParams instanceof ViewGroup.MarginLayoutParams)
                && (marginLayoutParams2 = (ViewGroup.MarginLayoutParams) layoutParams) != null) {
            marginLayoutParams2.bottomMargin = 0;                                   // line 1410  <-- GAP REMOVED
        }
    } else {                                                                        // VISIBLE
        ...
        ((BaseFragmentActivity) this).A00 = 0;                                      // line 1416
        BaseFragmentActivity.A19(this, C97373Hm.M62.A00());
        View viewFindViewById2 = findViewById(R.id.swipeable_tab_view_pager);       // line 1418
        layoutParams = viewFindViewById2 != null ? viewFindViewById2.getLayoutParams() : null;
        if ((layoutParams instanceof ViewGroup.MarginLayoutParams)
                && (marginLayoutParams = (ViewGroup.MarginLayoutParams) layoutParams) != null) {
            marginLayoutParams.bottomMargin = dimensionPixelOffset;                 // line 1421  <-- GAP = tabBarHeight
        }
    }
    ...
    ViewGroup viewGroup2 = A0F(this).A0F;
    if (viewGroup2 != null) {
        AbstractC27310cW.A0T(viewGroup2, i, -106430699);                            // line 1431  setVisibility(i)
    }
}
```

So:
- `i == 0` (VISIBLE) → `swipeable_tab_view_pager.bottomMargin = tabBarHeight`
  (≈56-64dp). This is the **black strip below the Reels video**.
- `i == 8` (GONE) → `swipeable_tab_view_pager.bottomMargin = 0`.

`swipeable_tab_view_pager` (`0x7f0b3f45`) is the ViewPager2 that hosts
the swipeable tab fragments (Feed, Reels, Search, Profile…). It is
initialized in `C0ZS` (`p002X/C0ZS.java:226-262`) as a `ViewPager2` —
see `viewPager2.setAdapter(new C39060vT(...))` at line 262.

### Public entry: `Gvc(int i)` — the IG-wide tab-bar visibility API

`InstagramMainActivity.Gvc(int i)` (lines 7992-8018) implements
`InterfaceC78925Uol.Gvc`. It is called from ~60 places (Reels viewer,
live, direct, surveys, contextual feed, etc.).

```java
// com/instagram/mainactivity/InstagramMainActivity.java:7992
@Override   // p002X.InterfaceC78925Uol
public final void Gvc(int i) {
    ViewGroup.MarginLayoutParams marginLayoutParams;
    if (isDestroyed()) return;
    if (C64121un.A0E(C0XW.A00(getResources().getConfiguration().screenWidthDp))) {  // tablet/foldable
        this.A01 = i;
        A0X(i, true);                                                              // line 8000
        View v = findViewById(R.id.swipeable_tab_view_pager);
        ViewGroup.LayoutParams lp = v != null ? v.getLayoutParams() : null;
        if (!(lp instanceof ViewGroup.MarginLayoutParams) || ...) return;
        marginLayoutParams.bottomMargin = 0;                                       // line 8006  <-- always 0 on tablet
        return;
    }
    if (this.A0J) return;
    this.A01 = i;
    A0V(i);                                                                        // line 8013  <-- phone path
    C26630bQ c26630bQ = C26630bQ.A00;
    if (this instanceof InterfaceC78925Uol) {
        C26630bQ.A01.GyR(Boolean.valueOf(i == 0));                                 // line 8016
    }
}
```

### Other related visibility helpers

- `A0W(int i)` (line 1435) — toggles the tablet side-nav-title container.
- `A0X(int i, boolean z)` (line 1449) — tablet path that also collapses
  the side-nav stubs to width/height = 0 when hidden (lines 1459-1469).

---

## 5. Visibility / lifecycle on Reels — bar stays VISIBLE, only colour changes

The key insight: **Instagram does NOT hide the bottom nav on Reels.**
The bar remains `VISIBLE` (i = 0). What changes is its **colour**:

- Tab bar background `tab_bar` -> `igds_color_clips_tab_bar_background` (black)
- Tab bar shadow `tab_bar_shadow` -> `igds_color_reels_tab_bar_separator`
- Tab icon tint -> `igds_color_clips_tab_bar_icon` (white)

This is done in **`p002X/C2ZS.java`** (`X.2ZS` original — the
"system UI manager for tab-bar theming"). The class is a singleton
(`A00`) and is the **single chokepoint** for entering/exiting the
Reels-style tab bar theme.

### Enter Reels — `C2ZS.A02` / `A03` (lines 108-116)

```java
// p002X/C2ZS.java:108
@NeverInline
public static final void A02(Activity activity, Fragment fragment, UserSession userSession, boolean z, boolean z2) {
    C109103l9.A0U(userSession, 2);
    A01(activity, fragment, userSession,
        AbstractC26520bF.A0Z(activity, R.attr.igds_color_clips_tab_bar_icon),   // icon tint = clips icon color
        z, z2, false);
}

// p002X/C2ZS.java:113
public static final void A03(Activity activity, Fragment fragment, UserSession userSession, boolean z, boolean z2, boolean z3) {
    C109103l9.A0U(userSession, 2);
    A01(activity, fragment, userSession,
        AbstractC26520bF.A0Z(activity, R.attr.igds_color_clips_tab_bar_icon),
        z, z2, z3);
}
```

### Enter Reels (the actual colour work) — `C2ZS.A01` (lines 36-105)

```java
// p002X/C2ZS.java:36
public static final void A01(Activity activity, Fragment fragment, UserSession userSession, int i, boolean z, boolean z2, boolean z3) {
    if (A09(userSession) && fragment != null) {
        ((AbstractMap) A01.getValue()).put(activity, fragment);
    }
    int iA0W = AbstractC26520bF.A0W(C26560bJ.A01(activity), R.attr.igds_color_primary_background);  // line 40
    if (z) {                                                                                          // line 41
        C26630bQ.A04(activity, userSession,
            AbstractC26520bF.A0Z(activity, R.attr.igds_color_clips_tab_bar_background),              // line 42  <-- bar bg = black
            AbstractC26520bF.A0Z(activity, R.attr.igds_color_reels_tab_bar_separator));              // line 42  <-- shadow
        C26630bQ c26630bQ = C26630bQ.A00;
        c26630bQ.A09(activity, i);                                                                    // line 44  <-- icon tint
        c26630bQ.A0A(activity, userSession, i);                                                       // line 45  <-- tablet icon tint
    }
    ...
    // Below: paints the system navigation bar, status bar, and the activity decorView background.
    // Lines 70-93: window.addFlags(FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS), setNavigationBarColor(iA0W), decorView.setBackgroundColor(iA0W).
}
```

### Swipe-transition interpolation — `C2ZS.A0A` (lines 159-210)

Used while swiping between Feed and Reels (or between two themed
surfaces). It linearly interpolates the tab bar colour between the two
end-states via `C140164u9.A02(f, i, i2)` and then calls
`AbstractC27310cW.A0R(...)` on `tab_bar`, `ls_nav_bar`,
`tab_bar_shadow`, `ls_nav_bar_shadow`, and `decorView`, plus
`AbstractC26550bI.A0B(iA03, iA03)` for each icon.

### Exit Reels — `C2ZS.A0B` (lines 213-282)

```java
// p002X/C2ZS.java:213
public final void A0B(Activity activity, Fragment fragment, UserSession userSession, boolean z, boolean z2) {
    ...
    if (z) {                                                                                          // line 222
        C26630bQ c26630bQ = C26630bQ.A00;
        View v1 = activity.findViewById(R.id.tab_bar);
        View v2 = activity.findViewById(R.id.ls_nav_bar);
        if (v1 != null) {
            AbstractC27310cW.A0R(v1, activity.getColor(
                AbstractC26520bF.A0Z(activity, R.attr.igds_color_primary_background)), 1917613381);  // line 227  <-- bar bg = primary
        }
        if (v2 != null) {
            AbstractC27310cW.A0R(v2, AbstractC26520bF.A06(activity), -1736172191);                    // line 230
        }
        View v3 = activity.findViewById(R.id.tab_bar_shadow);
        View v4 = activity.findViewById(R.id.ls_nav_bar_shadow);
        if (v3 != null) {
            AbstractC27310cW.A0R(v3, activity.getColor(
                AbstractC26520bF.A0Z(activity, R.attr.igds_color_separator)), 321580294);             // line 235
        }
        if ((!C64121un.A00 || !C0PQ.A0J(userSession)) && v4 != null) {
            AbstractC27310cW.A0R(v4, activity.getColor(
                AbstractC26520bF.A0Z(activity, R.attr.igds_color_separator)), 879064636);             // line 238
        }
        c26630bQ.A08(activity);                                                                       // line 240  <-- icon tint -> primary_icon
        c26630bQ.A0A(activity, userSession, activity.getColor(
            AbstractC26520bF.A0Z(activity, R.attr.igds_color_primary_background)));                   // line 241
    }
    ...
}
```

### Where these are called

`C2ZS.A02 / A03` (enter Reels) is called by:
- `ReelViewerFragment.java:6572, 9368` (Stories, not Reels tab, but
  uses the same theming API)
- `C48247ISr.java:217, 235` — Clips tray enter/exit
- `C65607PAk.java:145` — Clips tab exit
- `C65607PAk.java:171` calls `A07` which is the "soft enter"
  (`z = false` path that only changes icon tint, not bar background).
- `C109343lX.java:973`
- `C27528AFt.java:860`
- Many others — see the grep in the work-log.

`C2ZS.A06` (exit Reels; calls `A0B`) is called by:
- `C55091gE.java:4934` — the NewsfeedFragment
- `ReelViewerFragment.java:18171, 18179`
- `C48247ISr.java:225` — Clips tray exit
- `C65607PAk.java:169` — Clips tab exit
- Many others.

### Reels (Clips) tab entry path

`C65607PAk.java:145` is `C2ZS.A02(activity, this, getSession(), false, true)`
followed at line 169 by `C2ZS.A06(activity, getSession(), true)` on exit
and line 171 by `C2ZS.A07(activity, getSession(), false)` (soft re-enter
— icon tint only, no bg change) — this is the **ClipsTabFragment**
lifecycle. `C65607PAk` should be examined in a sibling task to confirm
the exact `onResume/onPause` mapping.

Also `C65632PBj.java:74`, `C65637PBo.java:1262`, `PBQ.java:63`,
`PBZ.java:92`, `C86273YQn.java:171`, `YQ1.java:73`,
`C49148IlS.java:136, 193`, `FVF.java:4529`, `C124064Md.java:1165`
all call `C2ZS.A04` (the "soft enter" — `z = false`, only sets icon
tint, NOT the bar background). This is a separate code path used by
the comment sheet / direct / IGTV surfaces where they want white icons
on a still-dark bar.

---

## 6. The "+" / Create button

There is **no special create-button view**. The "+" is just the
`EnumC108993ky.A09 = CREATION` (or legacy `A0H = SHARE`) tab button,
built by the same `C26570bK` constructor with the same
`R.layout.tab_button` layout and icon `R.drawable.tab_camera_drawable`
(see `EnumC108993ky.java:77-78`).

Its tint is set by the same `AbstractC26550bI.A0B(...)` call as every
other tab — when entering Reels, `C26630bQ.A09` walks every tab
(including the create tab) and sets both active/normal colours to
`igds_color_clips_tab_bar_icon`. No special handling needed.

The camera/create flow itself has a separate `MediaTabBar` class
(`com/instagram/creation/base/p074ui/mediatabbar/MediaTabBar.java`) —
that is the in-camera top tab bar (Story/Reel/Live), NOT the main
bottom nav. Not relevant to Feature B.

The Barcelona (Threads) tabbar at
`com/instagram/barcelona/bds/components/navigation/tabbar/` is the
Threads app's tabbar — only gesture helpers (`BdsTabBarButtonGesturesKt`)
are present, no Threads tab bar view is shipped in the IG APK. Not
relevant.

---

## 7. FixedTabBar (NOT used for main bottom nav)

`com/instagram/p132ui/widget/fixedtabbar/FixedTabBar.java` (a
`FrameLayout`) is a top-of-screen tab strip used by `ArchiveReelTabbedFragment`
(see grep `FixedTabBar` results). It inflates
`R.layout.fixed_tabbar_layout` (line 83) and uses a
`FixedTabBarIndicator` underline. It is **not** the bottom navigation
bar. (Initial entry-point hint was misleading; confirmed by the lack
of `R.id.tab_bar` reference in `FixedTabBar.java`.)

---

## Patch implications — what to change to make the nav float transparent with white icons

Goal: in Reels (and ideally feed/profile too), make `R.id.tab_bar`
transparent, the icons white, and remove the bottom-margin gap so the
video extends behind the bar.

### Change 1 — make the tab bar background transparent on Reels

File: **`p002X/C26630bQ.java`**, method `A04` (lines 120-138).

Currently:
```java
AbstractC27310cW.A0R(viewFindViewById, activity.getColor(i), -1293857592);   // line 124
```
where `i` is `igds_color_clips_tab_bar_background`.

Patch options (smali-level):
1. **Best:** replace `activity.getColor(i)` with `0` (Color.TRANSPARENT)
   when `i == R.attr.igds_color_clips_tab_bar_background`. Easiest is to
   hijack `A04`: if first arg matches `igds_color_clips_tab_bar_background`,
   substitute `0` for both `i` and `i2`. That kills both the bar bg and
   the separator.
2. **Alternative:** edit the colour resource `igds_color_clips_tab_bar_background`
   itself in `res/values/colors.xml` (apktool) to `#00000000`. This also
   affects `igds_color_reels_tab_bar_separator` if desired. Lower-risk,
   smaller diff, but global (affects every place that reads the attr).

Same change for `R.id.tab_bar_shadow` (line 132) and `R.id.ls_nav_bar_shadow`
(line 137) — set to transparent too, or the shadow line will still draw
on top of the video.

### Change 2 — make the icons solid white (already white on Reels, but make it explicit)

File: **`p002X/C26630bQ.java`**, method `A09` (lines 196-202).

The default `igds_color_clips_tab_bar_icon` is already white-ish in the
dark theme, so this works as-is. To guarantee white in every theme, in
`A09` substitute `Color.WHITE` (0xFFFFFFFF) for `activity.getColor(i)`.
Same for `A0A` (lines 205-212) which calls `A08(i)` on each tab — also
substitute white.

Alternatively edit `igds_color_clips_tab_bar_icon` in
`res/values/colors.xml` to `#FFFFFFFF`.

### Change 3 — REMOVE the bottom-margin gap so video extends behind the bar

File: **`com/instagram/mainactivity/InstagramMainActivity.java`**,
method `A0V(int i)` (line 1421).

Currently when `i != 8` (bar visible):
```java
marginLayoutParams.bottomMargin = dimensionPixelOffset;   // line 1421  <-- tabBarHeight
```
Patch: force `bottomMargin = 0` unconditionally (both branches). The
simplest smali edit is to replace the `marginLayoutParams.bottomMargin = dimensionPixelOffset`
instruction at line 1421 with `= 0`. (Equivalently, replace
`dimensionPixelOffset` with `0` only at line 1421, leaving the GONE
branch alone.)

For the tablet path, also patch `Gvc(int)` at line 8006 — it already
sets `bottomMargin = 0`, so no change needed there.

### Change 4 (optional) — make the bar TRANSLUCENT instead of fully transparent

If a TikTok-style "frosted" look is wanted, do NOT set the bg to 0;
instead set it to `0x80000000` (50% black) and additionally apply a
`BlurView` behind the bar. That requires adding a custom view in
`R.layout.layout_activity_main_coordinator_layout.xml`. Out of scope
for the minimal patch — defer until Change 1-3 verified.

### Change 5 (optional) — verify the gap is not re-applied elsewhere

`C26630bQ.A02` (lines 69-111) re-applies `tabBarHeight` to
`R.id.layout_container_main`, `R.id.layout_bottom_searchbar`,
`R.id.tab_bar_shadow`, etc. on activity start. The fragment host
`layout_container_main` is the parent of `swipeable_tab_view_pager`
on non-swipeable layout variants. If after Change 3 the gap reappears
on some devices, also neutralise `A02`'s `bottomMargin` assignments
at lines 89-91. (Verify post-patch.)

### Smali patching summary

| # | File (smali path) | Method | Line | Change |
|---|-------------------|--------|------|--------|
| 1 | `p002X/C26630bQ.java` | `A04` | 124, 127, 132, 137 | replace colour arg with `0` (TRANSPARENT) when called with clips attrs |
| 2 | `p002X/C26630bQ.java` | `A09` | 200 | replace `activity.getColor(i)` with `0xFFFFFFFF` |
| 2b| `p002X/C26630bQ.java` | `A0A` | 209 | (chained to A08 — patch `A08` line 191 similarly) |
| 3 | `com/instagram/mainactivity/InstagramMainActivity.java` | `A0V` | 1421 | `marginLayoutParams.bottomMargin = 0` |
| 4 | `res/values/colors.xml` | — | — | `igds_color_clips_tab_bar_background` = `#00000000`, `igds_color_clips_tab_bar_icon` = `#FFFFFFFF` (alternative to 1-2b) |

### Resource-only fallback (lowest-risk)

If smali edits are too invasive, do everything via resources:
- `res/values/colors.xml`:
  - `igds_color_clips_tab_bar_background` -> `#00000000`
  - `igds_color_reels_tab_bar_separator` -> `#00000000`
  - `igds_color_clips_tab_bar_icon` -> `#FFFFFFFF`
- `res/values/dimens.xml`:
  - find the dimension referenced by `R.attr.tabBarHeight` and set it
    to `0dp`. (Need to inspect `res/values/attrs.xml` to find the
    concrete `tabBarHeight` dimen; the attr is `0x7f040d30`.)

This alone makes the bar transparent + icons white, AND collapses the
gap (because `dimensionPixelOffset` in `A0V` line 1399 reads the same
dimen). The downside: the bar height also collapses to 0, hiding the
icons. So this is NOT viable alone — the bar height must be preserved
while the bottomMargin is zeroed. So **smali edit at `A0V:1421` is
required** even in the resource-only fallback.

### Confirmation: Reels container bottom padding MUST be removed

Yes — `InstagramMainActivity.A0V` line 1421 (phone) and `Gvc` line
8006 (tablet) are the two places that set the bottom padding/margin
on the Reels host (`swipeable_tab_view_pager`). The phone path sets
it to `tabBarHeight`; that line MUST be patched to 0 for the video
to extend behind the floating nav.
