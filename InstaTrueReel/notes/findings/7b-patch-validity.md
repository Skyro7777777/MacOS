# Task 7-b: A6 Patch Validity + Path Gating Verification

**Agent:** Explore (sub-agent, READ-ONLY diagnostic)
**Date:** 2025-08-09
**Decoded source:** `/home/z/MacOS/insta-dec/` (freshly decoded, UNPATCHED — patches in `apply_patches.py` not yet applied here)
**Patch source:** `/home/z/MacOS/InstaTrueReel/patches/apply_patches.py`

---

## TL;DR

| # | Question | Verdict |
|---|----------|---------|
| Q1 | Is A6 smali syntactically valid? | **✅ VALID** — all 4 sub-checks pass (registers, labels, branch targets, params) |
| Q2 | Does ClipsTabFragment.onResume actually call 2ZS.A02 → A01? | **✅ YES — UNGATED.** Direct call at `AFt.smali:2598`, no feature flag, no MobileConfig check between onResume and A01 |
| Q3 | Is there a feed-reel entry path that BYPASSES 2ZS.A01? | **❌ NO.** Feed-reel viewer (`1gE.smali:15884` onResume) ALSO calls `2ZS.A02` (line 16127). Stories (`ReelViewerFragment.smali`) calls `2ZS.A03` which also delegates to `A01`. All paths flow through `2ZS.A01` → A6 runs everywhere |
| Q4 | Does A6 run BEFORE or AFTER InstagramMainActivity.A1z? | **A6 runs AFTER A1z (correct order).** Android lifecycle: Activity.onResume → Fragment.onResume. `onWindowFocusChanged` does NOT touch status bar color (verified). No posted callback re-paints BLACK after fragment.onResume |
| Q5 | Diagnostic RED recommendation | **Change A6's `setStatusBarColor(0)` → `setStatusBarColor(0xFFFF0000)` (RED).** See §5 below |

**Key finding:** Both A5 (`1fC.A04` zero p1) and A6 (`2ZS.A01` legacy edge-to-edge) patches are syntactically valid AND the call path IS reached. With A5 applied, even the BLACK `1fC.A04(BLACK)` call at `2ZS.A01:283` is forced to transparent. The patches SHOULD work. The fact that the bar is still black suggests either (a) the patches are not actually being applied to the running APK (build/install issue), or (b) some other override path not yet identified. The RED diagnostic test (§5) is the recommended next step to disambiguate.

---

## 1. A6 Smali Validity Verdict

### Source: `apply_patches.py` lines 77-99

The A6 patch is a single `patch_text` call that replaces:
```
'.method public static final A01(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;IZZZ)V\n    .locals 7'
```
with the same string + `\n\n` + the InstaTrueReel block + `\n    :itre_skip`.

### 1a. Register Safety — ✅ SAFE

**Method signature (unpatched `2ZS.smali:59-60`):**
```smali
.method public static final A01(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;IZZZ)V
    .locals 7
```

Static method, 7 params (p0=Activity, p1=Fragment, p2=UserSession, p3=I, p4=Z, p5=Z, p6=Z), `.locals 7` (v0-v6).

**Register map (Dalvik):**
- Locals: v0, v1, v2, v3, v4, v5, v6
- Params: p0=v7, p1=v8, p2=v9, p3=v10, p4=v11, p5=v12, p6=v13
- Total registers: 14 (v0-v13)

**A6 patch register usage:**
- `move-result-object v0` — stores getWindow() result, then later overwrites with getDecorView() result
- `const/high16 v1, ...`, `const/4 v1, ...` — sets color/flags constants

**Original first real instruction (unpatched `2ZS.smali:62`):**
```smali
const/4 v2, 0x0
```
Uses v2 (NOT v0/v1). So v0 and v1 are safe to clobber at method start.

**Original code's first write to v0:** `move-result v0` at line 66 (after `2ZS.A09(p2)` call). v0 is dead until then. ✅
**Original code's first write to v1:** `move-result-object v1` at line 85 (after `0bJ.A01(p0)` call). v1 is dead until then. ✅

**After `:itre_skip`:** control falls through to `const/4 v2, 0x0` (original line 62). v2 is initialized correctly. v0/v1 are dead until their next assignment. ✅

### 1b. Label Collision — ✅ NO COLLISION

**Existing labels in `2ZS.A01` (unpatched):**
`:cond_0` (82), `:cond_1` (115), `:cond_2` (150), `:cond_3` (169), `:goto_0` (170), `:cond_4` (193), `:cond_5` (210), `:cond_6` (213), `:cond_7` (220), `:cond_8` (229), `:goto_1` (232), `:cond_9` (247), `:cond_a` (266), `:cond_b` (271), `:cond_c` (280), `:cond_d` (285), `:cond_e` (290), `:cond_f` (299)

**A6 patch label:** `:itre_skip` — UNIQUE. Does not collide with any existing label. ✅

### 1c. Branch Target Safety — ✅ SAFE

