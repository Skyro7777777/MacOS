# Task 5-b — Caption overlapping bottom nav (post-patch-B1)

Exploration of why the reel caption/username/title text overlaps the
floating bottom nav bar after patch B1 zeroed
`swipeable_tab_view_pager.bottomMargin`, and identification of the
concrete smali patch point to lift the caption above the nav bar.

**Smali root:** `/home/z/insta-orig/` (apktool `-r` decode, binary resources preserved)
**Prior context:** read worklog.md (3-a/3-c/3-d/3-e + 4-a..4-d) and
`/home/z/MacOS/InstaTrueReel/patches/apply_patches.py` (defines patches A1..A3, B1, B2-smali, C1, C2, D1, D2).

---

## TL;DR

- The reel caption (username + follow button + caption text + audio info)
  is rendered by the **Litho section `LX/33g`** (file
  `smali_classes17/X/33g.smali`), NOT by an XML layout. The Litho section
  is mounted inside a `LithoView` hosted in the inner vertical
  `RecyclerView`/`ReboundViewPager` of `ClipsViewerFragment`
  (`smali_classes16/X/9Wz.smali`, jadx name `C254289Wz`).
- The caption+ufi overlay is wrapped by a Litho component keyed
  **`"clips_info_overlay_component"`** (`33g.smali:1027`). This overlay
  wraps both `clips_media_info_component` (R.id `0x7f0b0bc1`, the caption
  block) and `clips_ufi_component` (R.id `0x7f0b0c62`, the side
  like/comment/share buttons).
- The overlay's bottom padding is currently **hard-coded to `0.0`** via
  `LX/JAu(LX/4sC;->A0I:PADDING_BOTTOM, 0.0)` at
  **`33g.smali:1003-1019`**. The caption's bottom position is **NOT**
  computed from `tabBarHeight` (`0x7f040d30`) anywhere in the Litho
  section — the section uses static Litho spacing tokens
  (`LX/4sC` / `LX/5OA` enums) and MobileConfig-driven doubles, never the
  IG `tabBarHeight` attr.
- Therefore B1 (zeroing `swipeable_tab_view_pager.bottomMargin`) DID
  push the caption down to overlap the now-floating nav bar: previously
  the caption's bottom anchor was the top of the bottomMargin gap (i.e.
  the top of the nav bar); with B1 the bottom anchor is the bottom of
  the screen (under the transparent nav bar).
- **Recommended fix (Approach a):** keep B1 + change the overlay's
  `PADDING_BOTTOM` from `0.0` to the nav-bar height. The single smali
  edit is at `33g.smali:1003`:
  `const-wide/16 v3, 0x0` → `const-wide v3, 0x4065000000000000L`
  (= double 168.0 ≈ 56 dp at 3× density — the typical IG tab-bar height).
  A fully dynamic patch (resolve `?tabBarHeight` at runtime) is also
  spelled out below.
- Approach (b) (revert B1 + make the nav bar overlay the video) is
  **rejected**: B2-smali already makes the nav transparent, but with B1
  reverted the pager ends ABOVE the tab bar, leaving a visible primary-bg
  strip below the video that shows through the transparent nav. That is
  the exact black strip Feature B was designed to eliminate.

---

## Q1 — What positions the reel caption/username/title text?

### Smali file for ClipsViewerFragment

The jadx class `X/C254289Wz` is smali **`smali_classes16/X/9Wz.smali`**
(62,253 lines). Confirmed by
`9Wz.smali:38: .field public static final __redex_internal_original_name:Ljava/lang/String; = "ClipsViewerFragment"`.

### The caption block is Litho-rendered, not XML

The ClipsViewerFragment inflates `R.layout.layout_clips_viewer_fragment`
(`9Wz.smali:49386` — `const v0, 0x7f0e0a3a` region, see 3-a finding
`layout_clips_viewer_fragment = 0x7f0e0a39`). That layout contains the
host containers (`root_clips_layout` `0x7f0b35ae`,
`clips_linear_layout_container` `0x7f0b0bbd`, etc.) but the actual reel
UI — video + caption + side buttons — is rendered by a **Litho Section**
mounted in a `LithoView` inside the inner `RecyclerView`/`ViewPager2`.

