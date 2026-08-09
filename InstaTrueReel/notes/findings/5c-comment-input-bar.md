# Task 5-c — Comment Input Bar Transparency (HOME FEED reel viewer)

**Agent:** Explore (sub-agent, RETRY tighter scope)
**Scope:** The "Add Comments…" input bar that REPLACES the main nav bar at the
bottom when a reel is opened from the HOME FEED. B2-smali zeroed only
`0bQ.A04` (main nav painter); this bar is a DIFFERENT view and stayed opaque.

Smali root: `/home/z/insta-orig/`

---

## TL;DR

1. **View IDs (per BottomSheetFragment field name + cmJ string log):**
   - `0x7f0b06b2` = `bottom_sheet_container` (a `ViewGroup`) — confirmed by
     `Lcom/instagram/igds/components/bottomsheet/BottomSheetFragment;->bottomSheetContainer:Landroid/view/ViewGroup;`
     at `smali_classes17/com/instagram/igds/components/bottomsheet/BottomSheetFragment.smali:70`,
     populated at line 7395–7403 via `requireViewById(0x7f0b06b2)`.
   - `0x7f0b06b3` = `bottom_sheet_container_stub` (the `ViewStub` that
     lazily inflates `0x7f0b06b2`) — confirmed by the log string
     `"Failed to find container: Neither bottom_sheet_container_stub nor bottom_sheet_container found"`
     at `smali_classes12/X/cmJ.smali:91` (the `:cond_2` branch immediately
     follows the `0x7f0b06b3` lookup at line 81).
   - `0x7f0b2243` (also listed by agent 3-d) is **NOT** the comment composer.
     It is `swipe_navigation_status_bar_manager_hide_nav_bar_layout` — see
     `smali_classes13/X/0tY.smali:173` followed by the string
     `"SwipeNavigationStatusBarManagerHideNavBarLayout"` at line 187.
     Agent 3-d's name mapping for `0x7f0b2243` (`layout_comment_thread_edittext`)
     was incorrect. We do NOT need to touch `0x7f0b2243`.

2. **No smali file calls `setBackgroundColor` / `0cW.A0R` / `0cW.A0S` on
   `0x7f0b06b2` or `0x7f0b06b3`.** Exhaustive grep across all 23 smali files
   that reference these IDs (see "Files referencing the IDs" below) returns
   ZERO background-painting calls. The opaque background is set in the
   **layout XML** that inflates `bottom_sheet_container` (most likely
   `android:background="?igds_color_primary_background"` = BLACK, same as
   the rest of the IG theme — confirmed for `Theme.Instagram` in worklog 5-a).

3. **`6BM.pswitch_6` DOES handle these views — but only for MARGINS, not
   background.** See `smali_classes15/X/6BM.smali:234-274`. It calls
   `LX/6wm;->A0d(Landroid/view/View;I)V` (set bottom margin) and
   `LX/6wm;->A0p(Landroid/view/View;I)V` (set top margin) so the comment
   composer bar dodges the system nav bar. It never touches the background.

4. **Patch:** Add `setBackgroundColor(0)` calls inside `6BM.pswitch_6` on
   the views already looked up (`v1` from `0x7f0b06b3`, `v0` from
   `0x7f0b06b2`). This is the most reliable hook because `pswitch_6` is the
   `WindowInsets` listener callback registered by `BaseFragmentActivity`
   (every `IgFragmentActivity` subclass, including `InstagramMainActivity`),
   so it runs on resume, on keyboard show/hide, and on configuration changes
   — same lifecycle moments when the bar would otherwise be re-painted black
   by the theme. Drop-in smali patch in section "Patch" below.

---

## Q1 — What view ID is the comment input bar?

The "Add Comments…" bar that replaces the main nav bar when a reel is opened
from the home feed is the **`bottom_sheet_container`** (`0x7f0b06b2`), or its
ViewStub `bottom_sheet_container_stub` (`0x7f0b06b3`).

### Evidence

