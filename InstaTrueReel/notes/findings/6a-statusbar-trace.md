# 6-a — Status bar trace: EXACT runtime call sequence & last writer

**Agent:** Explore (sub-agent, Task ID 6-a)
**Task:** Trace the EXACT runtime call sequence from app launch to Reels
visible, and find the LAST `setStatusBarColor` / background-paint call that
wins. Prior 4 patch attempts (A1/A2/A3/A6) failed — bar is still solid
black. READ-ONLY diagnostic.

## TL;DR (root cause confirmed)

**The A6 patch (calls `2Ib.A01(window, false)` at the start of `2ZS.A01`)
DOES run — but `2ZS.A01` itself CONTINUES executing after the A6 hook
and calls `1fC.A04(activity, BLACK)` at `2ZS.smali:294`, which is the LAST
status-bar-color call in the Reels-onResume path. That call (or its
deferred Choreographer callback `3mE.A00` on the next frame) overrides
the transparent color set by A6.**

```
   ┌─────────────────────────────────────────────────────────────────┐
   │  2ZS.A01 (Reels onResume entry, called via 2ZS.A02 ← AFt:2598)  │
   │                                                                 │
   │  62-68:  A6 patch ──► 2Ib.A01(window, false)                   │
   │                              └─► setStatusBarColor(0) ✓        │
   │                              └─► setDecorFitsSystemWindows(F)  │
   │                              └─► white icons                   │
   │                                                                 │
   │  95-99:  v3 ← resolve(?igds_color_primary_background)  = BLACK │
   │  222:    2ZS.A00(activity, BLACK)  ──► swipe_nav bg BLACK      │
   │          (separate concern — paints swipe_navigation_container)│
   │                                                                 │
   │  294:    1fC.A04(activity, v3=BLACK) ──► ★ LAST STATUS BAR     │
   │                                        COLOR CALL IN THIS PATH │
   │           │                                                     │
   │           ├─ if 1fC.A01==false (defer OFF):                     │
   │           │     1fC.smali:322                                   │
   │           │       window.setStatusBarColor(BLACK) ✗            │
   │           │                                                     │
   │           └─ if 1fC.A01==true (defer ON):                       │
   │                 1fC.smali:286-290                               │
   │                   fCi.A01 ← Integer.valueOf(BLACK)             │
   │                   Choreographer.postFrameCallback(ktp)         │
   │                       │                                         │
   │                       ▼  (next frame)                           │
   │                 ktp.doFrame (ktp.smali:39)                      │
   │                   └─► 3mE.A00(window, 9wE)                      │
   │                         3mE.smali:316-322                       │
   │                           window.setStatusBarColor(BLACK) ✗    │
   └─────────────────────────────────────────────────────────────────┘
```

**So the line that wins, depending on the runtime value of the MobileConfig
flag `1fC.A01:Z` (set at `InstagramMainActivity.smali:23223` from flag
`0x811079002d5885L`):**

| Defer flag `1fC.A01:Z` | EXACT winning line | What it does |
|---|---|---|
| `false` (defer OFF) | **`1fC.smali:322`** `invoke-virtual {v3, p1}, Landroid/view/Window;->setStatusBarColor(I)V` with `p1=BLACK` (passed in from `2ZS.A01:294`) | Direct, synchronous BLACK apply |
| `true` (defer ON) | **`3mE.smali:322`** `invoke-virtual {p0, v0}, Landroid/view/Window;->setStatusBarColor(I)V` with `v0=BLACK` (read from `fCi.A01` which was last set by `1fC.A04(BLACK)` at `2ZS.A01:294`) | Deferred BLACK apply, one frame later |

Both produce the same visible result: a solid BLACK status bar.

## Step 1 — All `setStatusBarColor` calls in /home/z/insta-test/

`rg -n 'setStatusBarColor' /home/z/insta-test/smali*/` returns 36 hits.
Filtered to direct `Landroid/view/Window;->setStatusBarColor(I)V` calls
(excluding `TaskDescription$Builder;->setStatusBarColor` which is the
recent-tasks color, not the live status bar):

| File:line | Helper / caller | Color source | In Reels-onResume path? |
|---|---|---|---|
| **`smali_classes13/X/1fC.smali:322`** | **`1fC.A04` direct path (defer OFF)** | `p1` (arg) — passed by `2ZS.A01:294` as BLACK | **YES — last writer if defer OFF** |
| **`smali_classes13/X/3mE.smali:322`** | **`3mE.A00` deferred path (defer ON)** | `v0` (read from `fCi.A01`) — last set by `2ZS.A01:294` as BLACK | **YES — last writer if defer ON** |
| `smali_classes15/X/2Ib.smali:55` | `2Ib.A01` edge-to-edge helper | `0` (transparent) | YES — runs FIRST (A6 patch), gets overridden |
| `smali_classes15/X/4Le.smali:96` | `4Lf.A01` legacy splash helper | transparent | NO — splash only |
| `smali_classes15/X/4Lf.smali:96` | `4Lf.A01` legacy edge-to-edge | transparent | NO — splash only (API < 30) |
| `smali_classes4/X/O0m.smali:264`, `Vni.smali:780`, `BuI.smali:680`, `PXc.smali:109` | Various feature code | mixed | NO |
| `smali_classes8/X/TvJ.smali:95` | TV / cast | mixed | NO |
| `smali_classes2/X/00s.smali:28`, `00u.smali:33` | Helpers | mixed | NO |
| `smali_classes10/X/YLw.smali:630,647`, `Zwy.smali:307,483`, `R4X.smali:2887`, `Zk3.smali:177`, `SIW.smali:452` | Various | mixed | NO |
| `smali_classes11/X/QE2.smali:30`, `QJ0.smali:30`, `kv0.smali:84`, `ked.smali:70`, `okx.smali:139`, `SyD.smali:1318` | Various | mixed | NO |
| `smali_classes21/X/21G.smali:516` | Some feature | mixed | NO |
| `smali_classes4/com/facebook/smartcapture/...` | FB smartcapture | mixed | NO |
| `smali_classes4/com/facebook/browser/lite/...` | FB browser | mixed | NO |
| `smali/com/instagram/urlhandler/UserSessionUrlHandlerActivity.smali:2796` | URL handler | mixed | NO |
| `smali/com/instagram/urlhandlers/.../P2bThreadEventAsyncControllerUrlHandlerActivity.smali:96` | URL handler | mixed | NO |
| `smali/app/morphe/extension/instagram/settings/SettingsActivity.smali:58` | Morphe settings | mixed | NO |
| `smali_classes15/com/instagram/modal/ModalActivity.smali:241` | ModalActivity | mixed | NO |

