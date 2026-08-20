# Task 7-c: View overlay vs statusBarColor — which is producing the black strip?

**Agent:** Explore (sub-agent, READ-ONLY diagnostic)
**Task ID:** 7-c
**Decoded source:** `/home/z/MacOS/insta-dec/` (freshly apktool-decoded with `-r`)
**Patch source:** `/home/z/MacOS/InstaTrueReel/patches/apply_patches.py` (v3, with current A5+A6)
**Prior work:** Built on 5-a, 6-a, 7-a, 7-b findings.

---

## TL;DR — VERDICT

| # | Question | Verdict |
|---|----------|---------|
| 1 | View overlay or statusBarColor? | **🎯 VIEW OVERLAY (`swipe_navigation_container`).** With current A5+A6 patches, `window.statusBarColor` IS 0 (transparent) AND `decorView` background IS 0 (transparent). The remaining BLACK strip is the **`swipe_navigation_container` view (id `0x7f0b3f31`) painted BLACK by the `47l` Runnable** (posted from `2ZS.A01` line 211, cond_5 path). After A6 enables edge-to-edge via `decorView.setSystemUiVisibility(0x500)`, the content area extends behind the status bar — so the BLACK `swipe_navigation_container` background becomes visible THROUGH the transparent status bar. This is the SAME conclusion 7-a reached; this task confirms it and refutes the alternative Q6 hypothesis. |
| 2 | Exact view producing the black strip | **`Lcom/instagram/ui/swipenavigation/container/SwipeNavigationContainer;`** (id `0x7f0b3f31`, the top-level container of InstagramMainActivity). Painted BLACK by `47l.run()` → `0cW.A0R(view, BLACK, 0x6bad5ee0)` → `view.setBackgroundColor(BLACK)`. Source: `2ZS.A00(activity, v3=BLACK)` at `2ZS.smali:211` (cond_5 path). |
| 3 | Does `1fC.A06(false)` re-set `FLAG_TRANSLUCENT_STATUS` after A6? | **❌ NO — REFUTED on TWO independent grounds.** (a) `1fC.A06` is NOT called in the Reels path at all — it's gated on `1fC.A09(decorView, window)` which returns TRUE after A6 (since neither `FLAG_FULLSCREEN` 0x400 nor `SYSTEM_UI_FLAG_FULLSCREEN` 0x4 is set), so the call at `2ZS.smali:278` is SKIPPED via `if-nez v0, :cond_c`. (b) Even if it were called, `1fC.A06` uses constant `0x400` which is **`FLAG_FULLSCREEN`** (WindowManager.LayoutParams = 1024), NOT `FLAG_TRANSLUCENT_STATUS` (which is `0x04000000` = 67108864). The user's hypothesis confused the two flag values. Verified by reading `1fC.smali:393-429` in full. |
| 4 | The specific fix needed | **Patch `2ZS.A00` (or `47l.run()`) to force color=0.** This is the missing "A7" patch. Three equivalent options: (a) Insert `const/4 p1, 0x0` at start of `2ZS.A00` (chokepoint, like A5 for `1fC.A04`); (b) Insert `const/4 v1, 0x0` before `0cW.A0R` in `47l.run()`; (c) Zero `v3` BEFORE the `2ZS.A00(activity, v3)` call at `2ZS.smali:211` (this is 5-a's "PATCH 1" / 6-a's "Fix Option B" — proposed twice but NEVER applied). Option (a) is cleanest. |

---

## 1. Background — what the current A5+A6 patches actually do

Verified by reading `/home/z/MacOS/InstaTrueReel/patches/apply_patches.py` lines 77-112.

### A6 patch (apply_patches.py:77-99) — inserted at start of `2ZS.A01`

Uses **direct legacy API calls** (NOT the `2Ib.A01` helper — that was the old v5 approach which crashed on Android 10 because `2Ib.A01` calls `setDecorFitsSystemWindows` which is API 30+). The A6 block:

```smali
invoke-virtual {p0}, Landroid/app/Activity;->getWindow()Landroid/view/Window;
move-result-object v0
if-eqz v0, :itre_skip
const/high16 v1, 0xc000000
invoke-virtual {v0, v1}, Landroid/view/Window;->clearFlags(I)V        # clears FLAG_TRANSLUCENT_STATUS(0x04000000)|FLAG_TRANSLUCENT_NAVIGATION(0x08000000)
const/high16 v1, -0x80000000
invoke-virtual {v0, v1}, Landroid/view/Window;->addFlags(I)V          # adds FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS(0x80000000)
const/4 v1, 0x0
invoke-virtual {v0, v1}, Landroid/view/Window;->setStatusBarColor(I)V # statusBarColor = 0 ✓
invoke-virtual {v0, v1}, Landroid/view/Window;->setNavigationBarColor(I)V
invoke-virtual {v0}, Landroid/view/Window;->getDecorView()Landroid/view/View;
move-result-object v0
if-eqz v0, :itre_skip
const/16 v1, 0x500
invoke-virtual {v0, v1}, Landroid/view/View;->setSystemUiVisibility(I)V  # LAYOUT_FULLSCREEN(0x400)|LAYOUT_STABLE(0x100)
const/4 v1, 0x0
invoke-virtual {v0, v1}, Landroid/view/View;->setBackgroundColor(I)V     # decorView bg = 0 ✓
:itre_skip
```

