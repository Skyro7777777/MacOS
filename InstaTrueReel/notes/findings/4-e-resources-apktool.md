# 4-e — Resource findings (apktool decode of the actual APK)

Decoded the real APK (`/home/z/insta.apk`, 240 MB) with apktool 2.9.3
`-s` (resources only, no smali) → `/home/z/insta-res/` (574 MB). This fills the
gap left by the jadx `--no-res` run. All file paths below are relative to
`/home/z/insta-res/`.

---

## R1. AndroidManifest.xml — InstagramMainActivity

```xml
<activity
  android:configChanges="keyboardHidden|orientation|screenLayout|screenSize|smallestScreenSize"
  android:screenOrientation="locked"
  android:supportsPictureInPicture="true"
  android:theme="@style/Base.Theme.Launcher"
  android:windowSoftInputMode="adjustNothing"
  android:name="com.instagram.mainactivity.InstagramMainActivity" ...>
```

**Implications:**
- `configChanges` includes `orientation|screenSize` → **rotation does NOT
  recreate the activity**; `onConfigurationChanged` handles it. ✅ Our
  activity-level patches (window chrome) survive rotation.
- `screenOrientation="locked"` (=`SCREEN_ORIENTATION_LOCKED`, const 14) →
  runtime `setRequestedOrientation(LANDSCAPE)` **overrides** this (per Android
  docs, runtime call wins). ✅ Feature D rotation works without manifest patch.
  BUT if any device refuses, trivial patch: change `locked` → `unspecified` /
  `fullUser` in the manifest (resource patch). Fallback ready.
- ⚠️ Android 8.0+ throws `IllegalStateException("Only fullscreen activities can
  request orientation")` if the activity theme lacks `windowIsFullScreen=true`.
  Agent 4-b confirmed `AbstractC186396mW.A00` already catches this. ✅ Covered.
  (If needed: add `<item name="android:windowIsFullscreen">true</item>` to the
  activity theme — resource patch.)

---

## R2. Theme chain (runtime)

Manifest declares `android:theme="@style/Base.Theme.Launcher"` — but that's the
SPLASH theme (windowBackground=instagram_splash_screen). At runtime the activity
switches to `Theme.Instagram` (via `setTheme()` in code). The inheritance:

```
Theme.Instagram
  └─ Base.Theme.Instagram  (styles.xml:694)
       ├─ android:windowBackground = ?igds_color_primary_background
       ├─ android:colorBackground  = ?igds_color_primary_background
       └─ Base.Theme (styles.xml:676)
            └─ Theme.AppCompat.DayNight.NoActionBar
```

`Theme.Instagram` (styles.xml, the `statusBarColor` line):
```xml
<item name="android:statusBarColor">?igds_color_primary_background</item>
```

