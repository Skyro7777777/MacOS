# 5-d — Fullscreen button visibility on horizontal (16:9) reels

**Agent:** Explore (Task ID 5-d — RETRY, tighter scope)
**Task:** The user reports "fullscreen button didn't appear in 16:9 videos."
Find (a) whether a visible fullscreen button exists in the code,
(b) what gates its visibility, and (c) the exact patch to force-show
it for horizontal videos.

Smali root: `/home/z/insta-orig/` (apktool `-r` decode of v435.0.0.37.76,
ReVanced-patched v3.8.0). The InstaTrueReel D1/D2 patches are already
applied in this tree (see `/home/z/MacOS/InstaTrueReel/patches/apply_patches.py`
lines 177-216, and the `# InstaTrueReel: rotate to landscape` /
`# InstaTrueReel: restore orientation` comments visible at
`smali_classes8/X/VBP.smali:272` and `:86`).

> **Note on string obfuscation:** `rg` strips non-ASCII bytes from
> `const-string` lines in this APK, so e.g. `"clips_info_overlay_component"`
> shows as `"n_component"`, `"isFullscreenViewActive"` shows as
> `"isnActive"`, and resource-id constants like `0x7f082390` show as
> `n`. The smali files themselves are intact — `sed -n` / `cat -v`
> shows the true content. All file:line refs below were verified with
> `sed -n`.

---

## TL;DR

**There is NO always-visible inline "fullscreen button" anywhere in
the Instagram Reels UI.** The only fullscreen affordances are:

1. **A popup-menu entry** (`MediaOption$Option.FULLSCREEN_VIEW`) added
   unconditionally to the long-press / 3-dot popup menu by
   `X/VSL.smali:63`. The entry's tap handler (`X/I34.smali` pswitch_7
   → `LX/oAK;->FGC(...)`) calls `LX/14U;->FGC(LX/1j0;LX/11R;)V`
   (`smali_classes17/X/14U.smali:1207`), which **only stores the clip
   ref + fires analytics (`A8Q.Dij/Dik`)** — it does NOT call
   `VBP.FSS` and does NOT rotate or show a scrubber. (Confirms 4-b's
   finding.) So even when the user discovers this entry, tapping it
   does nothing visible.
2. **A swipe-gesture-triggered hide-UFI action** (`VBP.FSS`) — invoked
   by `AnonymousClass940.java:548` (scroll/gesture broadcaster). This
   is the only path that actually hides the side buttons, and (after
   our D1/D2 patches) also rotates to landscape.

The "fullscreen button didn't appear" complaint therefore matches the
code: **there is no button to appear.** The user must swipe (gesture)
to trigger fullscreen; the popup-menu entry is a dead end.

**Recommended patch (cleanest):** hook the popup-menu "Fullscreen
View" tap (currently analytics-only) so it actually invokes
`VBP.FSS`. This repurposes an existing UI affordance that IG already
renders unconditionally — no new Litho component, no new drawable, no
layout XML changes. As a secondary enhancement, also force-show the
existing `VideoScrubberSeekBar` (it's already integrated —
`X/AFz.smali:1310` calls `LX/BTc;->A01(...)` to find it; we just need
to ensure the gate at `X/33g.smali:2715` (`A0x:Z`) is true).

A "true" inline button (TikTok-style corner button) would require
adding a new child to the `clips_info_overlay_component` Litho
section in `X/33g.smali` and is **not recommended** — too invasive
(see "Alternative considered" below).

---

## Step 1 — Search for an inline fullscreen / expand button view

### 1.a. String searches

```
rg -rn 'fullscreen|FULLSCREEN|expand|EXPAND' /home/z/insta-orig/smali*/X/ \
   | grep -i 'button|icon|view|component|click|tap|visible' | head -20
rg -rn 'enter_fullscreen|toggle_fullscreen|fullscreen_button|expand_button|zoom_button|fullscreen_icon' \
   /home/z/insta-orig/smali*/ | head -20
```

Hits, in order of relevance:

| Hit | Class | Meaning | Inline button? |
|---|---|---|---|
| `FULLSCREEN_VIEW` enum | `com/instagram/feed/media/mediaoption/MediaOption$Option.smali:131, 2718-2728` | A popup-menu option (PLAYBACK_SPEED, FULLSCREEN_VIEW, VIDEO_CAPTIONS, VIDEO_TRANSLATIONS). ordinal `0xa6` (=166), `iconDrawable = 0x7f082390`. | **NO** — popup entry only |
| `FIT_SCREEN` enum | same file, line 129, 1568-1576 | Sibling enum used in IGTV-style feed (NOT in clips — no callers in `2OR.smali`/`15T.smali`/`VSL.smali`). | NO |
| `FULLSCREEN_BUTTON` constant | `smali_classes13/X/2uH.smali:2087` | An enum constant in `LX/2uH` (a "ClipsElementLoggingName"-style enum — callers pass it as a logging tag, e.g. `TOr.smali`, `TBm.smali`, `EWd.smali`, `EXB.smali`, `HM7.smali`). NOT a button view. | NO |
| `expand_button_label` string | `smali_classes17/X/7XO.smali:43, 387` and `smali_classes17/X/9r6.smali:249` | Persisted state for the "interests" picker ("show more rows" expand button on the Reels tray carded UI — `LX/9k7;->A07:Ljava/util/List;` is the interests list). NOT a video fullscreen button. | NO |
| `FULLSCREEN` string (action source) | `smali_classes7/X/F2v.smali:110, 379, 795`, `smali_classes19/X/Dkh.smali:4339`, `smali_classes12/X/V3P.smali:10`, `smali_classes18/X/20y.smali:6857` | Logging constants (e.g. `ClipsGesturesLogger$ActionSource.FULLSCREEN`). NOT a view. | NO |

### 1.b. Class-name searches