The Litho section that builds the per-reel UI is **`LX/33g`** in
`smali_classes17/X/33g.smali` (2,921 lines, `.locals 79` in its render
method `A0i`). It is constructed by `LX/Xrr` (see `33g.smali:2677` —
`new-instance ... LX/Xrr;-><init>(... LX/2QX; ...)` — `Xrr` is the
per-reel composite section that bundles the media-info section `2QX`,
the UFI/caption overlay built inline in `33g`, and the video component).

### The two caption-related Litho component keys

Grep of the smali tree for the two R.id values that 3-a/3-e already
mapped:

```
clips_media_info_component  → R.id 0x7f0b0bc1
clips_ufi_component         → R.id 0x7f0b0c62
```

`0x7f0b0bc1` is referenced in:
- `smali_classes17/X/33g.smali:1927` (assigned via `LX/4rZ;->A0C(LX/0XB;I)`)
- `smali_classes17/X/2QX.smali:158` (the media-info section `2QX`)
- `smali_classes17/X/33g.smali:1955` (`const-string "clips_media_info_component"`)

`0x7f0b0c62` is referenced in:
- `smali_classes17/X/33g.smali:2390` (assigned to the UFI wrapper)
- `smali_classes17/X/33g.smali:2384` (`const-string "clips_ufi_component"`)
- `smali_classes8/X/VBP.smali:133,409` (the FSS/EvT fullscreen fade — 3-e)
- `smali_classes17/X/2CR.smali:877` (the UFI sub-section)
- `smali_classes17/X/Hso.smali:187` (touch dispatcher)

### The wrapper that groups caption + ufi: `"clips_info_overlay_component"`

Inside `33g.A0i`, the section builds a wrapper Litho component keyed
**`"clips_info_overlay_component"`** at
**`33g.smali:1027`**:

```smali
# 33g.smali:1001-1031  (excerpt)
sget-object v28, LX/0XB;->A02:LX/4qC;     # empty/null component placeholder

const-wide/16 v3, 0x0                      # ← THE PADDING_BOTTOM VALUE (0.0)
invoke-static {v3, v4}, Ljava/lang/Double;->doubleToRawLongBits(D)J
move-result-wide v16

sget-object v22, LX/4sC;->A0I:LX/4sC;     # PADDING_BOTTOM enum token
const/16 v30, 0x0

new-instance v10, LX/JAu;
move-object/from16 v11, v22
move-wide/from16 v3, v16
invoke-direct {v10, v11, v3, v4}, LX/JAu;-><init>(LX/4sC;J)V
                                          # JAu(PADDING_BOTTOM, 0.0)

new-instance v4, LX/0XB;
move-object/from16 v3, v30
invoke-direct {v4, v3, v10}, LX/0XB;-><init>(LX/0XB;LX/0XC;)V

const-string v3, "clips_info_overlay_component"
invoke-static {v4, v3}, LX/4rZ;->A0F(LX/0XB;Ljava/lang/Object;)LX/0XB;
move-result-object v10                     # v10 = the info-overlay wrapper
```

Then children are appended to `v10` via `LX/0XB;->A00(LX/0XB;)LX/0XB;`:

- `33g.smali:1074` — appends a conditionally-built child (the
  `clips_media_info_component` built in the surrounding block at
  `:1927` via `LX/1Ki;->A0H()LX/0QR;` and `LX/0XG;->A00`).