**Implication:** the theme itself sets `statusBarColor` and `windowBackground` to
`?igds_color_primary_background` (resolves to `#ff0c1014` in prism dark theme —
a very dark blue-gray, NOT pure black). The code calls at
`InstagramMainActivity:3256` (`AbstractC54451fC.A03`) OVERRIDE the theme at
runtime. To fully fix: either (a) patch the code calls (3-b's finding), or
(b) override `?igds_color_primary_background` resolution — but (b) would change
the whole app's background, not just Reels. So **(a) code/Smali patch is the
correct path** for Feature A.

---

## R3. igds color values (the "black" strips)

From `res/values/colors.xml` + `res/values/styles.xml`:

| Color / attr | Resolves to | Hex | Where used |
|---|---|---|---|
| `igds_color_clips_tab_bar_background` (attr) | `@color/igds_prism_black` | `#ff0c1014` | bottom nav bg (Reels mode), set in 4 theme variants: styles.xml:4498, 4556, 4768, 4994 |
| `igds_color_clips_tab_bar_icon` (attr) | `@color/igds_prism_gray_00` | `#fff8f9f9` | nav icons — **ALREADY near-white** ✅ |
| `igds_color_reels_tab_bar_separator` (attr) | `@color/igds_prism_gray_09` | `#ff25292e` | nav top separator line |
| `igds_color_primary_background` (attr) | prism dark = `igds_prism_black` | `#ff0c1014` | window/statusBar bg |
| `igds_color_elevated_background` (attr) | prism dark (dark gray) | ~`#ff1a1d22` | comment sheet panel |
| `bds_black_50_transparent` | literal | `#80000000` | 50% black (used by BottomSheetFragment status scrim) |

**Implication for Feature B:** nav icons are ALREADY white (`#fff8f9f9`). We only
need to make the **background** transparent. Two paths:
- **(a) Smali** (3-c's finding): `C26630bQ.A04:124,127,132,137` — substitute `0`
  for the color arg. Cleanest, Reels-scoped.
- **(b) Resource**: edit the 4 theme variants in styles.xml (lines 4498, 4556,
  4768, 4994) to set `igds_color_clips_tab_bar_background` →
  `@color/bds_transparent` or `#00000000`. Global to all Reels-mode bars.
Either works. (a) is more surgical; (b) is simpler to apply via apktool.

---

## R4. tab_bar height + the GAP

The bottom nav height is a **theme attr** `?tabBarHeight` (NOT a dimen — that's
why searching dimens.xml failed):
- `attrs.xml:3461` → `<attr name="tabBarHeight" format="dimension" />`
- Resolved in `styles.xml:881` → `<item name="tabBarHeight">@dimen/tab_bar_height_panorama</item>`
- `tab_bar_height_panorama` = **44.0dip** (hdpi/mdpi/xhdpi) / **48.0dip** (xxhdpi/xxxhdpi).

**The GAP below the reel video** = the code at `InstagramMainActivity.java:1421`
(`A0V`) sets `swipeable_tab_view_pager.bottomMargin = tabBarHeight` (44-48dp).
This margin IS the black strip. Zero it → video extends to the bottom edge.
(Confirmed: the XML layout has NO bottomMargin on `swipeable_tab_view_pager` —
the code adds it.)

---

## R5. layout_activity_main_internal_viewpager2.xml — THE key layout

This is the main activity's content layout (included via
`layout_activity_main_coordinator_layout_viewpager2.xml`). Contains the tab_bar.
Key elements (verbatim from the XML):

```xml
<com.instagram.common.ui.base.IgFrameLayout android:id="@id/layout_container_main_wrapper" ...>
    <!-- FEED container: has marginBottom = ?tabBarHeight (so feed doesn't go under nav) -->
    <IgFrameLayout android:id="@id/layout_container_main"
                   android:layout_marginBottom="?tabBarHeight" ... />

    <!-- REELS host ViewPager2: fill_parent × fill_parent, NO marginBottom in XML -->
    <androidx.viewpager2.widget.ViewPager2 android:id="@id/swipeable_tab_view_pager"
                   android:layout_width="fill_parent" android:layout_height="fill_parent" />

    <!-- tab_bar_shadow: the separator line above the nav -->
    <IgView android:id="@id/tab_bar_shadow"
            android:background="?igds_color_separator"
            android:layout_height="?tabBarSeparatorHeight"
            android:layout_marginBottom="?tabBarHeight" ... />

    <!-- THE BOTTOM NAV: TouchInterceptorLinearLayout, height = ?tabBarHeight, gravity=bottom -->
    <TouchInterceptorLinearLayout android:id="@id/tab_bar"
            android:layout_height="?tabBarHeight" android:layout_gravity="bottom" ... />

    <!-- bottom_sheet_container (for comment sheets) -->
    ...
</IgFrameLayout>
```

**Implications:**
- `tab_bar` is a `TouchInterceptorLinearLayout` — a plain ViewGroup, NOT a
  `BottomNavigationView`. Its background is set in CODE (`C26630bQ.A04`), not
  XML. So Feature B's bg transparency is a Smali patch (or the theme-attr
  resource override in R3-b).
- `swipeable_tab_view_pager` (Reels host) fills the parent fully in XML — the
  bottomMargin is added by code. Zeroing `InstagramMainActivity:1421` removes
  the gap. ✅
- `layout_container_main` (FEED) has `layout_marginBottom="?tabBarHeight"` in
  XML — the feed also has the gap, but the user only cares about Reels. Leave
  feed as-is (or zero it too if desired — low risk).
- `tab_bar_shadow` (separator line) also has `marginBottom=?tabBarHeight` and
  `background=?igds_color_separator` — for TikTok look we likely hide/shrink
  this too.

---

## R6. Clips viewer layouts = BLOKS / LITHO (NOT XML)