```
rg -rn 'FullscreenController|FullscreenPresenter|FullscreenButton|FullscreenIcon|FullscreenManager|FullscreenView' \
   /home/z/insta-orig/smali*/
```

Returns only matches in `11R.smali` (`isFullscreenViewActive` /
`isFullscreenViewNuxActive` — the immutable per-reel config booleans,
per 3-e) and `RK1.smali`/`R70.smali`/`RL0.smali` (MethodHandle
accessors for the same booleans). **No `FullscreenButton` /
`FullscreenView` / `FullscreenController` class exists.**

### 1.c. Drawable / resource-id searches

```
rg -rn 'fullscreen_enter|fullscreen_exit|ic_fullscreen|ic_expand|ic_zoom|btn_fullscreen|btn_expand' \
   /home/z/insta-orig/smali*/
```

**ZERO matches.** There is no dedicated "fullscreen enter" drawable
referenced from any smali file. (The `FULLSCREEN_VIEW` popup entry
uses drawable `0x7f082390`, but that drawable is only ever loaded via
`MediaOption$Option.getIconDrawable()` from `VSL.run()` for the popup
menu — never from an inline overlay binder.)

### 1.d. Verdict for step 1

**No inline / always-visible fullscreen button exists in the code.**
The only fullscreen UI affordances are:
- The popup-menu entry (VSL.smali).
- The swipe-gesture-triggered alpha-fade (VBP.FSS).

---

## Step 2 — Aspect-ratio / horizontal-video detection

### 2.a. Runtime accessor on `Media` / `ClipsItem` / player

```
rg -rn 'isLandscape|isHorizontal|videoWidth.*videoHeight|landscape.*video|aspectRatio.*1[69]' \
   /home/z/insta-orig/smali*/X/
```

**ZERO matches** in `X/` (the obfuscation renames `isLandscape` →
`n`, but `Media.smali` and `1j0.smali` (ClipsItem) have no
`n:Z`/`n()Z` boolean accessor with a landscape-flavored
toString-formatter either — verified by reading the toString methods
of `X/1j0.smali` and `com/instagram/feed/media/Media.smali`).

This **confirms 3-e's finding**: there is NO runtime
`isLandscape` / `isHorizontal` / `getVideoWidth` / `getVideoHeight`
accessor on `Media` or `ClipsItem`.

### 2.b. Creation-side only

The drafts DB schema (`smali_classes17/X/Akk.smali`,
`smali_classes15/X/5o6.smali`, `smali_classes11/X/TWZ.smali`) has a
`feedmetadata_isLandscape` column (truncated to `feedmetadata_n` in
the obfuscated smali). This is parsed at draft-creation time
(`C28856Amv.java:261` per 3-e) and is NOT exposed as a runtime
accessor on the playback-side `Media` model. So it cannot be used to
gate UI on the viewer side.

### 2.c. Runtime aspect-ratio math

Per 3-a / 4-c, the only runtime aspect-ratio computation happens in
`C25U.A00` (smali `X/25U.smali`), which is called from
`AbstractC210917ky.onSizeChanged` (smali
`X/AbstractC210917ky.smali`) to compute TextureView width/height/x/y
and pick FIT vs ZOOM. It does NOT expose a "is landscape" boolean
back to the caller.

### 2.d. Player-level dimensions (per 4-a)

`C50741Yd` (the per-reel "GrootPlayer" wrapper) does expose the
underlying video dimensions (via the wrapped `IgGrootPlayer`
`C50301Wl`), but this is a player-internal API — there is no public
`getVideoWidth()` / `getVideoHeight()` method that the UI layer can
call without reflection.

### 2.e. Verdict for step 2

**There is no IG-provided "is landscape" gate** that the UI uses to
decide whether to show a fullscreen affordance. This means IG's
existing fullscreen popup-menu entry (VSL.smali) is shown
**unconditionally** for every clip — portrait or landscape. So the
user's "fullscreen button didn't appear in 16:9 videos" complaint
cannot be explained by aspect-ratio gating; it can only mean there is
no visible button at all (which is what step 1 found).

---

## Step 3 — MobileConfig flags gating fullscreen / scrubber visibility

### 3.a. The `EEr()` flag (fullscreen-related)

`X/9Wz.smali:36584-36620` (ClipsViewerFragment):

```smali
.method public final EEr()Z
    .locals 3
    invoke-virtual {p0}, LX/9Wz;->A1w()Lcom/instagram/clips/intf/ClipsViewerConfig;
    move-result-object v0
    iget-boolean v0, v0, Lcom/instagram/clips/intf/ClipsViewerConfig;->A2g:Z
    if-nez v0, :cond_1
    invoke-virtual {p0}, LX/9Wz;->A1w()Lcom/instagram/clips/intf/ClipsViewerConfig;
    move-result-object v0
    iget-boolean v0, v0, Lcom/instagram/clips/intf/ClipsViewerConfig;->A3H:Z
    if-nez v0, :cond_0
    invoke-virtual {p0}, LX/9Wz;->A1x()Lcom/instagram/common/session/UserSession;
    move-result-object v1
    const/4 v0, 0x0
    invoke-static {v1, v0}, LX/3l9;->A0U(Ljava/lang/Object;I)V
    invoke-static {v1}, LX/1wu;->A01(LX/3Au;)LX/0Ag;
    move-result-object v2
    const-wide v0, 0x8109d400023873L
    check-cast v2, Lcom/facebook/mobileconfig/factory/MobileConfigUnsafeContext;
    invoke-interface {v2, v0, v1}, Lcom/facebook/mobileconfig/factory/MobileConfigUnsafeContext;->BHQ(J)Z
    move-result v0
    if-eqz v0, :cond_1
    :cond_0
    const/4 v0, 0x1
    return v0
    :cond_1
    const/4 v0, 0x0
    return v0
.end method
```