- `33g.smali:1100` — appends a `LX/D99` click-handler child.
- `33g.smali:1117` — attaches a `LX/Anj` touch handler via
  `LX/7ov;->A06(...)`. `Anj.A00` (`Anj.smali:38-95`) confirms the scope:
  it dispatches taps on **`"clips_media_info_component"`** (line 73) and
  **`"clips_ufi_component"`** (line 89) — i.e. the
  `"clips_info_overlay_component"` is exactly the overlay that covers
  both the caption and the side UFI buttons.

So `clips_info_overlay_component` is the **single Litho wrapper whose
children are the caption block + the UFI column**, and it is the wrapper
whose bottom padding we can raise.

### How the overlay's bottom position is computed

`33g.smali:425` — `.method private final A01(LX/J3H;)LX/XWZ;` builds
the info-overlay into a `LX/4sH` (a Litho Column component —
`4sH.smali:44` picks `LX/4sI;->A03` = `COLUMN` when `p7=false`,
which is what `33g.smali:1220` passes via `move v15, v7` with `v7=0`):

```smali
# 33g.smali:1206-1224
new-instance v8, LX/4sH;
move-object/from16 v9, v18                # v18 = the info-overlay wrapper (with key + padding)
move-object/from16 v10, v30               # null deps
... (null deps) ...
move-object v14, v0                       # the section instance (List arg)
move v15, v7                              # 0 → COLUMN layout
invoke-direct/range {v8 .. v15}, LX/4sH;-><init>(LX/0XB;LX/0XI;LX/4sR;LX/4sR;LX/5Hz;Ljava/util/List;Z)V
return-object v8
```

The `LX/4sH` Column is then handed to `LX/Xrr` (the per-reel composite
section) at `33g.smali:2677` and ultimately laid out inside a `LX/4tP`
(`33g.smali:2459` and `:2493`). The second `4tP` uses
**`LX/4sR;->A07`** (= `FLEX_END`, set at `33g.smali:1277`) as one of
its `LX/4sR` alignment args — that is the flexbox `align-items: flex-end`
that bottom-anchors the caption overlay inside the reel.

### Does the caption read `tabBarHeight` / `0x7f040d30`?

**No.** I grepped every smali file that references BOTH a clips view id
(`0x7f0b0c62`, `0x7f0b0bc1`, `0x7f0b0bbd`, `0x7f0b35ae`,
`clips_ufi`, `clips_media_info`, `clips_info_overlay`, `root_clips`,
`clips_linear_layout`) AND the `tabBarHeight` attr `0x7f040d30`.
**Only `smali_classes11/X/iPM.smali` matches both** — and `iPM` is the
"ClipsOfflineOverlay" (its own error string at `iPM.smali:493`:
`"clips_linear_layout_container not found, bottom bar not attached"`).
`iPM.A00` uses `0x7f040d30` only to size the offline-indicator bar
(`iPM.smali:240-256`) and to add a system-nav-bar-height strip to
`android.R.id.content` (`iPM.smali:280-316`). It is NOT the caption.

`33g.smali` and `2QX.smali` (the two caption-rendering Litho sections)
contain **zero** references to `0x7f040d30`. Their bottom paddings
come from:

- static Litho `LX/4sC` / `LX/5OA` enum tokens (`PADDING_BOTTOM`,
  `MARGIN_BOTTOM`, `POSITION_BOTTOM`) with hard-coded double values, OR
- MobileConfig-driven doubles via
  `MobileConfigUnsafeContext.BiY(J)D` (e.g. `33g.smali:707`,
  `2QX.smali:707,727`).

So the caption's bottom Y is **the bottom of the LithoView's content
area**. Pre-B1 that was the top of the `swipeable_tab_view_pager`
bottomMargin gap (= top of the nav bar). Post-B1 it is the bottom of
the screen. That is the regression.

---

## Q2 — Is the caption position tied to the same bottomMargin we zeroed?

**Indirectly yes, but not via a shared dimen read.** The caption does
not itself read `tabBarHeight`. The link is structural:

```
Activity coordinator layout
└── swipeable_tab_view_pager (R.id 0x7f0b3f45)  ← B1 zeroed its bottomMargin
    └── ClipsTabFragment (C27528AFt → smali_classes16/X/AFt.smali)
        └── clips_tab_view_pager (R.id 0x7f0b0c49)
            └── ClipsViewerFragment (9Wz.smali)
                └── root_clips_layout (R.id 0x7f0b35ae)
                    └── RecyclerView / ReboundViewPager (LX/ADl)
                        └── LithoView (per reel item)
                            └── Litho Section LX/Xrr → 33g.A0i
                                └── LX/4tP (Row, FLEX_END)  ← bottom-anchors children
                                    └── LX/4sH (Column)     ← wraps the info overlay
                                        └── "clips_info_overlay_component" (PADDING_BOTTOM=0)
                                            ├── clips_media_info_component (caption)
                                            └── clips_ufi_component (side buttons)
```

Pre-B1: `swipeable_tab_view_pager.bottomMargin = tabBarHeight` (~56–64 dp).
The pager's content height = screen − tabBarHeight. The LithoView fills
the pager content. The caption (bottom-anchored) sits at Y =
screen − tabBarHeight = top of the nav bar. No overlap.

Post-B1: `swipeable_tab_view_pager.bottomMargin = 0`. The pager's
content height = screen. The LithoView fills the screen. The caption
(bottom-anchored) sits at Y = screen = bottom of the screen, which is
where the (now transparent, B2-smali) nav bar floats. Overlap.

The Litho section's `PADDING_BOTTOM=0` on `clips_info_overlay_component`
(`33g.smali:1003`) was always 0 — it was never the mechanism that
lifted the caption. The lift came from the pager's bottomMargin. With
that gone, the lift must be re-added at the Litho layer.

---

## Q3 — The cleanest fix

### Approach (a) — keep B1, add bottom padding to the caption overlay  ✅ RECOMMENDED

**Single-line smali edit** at `smali_classes17/X/33g.smali:1003`:

```smali
# BEFORE (line 1003):
    const-wide/16 v3, 0x0

# AFTER:
    # InstaTrueReel: lift caption above floating nav bar (≈56dp at 3× = 168px)
    const-wide v3, 0x4065000000000000L
```

Why this works:
- `const-wide/16 v3, 0x0` loaded the bit pattern of `double 0.0` into
  `v3:v4`. The very next two instructions
  (`invoke-static {v3, v4}, Ljava/lang/Double;->doubleToRawLongBits(D)J`
  + `move-result-wide v16`) just re-encode that same double as a long,
  so changing `v3:v4` to the bit pattern of a different double flows
  straight through to the `LX/JAu` constructor at line 1019.
- `0x4065000000000000L` is the IEEE-754 bit pattern of **`double 168.0`**
  (= 56 dp × 3× density = the typical IG `tabBarHeight`). Litho
  padding values are in raw pixels, same as `View.setPadding`.
- The `clips_info_overlay_component` is wrapped in a `LX/4sH` Column
  which is a child of a `LX/4tP` Row with `FLEX_END` cross-axis
  alignment (`33g.smali:1277`) — i.e. the overlay is bottom-anchored.
  Adding `PADDING_BOTTOM` to the overlay inserts a bottom inset inside
  the overlay, pushing its children (caption + ufi) up by that many
  pixels, while the video component (a separate child of the same
  `4tP` Row, NOT a child of `clips_info_overlay_component`) keeps
  filling the screen edge-to-edge.

Caveats:
- The 168 px literal is hard-coded for 3× density (xxhdpi, the most
  common phone density). On 2× (hdpi) it should be 112 px
  (`0x405c000000000000` = double 112.0); on 4× (xxxhdpi) it should be
  224 px (`0x406c000000000000` = double 224.0). A wrong-density device
  will see the caption a few dp too high or too low — still functional,
  just not pixel-perfect.
- It lifts BOTH the caption and the UFI side buttons (they are both
  children of the same overlay). That is the desired TikTok behaviour
  — the side buttons also sit above the nav bar.