**A. `BottomSheetFragment.smali:70` field declaration** (the smoking gun):
```smali
.field public bottomSheetContainer:Landroid/view/ViewGroup;
```
And its assignment at lines 7395–7403:
```smali
:cond_0
const v0, 0x7f0b06b2
invoke-virtual {p1, v0}, Landroid/view/View;->requireViewById(I)Landroid/view/View;
move-result-object v0
check-cast v0, Landroid/view/ViewGroup;
iput-object v0, p0, Lcom/instagram/igds/components/bottomsheet/BottomSheetFragment;->bottomSheetContainer:Landroid/view/ViewGroup;
```

**B. `cmJ.smali` ("Y View" container finder) lines 16–114** — uses both IDs
and emits the diagnostic strings that name them:
```smali
const v0, 0x7f0b06b3                                  # line 16
invoke-virtual {p1, v0}, Landroid/app/Activity;->findViewById(I)Landroid/view/View;
move-result-object v0
...
:cond_2
const v0, 0x7f0b06b2                                  # line 81
invoke-virtual {p1, v0}, Landroid/app/Activity;->findViewById(I)Landroid/view/View;
move-result-object v0
const-string v1, "InstagramYViewContainerFinder"
if-nez v0, :cond_3
const-string v0, "Failed to find container: Neither bottom_sheet_container_stub nor bottom_sheet_container found"
```
The string `"Neither bottom_sheet_container_stub nor bottom_sheet_container found"`
follows immediately after the `0x7f0b06b2` lookup, naming both IDs.

**C. `8KQ.smali:100-110`** (IgBloksScreenQueryBottomSheetFragment) confirms
the same naming:
```smali
const v0, 0x7f0b06b2
invoke-virtual {v1, v0}, Landroid/app/Activity;->findViewById(I)Landroid/view/View;
move-result-object v5
const-string v1, "IgBloksScreenQueryBottomSheetFragment"
if-nez v5, :cond_2
const-string v0, "bottom_sheet_container missing in activity; skipping InsetsAwareFrameLayout setup"
```

**D. The comment composer "Add Comments…" EditText is inflated INSIDE
`bottom_sheet_container`.** See `smali_classes16/X/9Wz.smali:2458-2499`
(ClipsViewerFragment, the home-feed reel viewer):
```smali
const v7, 0x7f0b0b44
const v0, 0x7f0b0b43                                  # ViewStub for comment composer
invoke-virtual {v1, v0}, Landroid/view/View;->findViewById(I)Landroid/view/View;
move-result-object v0
check-cast v0, Landroid/view/ViewStub;
if-eqz v0, :cond_1
invoke-virtual {v0}, Landroid/view/ViewStub;->inflate()Landroid/view/View;
move-result-object v3
const v0, 0x7f0b2242                                  # comment composer EditText view
invoke-virtual {v3, v0}, Landroid/view/View;->findViewById(I)Landroid/view/View;
move-result-object v0
if-eqz v0, :cond_0
invoke-virtual {v0, v7}, Landroid/view/View;->setId(I)V    # rename to 0x7f0b0b44
:cond_0
...
new-instance v1, LX/3lI;
invoke-direct/range {v1 .. v8}, LX/3lI;-><init>(...)V     # construct comment controller
```
And the fallback at line 2502–2513 (when the ViewStub isn't present):
```smali
:cond_1
const v0, 0x7f0b06b2
invoke-virtual {v1, v0}, Landroid/view/View;->findViewById(I)Landroid/view/View;
move-result-object v3
if-nez v3, :cond_0
const/4 v1, 0x0
goto :goto_0
```
This proves `0x7f0b06b2` (`bottom_sheet_container`) is the FALLBACK container
that holds the comment composer when the dedicated ViewStub (`0x7f0b0b43`)
isn't present — exactly the home-feed-reel-viewer case where the comment
input bar replaces the main nav bar.

### Note on the third ID from agent 3-d

`0x7f0b2243` is NOT the comment composer. It is
`swipe_navigation_status_bar_manager_hide_nav_bar_layout` — see
`smali_classes13/X/0tY.smali:173-187`:
```smali
:cond_2
...
.method public static final A01(LX/0tY;I)V
.locals 5
iget-object v4, p0, LX/0tY;->A05:Landroid/app/Activity;
const v0, 0x7f0b2243
invoke-virtual {v4, v0}, Landroid/app/Activity;->requireViewById(I)Landroid/view/View;
move-result-object v3
const v0, 0x7f0b2b91
invoke-virtual {v4, v0}, Landroid/app/Activity;->requireViewById(I)Landroid/view/View;
move-result-object v2
if-gtz p1, :cond_0
const-string v1, "SwipeNavigationStatusBarManagerHideNavBarLayout"
const-string v0, "_stable_nav_bar"
```
It's the swipe-nav hide-nav-bar layout (referenced by `InstagramMainActivity.smali:19530`,
`3lX.smali:772`, `0zL.smali:169`, `9aO.smali:199`, `RqR.smali:3486`, `0tY.smali:173`,
`3lX.smali:2612`). All of these set padding/margins/translation on it — none set
background. Leave `0x7f0b2243` alone.