**Meaning:** `EEr()` returns true if ANY of:
- `ClipsViewerConfig.A2g == true`, OR
- `ClipsViewerConfig.A3H == true`, OR
- MobileConfig flag `0x8109d400023873L` returns true from `BHQ(J)Z`.

**Callers of `EEr()`** (`rg -n 'EEr\(\)Z'`):

| File:line | Role |
|---|---|
| `smali_classes16/X/9Wz.smali:18443` | inside `A0i` (the per-reel Litho section binder) — sets `v89 = EEr()` and passes it down. |
| `smali_classes16/X/9Wz.smali:25737` | another binder path — sets `v32 = EEr()`. |
| `smali_classes16/X/9Wz.smali:39926` | inside a method that calls `0cW.A03` (drawable tinting) — gates a drawable tint branch. |
| `smali_classes17/X/2Iv.smali` (3 refs) | the ClipsViewer presenter — gates whether `$t=5` WindowInsets listener is registered (per 5-a). |
| `smali_classes16/X/AIr.smali`, `smali_classes16/X/AFt.smali` | sub-presenters. |

**Verdict:** `EEr()` is the master "fullscreen-related code path is
enabled" gate for the ClipsViewer. Per 5-a, in the basic Reels-tab
case all three sub-conditions are false → `EEr()` returns false →
the `$t=5` WindowInsets listener is NOT registered → `0jS.A0D` stays
false → InstagramMainActivity uses the BLACK status-bar branch.

This gate ALSO controls what `A0i` does with `v89` (and downstream
the `33g.A0x` scrubber gate, see step 4) — but **it does NOT gate
the popup-menu "Fullscreen View" entry** (VSL.smali adds
FULLSCREEN_VIEW unconditionally, see step 5).

### 3.b. The scrubber MobileConfig flag

Per 4-a, the scrubber (`VideoScrubberSeekBar` / Litho component
`C30423BTc`) is gated by MobileConfig flag `36320867680860001L`
(= `0x80b3d0000074a21L`). Searching the smali tree:

```
rg -rn '0x80b3d0000074a21' /home/z/insta-orig/smali*/   # ZERO matches
rg -rn '80b3d0000074a21'   /home/z/insta-orig/smali*/   # ZERO matches
rg -rn '36320867680860001' /home/z/insta-orig/smali*/   # ZERO matches
```

**The literal hex/decimal value does not appear in the smali tree.**
This means either (a) 4-a's flag value was from a different APK
version, or (b) the value is materialized via a QPL token /
parameterized helper rather than a literal `const-wide`. The closest
related flags actually present in `9Wz.smali` are:

| Hex literal | File:line | Used by |
|---|---|---|
| `0x8109d400023873L` | `9Wz.smali:36614` | `EEr()` (see 3.a) |
| `0x8111b600065de7L` | `9Wz.smali:5517` | unrelated ClipsViewer flag |
| `0x8111b600265dfaL` | `9Wz.smali:5529` | unrelated |
| `0x810a9e00053d99L` | `9Wz.smali:5541` | unrelated |
| `0x81093c000832fdL` | `9Wz.smali:5553` | unrelated |
| `0x810784000627c0L` | `9Wz.smali:5565` | unrelated |
| `0x810f3f000953deL` | `9Wz.smali:5577` | unrelated |

**Verdict:** The 4-a-cited scrubber flag (`0x80b3d0000074a21`) is not
present in this APK build. The actual scrubber gate in this build is
the `33g.A0x:Z` boolean field (see step 4) — set from a constructor
arg (`p52`) decided by `2CP.smali` at Litho-section build time, with
`EEr()` likely in the decision path (since `EEr`'s result is passed
to the binder at `9Wz.smali:18443` as `v89`).

---

## Step 4 — Litho component that renders the reel overlay (where a button would be)

### 4.a. The overlay section

Per 5-b, the per-reel overlay (caption + UFI side buttons) is built
by Litho section `LX/33g` (`smali_classes17/X/33g.smali`), method
`A0i` (line 865). Confirmed key sites (re-verified in this task):

| Site | File:line | What it builds |
|---|---|---|
| `"clips_info_overlay_component"` (Litho component key) | `33g.smali:1027` | The overlay wrapper (Column with `PADDING_BOTTOM = 0.0`). |
| `"clips_media_info_component"` (Litho component key) | `33g.smali:1955` | Caption + username + audio title. |
| `"clips_ufi_component"` (Litho component key) | `33g.smali:2384` | Like / comment / share / more side buttons. |
| `"trans_key_scrubber"` (Litho transition key) | `33g.smali:2735` | **The scrubber overlay sub-component** — wrapped in a `4tP` Row with `PADDING_BOTTOM = 33g.A06` (a `J` long = double bits). |

### 4.b. The scrubber gate

The `trans_key_scrubber` sub-component is conditionally added at
`33g.smali:2714-2740`:

```smali
    iget-boolean v1, v0, LX/33g;->A0x:Z
    const/4 v4, 0x0
    if-eqz v1, :cond_25
    iget-wide v0, v0, LX/33g;->A06:J
    sget-object v3, LX/4sC;->A02:LX/4sC;          # PADDING_BOTTOM enum
    new-instance v2, LX/JAu;
    invoke-direct {v2, v3, v0, v1}, LX/JAu;-><init>(LX/4sC;J)V
    new-instance v4, LX/0XB;
    move-object/from16 v0, v30
    invoke-direct {v4, v0, v2}, LX/0XB;-><init>(LX/0XB;LX/0XC;)V
    const-string v2, "trans_key_scrubber"
    new-instance v3, LX/7oj;
    move-object/from16 v1, v78
    move-object/from16 v0, v27
    invoke-direct {v3, v1, v0, v2}, LX/7oj;-><init>(LX/2iq;LX/7oi;Ljava/lang/String;)V
    :goto_10
    new-instance v0, LX/0XB;
    invoke-direct {v0, v4, v3}, LX/0XB;-><init>(LX/0XB;LX/0XC;)V
    ...
```