**Two `if-eqz` branches target `:itre_skip`:**
1. `if-eqz v0, :itre_skip` — when `getWindow()` returns null
2. `if-eqz v0, :itre_skip` — when `getDecorView()` returns null

**After `:itre_skip`:** falls through to `const/4 v2, 0x0` (original line 62), which is the FIRST instruction of the original method body. No initialization is skipped. ✅

**Risk check — could `:itre_skip` jump PAST important initialization?**
- The patch is inserted BETWEEN `.locals 7` and `const/4 v2, 0x0`. The `:itre_skip` label is positioned IMMEDIATELY before `const/4 v2, 0x0`. No original code exists between `.locals 7` and `:itre_skip` other than the A6 block itself. ✅

### 1d. Parameter Count — ✅ `invoke-virtual` (non-range) WORKS

For a STATIC method with `.locals 7` and 7 params:
- p0 = v7 (within 0-15 range for `invoke-virtual` 35c format)
- p1 = v8, p2 = v9, p3 = v10, p4 = v11, p5 = v12, p6 = v13

**A6 patch invoke instructions (all ≤ 2 registers):**
```smali
invoke-virtual {p0}, Landroid/app/Activity;->getWindow()...        # 1 reg (p0=v7)
invoke-virtual {v0, v1}, Landroid/view/Window;->clearFlags(I)V     # 2 regs
invoke-virtual {v0, v1}, Landroid/view/Window;->addFlags(I)V       # 2 regs
invoke-virtual {v0, v1}, Landroid/view/Window;->setStatusBarColor(I)V  # 2 regs
invoke-virtual {v0, v1}, Landroid/view/Window;->setNavigationBarColor(I)V  # 2 regs
invoke-virtual {v0}, Landroid/view/Window;->getDecorView()...      # 1 reg
invoke-virtual {v0, v1}, Landroid/view/View;->setSystemUiVisibility(I)V  # 2 regs
invoke-virtual {v0, v1}, Landroid/view/View;->setBackgroundColor(I)V  # 2 regs
```

`invoke-virtual` (35c format) supports up to 5 registers. All A6 invokes use ≤ 2 registers. p0 (=v7) fits in the 4-bit register field (range 0-15). **No `/range` form needed.** ✅

(Reference: existing unpatched code uses `invoke-virtual {v0, p0, p1}` at line 80 and `invoke-virtual {v0, p0, p3}` at line 111 — non-range form with p0/p1/p3 works fine throughout.)

### 1e. Instruction-Level Validity Checks — ✅ ALL VALID

| Instruction | Format | Literal | Constraint | Pass? |
|---|---|---|---|---|
| `const/high16 v1, 0xc000000` | 21s (high16) | 0x0C000000 (FLAG_TRANSLUCENT_STATUS\|FLAG_TRANSLUCENT_NAVIGATION) | Low 16 bits = 0; high 16 bits = 0x0C fits in signed 16-bit | ✅ |
| `const/high16 v1, -0x80000000` | 21s (high16) | 0x80000000 (FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS) | Smali parses `-0x80000000` as two's complement = 0x80000000; low 16 bits = 0; high 16 bits = 0x8000 fits in signed 16-bit (-32768) | ✅ |
| `const/16 v1, 0x500` | 22s | 0x500 (SYSTEM_UI_FLAG_LAYOUT_STABLE\|LAYOUT_FULLSCREEN = 0x100\|0x400) | Fits in signed 16-bit (-32768..32767) | ✅ |
| `const/4 v1, 0x0` | 11n | 0 | -8 ≤ 0 ≤ 7 | ✅ |
| `if-eqz v0, :itre_skip` | 21t | — | Branch target within method | ✅ |

### 1f. Patch Application Pattern — ✅ OLD STRING EXISTS

The OLD pattern in `patch_text` is:
```
.method public static final A01(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;IZZZ)V\n    .locals 7
```

This matches `2ZS.smali` lines 59-60 exactly (verified by Read). No false-negative risk from whitespace mismatch. ✅

### A6 Validity Summary

**VERDICT: A6 patch is fully syntactically valid. All instructions will assemble correctly. No register corruption, no label collision, no skipped initialization, no need for `/range` form.**

---

## 2. Call Path Verification — Does 2ZS.A01 Actually Run on Reels?

### 2a. `ClipsTabFragment.onResume()` — Direct, Ungated Call

**File:** `/home/z/MacOS/insta-dec/smali_classes16/X/AFt.smali`
**Method:** `onResume()V` at line 2564

```smali
.method public final onResume()V
    .locals 5
    ...
    :try_start_0
    invoke-super {p0}, LX/2yN;->onResume()V        # line 2580

    invoke-virtual {p0}, Landroidx/fragment/app/Fragment;->requireActivity()...   # line 2582
    move-result-object v3                                                            # v3 = activity

    iget-object v0, p0, LX/AFt;->A0A:LX/JDl;       # line 2586
    invoke-interface {v0}, LX/JDl;->getValue()...   # line 2588
    move-result-object v2                                                            # v2 = userSession
    check-cast v2, Lcom/instagram/common/session/UserSession;

    const/4 v1, 0x1
    const/4 v0, 0x0

    invoke-static {v3, p0, v2, v1, v0}, LX/2ZS;->A02(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;ZZ)V   # line 2598
    :try_end_0
    .catchall {:try_start_0 .. :try_end_0} :catchall_0
    ...
.end method
```