---

## Q2 — Which fragment/view shows the "Add comment..." bar from the HOME FEED?

**ClipsViewerFragment** = `smali_classes16/X/9Wz.smali`
(jadx `C254289Wz`, confirmed by `__redex_internal_original_name = "ClipsViewerFragment"`
at line 38). This is the SAME fragment used by both the Reels tab AND the
home-feed reel viewer — the difference is which container it's embedded in.

The comment composer bar is set up by `9Wz.A0W()` (the method containing the
code at lines 2440–2517). It creates an `LX/3lI` instance (the comment
bottom-sheet controller, jadx `C206313lI`) and stores it in
`LX/9Wz;->A0W:LX/3lH;` (line 2498). The string `"clips_bottom_sheet_fragment_tag"`
at `3lI.smali:1897` confirms `3lI` is the clips/reels comment controller.

The home-feed-specific path: when a reel is tapped in `ClipsTabFragment` /
home feed, `InstagramMainActivity` hosts the `ClipsViewerFragment` as a modal
overlay. The `bottom_sheet_container` (`0x7f0b06b2`) — which is part of the
ACTIVITY's main layout (`layout_activity_main_coordinator_layout_viewpager2.xml`,
per worklog 5-a) — becomes visible at the bottom with the comment composer
inside, while the main nav bar (`0x7f0b3f67` = `tab_bar`) is hidden. From the
user's perspective, the comment input bar has "replaced" the nav bar.

---

## Q3 — `setBackgroundColor` calls on the comment composer views

**NONE.** Exhaustive grep across all 23 smali files that reference
`0x7f0b06b2` or `0x7f0b06b3`:

```
smali/com/instagram/base/activity/IgFragmentActivity.smali
smali_classes3/X/EUK.smali
smali_classes3/X/OQC.smali
smali_classes3/X/PJf.smali
smali_classes3/instagram/features/direct/ui/drawer/DirectConversationHistoryActivity.smali
smali_classes4/X/GZJ.smali
smali_classes5/X/RmK.smali
smali_classes5/X/RsP.smali
smali_classes10/X/QG3.smali
smali_classes10/X/gbN.smali
smali_classes10/X/gbO.smali
smali_classes10/X/kmd.smali
smali_classes11/X/oHA.smali
smali_classes11/X/qkA.smali
smali_classes12/X/cmJ.smali
smali_classes13/X/3lI.smali
smali_classes15/X/5g1.smali
smali_classes15/X/6BM.smali
smali_classes15/com/instagram/direct/fragment/permanentmedia/DirectAggregatedMediaViewerController.smali
smali_classes16/X/10d.smali
smali_classes16/X/9Wz.smali
smali_classes17/X/8KQ.smali
smali_classes17/com/instagram/igds/components/bottomsheet/BottomSheetFragment.smali
```