**Gate:** `33g.A0x:Z` (declared at `33g.smali:125`, set from
constructor arg `p52` at `33g.smali:260`).

`33g` instances are created only from `smali_classes17/X/2CP.smali:16248`
(Litho section composition). The constructor's `p52` arg maps to
register `v237` (since `33g.<init>` is invoked as
`invoke-direct/range {v185 .. v247}` — p0=v185, p52=v185+52=v237).
`v237` is set at `2CP.smali:16220`:

```smali
    move/from16 v237, v44
```

i.e. `33g.A0x` is set from `2CP.v44`. Tracing `v44` in `2CP.smali` is
a deep rabbit hole (2CP is ~16k lines), but the proximate cause is
almost certainly `EEr()` (since `9Wz.A0i` passes `EEr()`'s result
down to `2CP` as one of its 60+ arguments, per step 3.a). For the
purposes of this task, the actionable fact is: **flipping `33g.A0x`
to true (or skipping the `if-eqz` at `33g.smali:2715`) will
unconditionally include the scrubber sub-component in the overlay.**

### 4.c. The actual scrubber View (already integrated)

The `VideoScrubberSeekBar` class itself is at
`smali_classes17/com/instagram/ui/mediaactions/VideoScrubberSeekBar.smali`.

It is **already wired into the clips player view** (`LX/AFz` =
ClipsVideoPlayerView):

`smali_classes16/X/AFz.smali:1310`:
```smali
    invoke-static {v1, v3}, LX/BTc;->A01(Landroid/app/Activity;LX/1j0;)Lcom/instagram/ui/mediaactions/VideoScrubberSeekBar;
    move-result-object v0
    if-eqz v0, :cond_2
    invoke-virtual {v0, v1, p1}, Lcom/instagram/ui/mediaactions/VideoScrubberSeekBar;->A00(Landroid/app/Activity;I)V
```

`LX/BTc;->A01` (`smali_classes6/X/BTc.smali:147-188`) finds the
scrubber View by tag:

```smali
    const v0, 0x1020002                                      # android.R.id.content
    invoke-virtual {p0, v0}, Landroid/app/Activity;->findViewById(I)Landroid/view/View;
    move-result-object v0
    check-cast v0, Landroid/view/ViewGroup;
    const/4 p0, 0x0
    if-eqz v0, :cond_0
    invoke-virtual {v0, v1}, Landroid/view/ViewGroup;->getChildAt(I)Landroid/view/View;
    move-result-object v2
    if-eqz v2, :cond_0
    const-string v1, "clips_scrubber_"
    invoke-virtual {p1}, LX/1j0;->getId()Ljava/lang/String;
    move-result-object v0
    invoke-static {v1, v0}, LX/01v;->A0V(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
    move-result-object v0
    invoke-virtual {v2, v0}, Landroid/view/View;->findViewWithTag(Ljava/lang/Object;)Landroid/view/View;
    move-result-object v1
    if-eqz v1, :cond_0
    const v0, 0x7f0b3866                                      # R.id.scrubber (per 4-a)
    invoke-virtual {v1, v0}, Landroid/view/View;->findViewById(I)Landroid/view/View;
    move-result-object v0
    check-cast v0, Lcom/instagram/ui/mediaactions/VideoScrubberSeekBar;
    return-object v0
```