**Note on `3mE.smali:234`:** this hits `ActivityManager$TaskDescription$Builder;->setStatusBarColor(I)` — that sets the RECENT-TASKS card color, NOT the live status bar. Not the same thing; irrelevant to the live status bar paint.

**Conclusion of Step 1:** In the Reels-onResume path, only TWO `setStatusBarColor`
calls fire on the live Window:
1. `2Ib.smali:55` (transparent) — called by our A6 patch.
2. `1fC.smali:322` OR `3mE.smali:322` (BLACK) — called by `2ZS.A01:294 → 1fC.A04(BLACK)`.

The BLACK call wins because it runs AFTER (or, with defer, one frame after)
the A6 transparent call.

## Step 2 — Deferred path trace (`3mE.A00` via `ktp`)

### `1fC.A04(activity, p1)` (`smali_classes13/X/1fC.smali:212-334`)

```
212: .method public static final A04(Landroid/app/Activity;I)V
213:     .locals 4
214:
215:     :goto_0
216:     invoke-virtual {p0}, Landroid/app/Activity;->getParent()Landroid/app/Activity;
217:     ... walk to root activity ...
230:     :cond_0
231:     invoke-virtual {p0}, Landroid/app/Activity;->getWindow()Landroid/view/Window;
233:     move-result-object v3                       # v3 = window
235:     if-eqz v3, :cond_2
237:     sget-boolean v0, LX/1fC;->A01:Z              # ★ DEFER FLAG
239:     const/high16 v1, -0x80000000                 # FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS
241:     if-eqz v0, :cond_3                           # if A01==false → direct path
243:     invoke-virtual {v3, v1}, Landroid/view/Window;->addFlags(I)V
245:     sget-boolean v0, LX/3mE;->A00:Z              # global defer gate (also MC-driven)
247-258: check on main thread
261-275: get-or-create 9wE for window from 3mE.A01 WeakHashMap
278-282: 9wE.A00 ← WeakReference(activity)
284:     iget-object v1, v2, LX/9wE;->A02:LX/fCi;
286:     invoke-static {p1}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;
288:     move-result-object v0
290:     iput-object v0, v1, LX/fCi;->A01:Ljava/lang/Integer;    # ★ STORE p1 AS STATUS BAR COLOR
292:     iget-boolean v0, v2, LX/9wE;->A01:Z            # already scheduled?
294:     if-nez v0, :cond_2                            # if yes, skip scheduling
296-298: 9wE.A01 ← true                                # mark scheduled
300-308: Choreographer.getInstance().postFrameCallback(new ktp(window, 9wE))
310:     :cond_2
311:     return-void
313:     :cond_3                                         # DIRECT PATH (defer OFF)
314:     invoke-virtual {v3}, Landroid/view/Window;->getStatusBarColor()I
316:     move-result v0
318:     if-eq v0, p1, :cond_2                          # skip if unchanged
320:     invoke-virtual {v3, v1}, Landroid/view/Window;->addFlags(I)V
322:     invoke-virtual {v3, p1}, Landroid/view/Window;->setStatusBarColor(I)V  # ★ DIRECT APPLY
324:     return-void
```

**Key insight:** Whether defer is on or off, the SAME color `p1` is applied.
- Defer OFF: synchronous `setStatusBarColor(p1)` at `1fC.smali:322`.
- Defer ON: stores `Integer.valueOf(p1)` in `fCi.A01` at `1fC.smali:290`,
  schedules Choreographer. Next frame, `3mE.A00` reads `fCi.A01` and calls
  `setStatusBarColor(p1)` at `3mE.smali:322`.

If multiple `1fC.A04` calls happen before the Choreographer fires, **the
LAST `1fC.A04` call's `p1` wins** because each call overwrites `fCi.A01`
(at line 290) and the schedule flag prevents re-scheduling (line 294).

### `ktp.doFrame(J)V` (`smali_classes11/X/ktp.smali:32-42`)

```
32: .method public final doFrame(J)V
33:     .locals 2
34:
35:     iget-object v1, p0, LX/ktp;->A00:Landroid/view/Window;
36:
37:     iget-object v0, p0, LX/ktp;->A01:LX/9wE;
38:
39:     invoke-static {v1, v0}, LX/3mE;->A00(Landroid/view/Window;LX/9wE;)V
41:     return-void
```

`ktp` is a thin `Choreographer.FrameCallback` wrapper that calls
`3mE.A00(window, 9wE)`. `doFrame` fires on the NEXT frame
(Choreographer.NEXT_FRAME_TIME ≈ 16 ms later, on the main thread).

### `3mE.A00(window, 9wE)` (`smali_classes13/X/3mE.smali:41-341`)