**Critical finding:** `layout_clips_tab_fragment`, `layout_clips_viewer_fragment`,
and `bottom_sheet_fragment` do **NOT exist as XML files** in `res/layout/`.
- `find res -name "*clips_tab_fragment*" -o -name "*clips_viewer_fragment*"` → 0 results.
- `layouts.xml` index lists `bottom_sheet_fragment` but with a Bloks-style
  encoding (`L|10ECC|1748|6967`), not a real file.

**Implication:** the Reels viewer UI and the comment sheet are built via
**Bloks** (server-driven UI) or **Litho** (code-defined sections) — NOT
inflatable XML layouts. Therefore:
- **Feature A** (status bar / insets for Reels): MUST be Smali (no XML to edit).
  Hooks already found by 3-b (C2ZS.A01, C6BM, IgFragmentActivity.A1j).
- **Feature C** (comment sheet): the sheet panel bg is set in CODE
  (`BottomSheetFragment.java:1646` ColorFilter, per 4-d), NOT the drawable.
  The drawable `igds_bottom_sheet_background_prism.xml` EXISTS (R7 below) but
  the runtime may not use it directly. Smali patch of line 1646 is the safe path.
- **Feature D** (fullscreen seekbar): the `LegacyClipsAttachedScrubberComponent`
  (`C30423BTc`) is a Litho component — adding it means Litho section patching
  (Smali), not XML.

---

## R7. igds_bottom_sheet_background_prism.xml (the sheet drawable — EXISTS)

`res/drawable/igds_bottom_sheet_background_prism.xml`:
```xml
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="?igds_color_elevated_background" />
    <corners android:radius="32.0dip" />
</shape>
```
Plus a tablet variant (`_tablet.xml`) with `topLeftRadius`/`topRightRadius`.

**Implication:** to make the drawable translucent, change
`?igds_color_elevated_background` → `#CC000000` (80% black) — trivial resource
patch. BUT agent 4-d found the runtime path for Reels comments uses a
**ColorFilter** at `BottomSheetFragment.java:1646` (`setColorFilter(color2,
SRC_IN)` where `color2 = igds_color_elevated_background`), which overlays the
drawable. So **both** must be patched for translucency, OR just patch line 1646
(the ColorFilter) since it's the final paint. Verify at runtime which wins
(open question).

---

## R8. The FULLSCREEN_VIEW string (0x7f13815d)

- `strings.xml` has only 803 lines (IG obfuscates most strings to
  `string_0x7f13XXXX` names, fetched from server/Bloks).
- The string `0x7f13815d` (= 2131984733, the "Fullscreen" popup label per 3-e)
  is **NOT in `strings.xml`** — it's a Bloks/server-defined string.
- **Implication:** we cannot rename/relabel it via resource patch. Not needed
  for our features anyway (Feature D reuses the existing toggle, label stays).

---

## SUMMARY — resource-patch feasibility per feature

| Feature | Resource patch viable? | Smali patch needed? | Notes |
|---|---|---|---|
| A status bar | ❌ no (theme attr is global) | ✅ yes | patch C2ZS.A01:86,99,102,131 + C6BM + IgFragmentActivity:727 |
| B bottom nav bg | ✅ yes (R3-b: 4 theme lines) OR Smali (C26630bQ.A04) | either | icons already white |
| B bottom nav gap | ❌ no (code sets bottomMargin) | ✅ yes | InstagramMainActivity:1421 → 0 |
| B tab_bar_shadow | ✅ yes (XML attr) OR Smali | optional | hide for TikTok look |
| C comment sheet panel | ⚠️ partial (drawable R7) + Smali (line 1646 ColorFilter) | ✅ yes | patch BOTH drawable + code, or just code |
| C dimming layers | ❌ no | ✅ yes | EPN.java:534 + C109193lI.java:546,724 |
| D rotation | ✅ yes (manifest `screenOrientation` fallback) | ✅ yes (primary) | setRequestedOrientation via AbstractC186396mW.A00 |
| D seekbar | ❌ no (Litho component) | ✅ yes | force-show C30423BTc scrubber, bind to C3HU/C50741Yd player |

**Bottom line:** Resources help for Feature B (nav bg) and the sheet drawable
(Feature C partial), but the MAJORITY of patches must be **Smali** because the
Reels viewer + comment sheet + scrubber are Bloks/Litho (code-defined, no XML).
The apktool decode is still essential: it gives us the manifest (orientation
behavior), the theme chain (why bg is black), the tab_bar layout structure, the
prism drawable, and the color values. And we'll NEED apktool to REBUILD the
patched APK (Smali edits + the few resource edits) regardless.