**What A6 DOES cover:**
- `window.statusBarColor` = 0 (transparent) ✓
- `window.navigationBarColor` = 0 (transparent) ✓
- `decorView` background = 0 (transparent — overrides theme's BLACK `windowBackground`) ✓
- `decorView.setSystemUiVisibility(0x500)` — content extends behind status bar ✓
- `clearFlags(0xC000000)` — clears FLAG_TRANSLUCENT_STATUS|FLAG_TRANSLUCENT_NAVIGATION ✓
- `addFlags(0x80000000)` — FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS ✓

**What A6 does NOT cover:**
- `swipe_navigation_container` background (id `0x7f0b3f31`) ❌ — this is the gap.

### A5 patch (apply_patches.py:106-112) — at start of `1fC.A04`

```smali
.method public static final A04(Landroid/app/Activity;I)V
    .locals 4
    # InstaTrueReel: force transparent status bar color
    const/4 p1, 0x0
    :goto_0
    ...original A04 body...
```

Forces every `1fC.A04(activity, color)` call to use color=0. This catches the BLACK call from `2ZS.A01:283` (cond_b → cond_c path). So `window.statusBarColor` is ALWAYS 0 after A5+A6.

**A5 only catches `1fC.A04` (statusBarColor chokepoint). It does NOT catch:**
- `2ZS.A00` (which posts `47l` to paint swipe_navigation_container) ❌
- `0cW.A0R` (the generic setBackgroundColor helper used by `47l`) ❌

### A1 patch (apply_patches.py:49-52) — in `2ZS.A01` cond_4 fall-through

Zeroes `v3` before `0cW.A0R(decorView, v3, ...)`. **Only runs on Android 10-14** (where `2ZS.A08` returns TRUE → cond_4 fall-through taken). On Android 15+, cond_4 fall-through is BYPASSED → A1 is dead code.

### A2 patch (apply_patches.py:55-58) — in `2ZS.A05`

Zeroes `p2` before `0cW.A0R(contentView, p2, ...)`. `2ZS.A05` is only called from `2ZS.A01:204` (cond_4 fall-through — Android 10-14 only). On Android 15+, A2 is dead code.

### The gap (what NO patch addresses)

| Site | File:line (unpatched) | Effect | Patched? |
|---|---|---|---|
| `2ZS.A00(activity, v3=BLACK)` | `2ZS.smali:211` (cond_5 path) | Posts `47l.run()` → `swipe_navigation_container.setBackgroundColor(BLACK)` | **❌ NOT PATCHED** ← THE BUG |
| `47l.run()` → `0cW.A0R(view, BLACK, ...)` | `47l.smali:47` | `swipe_navigation_container.setBackgroundColor(BLACK)` | **❌ NOT PATCHED** |

---

## 2. Q3 — The `swipe_navigation_container` (id `0x7f0b3f31`) — CONFIRMED as the culprit

### 2a. What is `swipe_navigation_container`?

Verified by reading `/home/z/MacOS/insta-dec/smali_classes13/X/0ZS.smali:3090-3098`:
```smali
3090:    const v0, 0x7f0b3f31
3092:    invoke-virtual {v2, v0}, Landroid/view/View;->requireViewById(I)Landroid/view/View;
3094:    move-result-object v0
3096:    check-cast v0, Lcom/instagram/ui/swipenavigation/container/SwipeNavigationContainer;
3098:    iput-object v0, v4, LX/0a2;->A0E:Lcom/instagram/ui/swipenavigation/container/SwipeNavigationContainer;
```

`0x7f0b3f31` is the id of `Lcom/instagram/ui/swipenavigation/container/SwipeNavigationContainer;`.

Reading `SwipeNavigationContainer.smali` lines 1-2:
```smali
.class public final Lcom/instagram/ui/swipenavigation/container/SwipeNavigationContainer;
.super Landroid/widget/FrameLayout;
```

It's a `FrameLayout` subclass — a generic full-bleed container that hosts the main viewpager2 (the IG root nav host). Per worklog 5-a: "the top-level container of InstagramMainActivity (confirmed in `/tmp/insta-res-only/res/layout/layout_activity_main_coordinator_layout_viewpager2.xml:4`)".

### 2b. Is `swipe_navigation_container` full-screen (extends behind status bar)?

**YES — when `setSystemUiVisibility(0x500)` (LAYOUT_FULLSCREEN|LAYOUT_STABLE) is set on decorView, which our A6 patch does.**

Evidence:
- `SwipeNavigationContainer` extends `FrameLayout` with no `setFitsSystemWindows(true)` call in its constructor (lines 164-365) — confirmed by grep: NO `setFitsSystemWindows` call anywhere in `SwipeNavigationContainer.smali`.
- The class's `onLayout`/`onMeasure` methods (lines 4863, 4948) don't apply any window-inset padding.
- `5m5.smali:727` (MetaAiVoice banner controller) adjusts `swipe_navigation_container`'s `topMargin` to either `0` (default, full-screen) or status bar height (when MetaAiVoice banner is shown) — confirming that by default `topMargin = 0`, i.e., the container is positioned at the very top of the screen (y=0).
- With `setSystemUiVisibility(0x500)` on decorView (our A6 patch), the content area extends behind the status bar. Since `swipe_navigation_container` is the top-level content view (inside `android.R.id.content`), it ALSO extends behind the status bar.

### 2c. The `47l` Runnable — paints `swipe_navigation_container` with BLACK

Read `/home/z/MacOS/insta-dec/smali_classes17/X/47l.smali` in full (52 lines):

```smali
.class public final LX/47l;
.super Ljava/lang/Object;
.implements Ljava/lang/Runnable;

# instance fields
.field public final synthetic A00:I              # the color
.field public final synthetic A01:Landroid/app/Activity;

# constructor
.method public constructor <init>(Landroid/app/Activity;I)V
    .locals 0
    iput-object p1, p0, LX/47l;->A01:Landroid/app/Activity;
    iput p2, p0, LX/47l;->A00:I                  # store color
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method

# run
.method public final run()V
    .locals 3
    iget-object v1, p0, LX/47l;->A01:Landroid/app/Activity;
    const v0, 0x7f0b3f31                          # swipe_navigation_container
    invoke-virtual {v1, v0}, Landroid/app/Activity;->findViewById(I)Landroid/view/View;
    move-result-object v2
    if-eqz v2, :cond_0
    iget v1, p0, LX/47l;->A00:I                   # the color (BLACK from 2ZS.A01)
    const v0, 0x6bad5ee0                          # debug hash for "setBackgroundColor"
    invoke-static {v2, v1, v0}, LX/0cW;->A0R(Landroid/view/View;II)V
    :cond_0
    return-void
.end method
```

Verified `0cW.A0R` at `/home/z/MacOS/insta-dec/smali_classes13/X/0cW.smali:333-343`:
```smali
.method public static A0R(Landroid/view/View;II)V
    .locals 1
    const-string/jumbo v0, "setBackgroundColor"
    invoke-static {p0, v0, p2}, LX/0cW;->A0d(Landroid/view/View;Ljava/lang/String;I)V
    invoke-virtual {p0, p1}, Landroid/view/View;->setBackgroundColor(I)V    # ★ paints view with color p1
    return-void
.end method
```

So `47l.run()` calls `swipe_navigation_container.setBackgroundColor(BLACK)`. Confirmed.

### 2d. How `47l.run()` is scheduled

`2ZS.A00(activity, color)` at `/home/z/MacOS/insta-dec/smali_classes17/X/2ZS.smali:45-57`:
```smali
.method public static final A00(Landroid/app/Activity;I)V
    .locals 1
    new-instance v0, LX/47l;
    invoke-direct {v0, p0, p1}, LX/47l;-><init>(Landroid/app/Activity;I)V
    invoke-static {p0, v0}, LX/8ug;->A06(Landroid/app/Activity;Ljava/lang/Runnable;)V
    return-void
.end method
```

`8ug.A06(activity, runnable)` at `8ug.smali:691-857` either:
- Runs `runnable.run()` synchronously (line 722) if `8ug.A07` and `8ug.A06` static fields are both != -1 (i.e., stable status/nav bar heights are initialized — typically true after first frame).
- Otherwise, queues the runnable to `8ug.A02` or `8ug.A01` list (lines 820-834, 843-856) for later execution via Activity lifecycle callbacks (`onActivityPostResumed` etc.).

**Either way, by the time the user sees the screen, `47l.run()` has executed and `swipe_navigation_container` is BLACK.**

### 2e. Where `2ZS.A00(activity, BLACK)` is called

Read `2ZS.smali:193-218` (unpatched line numbers):
```smali
193:    :cond_4
194:    invoke-static {p0}, LX/2ZS;->A08(Landroid/app/Activity;)Z
196:    move-result v0
198:    if-eqz v0, :cond_5      # ★ if A08==0 (Android 15+ with swipe_nav), JUMP to cond_5

        # === cond_4 fall-through (Android 10-14, OR Android 15+ without swipe_nav) ===
200:    const v0, -0x92e8ab6
202:    invoke-static {v1, v3, v0}, LX/0cW;->A0R(Landroid/view/View;II)V   # decorView.setBackgroundColor(v3=BLACK) — A1 catches
204:    invoke-static {p0, p2, v3}, LX/2ZS;->A05(...)V                      # A05 — paints android.R.id.content — A2 catches
206:    sget-boolean v0, LX/1un;->A00:Z
208:    if-eqz v0, :cond_6      # if 1un.A00==false (typical phone), JUMP to cond_6 (skip cond_5)

210:    :cond_5
211:    invoke-static {p0, v3}, LX/2ZS;->A00(Landroid/app/Activity;I)V     # ★ 2ZS.A00(activity, v3=BLACK) → 47l.run() → swipe_nav BLACK

213:    :cond_6
214:    if-eqz p5, :cond_b         # p5=0 for Reels path → JUMP to cond_b
216:    invoke-static {v1, v6, v2}, LX/1fC;->A06(...)V                       # SKIPPED (p5=0)
218:    return-void
```

### 2f. `2ZS.A08` behavior — verified Android-version branching

Read `2ZS.smali:458-483` + `3sA.smali:186-213`:

```smali
# 3sA.A02():
sget v1, Landroid/os/Build$VERSION;->SDK_INT:I
const/16 v0, 0x23              # 35 = Android 15
if-lt v1, v0, :cond_0          # if SDK < 35, return 0 (false)
const/4 v0, 0x1
return v0                      # SDK >= 35 → return 1 (true)
:cond_0
const/4 v0, 0x0
return v0

# 2ZS.A08(activity):
invoke-static {}, LX/3sA;->A02()Z
move-result v0
if-eqz v0, :cond_0             # if 3sA.A02()==false (Android 10-14), JUMP to cond_0 (return 1)
const v0, 0x7f0b3f31           # swipe_navigation_container
invoke-virtual {p0, v0}, ...->findViewById(I)...   # only checked on Android 15+
move-result-object v0
if-eqz v0, :cond_0             # if swipe_nav NOT found, return 1
const/4 v0, 0x0                # swipe_nav EXISTS → return 0 (FALSE) → cond_5 taken
return v0
:cond_0
const/4 v0, 0x1                # return 1 (TRUE) → cond_4 fall-through taken
return v0
```

**Branching summary:**

| Android version | `3sA.A02()` | `2ZS.A08` for MainActivity (has swipe_nav) | Path taken | `2ZS.A00` called? | `47l` posted? | swipe_nav painted BLACK? |
|---|---|---|---|---|---|---|
| Android 10-14 (SDK 29-34) | FALSE | TRUE (1) | cond_4 fall-through | Only if `1un.A00==true` | Only if `1un.A00==true` | Only if `1un.A00==true` |
| Android 15+ (SDK 35+) | TRUE | FALSE (0) | cond_5 | **ALWAYS** | **ALWAYS** | **ALWAYS** |

### 2g. `1un.A00` — large-screen / tablet flag

Read `InstagramMainActivity.smali:28580-28663` + `1un.smali:1369-1420`:

`1un.A00` is set to TRUE (1) at `InstagramMainActivity.smali:28663` ONLY when ALL THREE conditions pass:
1. `MobileConfig(0x81127d00116195L).BHQ()` returns TRUE (server-gated feature flag)
2. `1un.A0E(0XW.A00(screenWidthDp))` returns TRUE — screen width ordinal is 1 or 2 (likely "large" 600dp+ or "xlarge" 720dp+)
3. `1un.A0F(50L.A00(screenHeightDp))` returns TRUE — screen height bucket is non-zero

For a typical phone (e.g., 1080×1920 px at ~3× density = ~360×640 dp), the screen width is ~360dp → ordinal 0 (normal) → `1un.A0E` returns FALSE → `1un.A00` stays FALSE.

**So on a typical Android 10-14 phone:** `1un.A00 == false` → `2ZS.A00` SKIPPED → `47l` NOT posted → swipe_nav NOT painted BLACK. Existing A1+A2 patches handle decorView + android.R.id.content. Bar SHOULD be transparent.

**But the user reports BLACK.** This means one of:
- **(a) User is on Android 15+** (most likely) — `2ZS.A00` ALWAYS called → `47l` paints swipe_nav BLACK. This is the gap no patch addresses.
- **(b) User is on Android 10-14 with a large-screen device** (`1un.A00 == true`) — same outcome.
- **(c) User is on Android 10-14 phone AND patches are not actually applied** (build/install issue) — but 7-b verified patches ARE syntactically valid and the call path IS reached.
- **(d) Some OTHER paint path not yet identified** — 7-a's exhaustive trace found NO other paint path that fires after `2ZS.A01` for the basic Reels TAB case.

**Most likely: (a) — user is on Android 15+.** The task description's mention of "Android 10" in Q5 was the asker's hypothesis to test, not a confirmed device fact.

---

## 3. Q6 — Does `1fC.A06(false)` re-set `FLAG_TRANSLUCENT_STATUS`? — REFUTED

### 3a. `1fC.A06` source (verified by reading `1fC.smali:393-429` in full)

```smali
.method public static final A06(Landroid/view/View;Landroid/view/Window;Z)V
    .locals 2
    if-eqz p0, :cond_0
    const/16 v1, 0x400                                    # ★ v1 = 0x400 = 1024
    invoke-virtual {p0}, Landroid/view/View;->getSystemUiVisibility()I
    move-result v0
    if-eqz p2, :cond_1
    # p2 == TRUE branch:
    and-int/lit8 v0, v0, -0x5                             # clears bit 0x4 (SYSTEM_UI_FLAG_FULLSCREEN)
    or-int/lit16 v0, v0, 0x100                            # sets bit 0x100 (SYSTEM_UI_FLAG_LAYOUT_STABLE)
    invoke-virtual {p0, v0}, Landroid/view/View;->setSystemUiVisibility(I)V
    invoke-virtual {p1, v1}, Landroid/view/Window;->clearFlags(I)V   # window.clearFlags(0x400)
    :cond_0
    return-void
    :cond_1
    # p2 == FALSE branch:
    or-int/lit8 v0, v0, 0x4                               # sets bit 0x4 (SYSTEM_UI_FLAG_FULLSCREEN)
    and-int/lit16 v0, v0, -0x101                          # clears bit 0x100 (LAYOUT_STABLE)
    invoke-virtual {p0, v0}, Landroid/view/View;->setSystemUiVisibility(I)V
    invoke-virtual {p1, v1, v1}, Landroid/view/Window;->setFlags(II)V # window.setFlags(0x400, 0x400)
    return-void
.end method
```

### 3b. The constant `0x400` is `FLAG_FULLSCREEN`, NOT `FLAG_TRANSLUCENT_STATUS`

Verified Android `WindowManager.LayoutParams` flag values:

| Constant | Hex | Decimal | Meaning |
|---|---|---|---|
| `FLAG_FULLSCREEN` | `0x00000400` | 1024 | Hides status bar entirely (legacy window-level fullscreen) |
| `FLAG_TRANSLUCENT_STATUS` | `0x04000000` | 67108864 | Makes status bar translucent (gradient scrim) — disables `LAYOUT_FULLSCREEN` |
| `FLAG_TRANSLUCENT_NAVIGATION` | `0x08000000` | 134217728 | Same for nav bar |
| `FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS` | `0x80000000` | 2147483648 | Allows app to draw status/nav bar backgrounds |

**The user's Q6 hypothesis confused `FLAG_FULLSCREEN` (0x400) with `FLAG_TRANSLUCENT_STATUS` (0x04000000).** They are DIFFERENT flags with DIFFERENT effects:
- `FLAG_FULLSCREEN` (0x400) — Hides the status bar entirely. Does NOT cause a black strip; makes the status bar invisible.
- `FLAG_TRANSLUCENT_STATUS` (0x04000000) — Makes the status bar a semi-transparent gradient. WOULD cause a dark strip. But this is NOT what `1fC.A06` uses.

`1fC.A06(false)` calls `window.setFlags(0x400, 0x400)` which sets `FLAG_FULLSCREEN` (hides status bar) — NOT `FLAG_TRANSLUCENT_STATUS`.

### 3c. `1fC.A06` is NOT called in the Reels path anyway (gated on `1fC.A09`)

Read `2ZS.smali:271-280`:
```smali
271:    :cond_b
272:    invoke-static {v1, v6}, LX/1fC;->A09(Landroid/view/View;Landroid/view/Window;)Z
274:    move-result v0
276:    if-nez v0, :cond_c      # ★ if A09 != 0 (TRUE), SKIP A06 — JUMP to cond_c
278:    invoke-static {v1, v6, v4}, LX/1fC;->A06(Landroid/view/View;Landroid/view/Window;Z)V
280:    :cond_c
```

Read `1fC.smali:496-541` (`A09` method):
```smali
.method public static final A09(Landroid/view/View;Landroid/view/Window;)Z
    .locals 3
    invoke-virtual {p1}, Landroid/view/Window;->getAttributes()Landroid/view/WindowManager$LayoutParams;
    move-result-object v0
    iget v0, v0, Landroid/view/WindowManager$LayoutParams;->flags:I
    and-int/lit16 v0, v0, 0x400                          # check FLAG_FULLSCREEN (0x400)
    const/4 p1, 0x0
    if-eqz v0, :cond_0                                    # if FLAG_FULLSCREEN set, p1 = 1
    const/4 p1, 0x1
    :cond_0
    invoke-virtual {p0}, Landroid/view/View;->getSystemUiVisibility()I
    move-result v0
    const/4 p0, 0x4
    and-int/lit8 v2, v0, 0x4                              # check SYSTEM_UI_FLAG_FULLSCREEN (0x4)
    const/4 v1, 0x1
    const/4 v0, 0x0
    if-ne v2, p0, :cond_1                                 # if SYSTEM_UI_FLAG_FULLSCREEN set, v0 = 1
    const/4 v0, 0x1
    :cond_1
    if-nez p1, :cond_2                                    # if either set, return 0 (FALSE)
    if-nez v0, :cond_2
    return v1                                             # neither set → return 1 (TRUE)
    :cond_2
    const/4 v1, 0x0
    return v1
.end method
```

**`1fC.A09` returns TRUE (1) if NEITHER `FLAG_FULLSCREEN` (window 0x400) NOR `SYSTEM_UI_FLAG_FULLSCREEN` (view 0x4) is set.**

After A6 patch:
- `decorView.setSystemUiVisibility(0x500)` — does NOT set 0x4 (SYSTEM_UI_FLAG_FULLSCREEN) ✓
- `clearFlags(0xC000000)` — clears FLAG_TRANSLUCENT_STATUS (0x04000000) and FLAG_TRANSLUCENT_NAVIGATION (0x08000000). Does NOT touch FLAG_FULLSCREEN (0x400). But FLAG_FULLSCREEN was never set in the first place for a normal activity.
- So neither flag is set → `A09` returns 1 (TRUE) → `if-nez v0, :cond_c` JUMPS to cond_c → **`1fC.A06` is SKIPPED**.

**Conclusion:** `1fC.A06` is NOT called in the Reels path after A6. Even if it WERE called, it uses 0x400 (FLAG_FULLSCREEN), not 0x04000000 (FLAG_TRANSLUCENT_STATUS). The user's Q6 hypothesis is **REFUTED on two independent grounds.**

### 3d. No OTHER caller of `1fC.A06` in the Reels-onResume path

Grep across all smali for `LX/1fC;->A06\(` returns 26 hits. Filtered to Reels-relevant:
- `2ZS.smali:216` — `1fC.A06(decorView, window, v2=0)` — but ONLY if `p5 != 0` (line 214 `if-eqz p5, :cond_b`). For Reels path, `p5=0` → SKIPPED.
- `2ZS.smali:278` — `1fC.A06(decorView, window, v4=1)` — gated on `A09` returning 0 → SKIPPED after A6 (A09 returns 1).
- `2ZS.smali:1001` — inside `A0A` method (swipe gesture handler, not onResume).
- All other callers (`1gE.smali`, `BrowserActionActivity.smali`, `ArchiveReelFragment.smali`, etc.) are NOT in the Reels-TAB onResume path.

**No caller of `1fC.A06(false)` fires during Reels tab onResume.** Q6 fully refuted.

---

## 4. Q4 — Does the theme's black `windowBackground` show through?

### 4a. Theme sets `android:windowBackground = ?igds_color_primary_background` (BLACK)

Per worklog 4-e: `Theme.Instagram` sets `android:windowBackground = ?igds_color_primary_background` which resolves to BLACK. This becomes the decorView's background drawable on activity creation.

### 4b. A6 patch DOES clear decorView background

Verified by reading `apply_patches.py:77-99` — the A6 block includes:
```smali
invoke-virtual {v0, v1}, Landroid/view/View;->setBackgroundColor(I)V     # decorView.setBackgroundColor(0)
```
where `v1 = 0x0`. This sets the decorView's background to a transparent ColorDrawable, OVERRIDING the theme's BLACK windowBackground.

**So the theme's windowBackground is NOT the issue — A6 already handles it.** (Note: 6-a's earlier claim that "A6 does decorView.setBackgroundColor(0)" was correct for the current A6 patch, but I initially misread it by looking at the old `2Ib.A01` helper instead of the actual A6 patch in `apply_patches.py`.)