### Dynamic variant — resolve `?tabBarHeight` at runtime

If a hard-coded density assumption is unacceptable, the same site can
be patched to resolve the dimen dynamically. The `A0i` method already
has a `LX/2iq` (Litho ComponentContext) in scope as `v78` (set at
`33g.smali:876`), and `LX/2iq;->A0B:Landroid/content/Context;` is the
Android Context. A dynamic patch would replace line 1003 with a
sequence equivalent to:

```java
// pseudo-Java of what the patched smali should do
Context ctx = componentContext.A0B;                        // 33g.smali:876 (v78.A0B)
int dimenResId = AbstractC26520bF.A0Z(ctx, R.attr.tabBarHeight);  // 0x7f040d30
int tabBarHeightPx = ctx.getResources().getDimensionPixelOffset(dimenResId);
double padBottom = (double) tabBarHeightPx;
long padBottomBits = Double.doubleToRawLongBits(padBottom);
// then use padBottomBits in place of v16 when building JAu(PADDING_BOTTOM, …)
```

In smali, that is ~12 extra instructions inserted between line 999
and line 1003, ending with `move-result-wide v16` so the existing
`move-wide/from16 v3, v16` at line 1017 picks up the dynamic value
unchanged. The exact registers must be chosen to avoid the
`.locals 79` allocation already in `A0i` — use high-numbered regs
(e.g. `v70`/`v71`) that are free at that point. This is more surgery
than the static fix but removes the density assumption entirely.

### Approach (b) — revert B1, make the nav bar overlay the video  ❌ REJECTED

This would require:
1. Revert B1: restore `swipeable_tab_view_pager.bottomMargin =
   tabBarHeight` at the 3 sites in `InstagramMainActivity.smali`.
2. Make `R.id.tab_bar` (`0x7f0b3f67`) overlay the pager instead of
   sitting beside it — i.e. move `tab_bar` to draw ON TOP of the
   pager. The activity layout (`layout_activity_main_coordinator_layout`
   = `0x7f0e0943`) is a `ConstraintLayout` (per 3-c); the `tab_bar` and
   `swipeable_tab_view_pager` are siblings. Making `tab_bar` overlay
   the pager means either:
   - editing the XML (requires `apktool d` WITHOUT `-r`, then
     `apktool b` — but the v2 patch pipeline deliberately uses `-r` to
     preserve the binary `resources.arsc` because B0/XML edits were
     corrupting resources), OR
   - at runtime, in `InstagramMainActivity.A0V` / `Gvc`, re-parenting
     `tab_bar` into a `FrameLayout` that overlays the pager — invasive.
3. Even if (2) is done, the pager's bottomMargin = tabBarHeight means
   the pager ENDS at the top of the nav bar. The video would NOT extend
   under the nav bar — there would be a `tabBarHeight`-tall strip of
   `igds_color_primary_background` (set by `C2ZS.A01:86` /
   `:131` via `AbstractC27310cW.A0R(decorView, iA0W, …)` and
   `A0R(content, iA0W, …)`) between the bottom of the video and the
   top of the nav bar. With B2-smali making the nav transparent, that
   primary-bg strip is what the user sees through the nav — i.e. the
   black strip is STILL there, just painted by `decorView` /
   `android.R.id.content` instead of by `tab_bar`. To eliminate it,
   A1 (decorView transparent) + A2 (content transparent) must BOTH
   hold — but A1/A2 only run inside `C2ZS.A01` (the Reels enter path),
   not globally, and they are already being applied by the v2 patch
   pipeline. The remaining gap is the pager's own bottomMargin, which
   IS what B1 removed.

In short: approach (b) re-introduces the exact black strip that B1
removed. It is strictly worse than approach (a). Approach (a) is the
clean fix.

---

## Q4 — Caption container view IDs (smali grep results)

The task asked to grep for `clips_media_info|clips_caption|reels_caption|ufi_component|clips_ufi`:

```
$ grep -rn 'clips_media_info\|clips_caption\|reels_caption\|ufi_component\|clips_ufi' /home/z/insta-orig/smali*/
```

Sorted by relevance (Litho component keys, NOT View IDs — these are
Litho `Component.key` strings set via `LX/4rZ;->A0F`):

| Key string | File:line | Notes |
|---|---|---|
| `clips_info_overlay_component` | `smali_classes17/X/33g.smali:1027` | **The wrapper that groups caption + ufi.** Has PADDING_BOTTOM=0 here. ← PRIMARY PATCH POINT |
| `clips_info_overlay_component` | `smali_classes17/X/050.smali:317` | String-id table (packed-switch case `0x3c`). No logic. |
| `clips_media_info_component` | `smali_classes17/X/33g.smali:1955` | Inner caption block (username/follow/caption/audio). Built via `LX/1Ki;->A0H`. |
| `clips_media_info_component` | `smali_classes17/X/Anj.smali:73` | Touch dispatcher — confirms scope of the overlay. |
| `clips_media_info_parent_component` | `smali_classes17/X/2QX.smali:4920` | Parent of the media-info sub-tree in the dedicated `2QX` section. |
| `clips_media_info_sub_component` | `smali_classes17/X/2QX.smali:3099` | Sub-component (likely the caption text row). |
| `clips_ufi_component` | `smali_classes17/X/33g.smali:2384` | Side UFI column (like/comment/share/more). |
| `clips_ufi_component` | `smali_classes17/X/Anj.smali:89` | Touch dispatcher — confirms scope. |
| `clips_ufi_component` | `smali_classes17/X/2CR.smali:871` | UFI sub-section. |

View IDs (R.id, used with `LX/4rZ;->A0C(LX/0XB;I)`):

| R.id name | Hex | File:line | Set by |
|---|---|---|---|
| `clips_media_info_component` | `0x7f0b0bc1` | `33g.smali:1927`, `2QX.smali:158` | `LX/4rZ;->A0C` |
| `clips_ufi_component` | `0x7f0b0c62` | `33g.smali:2390`, `2CR.smali:877` | `LX/4rZ;->A0C` |

No `clips_caption` / `reels_caption` R.id exists — the caption text is
rendered as a sub-component inside `clips_media_info_component`, not as
its own view.

### Related Litho modifier enums (used in the patch analysis)

`LX/4sC` (`smali_classes13/X/4sC.smali`) — Litho style key:
- `A0I` = **PADDING_BOTTOM** (used at `33g.smali:1009` — the patch site)
- `A05` = MARGIN_BOTTOM
- `A0H` = PADDING_ALL
- `A0O` = PADDING_TOP
- `A0N` = PADDING_START

`LX/5OA` (`smali_classes13/X/5OA.smali`) — absolute-position type:
- `A06` = POSITION_BOTTOM (used at `33g.smali:2396` on the UFI, but with a `NaN` sentinel value = "auto" — so it is NOT a hard-coded offset)

`LX/4sR` (`smali_classes13/X/4sR.smali`) — flexbox align/justify:
- `A07` = FLEX_END (used at `33g.smali:1277` — bottom-anchors the overlay in the `4tP` Row)

`LX/4sI` (`smali_classes13/X/4sI.smali`) — layout direction:
- `A03` = COLUMN, `A04` = COLUMN_REVERSE, `A05` = ROW, `A06` = ROW_REVERSE

---

## Concrete patch (drop-in for `apply_patches.py`)

Add a new `B3` block to `/home/z/MacOS/InstaTrueReel/patches/apply_patches.py`,
mirroring the existing `patch_text` style:

```python
# ── Feature B3: lift caption above floating nav bar ─────────
print("\n── Feature B3: caption above nav bar ──")
sec33g = find_smali(decoded, '33g.smali')
# PADDING_BOTTOM on "clips_info_overlay_component" — 0.0 → 168.0 (56dp at 3×)
patch_text(sec33g,
    '    const-wide/16 v3, 0x0\n\n    invoke-static {v3, v4}, Ljava/lang/Double;->doubleToRawLongBits(D)J\n\n    move-result-wide v16\n\n    sget-object v22, LX/4sC;->A0I:LX/4sC;',
    '    # InstaTrueReel: caption PADDING_BOTTOM = 56dp (168px at 3x density)\n    const-wide v3, 0x4065000000000000L\n\n    invoke-static {v3, v4}, Ljava/lang/Double;->doubleToRawLongBits(D)J\n\n    move-result-wide v16\n\n    sget-object v22, LX/4sC;->A0I:LX/4sC;',
    'B3-caption-padding')
```

The `old` string is unique in `33g.smali` (verified: only one
`const-wide/16 v3, 0x0` immediately followed by
`Double.doubleToRawLongBits` + `move-result-wide v16` + `LX/4sC;->A0I`
exists in the file, at line 1003). The `new` string preserves the
`Double.doubleToRawLongBits` + `move-result-wide v16` plumbing so the
rest of the method is untouched.

### Verification commands (post-patch)

```bash
# Confirm the patch landed at exactly one site:
grep -n 'InstaTrueReel: caption PADDING_BOTTOM' /home/z/insta-orig/smali_classes17/X/33g.smali
# Should print exactly one line.

# Confirm no other PADDING_BOTTOM=0 site in 33g was accidentally hit:
grep -n 'const-wide/16 v3, 0x0' /home/z/insta-orig/smali_classes17/X/33g.smali
# Should print zero lines (the only occurrence was the patched one).

# Confirm the bits decode to 168.0:
python3 -c 'import struct; print(struct.unpack("<d", struct.pack("<Q", 0x4065000000000000))[0])'
# Should print 168.0
```

---

## Open questions for next agent

1. **Density adaptation.** Is the hard-coded 168 px (56 dp × 3×)
   acceptable? If not, implement the dynamic variant (resolve
   `?tabBarHeight` via `LX/0bF;->A0Z(context, 0x7f040d30)` →
   `Resources.getDimensionPixelOffset` → `Double.doubleToRawLongBits`).
   The `LX/0bF;->A0Z` helper is the same one used at
   `InstagramMainActivity.smali:7440` / `:11829` / `:16256` (per the
   B1 patch sites) and at `iPM.smali:240` for the offline bar.
2. **Side-effects of lifting the UFI.** The `clips_info_overlay_component`
   wraps BOTH the caption and the UFI side buttons. Lifting it lifts
   both. TikTok lifts both, so this is the desired behaviour — but
   verify that the UFI side buttons do not collide with the
   `clips_viewer_action_bar` (top) or the reels tray when lifted.
3. **Interaction with the existing fullscreen hide-ufi animator
   (`VBP.FSS` / `EPN.EhI`).** When the user enters fullscreen (hide-ufi),
   `VBP.FSS:153` sets `clips_ufi_component` alpha to 0 and
   `VBP.FSS:147` fades the media-info via `C2TW.A0J(0.0f)`. The
   `clips_info_overlay_component` wrapper itself is NOT alpha-faded
   (only its children are). So the PADDING_BOTTOM we add is unaffected
   by the fullscreen state — the overlay keeps its bottom inset even
   when its children are hidden, which is harmless (an invisible
   component with padding is invisible). No conflict expected, but
   worth a visual check.
4. **The `clips_media_info_parent_component` in `2QX.smali:4920`** also
   has its own PADDING_BOTTOM chain (lines 691, 1236, 6099, 8219 in
   `2QX.smali`). Those are INTERNAL paddings of the caption block
   (spacing between username / caption / audio rows) and should NOT be
   patched — they are not the screen-bottom inset. Only the
   `clips_info_overlay_component` PADDING_BOTTOM at `33g.smali:1003` is
   the outer inset that lifts the whole overlay.