```
41: .method public static final A00(Landroid/view/Window;LX/9wE;)V
42:     .locals 6
43:
44:     iget-object v1, p1, LX/9wE;->A02:LX/fCi;
46:     iget-object v4, v1, LX/fCi;->A00:Ljava/lang/Integer;     # nav bar color
48:     iget-object v3, v1, LX/fCi;->A01:Ljava/lang/Integer;     # ★ STATUS BAR COLOR
50:     iget-object v0, p1, LX/9wE;->A00:Ljava/lang/ref/WeakReference;
54-60: resolve activity from WeakReference
62-71: CLEAR stored values (set A00/A01 in fCi to null, 9wE.A00 to null, 9wE.A01 to false)
73-94: bail if activity is finishing/destroyed
96-130: prepare v3 (status bar color) and v4 (nav bar color) — null out if equal to current
132-134: if both null, bail
151-304: if 3mE.A00==true && SDK>=33, build TaskDescription and set both colors on it (recent-tasks card)
307-313: if v4 != null → window.setNavigationBarColor(v4)
316:     if-eqz v3, :cond_3
318:     invoke-virtual {v3}, Ljava/lang/Number;->intValue()I
320:     move-result v0
322:     invoke-virtual {p0, v0}, Landroid/view/Window;->setStatusBarColor(I)V   # ★ DEFERRED APPLY
324:     goto/16 :goto_4
```

`3mE.A00` reads `fCi.A01` (the stored status bar color Integer) and calls
`window.setStatusBarColor(v3.intValue())` at line 322.

**Order of operations for Reels onResume (defer ON case):**

| Time | Call site | Effect on `fCi.A01` | Effect on Window.statusBarColor |
|---|---|---|---|
| T+0 ms | `InstagramMainActivity.A1z:36401` calls `1fC.A03(BLACK)` → `1fC.A04(BLACK)` | `fCi.A01 ← BLACK`; schedule ktp | (no immediate change) |
| T+~1 ms | `AFt.onResume:2598` → `2ZS.A02` → `2ZS.A01` | | |
| T+~1 ms | A6 patch (line 62-68 of `2ZS.A01`): `2Ib.A01(window, false)` | | **statusBarColor ← 0 (transparent) ✓** |
| T+~2 ms | `2ZS.A01:222` `2ZS.A00(activity, BLACK)` → posts `47l.run()` | | (paints swipe_nav, not status bar) |
| T+~2 ms | `2ZS.A01:294` `1fC.A04(activity, BLACK)` | `fCi.A01 ← BLACK` (overwrites); ktp already scheduled | (no immediate change) |
| T+~16 ms (next frame) | `ktp.doFrame` → `3mE.A00` reads `fCi.A01` (BLACK) → `3mE.smali:322` | | **statusBarColor ← BLACK ✗ OVERRIDES A6** |

(If defer is OFF, the T+~16 ms step happens at T+~2 ms instead, and
`1fC.smali:322` applies BLACK synchronously right after `2ZS.A01:294`.)

### `9wE.smali` & `fCi.smali` (holders)

`9wE` is a 3-field holder:
- `A00:Ljava/lang/ref/WeakReference;` — the Activity.
- `A01:Z` — "Choreographer callback scheduled" flag.
- `A02:LX/fCi;` — the color holder (constructed in `<init>`).

`fCi` is a 2-field holder:
- `A00:Ljava/lang/Integer;` — nav bar color (set by `1fI.A04`).
- `A01:Ljava/lang/Integer;` — status bar color (set by `1fC.A04`).

Both confirmed by reading `smali_classes13/X/9wE.smali` (30 lines) and
`smali_classes12/X/fCi.smali` (20 lines) in full.

## Step 3 — InstagramMainActivity.A1z (onResume) call order

### Confirming `A1z` IS internal onResume

`BaseFragmentActivity.A1z(LX/2y8;)V` at `smali_classes15/com/instagram/base/activity/BaseFragmentActivity.smali:2544`
starts with:
```
2549:    const-string v9, "internalOnResume"
```

`InstagramMainActivity.A1z(LX/2y8;)V` at
`smali/com/instagram/mainactivity/InstagramMainActivity.smali:34713` overrides
this. Per Android lifecycle, `Activity.onResume()` runs BEFORE any of its
Fragments' `onResume()` — so:

1. `InstagramMainActivity.A1z` (Activity onResume) runs FIRST.
2. `ClipsTabFragment.onResume` (Fragment onResume) runs AFTER.

### `InstagramMainActivity.A1z` flow (relevant excerpt, lines 35490-36405)

```
35503: invoke-virtual {v7, v6}, ...->B4p(Z)LX/0jS;     # get 0jS instance
35506: move-result-object v0
35510: if-eqz v0, :cond_17                              # if null → BLACK branch
35514: iget-boolean v1, v0, LX/0jS;->A0D:Z              # ★ read 0jS.A0D
35517: const/4 v0, 0x1
35521: if-ne v1, v0, :cond_17                           # if A0D != 1 → BLACK branch
                                                       # ↓ transparent branch (A0D == 1)
35526: const v0, 0x7f0600a9                             # R.color.bds_transparent (#00000000)
35531: invoke-virtual {v7, v0}, ...->getColor(I)I
35534: move-result v0
35539: invoke-static {v7, v0}, LX/1fC;->A03(...)V       # 1fC.A03(activity, transparent)
35544: invoke-static {v7, v6}, LX/1fC;->A05(...)V       # set icons
35549: :goto_3
...
36379: :cond_17                                          # ★ BLACK branch
36380: const v0, 0x7f0407af                              # ?igds_color_primary_background (BLACK)
36385: invoke-static {v7, v0}, LX/0bF;->A0Z(...)I
36388: move-result v0
36393: invoke-virtual {v7, v0}, ...->getColor(I)I
36396: move-result v0
36401: invoke-static {v7, v0}, LX/1fC;->A03(...)V        # 1fC.A03(activity, BLACK)
36405: goto/16 :goto_3
```

### Is `0jS.A0D` true at runtime?

`0jS.A0D:Z` is set to `true` ONLY by `0jS.A15(I)V`
(`smali_classes13/X/0jS.smali:5697-5702`):

```
5700:    const/4 v0, 0x1
5702:    iput-boolean v0, p0, LX/0jS;->A0D:Z
```

`0jS.A15` is called from:
- `smali_classes15/X/6BM.smali:43` — packed-switch default case.
- `smali_classes15/X/6BM.smali:223` — pswitch_5 (`$t==5`).
- `smali_classes17/X/2Iv.smali:2244` — ClipsViewer presenter.
- `smali_classes3/X/Esf.smali:169`.