### 4c. A1 patch ALSO clears decorView background (Android 10-14 only)

On Android 10-14, the cond_4 fall-through runs (because `2ZS.A08` returns TRUE). The A1 patch zeroes `v3` before `0cW.A0R(decorView, v3, ...)`, so `decorView.setBackgroundColor(0)` is called AGAIN. Redundant with A6, but harmless.

On Android 15+, cond_4 fall-through is BYPASSED, so A1 doesn't run. But A6 already handles it.

### 4d. `android.R.id.content` background

`2ZS.A05` (called from `2ZS.A01:204`, cond_4 fall-through) paints `android.R.id.content` (id `0x1020002`) with `v3`. The A2 patch zeroes `p2` in `A05`, so it paints transparent.

On Android 10-14: A05 runs, A2 catches → `android.R.id.content` transparent ✓
On Android 15+: A05 does NOT run (cond_4 fall-through bypassed) → `android.R.id.content` keeps its default background (transparent for FrameLayout/ContentFrameLayout) ✓

**Either way, `android.R.id.content` is transparent.** Not the culprit.

---

## 5. Q5 — Does `setSystemUiVisibility(0x500)` work on Android 10?

### 5a. Flag values verified

```
0x500 = 0x400 | 0x100
     = SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN (0x400 = 1024)
     | SYSTEM_UI_FLAG_LAYOUT_STABLE     (0x100 = 256)
```