So the scrubber is added as a tagged child of
`android.R.id.content.getChildAt(0)` (which is the SwipeNavigationContainer
per 5-a's finding — `R.id.swipe_navigation_container = 0x7f0b3f31`). It
is found by the tag `"clips_scrubber_" + media.getId()` and contains
a sub-view with id `0x7f0b3866` (`R.id.scrubber`).

### 4.d. The AFz.A06 scrubber show/hide method

The full method (`smali_classes16/X/AFz.smali:1219-1330`) gates the
scrubber show on FOUR conditions:

```smali
    iget-boolean v0, v5, LX/AFy;->A0I:Z        # AFy.A0I = a final boolean set at construction
    if-eqz v0, :cond_2
    if-eqz v4, :cond_2                          # v4 = 9Ce.A00(media.A0R) — scrubber-capable flag
    if-nez v2, :cond_2                          # v2 = media.A0Y() — must be 0
    if-eqz v1, :cond_2                          # v1 = media.A07().A0K.A04.DaW().isEmpty() — captions list
```

If all four pass, it gets the Activity from `AFz.A03(this).getContext()`,
unwraps via `7wu.A01`, calls `BTc.A01(activity, media)` to find the
scrubber View, and invokes
`VideoScrubberSeekBar.A00(activity, p1)`.

**Verdict:** The scrubber is fully implemented and integrated — it
just isn't being shown because (a) `33g.A0x` is false in the basic
Reels-tab case (because `EEr()` returns false), and (b) `AFy.A0I` is
also false in the basic case. Both gates trace back through `EEr()`.

---

## Step 5 — VSL.smali (popup-menu builder) fullscreen option

`smali_classes8/X/VSL.smali` (implements `Runnable`). Single method
`run()` at line 30, body lines 30-180.

### 5.a. The FULLSCREEN_VIEW entry is added UNCONDITIONALLY

`VSL.smali:59-66`:
```smali
    sget-object v0, Lcom/instagram/feed/media/mediaoption/MediaOption$Option;->PLAYBACK_SPEED:Lcom/instagram/feed/media/mediaoption/MediaOption$Option;
    invoke-virtual {v1, v0}, Ljava/util/AbstractCollection;->add(Ljava/lang/Object;)Z

    sget-object v0, Lcom/instagram/feed/media/mediaoption/MediaOption$Option;->FULLSCREEN_VIEW:Lcom/instagram/feed/media/mediaoption/MediaOption$Option;
    invoke-virtual {v1, v0}, Ljava/util/AbstractCollection;->add(Ljava/lang/Object;)Z

    if-eqz v8, :cond_0
    sget-object v0, Lcom/instagram/feed/media/mediaoption/MediaOption$Option;->VIDEO_CAPTIONS:Lcom/instagram/feed/media/mediaoption/MediaOption$Option;
    invoke-virtual {v1, v0}, Ljava/util/AbstractCollection;->add(Ljava/lang/Object;)Z

    :cond_0
    if-eqz v7, :cond_1
    sget-object v0, Lcom/instagram/feed/media/mediaoption/MediaOption$Option;->VIDEO_TRANSLATIONS:Lcom/instagram/feed/media/mediaoption/MediaOption$Option;
    invoke-virtual {v1, v0}, Ljava/util/AbstractCollection;->add(Ljava/lang/Object;)Z
```

So the order is `[PLAYBACK_SPEED, FULLSCREEN_VIEW, (if v8) VIDEO_CAPTIONS, (if v7) VIDEO_TRANSLATIONS]`.
**`FULLSCREEN_VIEW` is added unconditionally** — no aspect-ratio gate.

`v8 = oAK.H2V(c56811j0, c11r)` and `v7 = oAK.H2W(c56811j0, c11r)`
(`VSL.smali:47-53`) — these are the per-clip "captions available" and
"translations available" predicates. There is **no equivalent predicate
for "is landscape"** — IG simply does not gate FULLSCREEN_VIEW.

### 5.b. The menu item is built via `LX/2OR;->A00`

`VSL.smali:107-127` (FULLSCREEN_VIEW item construction):

```smali
    sget-object v10, Lcom/instagram/feed/media/mediaoption/MediaOption$Option;->FULLSCREEN_VIEW:Lcom/instagram/feed/media/mediaoption/MediaOption$Option;
    const/16 v0, 0x14
    new-instance v13, LX/nQz;
    invoke-direct {v13, v0, v9, v11}, LX/nQz;-><init>(ILjava/lang/Object;Ljava/lang/Object;)V
    const/4 v12, 0x0
    invoke-static/range {v9 .. v14}, LX/2OR;->A00(LX/11R;Lcom/instagram/feed/media/mediaoption/MediaOption$Option;LX/2OR;Ljava/lang/Integer;Lkotlin/jvm/functions/Function0;I)LX/Ar8;
    move-result-object v0
    invoke-virtual {v3, v0}, LX/Sm5;->A00(Ljava/lang/Object;)V
```

The `Function0` (`LX/nQz;`) is the click handler. `nQz` is a
`kotlin/jvm/functions/Function0` lambda that delegates to `I34`
with `$t = 0x14` (= 20). **NOTE:** This `0x14` is the *lambda
dispatch ID*, NOT the case ordinal in `I34.invoke()` — the actual
case-ordinal-to-pswitch mapping in `I34.invoke()`'s packed-switch
table puts `0x14` (case 20) at `:pswitch_e` (per the table at
`I34.smali:844-888`).

However, the FULLSCREEN_VIEW tap-when-clicked path goes through a
**different dispatcher** (the `Ar8` `View$OnClickListener`):
- `Ar8`'s click handler invokes the `Function0` (`nQz`).
- `nQz.invoke()` calls `I34(c2or, 33)` per 4-b's finding (jadx line 234).
- `I34.invoke()` `packed-switch v0` with `v0 = 33 (0x21)` → `:pswitch_7`
  (per the table mapping: 0x21 is the 34th entry →
  `:pswitch_7` at `I34.smali:152`).

### 5.c. pswitch_7 calls FGC — but FGC only logs

`I34.smali:152-167`:
```smali
    :pswitch_7
    iget-object v0, p0, LX/I34;->A00:Ljava/lang/Object;
    check-cast v0, LX/2OR;
    iget-object v2, v0, LX/2OR;->A09:LX/oAK;
    iget-object v1, v0, LX/2OR;->A05:LX/1j0;
    iget-object v0, v0, LX/2OR;->A08:LX/Ait;
    invoke-virtual {v0, v1}, LX/Ait;->A08(LX/1j0;)LX/11R;
    move-result-object v0
    invoke-interface {v2, v1, v0}, LX/oAK;->FGC(LX/1j0;LX/11R;)V
    goto/16 :goto_2
```

`oAK` is implemented by `LX/14U` (`smali_classes17/X/14U.smali:1207`):

```smali
.method public final FGC(LX/1j0;LX/11R;)V
    .locals 2
    invoke-static {p2}, LX/3l9;->A0R(Ljava/lang/Object;)V
    iput-object p1, p0, LX/14U;->A00:LX/1j0;       # just stores
    iput-object p2, p0, LX/14U;->A01:LX/11R;       # just stores
    iget-object v0, p0, LX/14U;->A0Z:LX/JDl;
    invoke-interface {v0}, LX/JDl;->getValue()Ljava/lang/Object;
    move-result-object v0
    check-cast v0, LX/14Z;
    invoke-virtual {v0, p1, p2}, LX/14Z;->GLH(LX/1j0;LX/11R;)V    # forwards to 14Z.GLH (just stores again)
    iget-object v1, p0, LX/14U;->A0P:LX/A8Q;
    iget-boolean v0, p2, LX/11R;->A0v:Z             # isFullscreenViewActive
    if-eqz v0, :cond_0
    sget-object v0, LX/bLv;->A04:LX/bLv;
    invoke-virtual {v1, p1, v0}, LX/A8Q;->Dij(LX/1j0;LX/bLv;)V    # analytics: "entered fullscreen"
    return-void
    :cond_0
    sget-object v0, LX/bLv;->A04:LX/bLv;
    invoke-virtual {v1, v0}, LX/A8Q;->Dik(LX/bLv;)V               # analytics: "exited fullscreen"
    return-void
.end method
```

**Confirmed (matches 4-b):** the popup-menu "Fullscreen View" entry
does NOT call `VBP.FSS`. It only:
1. Stores the clip ref (`14U.A00`, `14U.A01`, `14Z.A00`, `14Z.A01`).
2. Fires analytics (`A8Q.Dij` if `c11r.A0v` is true = "fullscreen
   already active", else `A8Q.Dik`).

There is **no `.FSS(` or `.EvT(` call** anywhere in `14U.smali` or
`14Z.smali` (verified — `rg "\.FSS\(|\.EvT\(" 14U.smali 14Z.smali`
returns zero matches).

### 5.d. Verdict for step 5

**The popup-menu "Fullscreen View" entry exists and is added
unconditionally** (no aspect-ratio gating — would appear for any
clip, 9:16 or 16:9). But its click handler is **analytics-only** —
tapping it does nothing visible to the user (no rotation, no UFI
hide, no scrubber). This is the dead-end 4-b already identified.

---

## Q.A — Does a visible fullscreen button exist in code?

**No.** Comprehensive searches (step 1) across:
- All `X/*.smali` files for `fullscreen|FULLSCREEN|expand|EXPAND` +
  `button|icon|view|component|click|tap|visible` keywords.
- All smali trees for `enter_fullscreen|toggle_fullscreen|
  fullscreen_button|expand_button|zoom_button|fullscreen_icon`.
- Class names matching `FullscreenController|FullscreenPresenter|
  FullscreenButton|FullscreenIcon|FullscreenManager|FullscreenView`.
- Drawable / resource-id names matching `fullscreen_enter|
  fullscreen_exit|ic_fullscreen|ic_expand|ic_zoom|btn_fullscreen|
  btn_expand`.

All return either:
- The popup-menu enum `MediaOption$Option.FULLSCREEN_VIEW` (used only
  in the long-press popup, not as an inline button).
- Logging-related constants (`FULLSCREEN_BUTTON` enum in `2uH.smali`
  is a `ClipsElementLoggingName` tag, not a view).
- The unrelated "interests picker" expand button (`expand_button_label`
  in `7XO.smali` / `9r6.smali` — that's the Reels tray carded UI).
- The `isFullscreenViewActive` / `isFullscreenViewNuxActive` /
  `isFillToScreenActive` immutable booleans on `LX/11R` (state, not
  view).

**There is no `R.id.btn_fullscreen` / `R.id.fullscreen_button` /
`R.drawable.ic_fullscreen_enter` style resource, no
`FullscreenButton`/`FullscreenView` class, and no Litho component
that renders an always-visible fullscreen button.**

The only ways IG's existing code triggers "fullscreen-ish" behavior
are:
1. **Swipe gesture** → `AnonymousClass940.java:548` (gesture
   broadcaster) → iterates `c109193lI.A1b` listener set → calls
   `VBP.FSS(int, int)`. This is an alpha-fade of side buttons (NOT
   a button). After D1 patch, also rotates to landscape.
2. **Popup menu** → `VSL.run()` adds `FULLSCREEN_VIEW` to the long-press
   popup → tap → `nQz` lambda → `I34.invoke()` `:pswitch_7` →
   `oAK.FGC` → `14U.FGC` (analytics-only, no `VBP.FSS` call).

---

## Q.B — What gates the visibility of fullscreen UI?

Three independent gates exist (none aspect-ratio-based):

1. **Popup-menu "Fullscreen View" entry** (`VSL.smali:63`): added
   **unconditionally** to every clip's popup. No gate. Always
   appears in the popup for every clip. Tap does nothing visible
   (analytics-only).

2. **Swipe-gesture-triggered `VBP.FSS`**: gated only by the user
   performing a swipe gesture that the
   `AnonymousClass940`/`C106638kpe`/`C106635kpb` broadcasters
   forward. No aspect-ratio gate.

3. **Scrubber overlay Litho sub-component** (`33g.smali:2714-2740`):
   gated by `33g.A0x:Z` (a final boolean set from constructor arg
   `p52`, sourced from `2CP.v44`, almost certainly derived from
   `9Wz.EEr()`).

4. **Scrubber View show/hide** (`AFz.A06(I)`): gated on four
   conditions (`AFy.A0I:Z`, `9Ce.A00(media.A0R)`,
   `!media.A0Y()`, `media.A07().A0K.A04.DaW().isEmpty()`).

5. **`9Wz.EEr()` master gate**: returns true if
   `ClipsViewerConfig.A2g || ClipsViewerConfig.A3H || MobileConfig
   flag 0x8109d400023873L`. Per 5-a, all three are false in the
   basic Reels-tab case → `EEr()` returns false →
   `$t=5` WindowInsets listener not registered → `0jS.A0D` stays
   false → MainActivity uses the BLACK status-bar branch.

**None of these gates is aspect-ratio-based.** This means the user's
"fullscreen button didn't appear in 16:9 videos" complaint is NOT
because some flag incorrectly hides the button on 16:9 videos — it's
because **there is no button to begin with**.

---

## Q.C — Exact patch to force-show fullscreen affordance for horizontal videos

Since no visible inline button exists, we have three options. They
are NOT mutually exclusive — the recommended combination is **(1) +
(2)**, which together fully realize the TikTok-style UX without
adding any new Litho component.

### Option 1 (RECOMMENDED, PRIMARY) — Wire the popup-menu "Fullscreen View" tap to actually call `VBP.FSS`

This repurposes an existing, unconditionally-rendered UI affordance
(the popup-menu entry) into a working fullscreen toggle. Zero new
views, zero new drawables, zero XML changes.

**File:** `smali_classes17/X/14U.smali`

**Old (`14U.smali:1207-1237`, the `FGC` method):**
```smali
.method public final FGC(LX/1j0;LX/11R;)V
    .locals 2

    invoke-static {p2}, LX/3l9;->A0R(Ljava/lang/Object;)V

    iput-object p1, p0, LX/14U;->A00:LX/1j0;

    iput-object p2, p0, LX/14U;->A01:LX/11R;

    iget-object v0, p0, LX/14U;->A0Z:LX/JDl;
    ...
```

**New (prepend a call to `VBP.FSS` before the analytics):**
```smali
.method public final FGC(LX/1j0;LX/11R;)V
    .locals 2

    # InstaTrueReel: popup-menu "Fullscreen View" — actually trigger VBP.FSS
    iget-boolean v0, p2, LX/11R;->A0v:Z                # isFullscreenViewActive
    if-nez v0, :cond_fss_done                         # already fullscreen → skip enter
    iget-object v0, p0, LX/14U;->A0Y:LX/VBP;          # VBP ref (field name to verify)
    if-eqz v0, :cond_fss_done
    const/4 v1, 0x0
    const/4 v2, 0x0
    invoke-virtual {v0, v1, v2}, LX/VBP;->FSS(II)V
    :cond_fss_done

    invoke-static {p2}, LX/3l9;->A0R(Ljava/lang/Object;)V
    iput-object p1, p0, LX/14U;->A00:LX/1j0;
    iput-object p2, p0, LX/14U;->A01:LX/11R;
    iget-object v0, p0, LX/14U;->A0Z:LX/JDl;
    ...
```

**Caveat — field name to verify:** `14U` must hold a reference to the
`VBP` instance (or to `RE7`, which holds VBP via `E4I.java:575-576`).
Per 3-e/4-b, `VBP` is constructed via `E4I.java:575-576` (case 285)
as the `InterfaceC113320nxx` gesture listener registered via
`RE7.CaC()`. `14U` likely does NOT hold a direct VBP ref — it would
need to be looked up via `RE7.A0B` (the `9eY` clips-item controller)
→ `9eY.A03` (the `RE7` per-clip) → `RE7.A02` (the `EPN`) which
holds gesture listeners, OR via `c109193lI.A1b` (the gesture-listener
set). The exact `iget-object` chain needs a follow-up agent to
verify, OR the patch can be simplified by:

**Simpler variant — call `VBP.FSS` via the gesture broadcaster:**
```smali
    # InstaTrueReel: popup-menu "Fullscreen View" — broadcast FSS via the gesture set
    iget-boolean v0, p2, LX/11R;->A0v:Z
    if-nez v0, :cond_fss_done
    iget-object v0, p0, LX/14U;->A0B:LX/3Cz;          # the IX/3Cz broadcaster
    if-eqz v0, :cond_fss_done
    invoke-interface {v0}, LX/3Cz;->FSS()V            # (name to verify — may be A0i/A0j)
    :cond_fss_done
```

The exact field/method names need verification. Recommend a follow-up
"5-e" agent to map `14U`'s fields and confirm which one holds the
broadcaster.

### Option 2 (RECOMMENDED, SECONDARY) — Force-show the scrubber overlay

Patch the `33g.A0x` gate to always be true, so the scrubber
sub-component is always included in the overlay.

**File:** `smali_classes17/X/33g.smali`

**Patch A (simplest — force the gate true):** change line 2715
```smali
    iget-boolean v1, v0, LX/33g;->A0x:Z
```
to
```smali
    # InstaTrueReel: scrubber overlay — always include
    const/4 v1, 0x1
```

**Patch B (alternative — force the constructor field true):** change
line 260
```smali
    move/from16 v0, p52
    iput-boolean v0, p0, LX/33g;->A0x:Z
```
to
```smali
    # InstaTrueReel: scrubber overlay — force-on
    const/4 v0, 0x1
    iput-boolean v0, p0, LX/33g;->A0x:Z
```

Either works. Patch A is more localized (doesn't touch the
constructor); Patch B is more "principled" (sets the field once at
construction, so any other reader of `A0x` also sees true).

**Note:** The scrubber will still need its show/hide handler
(`AFz.A06`) to actually fire — which requires `AFy.A0I:Z` to also
be true. `AFy.A0I` is set from constructor arg `p25`, sourced deep
in `9Wz.A0i`. If `AFy.A0I` is false, the scrubber View will be
present in the layout tree but `AFz.A06` won't trigger
`VideoScrubberSeekBar.A00` to actually animate it visible. May need
a third patch to force `AFy.A0I = true` (or to bypass the
`if-eqz v0, :cond_2` at `AFz.smali:1278`).

### Option 3 (NOT RECOMMENDED) — Add a new inline "fullscreen" button to the Litho overlay

This is what the user literally asked for ("TikTok-style Full Screen
button"). However:

1. Requires adding a new child component to
   `clips_info_overlay_component` in `33g.smali:A0i` (a new
   `LX/0XB;` block built from an `LX/JAu;` style +
   `LX/4rZ;->A0F` keyed `"clips_fullscreen_button"` +
   `LX/4rZ;->A0H` `Function1` click handler that calls `VBP.FSS`).
2. Requires a new drawable (or reuse `0x7f082390`, the existing
   `FULLSCREEN_VIEW` popup icon).
3. Requires positioning logic — TikTok's button sits at the
   bottom-right corner above the side UFI buttons; this means
   tweaking the `4tP` Row layout / `4sR` FLEX_END alignment.
4. Requires a click-handler class (new smali file or repurpose
   `nQz`-style lambda) that calls `VBP.FSS`.
5. The reels tray has limited horizontal space — adding a 5th side
   button may crowd the layout.

This is significantly more invasive than Options 1+2 and would
likely require multiple iterations to get the layout right.
**Recommend Options 1+2 first** (which together give: tap "Fullscreen
View" in the popup → device rotates to landscape + side buttons fade
out + scrubber appears). If the user still wants a literal inline
button, escalate to Option 3 in a follow-up task.

### Option 4 (NOT RECOMMENDED) — Auto-trigger `VBP.FSS` when a landscape video is bound

Could be done by hooking `33g.A0i` (the per-reel Litho binder) or
`9Wz.A0i` to check video dimensions and call `VBP.FSS` if
`videoWidth > videoHeight`. **NOT recommended** because:

1. There's no clean runtime accessor for video dimensions on
   `Media`/`ClipsItem` (step 2 confirmed). Would need to query the
   player (`C50741Yd` / `C50301Wl`) which is invasive.
2. Auto-rotating on every landscape video is jarring UX — TikTok
   only auto-rotates if the user has "auto-play in fullscreen"
   enabled, and even then shows a clear "exit fullscreen" affordance.
3. Conflicts with the user's other Reels watching — if they're
   swiping through a feed that has a mix of 9:16 and 16:9, the
   constant rotation would be very disruptive.

If we want auto-trigger, it should be a separate user-configurable
toggle, not a default-on behavior.

---

## Recommended concrete patch sequence

```python
# ── Feature D3: popup-menu "Fullscreen View" actually triggers VBP.FSS ─
print("\n── Feature D3: popup-menu Fullscreen View → VBP.FSS ──")
sec14U = find_smali(decoded, '14U.smali')
patch_text(sec14U,
    '.method public final FGC(LX/1j0;LX/11R;)V\n    .locals 2\n\n    invoke-static {p2}, LX/3l9;->A0R(Ljava/lang/Object;)V',
    '.method public final FGC(LX/1j0;LX/11R;)V\n    .locals 2\n\n'
    '    # InstaTrueReel: popup Fullscreen View → VBP.FSS\n'
    '    # (field-name placeholder — verify 14U.A0? for the broadcaster ref)\n'
    '    iget-boolean v0, p2, LX/11R;->A0v:Z\n'
    '    if-nez v0, :cond_itr_fss\n'
    '    iget-object v0, p0, LX/14U;->A0B:LX/3Cz;\n'        # placeholder
    '    if-eqz v0, :cond_itr_fss\n'
    '    invoke-interface {v0}, LX/3Cz;->FSS()V\n'           # placeholder
    '    :cond_itr_fss\n\n'
    '    invoke-static {p2}, LX/3l9;->A0R(Ljava/lang/Object;)V',
    'D3-popup-FSS')

# ── Feature D4: force-include scrubber overlay Litho sub-component ─
print("\n── Feature D4: scrubber overlay always included ──")
sec33g = find_smali(decoded, '33g.smali')
patch_text(sec33g,
    '    iget-boolean v1, v0, LX/33g;->A0x:Z\n\n    const/4 v4, 0x0\n\n    if-eqz v1, :cond_25',
    '    # InstaTrueReel: scrubber overlay — always include\n'
    '    const/4 v1, 0x1\n\n'
    '    const/4 v4, 0x0\n\n'
    '    if-eqz v1, :cond_25',
    'D4-scrubber-overlay')
```

**Field-name verification gap:** the exact `iget-object` chain in D3
to reach the `VBP` (or the `IX/3Cz` gesture broadcaster) from `14U`
needs a follow-up agent (proposed "5-e"). The D4 patch is
self-contained and ready.

---

## Summary table

| Question | Answer |
|---|---|
| (a) Does a visible inline fullscreen button exist in code? | **NO.** Only a popup-menu entry (`FULLSCREEN_VIEW`) and a swipe-gesture alpha-fade (`VBP.FSS`). |
| (b) What gates fullscreen UI visibility? | Popup-menu entry: no gate (always shown). Scrubber overlay: `33g.A0x:Z`. Scrubber View show: `AFy.A0I:Z` + 3 media-predicates. Master gate: `9Wz.EEr()` (ClipsViewerConfig.A2g/A3H + MobileConfig `0x8109d400023873L`). **None are aspect-ratio-based.** |
| (c) Patch to force-show fullscreen on horizontal videos? | Two-part: (1) wire popup-menu "Fullscreen View" tap to call `VBP.FSS` (`14U.FGC` patch — D3); (2) force-include the scrubber overlay (`33g.A0x = true` patch — D4). A literal TikTok-style inline button (Option 3) is possible but invasive — defer until D3+D4 are verified. |

---

## Open gaps for next agent

1. **Verify `14U`'s field that holds the gesture broadcaster / VBP
   ref** — needed to finalize the D3 patch. Candidates:
   `14U.A0B`, `14U.A0Y`, or transitively via `14U.A0? : LX/9eY;` →
   `9eY.A03 : LX/RE7;` → `RE7.A02 : LX/EPN;` → gesture-listener set.
2. **Verify `AFy.A0I`'s source** — if `AFy.A0I` is false in the
   basic Reels-tab case, D4 alone won't make the scrubber actually
   show. May need a D5 patch on `AFz.smali:1278` (skip the
   `if-eqz v0, :cond_2` for `AFy.A0I`).
3. **Verify the manifest risk for `setRequestedOrientation`** (4-b
   open gap #1) — `AndroidManifest.xml` for
   `com.instagram.mainactivity.MainActivity` is in
   `/home/z/insta-orig/AndroidManifest.xml` (apktool `-r` preserves
   it). Check `android:screenOrientation` and `android:configChanges`.
4. **Consider Option 3 (inline button)** only if D3+D4 don't satisfy
   the user. The TikTok-style literal corner button requires
   significant Litho surgery.

READ-ONLY exploration complete. No patch code was written.