What these files do with the IDs (instead of `setBackgroundColor`):

| File               | What it does with `0x7f0b06b2`/`0x7f0b06b3`                            |
|--------------------|------------------------------------------------------------------------|
| `IgFragmentActivity.smali:5204,5212` | `findViewById` to detect presence, then constructs `LX/3lI` (comment controller). No bg call. |
| `9Wz.smali:2503`    | `findViewById` (fallback when ViewStub absent) — no bg call.           |
| `cmJ.smali:16,81`   | `findViewById` to find container for "Y view" inflation — no bg call.  |
| `8KQ.smali:100`     | `findViewById` to set up InsetsAwareFrameLayout — no bg call.          |
| `BottomSheetFragment.smali:7395` | `requireViewById` → cast to ViewGroup → store in `bottomSheetContainer` field. No bg call. |
| `6BM.smali:239,245` (pswitch_6) | `findViewById` → `6wm.A0d` (bottom margin) + `6wm.A0p` (top margin). **No bg call.** |
| `kmd.smali:81,94`   | `findViewById` → `6wm.A0p` + `6wm.A0d` (margin setters). No bg call.   |
| `oHA.smali:53,146`  | `findViewById` → `6wm.A0i` (bottom padding) + `6wm.A0p` (top margin). No bg call. |
| `3lI.smali:249,3906`| `3lI.<init>` stores `0x7f0b06b3` in `A1O:I`; `A0w()` looks up the view to wrap in `LX/Gsk` (Litho host). No bg call. |
| `DirectAggregatedMediaViewerController.smali:2890,3309` | `findViewById` for the DM composer — no bg call. |
| `DirectConversationHistoryActivity.smali:180` | `findViewById` for DM composer — no bg call. |
| All others (`gbN`, `gbO`, `qkA`, `5g1`, `10d`, `EUK`, `OQC`, `PJf`, `GZJ`, `RmK`, `RsP`, `QG3`) | `findViewById` for various bottom-sheet-style containers — no bg call. |

### Conclusion

The opaque BLACK background on the comment input bar is set in the **layout
XML** that defines `bottom_sheet_container` (resource `0x7f0b06b2` is the
view ID, but the layout XML file that contains it sets
`android:background="?igds_color_primary_background"` or similar — same
BLACK that `Theme.Instagram` uses everywhere, per worklog 5-a). Because we
are running apktool with `-r` (binary resources preserved, no `public.xml`),
we **cannot edit the layout XML directly**. We must override the background
at runtime via smali.

`0cW.A0R(view, color, hash)` is the IG helper that wraps
`view.setBackgroundColor(color)` (see `smali_classes13/X/0cW.smali:333-343`).
This is the same primitive B2-smali used to zero `0bQ.A04`. We use it again
here.

---

## Q4 — `6BM.pswitch_6` (NOT patched by A3) — does it handle this bar?

**YES, but only for insets/margins — NOT for background.**

Full code of `pswitch_6` from `smali_classes15/X/6BM.smali:234-274`:
```smali
:pswitch_6
iget-object v2, p0, LX/6BM;->A00:Ljava/lang/Object;

check-cast v2, Lcom/instagram/base/activity/BaseFragmentActivity;

const v0, 0x7f0b06b3                                  # bottom_sheet_container_stub

invoke-virtual {v2, v0}, Landroidx/appcompat/app/AppCompatActivity;->findViewById(I)Landroid/view/View;

move-result-object v1                                 # v1 = view found by 0x7f0b06b3

const v0, 0x7f0b06b2                                  # bottom_sheet_container

invoke-virtual {v2, v0}, Landroidx/appcompat/app/AppCompatActivity;->findViewById(I)Landroid/view/View;

move-result-object v0                                 # v0 = view found by 0x7f0b06b2

if-eqz v1, :cond_6

invoke-static {v1, p2}, LX/6wm;->A0d(Landroid/view/View;I)V    # set bottom margin = p2

invoke-static {v1, p1}, LX/6wm;->A0p(Landroid/view/View;I)V    # set top margin = p1

:cond_5
:goto_1
invoke-virtual {v2}, Lcom/instagram/base/activity/BaseFragmentActivity;->DAb()LX/3lY;

move-result-object v0

invoke-virtual {v0, p2}, LX/3lY;->A09(I)V

return-void

:cond_6
if-eqz v0, :cond_5

invoke-static {v0, p2}, LX/6wm;->A0d(Landroid/view/View;I)V    # set bottom margin = p2

invoke-static {v0, p1}, LX/6wm;->A0p(Landroid/view/View;I)V    # set top margin = p1

goto :goto_1
```