Verified against `android.view.View` source constants. Correct.

### 5b. `setSystemUiVisibility` works on Android 10 (API 29)

`setSystemUiVisibility` is deprecated in API 30 (Android 11) but still functional through API ~32. On Android 10 (API 29), it's the standard non-deprecated API. It works.

**Caveat:** `setSystemUiVisibility(LAYOUT_FULLSCREEN)` only takes effect if `FLAG_TRANSLUCENT_STATUS` (0x04000000) is NOT set. Our A6 patch calls `clearFlags(0xC000000)` which clears `FLAG_TRANSLUCENT_STATUS` (0x04000000) and `FLAG_TRANSLUCENT_NAVIGATION` (0x08000000). So the precondition is satisfied.

**Conclusion:** `setSystemUiVisibility(0x500)` DOES work on Android 10 after A6 clears `FLAG_TRANSLUCENT_STATUS`. Content extends behind status bar. ✓

### 5c. On Android 15+ (API 35+), `setSystemUiVisibility` is IGNORED

Per Android docs, `setSystemUiVisibility` is fully ignored on API 35+ (Android 15) — the system uses `WindowInsetsController` instead. BUT — per 7-a's finding (line 251 of 7a-statusbar-complete-trace.md), `InstagramMainActivity.A0h:13087` and `A0i:17489` set `setSystemUiVisibility(0x700)` during onCreate, which suggests IG has already configured edge-to-edge via this legacy API. AND — the more reliable signal is that `setDecorFitsSystemWindows(false)` is the modern equivalent, but our A6 patch doesn't call it (it uses legacy `setSystemUiVisibility(0x500)` instead, to avoid the API 30+ crash that the v5 `2Ib.A01` helper caused on Android 10).