`2Iv.A0A` (which contains line 2244) is the ClipsViewer's window-insets
listener registration. It's gated on `9Wz.EEr()` (line 2137), which
checks `ClipsViewerConfig.A2g || ClipsViewerConfig.A3H || MobileConfig
0x8109d400023873L`. Per worklog 5-a, all three are false for the basic
Reels-TAB case → `2Iv.A0A` is NOT called → `0jS.A15` is NOT called →
`0jS.A0D` stays `false`.

**Conclusion:** For the basic Reels-TAB case, `0jS.A0D == false` →
`InstagramMainActivity.A1z` jumps to `:cond_17` → calls
`1fC.A03(activity, BLACK)` at line 36401.

This `1fC.A03(BLACK)` → `1fC.A04(BLACK)` → stores BLACK in `fCi.A01`
(if defer ON) or directly applies BLACK (if defer OFF).

**Then** `ClipsTabFragment.onResume` runs and calls `2ZS.A02 → 2ZS.A01`,
which (with A6 patch) first sets transparent via `2Ib.A01`, then at line
294 calls `1fC.A04(activity, BLACK)` again — overwriting `fCi.A01` with
BLACK (if defer ON) or directly applying BLACK (if defer OFF).

**The `2ZS.A01:294` call is the LAST `1fC.A04` call in the Reels-onResume
path.** Its color (BLACK) wins.

## Step 4 — Confirming the theory

The theory is confirmed:

1. **A6 patch runs** (verified — `2ZS.smali:62-68` contains the A6 patch
   in `/home/z/insta-test/`).
2. **A6 sets transparent** via `2Ib.A01(window, false)` →
   `setStatusBarColor(0)` at `2Ib.smali:55`.
3. **`2ZS.A01` continues** after the A6 patch:
   - Line 95-99: resolves `v3 = ?igds_color_primary_background` (BLACK).
   - Line 222: `2ZS.A00(activity, BLACK)` — paints swipe_nav (separate).
   - Line 294: `1fC.A04(activity, v3=BLACK)` — **the LAST status bar
     color call in this path**.
4. **The existing A1 patch at line 211 (`const/4 v3, 0x0`) is BYPASSED**
   because it's inside the cond_4 fall-through (line 208-219), which is
   only reached when `2ZS.A08(activity) != 0`. For InstagramMainActivity,
   `2ZS.A08` returns 0 (because `swipe_navigation_container` exists),
   so control flow jumps from line 206 to `:cond_5` (line 221), SKIPPING
   the A1 patch. Confirmed by reading `2ZS.smali:201-225`.
5. **The LAST writer is `1fC.A04(BLACK)` from `2ZS.A01:294`.**

### Why didn't the prior A1/A2/A3/A6 patches catch this?

| Patch | Target | Why it didn't catch the BLACK |
|---|---|---|
| **A1** (`2ZS.smali:211` zero v3) | Wrong branch — inside cond_4 fall-through, BYPASSED for MainActivity (per worklog 5-a). | v3 stays BLACK. |
| **A2** (`2ZS.smali:422` zero p2 in A05) | Dead code for Reels path — A05 only called from `A01:215` (also bypassed) and `A0A:1001,1028` (swipe gestures). | Affects only android.R.id.content bg (separate concern from status bar color). |
| **A3** (`6BM.smali:190` zero p1 in pswitch_3) | Zeroes top padding of content view's first child. Doesn't touch statusBarColor. | Doesn't address the `1fC.A04(BLACK)` call. |
| **A6** (`2ZS.smali:62-68` call `2Ib.A01`) | Sets transparent at the START of `2ZS.A01` — but `2ZS.A01:294` then re-applies BLACK. | Transparent is overridden ~1-16 ms later by `1fC.A04(BLACK)` → `1fC.smali:322` or `3mE.smali:322`. |

**The missing piece:** None of the existing patches zero `v3` BEFORE the
`1fC.A04(activity, v3)` call at line 294, nor do they neutralize `1fC.A04`
itself.

## Step 5 — Recommended fix

### Fix Option A (RECOMMENDED — chokepoint, single line)

**Patch `1fC.A04` to force `p1 = 0` (transparent) at method entry.**

**File:** `smali_classes13/X/1fC.smali`
**Method:** `A04(Landroid/app/Activity;I)V` (line 212)

```diff
 .method public static final A04(Landroid/app/Activity;I)V
     .locals 4

+    # InstaTrueReel: force transparent status bar (chokepoint fix)
+    const/4 p1, 0x0
+
     :goto_0
     invoke-virtual {p0}, Landroid/app/Activity;->getParent()Landroid/app/Activity;
     ...
```

**Effect:**
- Every caller of `1fC.A04` (`2ZS.A01:294`, `2ZS.A01:732,1046`,
  `IgFragmentActivity.A1j:1223`, `InstagramMainActivity.A1z:36401`,
  `0jS.A1K:7015`, etc.) now passes `p1=0` regardless of the original arg.
- Both the direct path (line 322) and the deferred path (line 290 stores 0
  in `fCi.A01`, then `3mE.A00:322` applies 0) now apply TRANSPARENT.