`6BM` is a multi-purpose `LX/AIn;` (WindowInsets listener) dispatcher. The
`packed-switch` table at lines 287-297 maps case `0x4` → `:pswitch_6`. The
case id is stored in the `$t:I` field set by the constructor
`<init>(Ljava/lang/Object;I)V`. So `pswitch_6` is invoked whenever a
`6BM` instance with `$t == 4` has its `Fji(II)V` method called (the
WindowInsets callback).

`6wm.A0d(view, I)` sets the **bottom margin** (via `ViewGroup.MarginLayoutParams`).
`6wm.A0p(view, I)` sets the **top margin**. Verified at
`smali_classes2/X/6wm.smali:2327` (`A0d`) and `:3064` (`A0p`) — both
manipulate `MarginLayoutParams`, neither calls `setBackgroundColor`.

### Why pswitch_6 is the right hook for the patch

- It already looks up BOTH `0x7f0b06b3` (in `v1`) and `0x7f0b06b2` (in `v0`).
- It runs on every WindowInsets dispatch — which fires on resume, on
  keyboard show/hide, on configuration change, and on fragment
  transitions. This matches the lifecycle moments when the bottom_sheet_container
  would otherwise be re-painted BLACK by the theme.
- It's the SAME `6BM` class that A3 patched (`pswitch_3`, lines 131-195) —
  so we already know the pattern works.
- It operates on `BaseFragmentActivity` (the parent of `IgFragmentActivity`
  and `InstagramMainActivity`), so it covers BOTH the home-feed reel viewer
  AND any other surface that shows the comment composer.

---

## Q5 — Background color/drawable of the comment input bar

Greps for `igds_color.*comment`, `comment.*background`, `composer.*background`:

```
smali_classes13/X/0LZ.smali:456   "light_composer_icon_background_colors"
smali_classes13/X/0LZ.smali:502   "dark_composer_icon_background_colors"
smali_classes17/X/9Ia.smali:154   "theme_composer_background_color"
smali_classes17/X/050.smali:6942  "theme_composer_background_color"
smali_classes17/X/8Fy.smali:208   "theme_composer_background_color"
smali_classes17/X/Ajk.smali:754   "theme_composer_background_color"
smali_classes3/X/8W8.smali:105    "blurred_composer_background_color"
smali_classes3/X/8W8.smali:123    "blurred_composer_opaque_background_color"
```

These are all **theme key strings** (used by IG's dynamic theme system to
look up colors from a server-driven config), not direct painters. They're
consumed by Litho components (the comment composer's EditText is a Litho
section — see `smali_classes18/com/instagram/comments/mvvm/...`). None of
these files reference `0x7f0b06b2` or `0x7f0b06b3`.

### Concrete chain

1. Layout XML for `bottom_sheet_container` sets
   `android:background="?igds_color_primary_background"` (= BLACK, per
   `Theme.Instagram` in `/tmp/insta-res-only/res/values/styles.xml` cited
   in worklog 5-a). This XML is in the binary-only `res/` tree (apktool
   `-r` was used), so we cannot patch it directly.
2. At runtime, `bottom_sheet_container` is found via `findViewById` in
   `6BM.pswitch_6` (for margins), `BottomSheetFragment.onViewCreated`
   (for storage), `3lI.A0w` (for Litho host wrapping), etc.
3. None of these runtime lookups currently override the background.