**Possible issue on Android 15+:** If `setSystemUiVisibility(0x500)` is fully ignored on API 35+, then content might NOT extend behind the status bar — meaning the BLACK the user sees would be the status bar color itself (but A5 forces it to 0... so this scenario is inconsistent). More likely, the activity's onCreate already set up edge-to-edge via `0x700`, and our A6's `0x500` is redundant but harmless.

**This is a secondary concern.** The primary issue (swipe_nav painted BLACK by `47l`) is independent of whether `setSystemUiVisibility` works.

---

## 6. Q1 & Q2 — Status bar height views and Reels header

### 6a. Q1 — Views matching status_bar_height

Grep for `status_bar_height` across all smali returns 6 files:
- `smali_classes2/X/8ug.smali` — stable status bar height listener
- `smali/X/0tf.smali` — uses status bar height for some layout
- `smali_classes2/X/6wm.smali` — generic padding helper
- `smali_classes13/X/1fC.smali` — `1fC.A01()` reads status_bar_height (used by `1fC.A02` for some chrome)
- `smali_classes13/X/00B.smali` — uses status bar height
- `smali_classes19/X/Ixq.smali` — uses status bar height

None of these are in the Reels-onResume paint path. They're layout helpers that read the dimension for various UI elements (e.g., toolbar top padding). **No status-bar-height-sized overlay view is painted BLACK in the Reels path.** The BLACK is from the full-screen `swipe_navigation_container`, not a sized-to-status-bar overlay.