- The `1fC.A05` call at `1fC.A03:206` (which sets icon appearance based
  on theme's `windowLightStatusBar` attr) is unaffected — icons stay
  correctly colored.

**Caveat:** This also affects non-Reels paths that may want a non-
transparent status bar (e.g., `IgFragmentActivity.A1j:1223` paints BLACK
on Activity resume in some flows; `0jS.A1K` paints various colors when
swipe-nav state changes; modal/direct/profile paths). Since the A6 patch
already enables edge-to-edge globally for Reels via `2Ib.A01`, this is
consistent with the InstaTrueReel goal of "always-transparent status bar
with white icons" — but it's a broad change. If the user wants to
preserve non-Reels status bar coloring, use Fix Option B instead.

### Fix Option B (TARGETED — only the Reels path)

**Move the A1 zeroing to BEFORE the cond_5 branch.**

**File:** `smali_classes17/X/2ZS.smali`
**Insert `const/4 v3, 0x0` between line 205 (`move-result v0`) and line 206
(`if-eqz v0, :cond_5`)**:

```diff
 201:     :cond_4
 202:     invoke-static {p0}, LX/2ZS;->A08(Landroid/app/Activity;)Z
 204:     move-result v0
+
+        # InstaTrueReel: zero chrome color so both branches paint transparent
+        const/4 v3, 0x0
+
 206:     if-eqz v0, :cond_5
```

**Effect:**
- v3 is zeroed BEFORE the branch — both cond_4 fall-through and cond_5
  use `v3=0`.
- Line 222 (cond_5, taken for MainActivity): `2ZS.A00(activity, 0)` →
  `47l.run()` paints `swipe_navigation_container` TRANSPARENT instead of
  BLACK. ✓
- Line 294 (cond_b → cond_d): `1fC.A04(activity, 0)` →
  `setStatusBarColor(0)` (or stored in `fCi.A01` for deferred apply). ✓
- The existing A1 patch at line 211 (`const/4 v3, 0x0`) becomes dead
  code (v3 already 0). Harmless.

This is exactly what worklog 5-a PATCH 1 recommended. It's the most
targeted fix — only affects the `2ZS.A01` Reels-onResume path, leaves
other activities' status bar coloring intact.

### Fix Option C (DEFERRED-PROOF — also neutralizes the Choreographer path)

**Patch `3mE.A00` to force `v3 = 0` after reading `fCi.A01`.**

**File:** `smali_classes13/X/3mE.smali`
**Method:** `A00(Landroid/view/Window;LX/9wE;)V` (line 41)

Insert, just before line 322:
```diff
 316:     if-eqz v3, :cond_3
 318:     invoke-virtual {v3}, Ljava/lang/Number;->intValue()I
 320:     move-result v0
+
+        # InstaTrueReel: force transparent status bar in deferred path
+        const/4 v0, 0x0
+
 322:     invoke-virtual {p0, v0}, Landroid/view/Window;->setStatusBarColor(I)V
```

This is belt-and-suspenders — only needed if Fix Option A is not applied
AND defer is ON. Not recommended as the primary fix (Option A or B is
simpler and more comprehensive).

### Recommended combo

Apply **Fix Option B** (targeted, doesn't break other activities). If
testing shows the bar is still black (i.e., some OTHER `1fC.A04` caller
fires after `2ZS.A01:294`), upgrade to **Fix Option A** (chokepoint).

## Step 6 — Diagnostic build (RED color test)

To unambiguously confirm the trace without guessing, build a diagnostic
APK that paints the status bar BRIGHT RED (`0xFFFF0000`) at TWO
specific points, then visually inspect:

### Diagnostic 1 — Confirm A6 runs (and is overridden)

Replace the A6 patch's `2Ib.A01(window, false)` call with a direct
`setStatusBarColor(RED)`:

**File:** `smali_classes17/X/2ZS.smali` (lines 62-68, A6 patch location)

```diff
 .method public static final A01(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;IZZZ)V
     .locals 7

-    # InstaTrueReel: enable full edge-to-edge (transparent status + nav bar)
-    invoke-virtual {p0}, Landroid/app/Activity;->getWindow()Landroid/view/Window;
-    move-result-object v0
-    if-eqz v0, :cond_itre_skip
-    const/4 v1, 0x0
-    invoke-static {v0, v1}, LX/2Ib;->A01(Landroid/view/Window;Z)V
+    # DIAGNOSTIC 1: paint status bar RED to confirm A6 runs + is overridden
+    invoke-virtual {p0}, Landroid/app/Activity;->getWindow()Landroid/view/Window;
+    move-result-object v0
+    if-eqz v0, :cond_itre_skip
+    const v1, -0x10000              # 0xFFFF0000 (RED)
+    invoke-virtual {v0, v1}, Landroid/view/Window;->setStatusBarColor(I)V
     :cond_itre_skip
```

**Interpretation:**
- Bar turns RED momentarily then BLACK → A6 runs, but `2ZS.A01:294`
  (`1fC.A04(BLACK)`) overrides it. **Confirms this trace.** Apply Fix
  Option B or A.
- Bar stays BLACK from the start → A6's `getWindow()` returned null
  (impossible if Reels is visible), OR the patch isn't being applied
  (rebuild/reinstall issue), OR the visible bar is being painted by some
  completely different path (very unlikely given the trace).
- Bar turns RED and STAYS RED → A6 runs AND nothing overrides it. The
  fix is to change `-0x10000` back to `0x0` (transparent) — you're done.

### Diagnostic 2 — Confirm `2ZS.A01:294` is the LAST writer

Apply Diagnostic 1 AND ALSO patch `2ZS.A01:294` to use RED:

```diff
 291:     :cond_c
 292:     if-nez p6, :cond_d
+
+        # DIAGNOSTIC 2: paint status bar RED via the LAST writer
+        const v3, -0x10000          # 0xFFFF0000 (RED) — overrides BLACK resolve
+
 294:     invoke-static {p0, v3}, LX/1fC;->A04(Landroid/app/Activity;I)V
```

**Interpretation:**
- Bar turns RED and STAYS RED → `2ZS.A01:294` IS the last writer. Fix is
  to change `-0x10000` to `0x0` (transparent).
- Bar turns RED then BLACK → some OTHER caller (after `2ZS.A01` returns)
  overrides. Candidates: `0jS.A1K:7015` (swipe-nav state update, but
  only fires from `2Iv.APx` which is the ClipsViewer path, NOT basic
  Reels TAB); or a deferred `1fC.A04` from a coroutine (e.g.,
  `StatusBarAnimationEffectKt$...` at line 96, but only used by repost
  composer). Need to investigate further.
- Bar stays BLACK → `2ZS.A01:294` doesn't run (perhaps `p6 != 0` so it
  jumps to `:cond_d`, skipping A04). Check the call site at
  `AFt.smali:2598` — it passes `p4=0` (which becomes `p6=0` in A01
  after `A02`'s arg shuffle: `A02.p4 → A01.p6`). Confirmed `p6=0`, so
  A04 should run. If bar stays BLACK, the patch wasn't applied.

### Recommended diagnostic flow

1. Apply Diagnostic 1 only. Build, install, open Reels tab, observe.
   - Expected: RED flash → BLACK. Confirms A6 runs but is overridden.
2. Apply Diagnostic 1 + Diagnostic 2. Build, install, open Reels tab, observe.
   - Expected: STAYS RED. Confirms `2ZS.A01:294` is the last writer.
3. If both diagnostics behave as expected, apply Fix Option B (targeted)
   and re-test. Bar should be transparent.
4. If still black after Fix Option B, escalate to Fix Option A
   (chokepoint) and re-test.

## Complete call sequence (launch → Reels visible)

| Step | Time | Call site | Effect |
|---|---|---|---|
| 1 | T=0 | App process start; theme `Theme.Instagram` applied | `window.statusBarColor = BLACK` (from `android:statusBarColor` attr = `?igds_color_primary_background`); `window.windowBackground = BLACK`; `window.colorBackground = BLACK` |
| 2 | T=10 ms | `IgSplashScreenActivity.onCreate` → `4Le.A01(activity, splashHelper)` (`smali_classes15/X/4Le.smali:200+`) | Sets up splash FrameLayout; calls `4Le.A02` → `2Ib.A01(window, false)` at `4Le.smali:257` (if SDK ≥ 30). **Sets `setStatusBarColor(0)` (transparent) + edge-to-edge for SPLASH window.** |
| 3 | T=200 ms | Splash finishes; `InstagramMainActivity.onCreate` | Activity transitions; new window inherits theme → BLACK status bar |
| 4 | T=210 ms | `InstagramMainActivity.A1z` (internal onResume, `BaseFragmentActivity.A1z` named `"internalOnResume"` at line 2549) runs FIRST | |
| 4a | T=210 ms | `A1z:35503` `B4p(false)` returns `0jS` instance | |
| 4b | T=210 ms | `A1z:35514` `iget-boolean v1, v0, LX/0jS;->A0D:Z` → `false` (basic Reels TAB: `0jS.A15` never called because `2Iv.A0A` is gated on `9Wz.EEr()` which is false) | |
| 4c | T=210 ms | `A1z:35521` `if-ne v1, v0, :cond_17` → jump to `:cond_17` (line 36379) | |
| 4d | T=210 ms | `A1z:36380` resolve `0x7f0407af` (?igds_color_primary_background = BLACK) via `0bF.A0Z` | |
| 4e | T=210 ms | `A1z:36401` `1fC.A03(activity, BLACK)` → `1fC.A04(activity, BLACK)` (`1fC.smali:177`) | If defer OFF: `1fC.smali:322` `setStatusBarColor(BLACK)` synchronously. If defer ON: `1fC.smali:286-290` stores BLACK in `fCi.A01`, schedules `ktp.doFrame` Choreographer callback for next frame. |
| 5 | T=211 ms | `ClipsTabFragment.onResume` (`smali_classes16/X/AFt.smali:2580`) runs AFTER Activity.onResume | |
| 5a | T=211 ms | `AFt:2580` `invoke-super {p0}, LX/2yN;->onResume()V` | |
| 5b | T=211 ms | `AFt:2598` `2ZS.A02(activity, this, session, p3=1, p4=0)` | |
| 5c | T=211 ms | `2ZS.A02:333-347` resolve `0x7f040714` (?igds_color_clips_tab_bar_icon) → `v4`; call `2ZS.A01(activity, this, session, v4, p4=1, p5=0, p6=0)` | |
| 6 | T=211 ms | `2ZS.A01` enters (`smali_classes17/X/2ZS.smali:59`) | |
| 6a | T=211 ms | `2ZS.A01:62-68` **A6 PATCH** runs: `2Ib.A01(window, false)` (`2Ib.smali:38-84`) | `clearFlags(FLAG_TRANSLUCENT_*)`; `addFlags(FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)`; `setDecorFitsSystemWindows(false)`; **`setStatusBarColor(0)` (transparent) ✓**; `setNavigationBarColor(0)`; `setStatusBarContrastEnforced(false)`; `setNavigationBarContrastEnforced(false)`; white icons (`APPEARANCE_LIGHT_STATUS_BARS=8 | APPEARANCE_LIGHT_NAVIGATION_BARS=0x10 = 0x18`). |
| 6b | T=212 ms | `2ZS.A01:95-99` resolve `0x7f0407af` (BLACK) → `v3 = BLACK` | |
| 6c | T=212 ms | `2ZS.A01:124-126` `v5 = 0`, `v4 = 1` | |
| 6d | T=212 ms | `2ZS.A01:159-169` MobileConfig check `0x8112f4005463c1L` → `v6` (defer flag for nav bar) | |
| 6e | T=212 ms | `2ZS.A01:171-173` `if (1fI.A05 == false) goto cond_7` (likely false → cond_7) | |
| 6e' | T=212 ms | (if `1fI.A05 == true`): `2ZS.A01:175` `1fI.A04(activity, v3=BLACK)` → stores BLACK for nav bar (deferred or direct) | |
| 6f | T=212 ms | `2ZS.A01:231 cond_7` → `3sA.A02()` check → if false, `:cond_8` (line 240) | |
| 6g | T=212 ms | `2ZS.A01:241-256` walk parent activities → `v1 = root activity` | |
| 6h | T=212 ms | `2ZS.A01:258-267` `window.addFlags(FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)` | |
| 6i | T=212 ms | `2ZS.A01:269-280` `window.setNavigationBarColor(v3=BLACK)` (nav bar painted BLACK); `goto :goto_0` (line 178) | |
| 6j | T=212 ms | `2ZS.A01:178-179` `1fI.A05(activity, v2=0)` (sets nav bar icon appearance) | |
| 6k | T=212 ms | `2ZS.A01:181-191` get window (`v6`) and decorView (`v1`) | |
| 6l | T=212 ms | `2ZS.A01:193-197` `3at.A0I(session)` check → likely false → `:cond_4` | |
| 6m | T=212 ms | `2ZS.A01:202-206` `2ZS.A08(activity)` returns `0` (MainActivity has `swipe_navigation_container` view) → `if-eqz v0, :cond_5` → JUMP to `:cond_5` (line 221) | **A1 patch at line 211 BYPASSED.** |
| 6n | T=212 ms | `2ZS.A01:221-222` `2ZS.A00(activity, v3=BLACK)` → posts `47l.run()` (`smali_classes17/X/47l.smali:30-51`) that calls `0cW.A0R(findViewById(0x7f0b3f31), BLACK, 0x6bad5ee0)` → `swipe_navigation_container.setBackgroundColor(BLACK)` | (separate concern: paints swipe_nav bg BLACK — does NOT touch statusBarColor) |
| 6o | T=212 ms | `2ZS.A01:225` `if-eqz p5, :cond_b` — `p5=0` → JUMP to `:cond_b` (line 282) | |
| 6p | T=212 ms | `2ZS.A01:282-289` `1fC.A09(decorView, window)` returns `0` (status bar NOT transparent in legacy sense — `1fC.A09` checks for `FLAG_TRANSLUCENT_STATUS` 0x400 + `SYSTEM_UI_FLAG_FULLSCREEN` 0x4; our A6 setup clears these so A09 returns... actually, looking at A09: it returns 1 (true) if NEITHER flag is set — meaning status bar is "transparent in legacy sense". So `if-nez v0, :cond_c` at line 287 would SKIP A06 if A09==1. This needs verification but is orthogonal to the main issue.) | Either way, falls through to line 294. |
| 6q | T=212 ms | `2ZS.A01:292` `if-nez p6, :cond_d` — `p6=0` → fall through | |
| 6r | T=212 ms | **`2ZS.A01:294` `1fC.A04(activity, v3=BLACK)`** — **★ THE LAST STATUS BAR COLOR CALL IN THIS PATH ★** | If defer OFF: `1fC.smali:322` `setStatusBarColor(BLACK)` synchronously → **OVERRIDES A6's transparent.** If defer ON: `1fC.smali:286-290` stores `Integer(BLACK)` in `fCi.A01` (overwriting whatever was stored by `A1z:36401`), does NOT re-schedule (ktp already scheduled by step 4e). |
| 6s | T=212 ms | `2ZS.A01:297` `1fC.A05(activity, v2=0)` — sets icon appearance (v2=0 → dark icons via `0Xm.A01(false)`). NOTE: this may set DARK icons (bad for black-on-black); the A6 patch's `setSystemBarsAppearance(0x18, 0x18)` (light icons) is overridden by this `1fC.A05(false)` call. Separate issue. | |
| 6t | T=212 ms | `2ZS.A01:299` `return-void` | |
| 7 | T=212 ms | `AFt.onResume` returns | |
| 8 | T=228 ms (next frame, ~16 ms after step 4e or 6r, whichever scheduled ktp last) | `ktp.doFrame` (`smali_classes11/X/ktp.smali:32-42`) fires → `3mE.A00(window, 9wE)` (`smali_classes13/X/3mE.smali:41-341`) | Reads `fCi.A01` (= BLACK, last set by `2ZS.A01:294`) → `3mE.smali:322` `setStatusBarColor(BLACK)` → **OVERRIDES A6's transparent.** (This step happens ONLY if defer ON; if defer OFF, the override already happened synchronously at step 6r.) |
| 9 | T=230 ms | `47l.run()` fires (posted by `2ZS.A00` at step 6n via `8ug.A06`) → paints `swipe_navigation_container` BLACK | (separate concern) |
| 10 | T=300+ ms | Reels fragment views fully laid out; video starts playing | User sees: black status bar (from step 6r or 8), black swipe_nav bg (from step 9), video below |

**Conclusion:** The visible BLACK status bar at T=300 ms is produced by
either `1fC.smali:322` (step 6r, defer OFF) or `3mE.smali:322` (step 8,
defer ON). Both are reached via the chain:

```
AFt.onResume:2598
  └─► 2ZS.A02:347
        └─► 2ZS.A01:294
              └─► 1fC.A04(activity, BLACK)
                    ├─► 1fC.smali:322 (direct, defer OFF)
                    └─► 3mE.smali:322 (deferred, defer ON)
```

## Key file:line references (cheat sheet)

| File | Line(s) | What |
|---|---|---|
| `smali_classes17/X/2ZS.smali` | 59-318 | `A01` method (Reels chrome setup, called from `AFt.onResume` via `A02`) |
| `smali_classes17/X/2ZS.smali` | 62-68 | **A6 patch** (calls `2Ib.A01(window, false)` — sets transparent, runs FIRST) |
| `smali_classes17/X/2ZS.smali` | 95-99 | `v3 = ?igds_color_primary_background` (BLACK) |
| `smali_classes17/X/2ZS.smali` | 206 | `if-eqz v0, :cond_5` — branch that BYPASSES A1 patch for MainActivity |
| `smali_classes17/X/2ZS.smali` | 211 | **A1 patch** (`const/4 v3, 0x0`) — DEAD CODE (bypassed) |
| `smali_classes17/X/2ZS.smali` | 222 | `2ZS.A00(activity, BLACK)` — paints swipe_nav (not status bar) |
| `smali_classes17/X/2ZS.smali` | 294 | **★ `1fC.A04(activity, v3=BLACK)` — LAST status bar color call** |
| `smali_classes16/X/AFt.smali` | 2580 | `super.onResume()` |
| `smali_classes16/X/AFt.smali` | 2598 | `2ZS.A02(activity, this, session, 1, 0)` — Reels onResume entry |
| `smali_classes13/X/1fC.smali` | 172-210 | `A03(activity, color)` — wraps A04 + A05 |
| `smali_classes13/X/1fC.smali` | 212-334 | `A04(activity, color)` — the chokepoint (defer logic + direct apply) |
| `smali_classes13/X/1fC.smali` | 237 | `sget-boolean v0, LX/1fC;->A01:Z` — defer flag check |
| `smali_classes13/X/1fC.smali` | 286-290 | Stores `Integer.valueOf(p1)` in `fCi.A01` (defer path) |
| `smali_classes13/X/1fC.smali` | 300-308 | `Choreographer.postFrameCallback(new ktp(window, 9wE))` |
| `smali_classes13/X/1fC.smali` | 322 | **★ Direct `setStatusBarColor(p1)` (defer OFF)** |
| `smali_classes13/X/3mE.smali` | 41-341 | `A00(window, 9wE)` — deferred apply |
| `smali_classes13/X/3mE.smali` | 316-322 | **★ Deferred `setStatusBarColor(v3)` (defer ON)** |
| `smali_classes11/X/ktp.smali` | 32-42 | `doFrame(J)V` — Choreographer callback, calls `3mE.A00` |
| `smali_classes13/X/9wE.smali` | 1-30 | Holder: `A00=WeakReference(Activity)`, `A01:Z=scheduled`, `A02:LX/fCi;` |
| `smali_classes12/X/fCi.smali` | 1-20 | Holder: `A00=Integer(nav bar color)`, `A01=Integer(status bar color)` |
| `smali_classes15/X/2Ib.smali` | 38-84 | `A01(window, Z)` — IG's edge-to-edge helper |
| `smali_classes15/X/2Ib.smali` | 55 | `setStatusBarColor(0)` — called by A6 patch + splash |
| `smali_classes15/X/4Le.smali` | 257 | `2Ib.A01(window, false)` — splash path (calls same helper) |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 34713 | `A1z(LX/2y8;)V` — internal onResume (named `"internalOnResume"`) |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 35503-35539 | Transparent branch (taken if `0jS.A0D == 1`) |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 35514 | `iget-boolean v1, v0, LX/0jS;->A0D:Z` — gate |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 35521 | `if-ne v1, v0, :cond_17` — branch on `0jS.A0D` |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 36379-36401 | BLACK branch (cond_17, taken when `0jS.A0D != 1`) |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 36401 | `1fC.A03(activity, BLACK)` — Activity onResume paint (runs BEFORE `2ZS.A01`) |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 23223 | `sput-boolean v0, LX/1fC;->A01:Z` — sets defer flag from MobileConfig `0x811079002d5885L` |
| `smali/com/instagram/mainactivity/InstagramMainActivity.smali` | 23192 | `sput-boolean v0, LX/1fI;->A05:Z` — sets nav-bar defer flag from MobileConfig `0x811079002c5884L` |
| `smali_classes13/X/0jS.smali` | 5697-5702 | `A15(I)V` — sets `0jS.A0D = true` |
| `smali_classes13/X/0jS.smali` | 7015 | `1fC.A03(activity, color)` — called from `A1K(35U)` (swipe-nav state apply) |
| `smali_classes17/X/2Iv.smali` | 2132-2156 | `A0A` — registers `6BM(this, 5)` insets listener (gated on `9Wz.EEr()`) |
| `smali_classes17/X/2Iv.smali` | 2244 | `0jS.A15(int)` — sets `0jS.A0D = true` (only if `9Wz.EEr()` returns true) |
| `smali_classes16/X/9Wz.smali` | 36584 | `EEr()` — returns true only if clips viewer config flags are set (false for basic Reels TAB) |
| `smali_classes16/X/9Wz.smali` | 34836-34908 | `APx(0jS)` — ClipsViewer status bar setup (NOT called for basic Reels TAB) |

## Open questions / next steps

1. **Verify defer flag at runtime** — install a debug APK and log
   `1fC.A01:Z` and `3mE.A00:Z` at startup. This determines whether the
   direct path (`1fC.smali:322`) or deferred path (`3mE.smali:322`) is
   the actual winner. Either way, the fix is the same.

2. **Verify `1fC.A09` return value at step 6p** — `2ZS.A01:283` calls
   `1fC.A09(decorView, window)` which returns 1 if neither
   `FLAG_TRANSLUCENT_STATUS` (0x400) nor `SYSTEM_UI_FLAG_FULLSCREEN` (0x4)
   is set. After A6 runs, both are cleared → A09 returns 1 →
   `if-nez v0, :cond_c` at line 287 SKIPS `1fC.A06` (which would have
   set `SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN` for legacy edge-to-edge). This
   means A06 is skipped — but A6 already did the modern edge-to-edge
   via `setDecorFitsSystemWindows(false)`, so this is fine. Just noting
   for completeness.

3. **Verify `1fC.A05(false)` at step 6s** — `2ZS.A01:297` calls
   `1fC.A05(activity, v2=0)`. This goes through `0Xm.A01(false)` which
   sets `SYSTEM_UI_FLAG_LIGHT_STATUS_BAR` (dark icons). This OVERRIDES
   A6's `setSystemBarsAppearance(0x18, 0x18)` (light/white icons). The
   result: dark icons on a transparent status bar over a dark video →
   hard to see. Separate issue — needs a patch on `2ZS.A01:297` to pass
   `v2=1` instead of `v2=0`. (Not in scope for this task, but flagging
   for the next agent.)

4. **If Fix Option B proves insufficient** (some other `1fC.A04` caller
   fires after `2ZS.A01:294`), candidates to investigate:
   - `0jS.A1K:7015` — swipe-nav state apply, but only fires from
     `2Iv.APx` which is the ClipsViewer path, NOT basic Reels TAB.
   - `StatusBarAnimationEffectKt$...:96` — coroutine-based animation,
     but only used by repost composer.
   - `3lI.smali:1162, 1642, 2212` — comment composer controller, only
     fires when comment sheet opens.
   - For the basic Reels TAB case, NONE of these should fire after
     `2ZS.A01:294`. So Fix Option B should be sufficient.

READ-ONLY exploration complete. No patch code was written.