**Therefore:** the patch must ADD a `setBackgroundColor(0)` call at one of
these runtime lookup sites. `6BM.pswitch_6` is the best site (runs most
often, already looks up both views).

---

## Patch

### Primary patch — `6BM.pswitch_6`

**File:** `/home/z/insta-orig/smali_classes15/X/6BM.smali`

Insert `setBackgroundColor(0)` calls on the looked-up views, immediately
after the existing `6wm.A0d` / `6wm.A0p` margin calls in BOTH branches:

**OLD (lines 251-274):**
```smali
if-eqz v1, :cond_6

invoke-static {v1, p2}, LX/6wm;->A0d(Landroid/view/View;I)V

invoke-static {v1, p1}, LX/6wm;->A0p(Landroid/view/View;I)V

:cond_5
:goto_1
invoke-virtual {v2}, Lcom/instagram/base/activity/BaseFragmentActivity;->DAb()LX/3lY;

move-result-object v0

invoke-virtual {v0, p2}, LX/3lY;->A09(I)V

return-void

:cond_6
if-eqz v0, :cond_5

invoke-static {v0, p2}, LX/6wm;->A0d(Landroid/view/View;I)V

invoke-static {v0, p1}, LX/6wm;->A0p(Landroid/view/View;I)V

goto :goto_1
```

**NEW:**
```smali
if-eqz v1, :cond_6

invoke-static {v1, p2}, LX/6wm;->A0d(Landroid/view/View;I)V

invoke-static {v1, p1}, LX/6wm;->A0p(Landroid/view/View;I)V

# InstaTrueReel: transparent comment composer bar (bottom_sheet_container)
const/4 v3, 0x0
invoke-virtual {v1, v3}, Landroid/view/View;->setBackgroundColor(I)V

:cond_5
:goto_1
invoke-virtual {v2}, Lcom/instagram/base/activity/BaseFragmentActivity;->DAb()LX/3lY;

move-result-object v0

invoke-virtual {v0, p2}, LX/3lY;->A09(I)V

return-void

:cond_6
if-eqz v0, :cond_5

invoke-static {v0, p2}, LX/6wm;->A0d(Landroid/view/View;I)V

invoke-static {v0, p1}, LX/6wm;->A0p(Landroid/view/View;I)V

# InstaTrueReel: transparent comment composer bar (bottom_sheet_container)
const/4 v1, 0x0
invoke-virtual {v0, v1}, Landroid/view/View;->setBackgroundColor(I)V

goto :goto_1
```

**Register choice rationale:** `pswitch_6` has `.locals 6` (per
`.method public final Fji(II)V` at line 32, with `v0..v5` available beyond
`p0`, `p1`, `p2`). In the first branch (`if-eqz v1, :cond_6` fall-through),
`v3` is unused at this point (only `v0`, `v1`, `v2`, `p1`, `p2` are live).
In the `:cond_6` branch, `v1` is unused (the `if-eqz v0, :cond_5` only
needs `v0`). The chosen scratch registers (`v3` and `v1` respectively)
avoid clobbering live values.

**Alternative (cleaner, single insertion):** If you prefer one patch site
instead of two, use `0cW.A0R` (the IG setBackgroundColor wrapper that B2
already uses):

```smali
# In the if-eqz v1 branch (after the two 6wm calls):
const/4 v3, 0x0
const v4, 0x0
invoke-static {v1, v3, v4}, LX/0cW;->A0R(Landroid/view/View;II)V

# In the :cond_6 branch (after the two 6wm calls):
const/4 v1, 0x0
const v3, 0x0
invoke-static {v0, v1, v3}, LX/0cW;->A0R(Landroid/view/View;II)V
```

The `0cW.A0R` wrapper logs the call (for debug builds) — slightly more
overhead but consistent with the B2-smali style. The simpler
`setBackgroundColor(I)V` direct call works identically in production.

### Drop-in `apply_patches.py` block

Add a `B4` block alongside B1/B2-smali/B3 in
`/home/z/MacOS/InstaTrueReel/patches/apply_patches.py`:

```python
# ── Feature B4: transparent comment input bar (bottom_sheet_container) ──
print("\n── Feature B4: comment input bar transparent ──")
sec6BM = find_smali(decoded, '6BM.smali')

# Branch 1: v1 = findViewById(0x7f0b06b3), after the two 6wm margin calls
patch_text(sec6BM,
    '    invoke-static {v1, p2}, LX/6wm;->A0d(Landroid/view/View;I)V\n\n'
    '    invoke-static {v1, p1}, LX/6wm;->A0p(Landroid/view/View;I)V\n\n'
    '    :cond_5\n',
    '    invoke-static {v1, p2}, LX/6wm;->A0d(Landroid/view/View;I)V\n\n'
    '    invoke-static {v1, p1}, LX/6wm;->A0p(Landroid/view/View;I)V\n\n'
    '    # InstaTrueReel: transparent comment composer bar\n'
    '    const/4 v3, 0x0\n\n'
    '    invoke-virtual {v1, v3}, Landroid/view/View;->setBackgroundColor(I)V\n\n'
    '    :cond_5\n',
    'B4-comment-bar-transparent-1')

# Branch 2: v0 = findViewById(0x7f0b06b2), after the two 6wm margin calls
patch_text(sec6BM,
    '    invoke-static {v0, p2}, LX/6wm;->A0d(Landroid/view/View;I)V\n\n'
    '    invoke-static {v0, p1}, LX/6wm;->A0p(Landroid/view/View;I)V\n\n'
    '    goto :goto_1\n',
    '    invoke-static {v0, p2}, LX/6wm;->A0d(Landroid/view/View;I)V\n\n'
    '    invoke-static {v0, p1}, LX/6wm;->A0p(Landroid/view/View;I)V\n\n'
    '    # InstaTrueReel: transparent comment composer bar\n'
    '    const/4 v1, 0x0\n\n'
    '    invoke-virtual {v0, v1}, Landroid/view/View;->setBackgroundColor(I)V\n\n'
    '    goto :goto_1\n',
    'B4-comment-bar-transparent-2')
```

### Verification