### 6b. Q2 — The "Reels/Friends" header

The screenshot shows a "Reels" header with a down-arrow below the status bar. Searched `AFt.smali` (ClipsTabFragment) for `setBackgroundColor` / `0cW;->A0R` — **NO matches**. ClipsTabFragment does NOT paint its header view BLACK. The header is likely a transparent TextView/Toolbar overlaid on the video, not a black-background view.

**The "Reels" header is NOT the source of the black strip.** The black strip is the full-screen `swipe_navigation_container` behind the header.

---

## 7. Layer-by-layer analysis (the definitive view)

After current A5+A6 patches, on Android 15+ (where `47l` fires):

| Layer | View | Background color | Source | Patched? |
|---|---|---|---|---|
| 1 | Status bar (window.setStatusBarColor) | **0 (transparent)** ✓ | A6 direct + A5 chokepoint in `1fC.A04` | ✓ |
| 2 | `decorView` | **0 (transparent)** ✓ | A6 direct `decorView.setBackgroundColor(0)` (also A1 on Android 10-14) | ✓ |
| 3 | `android.R.id.content` (0x1020002) | **0 (transparent)** ✓ | A2 patch in `2ZS.A05` (Android 10-14); default transparent (Android 15+) | ✓ |
| 4 | **`swipe_navigation_container` (0x7f0b3f31)** | **BLACK (0xFF000000)** ✗ | `47l.run()` → `0cW.A0R(view, BLACK, ...)` posted by `2ZS.A00` at `2ZS.smali:211` | **❌ NOT PATCHED** |
| 5 | viewpager2 / fragments | varies | (fragment backgrounds) | n/a |
| 6 | video view | video content | (player) | n/a |