**Args to A02:** (activity, this, userSession, true, false)

**Gating check:** The call to `2ZS.A02` is wrapped in a `:try_start_0`/`:try_end_0` for exception handling ONLY. There is **NO MobileConfig check, NO feature flag, NO `if`-condition** between `super.onResume()` and `2ZS.A02(...)`. The call is UNCONDITIONAL (modulo not throwing an exception). ✅

### 2b. `2ZS.A02` → `2ZS.A01` Delegation — Ungated

**File:** `/home/z/MacOS/insta-dec/smali_classes17/X/2ZS.smali`
**Method:** `A02(...)V` at line 309

```smali
.method public static final A02(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;ZZ)V
    .locals 8
    ...
    const/4 v7, 0x0                                  # line 314 — v7 = 0 (becomes A01.p6)
    ...
    const v0, 0x7f040714                             # line 322 — resource ID (icon color)
    ...
    invoke-static {p0, v0}, LX/0bF;->A0Z(Landroid/content/Context;I)I    # line 326
    move-result v4                                                            # v4 = resolved icon color (becomes A01.p3)

    move-object v2, p1                                # line 330 — v2 = fragment
    move v5, p3                                       # line 332 — v5 = p3 from A02 (=1, true from AFt)
    move v6, p4                                       # line 334 — v6 = p4 from A02 (=0, false from AFt)

    invoke-static/range {v1 .. v7}, LX/2ZS;->A01(...)   # line 336 — calls A01 with v1..v7
    return-void
.end method
```