After patching, rebuild + install + open a reel from the home feed. The
"Add Comments…" bar at the bottom should show the video bleeding through
its background (instead of solid BLACK). The EditText and its surrounding
icon should remain visible (they're separate child views with their own
backgrounds, not the container's background).

If the bar flashes BLACK on first show before going transparent, that's
because `pswitch_6` runs AFTER the initial layout pass — add a SECOND
patch in `9Wz.smali` right after the ViewStub inflate (line 2472) to
zero the background of the inflated view `v3` before it's added to the
hierarchy:

```smali
invoke-virtual {v0}, Landroid/view/ViewStub;->inflate()Landroid/view/View;

move-result-object v3

# InstaTrueReel: pre-empt the BLACK theme background on the comment composer
const/4 v0, 0x0
invoke-virtual {v3, v0}, Landroid/view/View;->setBackgroundColor(I)V

const v0, 0x7f0b2242
```

This second patch is OPTIONAL — only add it if the primary patch leaves a
visible BLACK flash. It is NOT needed in the common case because
`pswitch_6` fires synchronously on the first WindowInsets dispatch, which
happens before the user sees the bar.

---

## Files referencing the IDs (exhaustive list)

For the next agent's reference, here are all 23 smali files that reference
`0x7f0b06b2` or `0x7f0b06b3` (the bottom_sheet_container pair):

| File                                                                 | Lines              | Purpose                                            |
|----------------------------------------------------------------------|--------------------|----------------------------------------------------|
| `smali/com/instagram/base/activity/IgFragmentActivity.smali`         | 5204, 5212         | Detect presence → construct `LX/3lI` controller    |
| `smali_classes3/X/EUK.smali`                                         | 76                 | Generic bottom-sheet setup                         |
| `smali_classes3/X/OQC.smali`                                         | 85                 | Generic bottom-sheet setup                         |
| `smali_classes3/X/PJf.smali`                                         | 2557               | Generic bottom-sheet setup                         |
| `smali_classes3/instagram/features/direct/ui/drawer/DirectConversationHistoryActivity.smali` | 180 | DM composer |
| `smali_classes4/X/GZJ.smali`                                         | 593                | Generic bottom-sheet setup                         |
| `smali_classes5/X/RmK.smali`                                         | 2726               | Generic bottom-sheet setup                         |
| `smali_classes5/X/RsP.smali`                                         | 105                | Generic bottom-sheet setup                         |
| `smali_classes10/X/QG3.smali`                                        | 507                | Generic bottom-sheet setup                         |
| `smali_classes10/X/gbN.smali`                                        | 115                | Generic bottom-sheet setup                         |
| `smali_classes10/X/gbO.smali`                                        | 447                | Generic bottom-sheet setup                         |
| `smali_classes10/X/kmd.smali`                                        | 81, 94             | DM drawer insets: `6wm.A0d`/`A0p` (margins only)   |
| `smali_classes11/X/oHA.smali`                                        | 53, 146            | Bottom-sheet slide animation: `6wm.A0i`/`A0p`      |
| `smali_classes11/X/qkA.smali`                                        | 712, 720           | Generic bottom-sheet setup                         |
| `smali_classes12/X/cmJ.smali`                                        | 16, 81             | "Y view" container finder (logs the ID names)      |
| `smali_classes13/X/3lI.smali`                                        | 249, 3906          | Comment controller: stores ID in `A1O`, looks up in `A0w` |
| `smali_classes15/X/5g1.smali`                                        | 158                | Generic bottom-sheet setup                         |
| `smali_classes15/X/6BM.smali`                                        | 239, 245            | **`pswitch_6` insets listener (PATCH SITE)**      |
| `smali_classes15/com/instagram/direct/fragment/permanentmedia/DirectAggregatedMediaViewerController.smali` | 2890, 3309 | DM media viewer composer |
| `smali_classes16/X/10d.smali`                                        | 10                 | Generic bottom-sheet setup                         |
| `smali_classes16/X/9Wz.smali`                                        | 2503               | ClipsViewerFragment comment composer fallback      |
| `smali_classes17/X/8KQ.smali`                                        | 100                | IgBloksScreenQueryBottomSheetFragment insets       |
| `smali_classes17/com/instagram/igds/components/bottomsheet/BottomSheetFragment.smali` | 7395 | `bottomSheetContainer` field assignment  |

NONE of these 23 files call `setBackgroundColor` on the looked-up view.

---

## Open questions for next agent

1. **Verify the patch actually makes the bar transparent.** The bar's
   background MIGHT come from a child view (e.g., the EditText's parent
   inside `bottom_sheet_container`) rather than the container itself. If
   zeroing the container doesn't fully clear the BLACK, also zero the
   background of the inflated view `v3` in `9Wz.smali:2472` (the OPTIONAL
   second patch above).

2. **Side effect on other bottom sheets.** `0x7f0b06b2` is the GENERIC
   `bottom_sheet_container` — it hosts ALL IG bottom sheets (share sheet,
   options menu, comment list, etc.), not just the inline comment composer.
   Making it transparent will affect ALL of them. This is likely DESIRED
   (TikTok-style: video visible behind all overlays), but verify visually
   that no bottom sheet becomes unreadable. If a specific sheet needs its
   own opaque background, that sheet's content view should set its own
   background (not rely on the container's).

3. **Litho comment composer EditText background.** The actual
   "Add Comments…" EditText is a Litho component (built by sections in
   `smali_classes18/com/instagram/comments/mvvm/...`). Its own background
   (the rounded pill shape) is set by the Litho section, NOT by
   `bottom_sheet_container`. The patch above does NOT touch the EditText's
   pill background — only the container behind it. The pill will remain
   visible (which is what we want — TikTok shows the comment input pill
   floating over the video).

READ-ONLY exploration complete. No patch code was written.