**Layer 4 is the FRONTMOST BLACK layer.** With edge-to-edge enabled (A6's `setSystemUiVisibility(0x500)`), layer 4 extends behind the status bar. The transparent layers 1-3 allow the BLACK layer 4 to show through in the status bar area. User perceives this as "status bar is black" — but actually the status bar IS transparent; the BLACK is the content view's background showing through.

---

## 8. Recommended fix — "A7" patch (the missing piece)

### Option A (RECOMMENDED — chokepoint, mirrors A5's approach)

**Patch `2ZS.A00` to force `p1 = 0` at method entry.**

**File:** `smali_classes17/X/2ZS.smali`
**Method:** `A00(Landroid/app/Activity;I)V` (line 45)

```diff
 .method public static final A00(Landroid/app/Activity;I)V
     .locals 1
     .annotation build Ldalvik/annotation/optimization/NeverInline;
     .end annotation

+    # InstaTrueReel: force transparent swipe_navigation_container bg
+    const/4 p1, 0x0
+
     new-instance v0, LX/47l;

     invoke-direct {v0, p0, p1}, LX/47l;-><init>(Landroid/app/Activity;I)V

     invoke-static {p0, v0}, LX/8ug;->A06(Landroid/app/Activity;Ljava/lang/Runnable;)V

     return-void
 .end method
```

**Effect:** Every caller of `2ZS.A00` (only one: `2ZS.A01:211`) now passes `p1=0`. The `47l` Runnable is constructed with color=0, so `47l.run()` calls `swipe_navigation_container.setBackgroundColor(0)` — transparent. Layer 4 becomes transparent, matching layers 1-3.

**Side effects:** None. `2ZS.A00` is only called from `2ZS.A01:211` (cond_5 path) and `2ZS.A01:211` only (verified by grep). No other caller.

### Option B (TARGETED — patch the Runnable itself)

**Patch `47l.run()` to force `v1 = 0` before `0cW.A0R`.**

**File:** `smali_classes17/X/47l.smali`
**Method:** `run()V` (line 30)

```diff
 .method public final run()V
     .locals 3

     iget-object v1, p0, LX/47l;->A01:Landroid/app/Activity;

     const v0, 0x7f0b3f31

     invoke-virtual {v1, v0}, Landroid/app/Activity;->findViewById(I)Landroid/view/View;

     move-result-object v2

     if-eqz v2, :cond_0

     iget v1, p0, LX/47l;->A00:I

+    # InstaTrueReel: force transparent swipe_nav bg
+    const/4 v1, 0x0
+
     const v0, 0x6bad5ee0

     invoke-static {v2, v1, v0}, LX/0cW;->A0R(Landroid/view/View;II)V

     :cond_0
     return-void
 .end method
```

**Effect:** Same as Option A — `47l.run()` always paints swipe_nav transparent. Slightly more targeted (only affects `47l`, not `2ZS.A00`), but Option A is cleaner.

### Option C (Fix Option B from 6-a / PATCH 1 from 5-a — proposed twice, never applied)

**Zero `v3` BEFORE the `2ZS.A00(activity, v3)` call at `2ZS.smali:211`.**

**File:** `smali_classes17/X/2ZS.smali`
**Insert `const/4 v3, 0x0` between line 205 (`invoke-static A05`) and line 206 (`sget-boolean 1un.A00`)**:

```diff
 204:    invoke-static {p0, p2, v3}, LX/2ZS;->A05(Landroid/app/Activity;Lcom/instagram/common/session/UserSession;I)V
+
+        # InstaTrueReel: zero chrome color so both cond_5 and cond_b use transparent
+        const/4 v3, 0x0
+
 206:    sget-boolean v0, LX/1un;->A00:Z
```

**Effect:**
- v3 is zeroed BEFORE the cond_5/cond_6 branch.
- Line 211 (cond_5, taken on Android 15+): `2ZS.A00(activity, 0)` → `47l.run()` paints swipe_nav TRANSPARENT ✓
- Line 267 (cond_a, only if `1fI.A05==true`): `window.setNavigationBarColor(0)` — nav bar transparent (consistent with A6) ✓
- Line 283 (cond_c): `1fC.A04(activity, 0)` — statusBarColor(0) (redundant with A5, harmless) ✓

**Side effect:** Also zeroes the nav bar color (line 267) and statusBarColor (line 283) — both already handled by A6/A5, so consistent. No regression.

**Recommendation:** Apply **Option A** (chokepoint in `2ZS.A00`). It's the cleanest, most targeted, and mirrors the proven A5 approach.

---

## 9. Diagnostic RED test (to confirm before applying fix)

To unambiguously confirm `47l.run()` is the culprit (and not some unidentified other path), apply this temporary diagnostic:

**File:** `smali_classes17/X/47l.smali`
**Method:** `run()V`

```diff
     iget v1, p0, LX/47l;->A00:I

+    # DIAGNOSTIC: paint swipe_nav RED to confirm 47l is the last writer
+    const v1, -0x10000          # 0xFFFF0000 (RED)
+
     const v0, 0x6bad5ee0
```

**Interpretation:**
- Bar turns RED → `47l.run()` IS the last writer. Apply Option A fix (change RED to 0).
- Bar stays BLACK → `47l.run()` is NOT the culprit; some other paint path fires after it. Investigate further.
- Bar turns RED then BLACK → some OTHER caller fires after `47l.run()`. Candidates: none identified in 7-a's exhaustive trace, but possible if there's a deferred paint not yet found.

---

## 10. Summary of Q1-Q6 verdicts

| Q | Question | Verdict |
|---|----------|---------|
| Q1 | Views matching status_bar_height | **Not the culprit.** 6 files reference `status_bar_height` but none paint a status-bar-height-sized overlay BLACK in the Reels path. |
| Q2 | "Reels/Friends" header painted BLACK | **Not the culprit.** `AFt.smali` (ClipsTabFragment) has NO `setBackgroundColor` / `0cW.A0R` calls. Header is transparent overlay. |
| Q3 | `swipe_navigation_container` (0x7f0b3f31) painted BLACK by `47l` | **🎯 YES — THE CULPRIT.** `47l.run()` → `0cW.A0R(swipe_nav, BLACK, ...)` → `setBackgroundColor(BLACK)`. Posted by `2ZS.A00` at `2ZS.smali:211` (cond_5 path, taken on Android 15+ unconditionally, and on Android 10-14 if `1un.A00==true`). NOT caught by any current patch. |
| Q4 | Theme's black `windowBackground` showing through | **Already handled by A6.** A6 calls `decorView.setBackgroundColor(0)` which overrides the theme windowBackground. Not the culprit. |
| Q5 | `setSystemUiVisibility(0x500)` on Android 10 | **Works on Android 10.** 0x500 = LAYOUT_FULLSCREEN|LAYOUT_STABLE. Deprecated in API 30 but functional. Requires FLAG_TRANSLUCENT_STATUS to be cleared — A6 does this via `clearFlags(0xC000000)`. Not the culprit. (On Android 15+ it may be ignored, but the activity's onCreate already sets `0x700` for edge-to-edge.) |
| Q6 | `1fC.A06(false)` re-sets `FLAG_TRANSLUCENT_STATUS` | **❌ REFUTED on two grounds.** (a) `1fC.A06` is NOT called in the Reels path — gated on `1fC.A09` which returns TRUE after A6 (neither `FLAG_FULLSCREEN` 0x400 nor `SYSTEM_UI_FLAG_FULLSCREEN` 0x4 is set), so the call at `2ZS.smali:278` is SKIPPED. (b) `1fC.A06` uses constant `0x400` = `FLAG_FULLSCREEN` (1024), NOT `FLAG_TRANSLUCENT_STATUS` (`0x04000000` = 67108864). The user confused two different flag values. |

---

## 11. Key file:line references (cheat sheet)

| File | Line(s) | What |
|---|---|---|
| `smali_classes17/X/2ZS.smali` | 45-57 | `A00(activity, color)` — posts `47l` Runnable via `8ug.A06` |
| `smali_classes17/X/2ZS.smali` | 194-198 | `2ZS.A08` check + branch to cond_5 (Android 15+) or cond_4 fall-through (Android 10-14) |
| `smali_classes17/X/2ZS.smali` | 206-208 | `1un.A00` check — if true, fall through to cond_5 (paints swipe_nav); if false, skip to cond_6 |
| `smali_classes17/X/2ZS.smali` | 210-211 | **★ `:cond_5` → `2ZS.A00(activity, v3=BLACK)` — THE CULPRIT CALL ★** |
| `smali_classes17/X/2ZS.smali` | 271-280 | `:cond_b` → `1fC.A09` check → SKIPS `1fC.A06` if A09 returns 1 (which it does after A6) |
| `smali_classes17/X/2ZS.smali` | 283 | `1fC.A04(activity, v3=BLACK)` — A5 zeroes p1 → statusBarColor(0) ✓ |
| `smali_classes17/X/2ZS.smali` | 458-483 | `A08(activity)` — returns FALSE on Android 15+ with swipe_nav, TRUE otherwise |
| `smali_classes17/X/47l.smali` | 30-51 | `run()` — paints `swipe_navigation_container` (0x7f0b3f31) with stored color |
| `smali_classes17/X/47l.smali` | 47 | **★ `0cW.A0R(v2, v1=BLACK, 0x6bad5ee0)` — THE LAST WRITER ★** |
| `smali_classes13/X/1fC.smali` | 393-429 | `A06(View, Window, Z)` — uses `0x400` = FLAG_FULLSCREEN (NOT FLAG_TRANSLUCENT_STATUS) |
| `smali_classes13/X/1fC.smali` | 496-541 | `A09(View, Window)` — returns TRUE if neither FLAG_FULLSCREEN nor SYSTEM_UI_FLAG_FULLSCREEN is set |
| `smali_classes13/X/0cW.smali` | 333-343 | `A0R(View, color, hash)` — wrapper for `view.setBackgroundColor(color)` |
| `smali_classes13/X/0ZS.smali` | 3090-3098 | Casts `0x7f0b3f31` to `SwipeNavigationContainer` |
| `smali_classes2/X/3sA.smali` | 186-213 | `A02()` — returns TRUE on Android 15+ (SDK 35+), FALSE on Android 10-14 |
| `smali_classes2/X/8ug.smali` | 691-857 | `A06(activity, runnable)` — runs sync or deferred |
| `smali_classes15/X/2Ib.smali` | 38-84 | `A01(Window, Z)` — IG's edge-to-edge helper (NOT used by current A6 patch; A6 inlines legacy calls instead) |
| `smali/com/instagram/ui/swipenavigation/container/SwipeNavigationContainer.smali` | 1-2 | Extends `FrameLayout` — full-bleed container, no `setFitsSystemWindows` |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 28663 | `sput-boolean v5=1, LX/1un;->A00:Z` — sets large-screen flag (only if MC flag + screen size checks pass) |

---

## 12. Conclusion

**The user's hypothesis (Q3) is CORRECT.** The black status bar strip is NOT the status bar color itself (which IS transparent after A5+A6) — it's the **`swipe_navigation_container` view** being painted BLACK by the `47l` Runnable, visible through the transparent status bar because A6 enabled edge-to-edge layout.

**The user's Q6 hypothesis is REFUTED.** `1fC.A06(false)` is NOT called in the Reels path (gated on `1fC.A09` which returns TRUE after A6), and even if it were, it uses `0x400` = `FLAG_FULLSCREEN` (not `FLAG_TRANSLUCENT_STATUS` = `0x04000000`).

**The fix is a new "A7" patch** that forces the color to 0 in `2ZS.A00` (chokepoint) or `47l.run()` (targeted). This is the same fix 5-a ("PATCH 1") and 6-a ("Fix Option B") proposed — but applied at the `2ZS.A00` / `47l` level rather than at the `v3` zeroing level, which is cleaner and works regardless of Android version.

**READ-ONLY exploration complete.** No patch code was written to the APK. The recommended A7 patch is documented in §8 above for the implementer to apply.