**A01 receives:**
- p0 = v1 = activity
- p1 = v2 = fragment (ClipsTabFragment)
- p2 = v3 = userSession
- p3 = v4 = resolved icon color (from resource `0x7f040714`)
- p4 = v5 = 1 (true, from AFt.onResume's `v1=1`)
- p5 = v6 = 0 (false, from AFt.onResume's `v0=0`)
- p6 = v7 = 0 (hardcoded by A02)

**Gating check:** NO gating between A02 entry and the `invoke-static/range` call to A01. A01 is called UNCONDITIONALLY. ✅

**Therefore:** A6 (inserted at the start of A01) IS reached on every Reels tab onResume.

### 2c. Important Nuance — A6 Runs, But A01 Continues Afterward

After A6 runs at the start of A01, control falls through to the ORIGINAL A01 body, which:
1. Line 91: Resolves color `0x7f0407af` (`?igds_color_primary_background`, BLACK) → v3
2. Lines 93-114: `if-eqz p4, :cond_1` — p4=1 (true), so falls through; calls `0bQ.A04(activity, userSession, v1, v0)`, `0bQ.A09(...)`, `0bQ.A0A(...)`
3. Line 165-167: `if-eqz v0, :cond_7` — checks `1fI.A05:Z` static flag
   - If TRUE: calls `1fI.A04(activity, v3=BLACK)` (only sets NAV bar color, not status bar — verified `1fI.A04` does NOT call `setStatusBarColor`)
4. Line 194: `2ZS.A08(activity)` → v0 (Android-version-dependent; see §4 below)
5. Line 198: `if-eqz v0, :cond_5` — depending on A08 result
6. Line 283: `1fC.A04(activity, v3=BLACK)` — **★ THE STATUS BAR COLOR CALL ★**

This BLACK call at line 283 is what the A5 patch (`1fC.A04` zero p1) is designed to catch. With A5 applied, `1fC.A04(BLACK)` becomes `1fC.A04(0)` → `setStatusBarColor(0)` (transparent). ✅

---

## 3. Feed-Reel Path Check — Does It Use a Different Chrome Setup?

### 3a. All Callers of `2ZS.A01` / `2ZS.A02` / `2ZS.A03`

Grep across all smali files for `invoke-static.*LX/2ZS;->A0[123]\(` returns 23 hits:

| File | Line | Method | Calls |
|---|---|---|---|
| `smali_classes16/X/AFt.smali` | 2598 | `onResume()` | `2ZS.A02` ← **Reels tab (ClipsTabFragment)** |
| `smali/X/1gE.smali` | 16127 | `onResume()` | `2ZS.A02` ← **Feed-reel viewer** |
| `smali/instagram/features/stories/fragment/ReelViewerFragment.smali` | 14098 | (onResume or similar) | `2ZS.A03` ← **Stories viewer** |
| `smali/instagram/features/stories/fragment/ReelViewerFragment.smali` | 19317 | (lifecycle) | `2ZS.A03` |
| `smali_classes16/X/9b7.smali` | 173 | ? | `2ZS.A03` |
| `smali_classes16/X/Ias.smali` | 89 | ? | `2ZS.A02` |
| `smali_classes5/X/ISr.smali` | 734, 814 | ? | `2ZS.A02` (×2) |
| `smali_classes5/X/IPv.smali` | 1826 | ? | `2ZS.A02` |
| `smali_classes5/X/IGT.smali` | 529 | ? | `2ZS.A03` |
| `smali_classes6/X/P4F.smali` | 80 | ? | `2ZS.A02` |
| `smali_classes6/X/PAk.smali` | 653 | ? | `2ZS.A02` |
| `smali_classes7/X/O5r.smali` | 515 | ? | `2ZS.A01` (direct) |
| `smali_classes11/com/instagram/wellbeing/timespent/fragment/TimeSpentReminderFullyBlockingFragment.smali` | 943 | ? | `2ZS.A01` (direct) |
| `smali_classes13/X/3lX.smali` | 2413 | ? | `2ZS.A02` |
| `smali_classes7/instagram/features/stories/storiestemplate/discovery/view/StoryTemplateDiscoverySurfaceFragment.smali` | 1794 | ? | `2ZS.A02` |
| `smali_classes18/X/Jqr.smali` | 189 | ? | `2ZS.A03` |
| `smali_classes18/X/JeZ.smali` | 478 | ? | `2ZS.A03` |
| `smali_classes19/X/IbC.smali` | 854 | ? | `2ZS.A03` |
| `smali_classes21/X/218.smali` | 1770 | ? | `2ZS.A02` |
| `smali_classes17/X/2ZS.smali` | 336, 366, 384, 453 | `A02`, `A03`, `A05`, `A07` (internal delegation) | `A01` |

**ALL paths funnel through `2ZS.A01`.** A6 is at the start of `A01`, so A6 executes on EVERY surface (Reels tab, feed-reel, Stories, etc.).

### 3b. Feed-Reel Viewer (`1gE`) — Same Path

**File:** `/home/z/MacOS/insta-dec/smali/X/1gE.smali` (18,484 lines)
**Class:** `LX/1gE;` extends `LX/2yZ;` (different parent from ClipsTabFragment's `2yN`, but same Fragment lifecycle)
**Method:** `onResume()V` at line 15884

```smali
invoke-static {v0}, LX/3hz;->A00(Lcom/instagram/common/session/UserSession;)Z    # line 16103
move-result v0
if-eqz v0, :cond_8                                                              # line 16107

invoke-virtual {v4}, Landroidx/fragment/app/Fragment;->getActivity()...        # line 16109
move-result-object v6
if-eqz v6, :cond_8                                                              # line 16113

invoke-static {}, LX/3tz;->A03()Z                                               # line 16115
move-result v0
if-eqz v0, :cond_b                                                              # line 16119

invoke-virtual {v4}, LX/1gE;->A0J()...                                          # line 16121
move-result-object v1                                                            # v1 = userSession
const/4 v0, 0x1

invoke-static {v6, v4, v1, v0, v3}, LX/2ZS;->A02(...)                          # line 16127
```

**Args to A02:** (activity, fragment, userSession, true, v3 — last arg from local context)

**Gating:** Unlike ClipsTabFragment, the feed-reel path IS gated by THREE conditions:
1. `3hz.A00(userSession)` returns TRUE
2. `getActivity()` is non-null
3. `3tz.A03()` returns TRUE

If any fails, the call is skipped (`:cond_8` or `:cond_b`). But when opening a reel from the home feed, all three typically pass (otherwise the reel wouldn't be visible at all). So A6 IS reached on feed-reels in the common case.

### 3c. Stories Viewer (`ReelViewerFragment`) — Calls `A03` Which Calls `A01`

**File:** `/home/z/MacOS/insta-dec/smali/instagram/features/stories/fragment/ReelViewerFragment.smali`
**Lines:** 14098, 19317 — both call `2ZS.A03`

`2ZS.A03` (lines 341-369) delegates to `2ZS.A01` via `invoke-static/range {v1 .. v7}` at line 366. Same A6 entry point. ✅

### 3d. Other Surfaces

The other callers (ISr, IPv, P4F, PAk, etc.) are scattered across various surfaces — likely comment composer, story composer, archived reels, etc. ALL go through `2ZS.A01`. A6 runs everywhere. ✅

### 3e. Conclusion

**There is NO feed-reel entry path that bypasses `2ZS.A01`.** All paths (Reels tab, home-feed reel, Stories, archived reels, etc.) funnel through `2ZS.A01` via either `A02` or `A03`. A6 executes universally. If the user sees BLACK on ANY Reels surface, A6 IS running (assuming the patch was actually applied — see §6).

---

## 4. Execution Order — Does A6 Run Last?

### 4a. Android Lifecycle Guarantees

Per Android lifecycle:
1. `Activity.onResume()` runs FIRST
2. `Fragment.onResume()` runs AFTER Activity.onResume completes

So for InstagramMainActivity + ClipsTabFragment:
1. `InstagramMainActivity.A1z(LX/2y8;)V` (onResume) runs → calls `1fC.A03(activity, BLACK)` at lines 35535 or 36397 → `1fC.A04(activity, BLACK)` → `setStatusBarColor(BLACK)` (or schedules Choreographer if defer is on)
2. THEN `ClipsTabFragment.onResume()` runs → `2ZS.A02` → `2ZS.A01`:
   - A6 patch: `setStatusBarColor(0)` synchronously (TRANSPARENT)
   - Continues to line 283: `1fC.A04(activity, BLACK)` → **A5 patch zeroes p1** → `setStatusBarColor(0)` (TRANSPARENT)

### 4b. `onWindowFocusChanged` — Does NOT Re-paint

**File:** `/home/z/MacOS/insta-dec/smali/com/instagram/mainactivity/InstagramMainActivity.smali`
**Method:** `onWindowFocusChanged(Z)V` at line 50512, ends at line 50662

Grep for `setStatusBarColor`, `setNavigationBarColor`, `1fC;->A0[234]` in InstagramMainActivity.smali returns ONLY 4 hits — all in `A0m` (lines 20250, 21071) and `A1z` (lines 35535, 36397). `onWindowFocusChanged` has ZERO such calls. ✅

**Therefore:** `onWindowFocusChanged` does NOT re-paint the status bar after fragment.onResume. The last writer in the lifecycle is the `1fC.A04` call at `2ZS.A01:283` (with A5 patch, becomes transparent).

### 4c. `A1p` — Does NOT Re-paint

`A1p(Landroid/content/res/Configuration;LX/2y8;)V` is for configuration changes. Same grep confirms no `1fC.A03/A04` calls in A1p. ✅

### 4d. `A0m` — Called FROM A1z, Not Independently

`A0m(LX/2y8;Lcom/instagram/mainactivity/InstagramMainActivity;)V` is a static helper called from `A1z` at line 36756 (`invoke-static {v8, v7}, Lcom/instagram/mainactivity/InstagramMainActivity;->A0m(LX/2y8;Lcom/instagram/mainactivity/InstagramMainActivity;)V`). It runs DURING A1z (Activity.onResume), BEFORE Fragment.onResume. Its two `1fC.A03` calls are caught by A5. ✅

### 4e. Deferred Choreographer Path — Caught by A5

If `1fC.A01:Z` (defer flag) is TRUE:
1. A1z → `1fC.A04(BLACK)` → schedules Choreographer, stores BLACK in `fCi.A01`, sets schedule flag
2. Fragment.onResume → A6 → `setStatusBarColor(0)` synchronously (TRANSPARENT momentarily)
3. A01 continues → line 283 `1fC.A04(BLACK)` → **A5 zeroes p1** → stores 0 in `fCi.A01` (overwrites BLACK), does NOT reschedule (flag already set)
4. Choreographer `doFrame` fires on next frame → reads `fCi.A01` (=0) → `setStatusBarColor(0)` (TRANSPARENT)

**Edge case:** If the Choreographer `doFrame` fires BETWEEN A1z and Fragment.onResume (i.e., a frame boundary in the ~1ms gap):
1. A1z → schedules Choreographer with BLACK stored
2. Choreographer `doFrame` fires → reads BLACK → `setStatusBarColor(BLACK)` (BLACK briefly)
3. Fragment.onResume → A6 → `setStatusBarColor(0)` (TRANSPARENT)
4. A01 continues → A5-modified `1fC.A04(BLACK)` → stores 0 in `fCi.A01`, doesn't reschedule
5. Final state: TRANSPARENT

**Either way, the final state is TRANSPARENT.** ✅

### 4f. Important Nuance — `2ZS.A08` Behavior Differs by Android Version

**6-a's claim:** "`2ZS.A08(activity)` returns 0 for MainActivity"

**My finding:** This is INCOMPLETE. `2ZS.A08` (lines 458-483) checks `3sA.A02()` first, which returns:
- TRUE if `Build.VERSION.SDK_INT >= 0x23` (= 35 = Android 15+) — see `3sA.smali:186-213`
- FALSE if SDK < 35 (Android 10-14)

`A08` logic:
```smali
invoke-static {}, LX/3sA;->A02()Z      # TRUE on Android 15+, FALSE on Android 10-14
move-result v0
if-eqz v0, :cond_0                     # if FALSE (Android 10-14), jump to cond_0 → return 1 (TRUE)
const v0, 0x7f0b3f31
invoke-virtual {p0, v0}, Landroid/app/Activity;->findViewById(I)Landroid/view/View;
move-result-object v0
if-eqz v0, :cond_0                     # if view NOT found, jump to cond_0 → return 1 (TRUE)
const/4 v0, 0x0
return v0                              # view found: return 0 (FALSE)

:cond_0
const/4 v0, 0x1
return v0                              # return 1 (TRUE)
```

**Result by Android version:**
- **Android 10-14 (SDK 29-34):** `3sA.A02()` returns FALSE → `A08` ALWAYS returns TRUE (1) regardless of view presence. → `if-eqz v0, :cond_5` does NOT jump → falls through to line 200-202 → **`0cW.A0R(decorView, v3, hash)` fires → A1 patch (which inserts `const/4 v3, 0x0` before this call) ACTIVATES → decorView.setBackgroundColor(0) ✓**
- **Android 15+ (SDK 35+):** `3sA.A02()` returns TRUE → `A08` checks `findViewById(0x7f0b3f31)`. If found (likely `swipe_navigation_container` in MainActivity) → `A08` returns FALSE (0) → `if-eqz v0, :cond_5` JUMPS → SKIPS line 202 → A1 patch is BYPASSED at this location (but A5 at `1fC.A04` still catches the BLACK call at line 283).

**Implication:** 6-a's trace was correct ONLY for Android 15+. On Android 10-14, A1 patch DOES activate at line 202 (decorView transparent). Combined with A5 (status bar transparent), the bar should be transparent on Android 10-14. **If the user is on Android 10-14 and still sees BLACK, the patches are NOT applied.**

### 4g. Execution Order Summary

| Step | Caller | What Happens | Result |
|---|---|---|---|
| 1 | `A1z` (Activity.onResume) | `1fC.A03(BLACK) → 1fC.A04(BLACK)` → `setStatusBarColor(BLACK)` or schedule Choreographer with BLACK | BLACK (briefly) |
| 2 | `ClipsTabFragment.onResume` → `2ZS.A02 → 2ZS.A01` | A6 patch: `setStatusBarColor(0)` synchronously | TRANSPARENT (briefly) |
| 3 | `2ZS.A01` continues | Line 202 (Android 10-14): A1 patch sets v3=0 → `0cW.A0R(decorView, 0)` → decorView transparent | decorView transparent |
| 4 | `2ZS.A01:283` | `1fC.A04(BLACK)` → **A5 zeroes p1** → `1fC.A04(0)` → `setStatusBarColor(0)` | **TRANSPARENT (final synchronous state)** |
| 5 | (if defer ON) Choreographer `doFrame` next frame | Reads `fCi.A01` (=0, last stored by step 4) → `setStatusBarColor(0)` | TRANSPARENT (final deferred state) |

**A6 (or its successor via A5) runs LAST.** ✅

---

## 5. Diagnostic RED Recommendation

### 5a. Recommended Patch

Change A6 in `apply_patches.py` line 89 from:
```python
'    const/4 v1, 0x0\n'
'    invoke-virtual {v0, v1}, Landroid/view/Window;->setStatusBarColor(I)V\n'
```
to (RED = `0xFFFF0000` = `-0x10000` in signed int):
```python
'    const v1, -0x10000\n'
'    invoke-virtual {v0, v1}, Landroid/view/Window;->setStatusBarColor(I)V\n'
```

(`const v1, -0x10000` uses the 31i format for arbitrary 32-bit literal; -0x10000 = 0xFFFF0000 in two's complement = bright red.)

### 5b. Expected Outcomes

After rebuilding and installing:

| Observation | Meaning | Next Step |
|---|---|---|
| Bar turns RED briefly then BLACK | A6 runs but is overridden by `2ZS.A01:283 → 1fC.A04(BLACK)` → **A5 patch NOT applied** (build issue). The BLACK `1fC.A04` call wins. | Verify A5 patch regex matches actual file. Run `apply_patches.py` and grep the patched file for `InstaTrueReel: force transparent status bar color`. If missing, fix the pattern. |
| Bar stays BLACK from the start | A6 patch is NOT being executed. Either (a) patch not applied to running APK (build/install issue), or (b) `2ZS.A01` is never called (very unlikely given §2), or (c) `getWindow()` returned null (impossible for visible Reels). | Verify A6 patch is in the built APK: `apktool d` the built APK and grep `2ZS.smali` for `InstaTrueReel: edge-to-edge`. If missing, the build pipeline skipped smali patching. |
| Bar turns RED and STAYS RED | A6 runs AND nothing overrides it. **A6 is the sole winner.** | Change `-0x10000` (RED) back to `0x0` (transparent). Done. |
| Bar turns RED briefly then transparent | A6 runs, then A5 catches the `1fC.A04(BLACK)` call and forces transparent. **A5+A6 are both working as designed.** | This means the bar IS transparent in the current build. If the user still sees BLACK, the issue is display/perception (e.g., the video behind is dark, system theme overrides, OEM customization). Investigate windowBackground. |

### 5c. Complementary Secondary Diagnostic

Also patch `2ZS.A01:283` (the `1fC.A04(BLACK)` call) to verify it's the LAST writer:

In `apply_patches.py`, add after the A5 block:
```python
# DIAGNOSTIC: RED at 2ZS.A01:284 (the 1fC.A04 call). Confirms whether this
# call is the LAST status bar color writer. REMOVE after diagnosis.
patch_text(zs,
    '    :cond_c\n\n    if-nez p6, :cond_d\n\n    invoke-static {p0, v3}, LX/1fC;->A04(Landroid/app/Activity;I)V',
    '    :cond_c\n\n    if-nez p6, :cond_d\n\n    # InstaTrueReel DIAGNOSTIC: RED at 1fC.A04 call site\n    const v3, -0x10000\n\n    invoke-static {p0, v3}, LX/1fC;->A04(Landroid/app/Activity;I)V',
    'DIAG-red-at-1fC-A04-call')
```

(Note: temporarily disable A5 when running this diagnostic, otherwise A5 will zero p1 and override the RED.)

| Observation (with A5 disabled) | Meaning |
|---|---|
| Bar turns RED and STAYS RED | Confirms `2ZS.A01:284` (`1fC.A04`) IS the LAST writer. Apply A5 (zero p1) → bar becomes transparent. Done. |
| Bar stays BLACK | `2ZS.A01:284` is NOT the last writer. Some OTHER code path overrides after fragment.onResume. Need to trace further. |
| Bar turns RED briefly then BLACK | There's a deferred callback (`3mE.A00` via Choreographer) that fires AFTER `2ZS.A01` returns and re-applies BLACK. A5 patch should catch this (since A5 modifies `1fC.A04` itself, which is the source of the stored BLACK value). If still BLACK with A5 enabled, the deferred callback reads a DIFFERENT source. |

### 5d. Recommended Workflow

1. **Build 1:** Apply A6-RED only (disable A5). Observe bar color on Reels tab.
2. **Build 2:** Apply A6-RED + DIAG-red-at-1fC-A04-call (disable A5). Observe.
3. **Build 3:** Apply A6 (original transparent) + A5 + DIAG-red-at-1fC-A04-call (A5 should zero p1, but DIAG adds RED at call site — these conflict; for clarity, use either A5 OR DIAG, not both).
4. Based on outcomes, narrow down whether the issue is:
   - Patches not applied (Build 1 shows BLACK from start)
   - A6 runs but BLACK overrides (Build 1 shows RED→BLACK)
   - A6+A5 work as designed (Build 1 with A5 enabled shows RED→transparent)

---

## 6. Critical Open Question — Are the Patches Actually Applied?

Given:
- A6 is syntactically valid (§1)
- The call path IS reached (§2)
- No alternate feed-reel path bypasses A6 (§3)
- A6 (and A5) run LAST in the lifecycle (§4)
- A5 catches the BLACK `1fC.A04` call at `2ZS.A01:283`

**The patches SHOULD make the bar transparent.** The fact that the user reports "STILL black" after 7 attempts strongly suggests one of:

### 6a. Most Likely: Build Pipeline Issue

The patches in `apply_patches.py` may not be applied to the actual APK being installed on the user's device. Possible causes:
- `apktool b` is using a cached/unaltered smali directory
- The patch script is run against the wrong directory (`<decoded_dir>` argument mismatch)
- The patch script reports "✅ applied" but the regex didn't actually match (false-positive — unlikely given §1f verification, but possible if the file was already patched and the script reports "may already be patched" silently)
- The built APK is signed but the OS is using a previously-installed version (user didn't uninstall before installing the new build)
- ReVanced patches (already applied to the base APK per worklog) may interfere with smali patching

**Verification step:** After `apply_patches.py` runs, grep the patched `2ZS.smali` for the literal string `InstaTrueReel: edge-to-edge`. If absent, the patch didn't apply. Also grep `1fC.smali` for `InstaTrueReel: force transparent`. If absent, A5 didn't apply.

### 6b. Less Likely: Hidden Override Path

If §6a is verified (patches ARE in the built APK), then some OTHER code path is firing `setStatusBarColor(BLACK)` after `2ZS.A01` returns. Candidates to investigate:
- Any `Handler.post()` or `View.post()` delayed callback in `2ZS.A01` or its callees that re-applies BLACK
- A `Window.setAttributes` call that resets status bar color
- An OEM-specific system overlay (Samsung's One UI, Xiaomi's MIUI, etc.) that forces BLACK status bar regardless of app calls — this would be a device-level issue, not an APK issue

### 6c. Least Likely: A6 Patch Was Never Added to apply_patches.py

Verified: `apply_patches.py` lines 77-99 contain the A6 patch. Confirmed present. ✅

---

## 7. Summary Table

| # | Question | Answer | Confidence |
|---|---|---|---|
| Q1 | A6 syntactically valid? | ✅ YES — registers, labels, branches, params all valid | HIGH |
| Q2 | onResume → A02 → A01 path reached? | ✅ YES — ungated call at `AFt.smali:2598` | HIGH |
| Q3 | Feed-reel bypasses A01? | ❌ NO — `1gE.smali:16127` also calls A02 → A01; Stories via A03 → A01; all paths flow through A01 | HIGH |
| Q4 | A6 runs last? | ✅ YES — A1z runs before Fragment.onResume; onWindowFocusChanged/A1p don't re-paint; A5 catches deferred Choreographer | HIGH |
| Q5 | RED diagnostic | Replace `const/4 v1, 0x0` (before setStatusBarColor) with `const v1, -0x10000` in A6 patch | — |
| Q6 | Why still black? | Most likely: build pipeline issue (patches not actually in installed APK). Verify by grepping built APK's `2ZS.smali` / `1fC.smali` for `InstaTrueReel` marker comments | MEDIUM |

---

## 8. File-Line Cheat Sheet

| File | Line | What |
|---|---|---|
| `apply_patches.py` | 77-99 | A6 patch definition |
| `apply_patches.py` | 106-112 | A5 patch definition |
| `smali_classes17/X/2ZS.smali` | 59-307 | `A01` method (unpatched) |
| `smali_classes17/X/2ZS.smali` | 62 | First original instruction after `.locals 7` (where A6 inserts) |
| `smali_classes17/X/2ZS.smali` | 194-198 | `2ZS.A08(activity)` check (Android-version-dependent) |
| `smali_classes17/X/2ZS.smali` | 202 | `0cW.A0R(decorView, v3, ...)` — A1 patch target (only on Android 10-14) |
| `smali_classes17/X/2ZS.smali` | 283 | `1fC.A04(activity, v3=BLACK)` — **★ THE BLACK STATUS BAR CALL ★** (A5 catches this) |
| `smali_classes17/X/2ZS.smali` | 309-339 | `A02` method (delegates to A01) |
| `smali_classes17/X/2ZS.smali` | 341-369 | `A03` method (delegates to A01) |
| `smali_classes17/X/2ZS.smali` | 458-483 | `A08` method (Android-version-dependent gate) |
| `smali_classes16/X/AFt.smali` | 2564-2624 | `ClipsTabFragment.onResume()` |
| `smali_classes16/X/AFt.smali` | 2598 | `invoke-static ... 2ZS.A02(...)` — ungated call |
| `smali/X/1gE.smali` | 15884 | `1gE.onResume()` (feed-reel viewer) |
| `smali/X/1gE.smali` | 16127 | `invoke-static ... 2ZS.A02(...)` — gated by 3 conditions |
| `smali_classes13/X/1fC.smali` | 212-334 | `1fC.A04(activity, p1)` method (A5 patch target) |
| `smali_classes13/X/1fC.smali` | 215 | `:goto_0` label (A5 inserts `const/4 p1, 0x0` before this) |
| `smali_classes13/X/1fC.smali` | 322 | `setStatusBarColor(p1)` — direct path (defer OFF) |
| `smali_classes13/X/1fC.smali` | 286-308 | Deferred Choreographer scheduling (defer ON) |
| `smali_classes13/X/3mE.smali` | 322 | `setStatusBarColor(v0)` — deferred callback (defer ON, next frame) |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 34709 | `A1z` (onResume) |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 35535, 36397 | `1fC.A03` calls in A1z (transparent / BLACK branch) |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 19664 | `A0m` (called from A1z) |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 20250, 21071 | `1fC.A03` calls in A0m |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 50512-50662 | `onWindowFocusChanged` — does NOT touch status bar |
| `smali_classes2/X/3sA.smali` | 186-213 | `3sA.A02()` — returns TRUE only on Android 15+ (SDK 35+) |

---

## 9. Open Questions for Next Agent

1. **Verify patches are in the built APK.** Decompile the BUILT APK (not the source decoded dir) and grep `2ZS.smali` / `1fC.smali` for `InstaTrueReel:` marker comments. If absent, the build pipeline is broken. This is the MOST LIKELY root cause given that all patches are syntactically valid and paths are confirmed reachable.

2. **Run the RED diagnostic.** Per §5, change A6 to use RED. Observe bar color. This unambiguously determines whether A6 executes.

3. **If patches ARE applied and A6 RED shows RED→BLACK:** Trace what fires AFTER `2ZS.A01:283`. Candidates: a delayed `Handler.post()` in `2ZS.A05` (called at line 204), `0bQ.A04/A09/A0A` (called at lines 107-113), or `1fI.A04` (called at line 167 if `1fI.A05:Z` is true). Add DIAG-red markers at each suspect call site to narrow down.

4. **If patches ARE applied and A6 RED shows BLACK from start:** Check if `2ZS.A01` is even being entered. Add a RED `setStatusBarColor` at the VERY START of `2ZS.A01` (before any if-eqz). If still BLACK, the method isn't being called — investigate Fragment lifecycle or whether `AFt` is the active fragment.

5. **Android version of user's device.** Determine whether user is on Android 10-14 or 15+. This affects whether `2ZS.A08` returns TRUE or FALSE, which affects whether the A1 patch at line 202 activates. (See §4f.)

READ-ONLY exploration complete. No patch code was written to the codebase. Diagnostic recommendations only.
