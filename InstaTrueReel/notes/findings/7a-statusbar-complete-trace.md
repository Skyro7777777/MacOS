# Task 7-a: COMPLETE Status Bar Call Sequence Trace (Exhaustive)

**Agent:** Explore (sub-agent, READ-ONLY diagnostic)
**Date:** 2025-08-09
**Task ID:** 7-a
**Decoded source:** `/home/z/MacOS/insta-dec/` (freshly decoded, UNPATCHED — 0 `InstaTrueReel` markers)
**Patch source:** `/home/z/MacOS/InstaTrueReel/patches/apply_patches.py`
**Prior work:** Built on 6-a (status bar trace) and 7-b (patch validity). This task is the EXHAUSTIVE step-by-step runtime call-sequence trace.

---

## TL;DR — THE ROOT CAUSE (NEW FINDING)

**The status bar COLOR is NOT black.** With A5+A6 patches correctly applied, every `setStatusBarColor` call resolves to `setStatusBarColor(0)` (transparent). What LOOKS like a black status bar is actually the **`swipe_navigation_container` view (id `0x7f0b3f31`) painted BLACK by the `47l` Runnable**, which is posted by `2ZS.A00(activity, BLACK)` at `2ZS.smali:211`. Because `setSystemUiVisibility(0x500)` (= `LAYOUT_STABLE | LAYOUT_FULLSCREEN`) makes the content extend behind the status bar, the BLACK `swipe_navigation_container` background is visible THROUGH the transparent status bar.

**`47l.run()` is the LAST WRITER** for the visible "black bar" — and NO current patch (A1/A2/A3/A5/A6) catches it.

```
AFt.onResume:2598
  └─► 2ZS.A02:336
        └─► 2ZS.A01
              ├── (A6 patch)  setStatusBarColor(0) ✓ transparent
              ├── (A6 patch)  decorView.setBackgroundColor(0) ✓ transparent
              ├── (A6 patch)  decorView.setSystemUiVisibility(0x500) ✓ layout_fullscreen
              ├── 2ZS.A08(activity):Z  →  returns FALSE on Android 15+ (swipe_nav view found)
              │                    →  returns TRUE  on Android 10-14 (3sA.A02()=false)
              ├── [Android 10-14 only]
              │     ├── 0cW.A0R(decorView, BLACK, hash)    ← A1 PATCH CATCHES (zeroes v3)
              │     └── 2ZS.A05(activity, userSession, BLACK)
              │           └── 0cW.A0R(contentView, BLACK, hash)  ← A2 PATCH CATCHES (zeroes p2)
              ├── [Android 15+ only]
              │     └── 2ZS.A00(activity, BLACK)   ← ★ NOT CAUGHT BY ANY PATCH ★
              │           └── 8ug.A06(activity, new 47l(activity, BLACK))
              │                 └── 47l.run()    [runs sync OR deferred]
              │                       └── 0cW.A0R(swipe_navigation_container, BLACK, 0x6bad5ee0)
              │                             └── setBackgroundColor(BLACK)  ★ LAST WRITER ★
              ├── 1fC.A06(decorView, window, true)   ← sets LAYOUT_FULLSCREEN (re-applies)
              ├── 1fC.A04(activity, BLACK)   ← A5 PATCH CATCHES (zeroes p1) → setStatusBarColor(0) ✓
              └── 1fC.A05(activity, false)   ← sets DARK icons via 0Xm.A01(false)
```

**RECOMMENDED FIX:** Patch `47l.run()` (or `2ZS.A00`) to force the color to 0 (transparent). See §5.

---

## STEP 1: EXHAUSTIVE TABLE OF EVERY STATUS-BAR / WINDOW-BACKGROUND CALL

### 1a. Direct `Landroid/view/Window;->setStatusBarColor(I)V` calls (36 hits total)

Filtered to calls on the LIVE Window (excluding `TaskDescription$Builder->setStatusBarColor` which is recent-tasks card, and `BrowserLiteWrapperView->setStatusBarColor` which is in-app browser):

| # | File | Line | Method | Color arg | Phase | Notes |
|---|---|---|---|---|---|---|
| 1 | `2Ib.smali` | 55 | `2Ib.A01(Window, Z)` | `0x0` (transparent) | C (Reels via A6) | Our A6 patch hook calls this. Actually A6 INLINES the same calls; `2Ib.A01` itself is not invoked by current A6 patch. |
| 2 | `1fC.smali` | 322 | `1fC.A04(Activity, I)` | `p1` (caller-provided) | B+C+D+E | **CHOKEPOINT** — every `1fC.A03`/`A04` caller funnels here. **A5 PATCH FORCES `p1=0`** ✓ |
| 3 | `3mE.smali` | 322 | `3mE.A00(Window, 9wE)` | `v0 = fCi.A01.intValue()` | E (deferred) | Choreographer callback. Reads `fCi.A01` (last stored by `1fC.A04`). **A5 indirectly catches** (because A5 zeroes `p1` BEFORE it's stored in `fCi.A01`). |
| 4 | `O0m.smali` | 264 | (unclear) | `v1` | ? | Not in Reels path; likely ModalActivity or similar. |
| 5 | `Vni.smali` | 780 | ? | `v0` | ? | Not in Reels path. |
| 6 | `BuI.smali` | 680 | ? | `v1` | ? | Not in Reels path. |
| 7 | `PXc.smali` | 109 | ? | `v0` | ? | Not in Reels path. |
| 8 | `BaseSelfieCaptureActivity.smali` | 131 | ? | `v1` | A (smartcapture) | Smartcapture, not Instagram main. |
| 9 | `IdCaptureActivity.smali` | 1403 | ? | `v0` | A (smartcapture) | Same. |
| 10 | `SelfieCapturePermissionsActivity.smali` | 67 | ? | `v1` | A (smartcapture) | Same. |
| 11 | `UserSessionUrlHandlerActivity.smali` | 2796 | ? | `v8` | A (urlhandler) | URL handler, not Reels. |
| 12 | `P2bThreadEventAsyncControllerUrlHandlerActivity.smali` | 96 | ? | `v1` | A (urlhandler) | URL handler. |
| 13 | `TvJ.smali` | 95 | ? | `v2` | ? | Not in Reels path. |
| 14 | `4Lf.smali` | 96 | `4Lf.A0?(Window, Z)` | `v3` | ? | Not in Reels path. |
| 15 | `ModalActivity.smali` | 241 | ? | `v1` | A (modal) | ModalActivity, not Reels. |
| 16 | `00s.smali` | 28 | ? | `v0` | ? | Not in Reels path. |
| 17 | `00u.smali` | 33 | ? | `v0` | ? | Not in Reels path. |
| 18 | `SettingsActivity.smali` | 58 | ? | `v1` | A (morphe settings) | Morphe settings, not Reels. |
| 19 | `QE2.smali` | 30 | ? | `v0` | ? | Not in Reels path. |
| 20 | `SyD.smali` | 1318 | ? | `v1` | ? | Not in Reels path. |
| 21 | `kv0.smali` | 84 | ? | `v2` | ? | Not in Reels path. |
| 22 | `QJ0.smali` | 30 | ? | `v0` | ? | Not in Reels path. |
| 23 | `ked.smali` | 70 | ? | `v6` | ? | Not in Reels path. |
| 24 | `okx.smali` | 139 | ? | `v0` | ? | Not in Reels path. |
| 25 | `YLw.smali` | 630, 647 | ? | `v4`, `v10` | ? | Not in Reels path. |
| 26 | `SIW.smali` | 452 | ? | `v0` | ? | Not in Reels path. |
| 27 | `Zk3.smali` | 177 | ? | `v1` | ? | Not in Reels path. |
| 28 | `R4X.smali` | 2887 | ? | `v3` | ? | Not in Reels path. |
| 29 | `Zwy.smali` | 307, 483 | ? | `v0`, `v9` | ? | Not in Reels path. |
| 30 | `21G.smali` | 516 | ? | `v0` | ? | Not in Reels path. |

**Reels-relevant `setStatusBarColor` writers (only 3):**
- `2Ib.smali:55` — called by A6 patch hook (transparent)
- `1fC.smali:322` — sync path; A5 catches
- `3mE.smali:322` — deferred path; A5 indirectly catches

### 1b. `setSystemUiVisibility` calls on decorView (filtered to Reels-relevant)

| File | Line | Method | Flag | Phase | Notes |
|---|---|---|---|---|---|
| `2ZS.smali` | (none direct) | — | — | — | 2ZS delegates via `1fC.A06` |
| `1fC.smali` | 412 | `1fC.A06` (p2=true branch) | `or-int/lit16 v0, v0, 0x100` (LAYOUT_FULLSCREEN) | C | Sets LAYOUT_FULLSCREEN. Called from `2ZS.A01:278`. |
| `1fC.smali` | 424 | `1fC.A06` (p2=false branch) | `or-int/lit8 v0, v0, 0x4` (FLAG_FULLSCREEN) | — | Hides status bar entirely. NOT called from Reels path. |
| `InstagramMainActivity.smali` | 13087 | `A0h` (onCreate helper) | `0x700` (LAYOUT_STABLE \| LAYOUT_FULLSCREEN \| LAYOUT_HIDE_NAVIGATION) | B (onCreate) | Sets up edge-to-edge for whole activity. |
| `InstagramMainActivity.smali` | 17489 | `A0i` (onCreate helper) | `0x700` | B (onCreate) | Same. |
| `4Lf.smali` | 18, 31, 94, 117 | ? | varies | — | Not in Reels path. |
| `0Xk.smali`, `0Xh.smali`, `0Xg.smali` | various | ? | varies | — | AppCompat helpers, not Reels-specific. |
| Others (BVZ, PeR, keV, ijz, SJ6, ked, 0Xk, 0tY, 2hd, bBV, YIq, bmh, SIW, bWl, R9u, G3g) | various | ? | varies | — | Various components (keyboard, camera, etc.), NOT Reels path. |

**Reels-relevant `setSystemUiVisibility` writers:**
- `1fC.A06(true)` at `2ZS.A01:278` — sets LAYOUT_FULLSCREEN (this is what makes content extend behind status bar)
- `InstagramMainActivity.A0h:13087` and `A0i:17489` — initial setup during onCreate (also LAYOUT_FULLSCREEN + LAYOUT_HIDE_NAVIGATION)
- A6 patch — explicitly sets `0x500` on decorView at start of `2ZS.A01`

### 1c. `setDecorFitsSystemWindows` calls

| File | Line | Method | Arg | Phase | Notes |
|---|---|---|---|---|---|
| `2Ib.smali` | 33, 53 | `2Ib.A01` | `v0`, `v1` (both `false`) | C | API 30+ helper. **NOT called by current A6 patch** (A6 uses legacy flags instead). |
| `ijz.smali` | 126 | ? | `v4` | — | Not in Reels path. |
| `0Vu.smali` | 11 | ? | `p1` | — | Helper, not Reels. |
| `ked.smali` | 252, 279 | ? | `v0` | — | Not in Reels path. |
| `0Vs.smali` | 47 | ? | `p1` | — | Helper, not Reels. |
| `bWl.smali` | 20 | ? | `v2` | — | Not in Reels path. |

**Reels-relevant:** None directly. A6 uses `addFlags(FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)` + `clearFlags(FLAG_TRANSLUCENT_*)` instead (equivalent legacy approach).

### 1d. `1fC.A04(Activity, I)` callers (status bar color chokepoint)

| File | Line | Caller method | Color arg | Phase | A5 catches? |
|---|---|---|---|---|---|
| `2ZS.smali` | 283 | `2ZS.A01` (Reels onResume path) | `v3 = BLACK` (from `0x7f0407af`) | C | ✓ YES |
| `2ZS.smali` | 718 | `2ZS.A0A` (Stories? feed-reel?) | `v2 = BLACK` | D? | ✓ YES |
| `2ZS.smali` | 1032 | `2ZS.A0B` (Reels onStop, Stories exit) | `v4 = BLACK` | (exit) | ✓ YES |
| `IgFragmentActivity.smali` | 1223 | `A1j` (chrome helper) | `v2 = BLACK` | E (deferred via 6BM) | ✓ YES — but `A1j` NOT called for MainActivity (A1k overridden) |
| `qfa.smali` | 2220 | ? | `v3` | — | ✓ YES (not in Reels path) |
| `lti.smali` | 33 | ? | `v4` | — | ✓ YES |
| `fcx.smali` | 331 | ? | `v3` | — | ✓ YES |
| `LoggedOutAppActivity.smali` | 298, 516 | ? | `v0`, `v4` | A (logged-out) | ✓ YES (not logged-in path) |
| `OnBoardingExperienceTransparentModalActivity.smali` | 91 | ? | `v0` | A (onboarding) | ✓ YES |
| `BvI.smali` | 713 | ? | `v0` | — | ✓ YES |
| `StatusBarAnimationEffectKt$...:96` | 96 | repost composer | `v0` | (repost) | ✓ YES |
| `IbC.smali` | 874 | ? | `v2` | — | ✓ YES |
| `IlS.smali` | 496, 689 | ? | `v2` | — | ✓ YES |
| `1fC.smali` | 177 | `1fC.A03` (wrapper) | `p1` (passthrough) | varies | ✓ YES (`A03` calls `A04` which A5 catches) |

**All `1fC.A04` callers are caught by A5** (zeroes `p1` at method entry).

### 1e. `1fC.A03(Activity, I)` callers (status bar color + icon wrapper)

| File | Line | Caller method | Color arg | Phase | A5 catches? |
|---|---|---|---|---|---|
| `InstagramMainActivity.smali` | 20250 | `A0m` (transparent branch, `0jS.A0D==true`) | `0` (bds_transparent) | B | ✓ YES — but SKIPPED for Reels tab (`0jS.A0D==false`) |
| `InstagramMainActivity.smali` | 21071 | `A0m` (BLACK branch, `0jS.A0D==false`) | `BLACK` | B | ✓ YES — TAKEN for Reels tab |
| `InstagramMainActivity.smali` | 35535 | `A1z` (transparent branch) | `0` | B (onResume) | ✓ YES — but SKIPPED for Reels tab |
| `InstagramMainActivity.smali` | 36397 | `A1z` (BLACK branch) | `BLACK` | B (onResume) | ✓ YES — TAKEN for Reels tab |
| `IgFragmentActivity.smali` | 1241 | `A1j` | `v2 = BLACK` | E (deferred) | ✓ YES — but `A1j` not called for MainActivity |
| `7xj.smali` | 8279 | ? | `v0` | — | ✓ YES |
| `InstagramConsentFlowHostActivity.smali` | 742 | ? | `v0` | A (consent) | ✓ YES |
| `5Wj.smali` | 2884 | ? | `v2` | — | ✓ YES |
| `BrowserLiteWrapperView.smali` | 279 | ? | `p1` | — | ✓ YES |
| `4d9.smali` | 148 | ? | `v0` | — | ✓ YES |
| `HorizonLoadingActivity.smali` | 117 | ? | `v0` | A | ✓ YES |
| `VMW.smali` | 53 | ? | `v0` | — | ✓ YES |
| `DirectAggregatedMediaViewerController.smali` | 8986 | ? | `v3` | — | ✓ YES |
| `ModalActivity.smali` | 317 | ? | `v0` | A (modal) | ✓ YES |
| `C6U.smali` | 5808 | ? | `v0` | — | ✓ YES |
| `BottomSheetFragment.smali` | 7314 | ? | `v0` | (sheet) | ✓ YES |
| `58e.smali` | 1409 | ? | `v0` | — | ✓ YES |
| `3lH.smali` | 663, 1165 | ? | `v1` | — | ✓ YES |
| `0jS.smali` | 7015 | `A1K` (ClipsViewer path) | `v1` | D (ClipsViewer) | ✓ YES — only fires if `9Wz.EEr()` returns true (NOT basic Reels tab) |
| `YN0.smali` | 4992, 6295, 6404, 6453 | ? | `v0`/`v1` | — | ✓ YES |
| `YTa.smali` | 93 | ? | `v0` | — | ✓ YES |
| `YUM.smali` | 806 | ? | `v1` | — | ✓ YES |
| `RqR.smali` | 965 | ? | `v0` | — | ✓ YES |
| `bmh.smali` | 36 | ? | `v1` | — | ✓ YES |
| `klc.smali` | 265, 357 | ? | `v0` | — | ✓ YES |
| `ZNG.smali` | 94 | ? | `v1` | — | ✓ YES |
| `3lI.smali` | 1162, 1642, 2212 | ? | `v0` | (comment composer) | ✓ YES |
| `IIF.smali` | 11507 | ? | `v3` | — | ✓ YES |
| `N0r.smali` | 217 | ? | `v1` | — | ✓ YES |
| `UPm.smali` | 915 | ? | `v0` | — | ✓ YES |
| `ZYf.smali` | 844, 1028 | ? | `v0` | — | ✓ YES |
| `525.smali` | 1056 | ? | `v0` | — | ✓ YES |
| `IFw.smali` | 1908 | ? | `v1` | — | ✓ YES |
| `Ewb.smali` | 311 | ? | `v4` | — | ✓ YES |
| `Wes.smali` | 57 | ? | `v0` | — | ✓ YES |
| `Md2.smali` | 427 | ? | `v4` | — | ✓ YES |
| `Esf.smali` | 985 | ? | `v4` | — | ✓ YES |
| `231.smali` | 1186 | ? | `v0` | — | ✓ YES |
| `TaggingActivity.smali` | 8221 | ? | `v0` | — | ✓ YES |
| `DhG.smali` | 1669 | ? | `v0` | — | ✓ YES |
| `DirectPrivateStoryRecipientController.smali` | 3919 | ? | `v0` | — | ✓ YES |
| `AvatarEditorUrlHandlerActivity.smali` | 117 | ? | `v0` | A | ✓ YES |
| `AvatarViewerUrlHandlerActivity.smali` | 68 | ? | `v4` | A | ✓ YES |
| `UserDetailFragment.smali` | 25163 | ? | `v1` | — | ✓ YES |
| `MediaCaptureActivity.smali` | 6039 | ? | `v0` | A (capture) | ✓ YES |
| `9Yt.smali` | 76 | ? | `p1` (passthrough) | — | ✓ YES |
| `IlS.smali` | — | ? | — | — | ✓ YES |

**ALL `1fC.A03` callers funnel through `1fC.A04` which A5 catches.**

### 1f. `0cW.A0R(View, I, I)` callers that paint View backgrounds (Reels-relevant only)

`0cW.A0R` is a wrapper: `view.setBackgroundColor(color)`. There are 100+ call sites; filtered to those that fire on Reels path:

| File | Line | Caller method | Target view | Color | Phase | Patched? |
|---|---|---|---|---|---|---|
| `2ZS.smali` | 202 | `2ZS.A01` (A08==true branch) | `v1 = decorView` | `v3 = BLACK` | C | ✓ A1 patch (zeroes v3) — only on Android 10-14 |
| `2ZS.smali` | 410 | `2ZS.A05` (called from A01:204) | `p0 = findViewById(0x1020002)` (content view) | `p2 = BLACK` | C | ✓ A2 patch (zeroes p2) |
| `2ZS.smali` | 695 | `2ZS.A0A` (Stories etc.) | `v1 = decorView` | `v2 = BLACK` | D | ✗ NOT PATCHED (not in basic Reels path) |
| `2ZS.smali` | 814, 825 | `2ZS.A0B` (Reels exit) | `v4, v3 = tab views` | `v1 = BLACK` | (exit) | ✗ NOT PATCHED (exit path) |
| `2ZS.smali` | 854 | `2ZS.A0B` | `v4 = tab view` | `v1 = BLACK` | (exit) | ✗ NOT PATCHED |
| `2ZS.smali` | 993 | `2ZS.A0B` (A08==true branch) | `v3 = decorView` | `v4 = BLACK` | (exit) | ✗ NOT PATCHED |
| `2ZS.smali` | 1020 | `2ZS.A0B` (A08==false branch) | `v3 = decorView` | `v4 = BLACK` | (exit) | ✗ NOT PATCHED |
| `47l.smali` | 47 | `47l.run()` (POSTED by `2ZS.A00`) | `v2 = findViewById(0x7f0b3f31)` (**swipe_navigation_container**) | `v1 = BLACK` | E (deferred via 8ug.A06) | ✗ **NOT PATCHED — ★ THE CULPRIT ★** |
| `IgFragmentActivity.smali` | 1236 | `A1j` (chrome helper) | `v1 = decorView` | `v2 = BLACK` | E (deferred via 6BM) | ✗ NOT PATCHED — but `A1j` NOT called for MainActivity (A1k overridden) |
| `InstagramMainActivity.smali` | 12890, 12916 | `A0h` (onCreate) | `0ne.A0E`, `0jS.A0O` (nav-related views) | `v10 = color from 0x7f0407f3` | B (onCreate) | ✗ NOT PATCHED — paints nav-related views, not status bar area |
| `InstagramMainActivity.smali` | 17292, 17318 | `A0i` (onCreate) | same | `v10` | B (onCreate) | ✗ NOT PATCHED — same |
| `InstagramMainActivity.smali` | 47974 | ? | ? | ? | ? | ✗ NOT PATCHED — context unclear |
| `BaseFragmentActivity.smali` | 4269, 4334, 4791, 4885 | ? | various | various | — | ✗ NOT PATCHED — not in Reels path |
| `0bQ.smali` | 444, 455, 478, 500 | `0bQ.A04` (tab container bg) | `0x7f0b3f67`, `0x7f0b248e`, `0x7f0b3f68`, `0x7f0b248f` (tab views) | `v1 = BLACK` | C | ✓ B2-smali patch (zeroes v1) |

### 1g. `setNavigationBarColor` calls (Reels-relevant)

| File | Line | Method | Color | Phase | Patched? |
|---|---|---|---|---|---|
| `2Ib.smali` | 57 | `2Ib.A01` | `0x0` | C | (A6 inlines this) |
| `2ZS.smali` | 267 | `2ZS.A01` (deferred branch, `1fI.A05==false`) | `v3 = BLACK` | C | ✗ NOT PATCHED — sets NAV bar BLACK (not status bar) |
| `1fI.smali` | 416 | `1fI.A04` (deferred OFF branch) | `p1` | C | ✗ NOT PATCHED — NAV bar (not status bar) |
| `3mE.smali` | 313 | `3mE.A00` (deferred callback) | `v0 = fCi.A00` | E | ✗ NOT PATCHED — NAV bar deferred |
| `1fI.smali` | 1fI.A04 deferred path | stores in `fCi.A00` (NAV bar holder) | `p1` | E | ✗ NOT PATCHED — NAV bar |

**Note:** NAV bar color is separate from status bar color. A6 sets NAV bar to 0 (transparent), but later calls (`2ZS.A01:267`, `1fI.A04`, `3mE.A00`) may overwrite it with BLACK. This affects the BOTTOM nav bar, NOT the top status bar. Out of scope for this trace but flagged.

### 1h. Window `addFlags` / `clearFlags` calls (Reels-relevant)

| File | Line | Method | Flag | Phase | Notes |
|---|---|---|---|---|---|
| `2Ib.smali` | 45, 49 | `2Ib.A01` | `clearFlags(0xC0000000)`, `addFlags(0x80000000)` | C | A6 inlines this |
| `2ZS.smali` | 256 | `2ZS.A01` (deferred branch) | `addFlags(0x80000000)` (FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS) | C | OK — needed for transparent bar |
| `1fC.smali` | 243, 320 | `1fC.A04` | `addFlags(0x80000000)` | C+E | OK — same flag |
| `1fI.smali` | 310, 414 | `1fI.A04` | `addFlags(0x80000000)` | C | OK — same flag (NAV bar path) |
| `9Wz.smali` | 30453, 30467 | ? | `addFlags`, `clearFlags` | D (ClipsViewer) | Not in basic Reels tab |

---

## STEP 2: EXECUTION ORDER (Step-by-Step)

### Phase A — App Launch / Splash

1. `IgSplashScreenActivity.onCreate` — does NOT touch status bar (verified: no `1fC`/`setStatusBarColor`/`setSystemUiVisibility` calls).
2. Splash transitions to `InstagramMainActivity`.

### Phase B — MainActivity onCreate + onResume

3. `InstagramMainActivity.onCreate` (entry: ~line 10288 = `A0h`):
   - Line 13087: `decorView.setSystemUiVisibility(0x700)` (LAYOUT_STABLE | LAYOUT_FULLSCREEN | LAYOUT_HIDE_NAVIGATION) — sets up edge-to-edge for whole activity.
   - Line 12890: `0cW.A0R(0ne.A0E, color from 0x7f0407f3, hash)` — paints a nav-related view (NOT status bar area).
   - Line 12916: `0cW.A0R(0jS.A0O, color, hash)` — paints another nav-related view.
4. `InstagramMainActivity.A1z` (onResume, line 34709):
   - Line 35510: `v1 = 0jS.A0D:Z` (the "transparent status bar" flag)
   - Line 35517: `if-ne v1, v0(=1), :cond_17` — for Reels tab, `0jS.A0D == false` → JUMP to `:cond_17`
   - `:cond_17` (line 36375):
     - Line 36376: `v0 = 0x7f0407af` (`?igds_color_primary_background` = BLACK)
     - Line 36381-36389: resolves to actual BLACK color int
     - Line 36397: `1fC.A03(activity, BLACK)` → `1fC.A04(activity, BLACK)` → **A5 zeroes `p1`** → `setStatusBarColor(0)` ✓ TRANSPARENT
   - `:goto_3` (line 35545):
     - Line 35546: `1fI.A01(activity)` — caches `1fI.A03:Integer` (status bar color cache for `com.instagram.mainactivity.InstagramMainActivity`), then calls `1fI.A04(activity, cached_color)` (NAV bar) and `1fI.A05(activity, true)` (light icons)
   - Line 36756: `A0m(activity, this)`:
     - Line 20225: `v1 = 0jS.A0D:Z` (false for Reels)
     - Line 20232: `if-ne v1, v0(=1), :cond_14` → JUMP to `:cond_14`
     - `:cond_14` (line 21054):
       - Line 21055: `v0 = 0bF.A0O(activity):I` (resolves another color resource)
       - Line 21063: `v0 = activity.getColor(v0)`
       - Line 21071: `1fC.A03(activity, v0=BLACK-ish)` → `1fC.A04(activity, BLACK)` → **A5 zeroes `p1`** → `setStatusBarColor(0)` ✓ TRANSPARENT
     - `:goto_3` (line 20260): `1fI.A01(activity)` again (idempotent — `1fI.A03` already cached)

### Phase C — Fragment.onResume (ClipsTabFragment → 2ZS.A01)

5. `ClipsTabFragment.onResume` (line 2564):
   - Line 2598: `2ZS.A02(activity, this, userSession, p3=1, p4=0)`
6. `2ZS.A02` (line 309):
   - Line 322-328: `v4 = 0bF.A0Z(activity, 0x7f040714):I` (icon color)
   - Line 336: `2ZS.A01(activity, fragment, userSession, v4=iconColor, p3=1, p4=0, v7=0)`
7. `2ZS.A01` (line 59) — **★ A6 PATCH HOOK RUNS FIRST ★**:
   - **A6 patch (inserted between `.locals 7` and original line 62):**
     - `window = activity.getWindow()`
     - `window.clearFlags(0xC0000000)` (clears FLAG_TRANSLUCENT_STATUS | FLAG_TRANSLUCENT_NAVIGATION)
     - `window.addFlags(0x80000000)` (adds FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)
     - `window.setStatusBarColor(0)` ✓ TRANSPARENT
     - `window.setNavigationBarColor(0)` ✓ TRANSPARENT
     - `decorView = window.getDecorView()`
     - `decorView.setSystemUiVisibility(0x500)` (LAYOUT_STABLE | LAYOUT_FULLSCREEN)
     - `decorView.setBackgroundColor(0)` ✓ TRANSPARENT
   - Original code resumes at line 62:
     - Line 87-91: `v3 = 0bF.A0W(context, 0x7f0407af):I` = `?igds_color_primary_background` = BLACK
     - Line 93-114: `if-eqz p4, :cond_1` — p4=1 (true) → falls through; calls `0bQ.A04`, `0bQ.A09`, `0bQ.A0A` (tab container colors, B2-smali catches `A04`)
     - Line 120-124: `v6 = activity.getColor(0x7f060070)` (text color)
     - Line 126-148: TextView text colors
     - Line 151-161: `v6 = MobileConfig(0x8112f4005463c1L):Z` (deferred flag for `1fI`-related)
     - Line 163-165: `sget-boolean v0, LX/1fI;->A05:Z; if-eqz v0, :cond_7`
       - If `1fI.A05 == true` (likely on modern builds): falls through
         - Line 167: `1fI.A04(activity, v3=BLACK)` — sets NAV bar color (deferred via Choreographer `ktp` → `3mE.A00`). **Does NOT set status bar.**
       - If `1fI.A05 == false`: jump to `:cond_7` (line 220)
         - Line 221-225: `if-eqz 3sA.A02(), :cond_8` — Android version check
         - Line 227: `1fI.A06(activity, v6, v3)` — sets `setNavigationBarContrastEnforced`
         - `:cond_8` (line 229): parent-looper, then `:cond_9` (line 247) gets window
         - Line 256: `window.addFlags(0x80000000)` (FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)
         - Line 260-264: NAV bar color check
         - Line 267: `window.setNavigationBarColor(v3=BLACK)` — sets NAV bar BLACK (NOT status bar)
         - `goto :goto_0` (line 269) → falls into `:cond_3` block at line 169-170
     - Line 171 (`:cond_3`/`:goto_0`): `1fI.A05(activity, v2=0)` — DARK icons via `0Xm.A00(false)`
     - Line 173-181: `v6 = window; v1 = decorView`
     - Line 185-189: `if 3at.A0I(userSession) == 0, jump to :cond_4` (sets OnSystemUiVisibilityChangeListener)
     - Line 194 (`:cond_4`): `2ZS.A08(activity):Z`
       - **On Android 15+ (3sA.A02 returns TRUE):**
         - Checks `findViewById(0x7f0b3f31)` (swipe_navigation_container)
         - For MainActivity, view EXISTS → A08 returns FALSE (0)
       - **On Android 10-14 (3sA.A02 returns FALSE):**
         - A08 returns TRUE (1) regardless of view presence
     - Line 198: `if-eqz v0, :cond_5` — if A08 == 0 (FALSE), JUMP to `:cond_5`

   **★ ANDROID 10-14 PATH (A08 returns TRUE) ★**
     - Line 200: `v0 = -0x92e8ab6` (hash)
     - Line 202: `0cW.A0R(v1=decorView, v3=BLACK, v0=hash)` — **A1 PATCH zeroes v3** → `decorView.setBackgroundColor(0)` ✓ TRANSPARENT
     - Line 204: `2ZS.A05(activity, userSession, v3=BLACK)`:
       - `2ZS.A05` (line 389): `if 3at.A0I(userSession) == 0, return` (skipped if session flag false)
       - Line 400: `v0 = 0x1020002` (android.R.id.content)
       - Line 402-406: `findViewById(0x1020002)` → first child
       - Line 408-410: `0cW.A0R(contentViewChild, p2=BLACK, -0x7ff859fd)` — **A2 PATCH zeroes p2** → `setBackgroundColor(0)` ✓ TRANSPARENT
     - Line 206-208: `if-eqz 1un.A00, :cond_6` — typically falls through to `:cond_6`
     - `:cond_6` (line 213): `if-eqz p5, :cond_b` — p5=0 → JUMP to `:cond_b`

   **★ ANDROID 15+ PATH (A08 returns FALSE) ★**
     - `:cond_5` (line 210): `2ZS.A00(activity, v3=BLACK)` — **★ NOT CAUGHT BY ANY PATCH ★**
       - `2ZS.A00` (line 45): `new 47l(activity, BLACK); 8ug.A06(activity, 47l)`
       - `8ug.A06` (line 691): if `8ug.A07:I != -1 && 8ug.A06:I != -1` → `47l.run()` SYNCHRONOUSLY; else deferred via `1cK`/`B9l` wrapper
       - `47l.run()` (line 30):
         - `v2 = activity.findViewById(0x7f0b3f31)` (**swipe_navigation_container**)
         - `if-eqz v2, :cond_0` — if view found (it IS in MainActivity), continue
         - `v1 = this.A00:I` = BLACK (passed by `2ZS.A00`)
         - `0cW.A0R(v2, v1=BLACK, 0x6bad5ee0)` → **`swipe_navigation_container.setBackgroundColor(BLACK)` ★★★ THE LAST WRITER ★★★**
     - `:cond_6` (line 213): `if-eqz p5, :cond_b` — p5=0 → JUMP to `:cond_b`

   **★ COMMON PATH (both Android versions) ★**
     - `:cond_b` (line 271):
       - Line 272: `v0 = 1fC.A09(decorView, window):Z` — checks if window is already edge-to-edge
       - Line 276: `if-nez v0, :cond_c` — if A09 returned 1 (already edge-to-edge), SKIP A06
       - Line 278: `1fC.A06(decorView, window, v4=1)` — sets `LAYOUT_FULLSCREEN` on decorView, clears `FLAG_FORCE_NOT_FULLSCREEN` (re-applies what A6 already set)
     - `:cond_c` (line 280):
       - Line 281: `if-nez p6, :cond_d` — p6=0 → fall through
       - Line 283: `1fC.A04(activity, v3=BLACK)` → **A5 PATCH zeroes `p1`** → `1fC.A04(activity, 0)` → `setStatusBarColor(0)` ✓ TRANSPARENT
     - `:cond_d` (line 285):
       - Line 286: `1fC.A05(activity, v2=0)` — DARK icons via `0Xm.A01(false)` (overrides A6's transparent + dark icons combo — icons are DARK on transparent bar)
     - Line 288: `return-void`

### Phase D — Reels Viewer (ClipsViewerFragment / 9Wz)

Not entered for basic Reels TAB (only for `9Wz.EEr()` == true). Skipped.

### Phase E — Deferred / Async Callbacks

8. **`ktp.doFrame` → `3mE.A00`** (deferred status bar color applier, fires on next Choreographer frame IF `1fC.A01:Z` is TRUE):
   - Reads `fCi.A01:Integer` (status bar color holder)
   - The LAST `1fC.A04` call stored `p1` in `fCi.A01`. With A5 patch, `p1` was forced to 0, so `fCi.A01 = Integer.valueOf(0)`.
   - Calls `window.setStatusBarColor(0)` ✓ TRANSPARENT
9. **`47l.run()`** (posted by `2ZS.A00`, fires sync or deferred via `8ug.A06`):
   - **★ Paints `swipe_navigation_container` BLACK ★** — this is the LAST WRITER for the view that extends into the status bar area.
10. **`9A4.doFrame`** (deferred `1fI.A01` Choreographer callback, fires if `3tz.A03()` is true):
    - Calls `1fI.A01(activity)` again — but `1fI.A03` is already cached, so it just calls `1fI.A04` (NAV bar) + `1fI.A05(true)` (light icons).
    - Does NOT set status bar color.

### Phase F — NOT Triggered

- `IgFragmentActivity.A1k` — overridden in InstagramMainActivity as no-op (line 25596-25601). The `6BM($t=0)` Runnable that would call `A1j()` is NEVER posted for MainActivity. So `A1j()` does NOT fire.
- `onWindowFocusChanged` — verified (per 7-b) to have ZERO status bar calls.
- `A1p` (onConfigurationChanged) — verified to have ZERO status bar calls.

---

## STEP 3: THE LAST WRITER (Definitive Answer)

### 3a. Last Writer for `setStatusBarColor` (status bar COLOR)

**The LAST `setStatusBarColor` call, in chronological execution order:**

1. `InstagramMainActivity.A1z:36397` → `1fC.A03(BLACK)` → `1fC.A04(BLACK)` → **A5 zeroes p1** → `setStatusBarColor(0)` (sync OR deferred)
2. `InstagramMainActivity.A0m:21071` → `1fC.A03(BLACK)` → `1fC.A04(BLACK)` → **A5 zeroes p1** → `setStatusBarColor(0)` (sync OR deferred)
3. `2ZS.A01` A6 patch → `setStatusBarColor(0)` ✓
4. `2ZS.A01:283` → `1fC.A04(BLACK)` → **A5 zeroes p1** → `setStatusBarColor(0)` (sync OR deferred)
5. (If defer ON) `3mE.A00` Choreographer callback → reads `fCi.A01` (=0, last stored by step 4) → `setStatusBarColor(0)` ✓

**FINAL `setStatusBarColor` VALUE: 0 (TRANSPARENT).** The status bar COLOR is NOT black.

### 3b. Last Writer for `swipe_navigation_container` Background (the ACTUAL visible BLACK)

**The LAST `setBackgroundColor` call on `swipe_navigation_container` (id `0x7f0b3f31`):**

1. (XML layout) — initial background, likely set by theme (probably BLACK or transparent).
2. `47l.run()` (posted by `2ZS.A00` from `2ZS.A01:211`) → `0cW.A0R(swipe_navigation_container, BLACK, 0x6bad5ee0)` → **`setBackgroundColor(BLACK)` ★★★ THE LAST WRITER ★★★**

**This `47l.run()` call is NOT caught by ANY current patch (A1/A2/A3/A5/A6).**

### 3c. Why This Produces a Visible BLACK Bar

- `2ZS.A01:278` calls `1fC.A06(decorView, window, true)` which sets `LAYOUT_FULLSCREEN` (0x100) on decorView. This makes the content view extend INTO the status bar area.
- A6 patch ALSO sets `setSystemUiVisibility(0x500)` (LAYOUT_STABLE | LAYOUT_FULLSCREEN) — same effect.
- `swipe_navigation_container` is the ROOT content view of `InstagramMainActivity` (it's the swipeable tab container holding Home/Reels/Search/etc. fragments).
- With LAYOUT_FULLSCREEN, `swipe_navigation_container`'s top edge is at y=0 (top of screen, BEHIND the status bar).
- `47l.run()` paints `swipe_navigation_container` BLACK.
- The status bar COLOR is transparent (0), so the BLACK `swipe_navigation_container` background shows THROUGH the transparent status bar.
- **User perceives this as "status bar is black"** — but actually the status bar IS transparent; the BLACK is the content view's background showing through.

### 3d. Android Version Branching (Critical)

The `47l` Runnable ONLY fires on **Android 15+ (SDK 35+)** where `3sA.A02()` returns TRUE. On Android 10-14:
- `2ZS.A08(activity)` returns TRUE (1) → control falls through to line 200-204
- Line 202: `0cW.A0R(decorView, BLACK)` — **A1 PATCH CATCHES** → decorView transparent
- Line 204: `2ZS.A05(activity, userSession, BLACK)` → `0cW.A0R(contentView, BLACK)` — **A2 PATCH CATCHES** → contentView transparent
- **`2ZS.A00` is NOT called** → `47l` Runnable is NOT posted → `swipe_navigation_container` is NOT painted BLACK by this path.

**Therefore:** On Android 10-14, the existing A1+A2 patches SHOULD make the bar transparent. If the user is on Android 10-14 and still sees BLACK, the patches are NOT being applied (build pipeline issue).

On Android 15+, the `47l` Runnable fires and paints `swipe_navigation_container` BLACK, bypassing all current patches. **This is the most likely root cause if the user is on Android 15+**.

---

## STEP 4: VERIFICATION — Does `47l.run()` Run AFTER `2ZS.A01` Returns?

### 4a. `8ug.A06` Synchronous-vs-Deferred Logic

`8ug.A06(activity, runnable)` (line 691):
```smali
sget v0, LX/8ug;->A07:I
const/4 v1, -0x1
if-eq v0, v1, :cond_0       # if A07 == -1, jump to :cond_0 (deferred)
sget v0, LX/8ug;->A06:I
if-eq v0, v1, :cond_0       # if A06 == -1, jump to :cond_0 (deferred)
invoke-interface {p1}, Ljava/lang/Runnable;->run()V   # SYNC: run immediately
return-void

:cond_0
# DEFERRED: wrap in 1cK or B9l, add to A01 or A02 list
```

`8ug.A07:I` and `8ug.A06:I` are static fields initialized elsewhere (likely in `IgApplication.onCreate` or first `8ug` call). If both are initialized (not -1), the runnable runs **SYNCHRONOUSLY inside `8ug.A06`** — meaning `47l.run()` fires BEFORE `2ZS.A01` returns (during the `2ZS.A00` call at line 211).

If either is -1 (uninitialized), the runnable is deferred until later (probably `onWindowFocusChanged` or similar).

**Either way**, `47l.run()` fires (whether sync or deferred), and it paints `swipe_navigation_container` BLACK.

### 4b. Execution Order with `47l` Sync

If `47l.run()` runs synchronously inside `2ZS.A00`:
1. A6 patch: `setStatusBarColor(0)`, `decorView.setBackgroundColor(0)` ✓
2. `2ZS.A01:211` → `2ZS.A00` → `47l.run()` → `swipe_navigation_container.setBackgroundColor(BLACK)` ★
3. `2ZS.A01:278` → `1fC.A06` → sets LAYOUT_FULLSCREEN
4. `2ZS.A01:283` → `1fC.A04(BLACK)` → A5 zeroes p1 → `setStatusBarColor(0)` ✓
5. `2ZS.A01:286` → `1fC.A05(false)` → dark icons
6. `2ZS.A01` returns.
7. (If defer ON) Choreographer fires → `3mE.A00` → `setStatusBarColor(0)` ✓

**FINAL STATE:** status bar color = 0 (transparent), BUT `swipe_navigation_container` is BLACK. The BLACK background shows through the transparent status bar.

### 4c. Execution Order with `47l` Deferred

If `47l.run()` is deferred:
1. A6 patch: `setStatusBarColor(0)`, `decorView.setBackgroundColor(0)` ✓
2. `2ZS.A01:211` → `2ZS.A00` → `8ug.A06` queues `47l` for later
3. `2ZS.A01:278` → `1fC.A06` → sets LAYOUT_FULLSCREEN
4. `2ZS.A01:283` → `1fC.A04(BLACK)` → A5 zeroes p1 → `setStatusBarColor(0)` ✓
5. `2ZS.A01:286` → `1fC.A05(false)` → dark icons
6. `2ZS.A01` returns.
7. (If defer ON) Choreographer fires → `3mE.A00` → `setStatusBarColor(0)` ✓
8. **Later (next frame or onWindowFocusChanged):** `47l.run()` fires → `swipe_navigation_container.setBackgroundColor(BLACK)` ★

**FINAL STATE:** Same — status bar transparent, but `swipe_navigation_container` BLACK.

### 4d. Conclusion

**The LAST WRITER for the visible "black bar" is `47l.run()` → `swipe_navigation_container.setBackgroundColor(BLACK)`.** This runs either synchronously inside `2ZS.A01` or shortly after (deferred). In both cases, it OVERWRITES the transparent decorView background set by A6.

---

## STEP 5: DIAGNOSTIC RECOMMENDATION — RED Color Test

### 5a. Goal

Disambiguate between:
- (H1) Patches are NOT applied → bar stays BLACK from start.
- (H2) Patches ARE applied, but `47l.run()` paints `swipe_navigation_container` BLACK → bar turns RED (with RED patch) then BLACK.
- (H3) Patches ARE applied, `47l.run()` is the ONLY writer → bar turns RED and STAYS RED.

### 5b. Recommended Diagnostic Patches

Apply ALL THREE patches simultaneously to unambiguously trace:

#### Patch RED-1: A6 hook uses RED for `setStatusBarColor`

In `apply_patches.py`, modify the A6 block (lines 79-98) — change:
```python
'    const/4 v1, 0x0\n'
'    invoke-virtual {v0, v1}, Landroid/view/Window;->setStatusBarColor(I)V\n'
```
to:
```python
'    const v1, -0x10000\n'                              # 0xFFFF0000 = BRIGHT RED
'    invoke-virtual {v0, v1}, Landroid/view/Window;->setStatusBarColor(I)V\n'
```

#### Patch RED-2: A5 uses RED for `1fC.A04` p1

In `apply_patches.py`, modify the A5 block (lines 106-112) — change:
```python
'    # InstaTrueReel: force transparent status bar color\n'
'    const/4 p1, 0x0\n\n'
```
to:
```python
'    # InstaTrueReel DIAGNOSTIC: force RED status bar color\n'
'    const p1, -0x10000\n\n'                            # 0xFFFF0000 = BRIGHT RED
```

#### Patch RED-3: `47l.run()` uses RED for `swipe_navigation_container` background

Add a NEW patch in `apply_patches.py` after the A5 block:
```python
# DIAGNOSTIC RED-3: paint swipe_navigation_container RED instead of BLACK.
# Confirms whether 47l.run() is the LAST writer for the visible bar.
run_l = find_smali(decoded, '47l.smali')
patch_text(run_l,
    '    iget v1, p0, LX/47l;->A00:I\n\n    const v0, 0x6bad5ee0\n\n    invoke-static {v2, v1, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
    '    iget v1, p0, LX/47l;->A00:I\n\n    # InstaTrueReel DIAGNOSTIC: RED swipe_nav bg\n    const v1, -0x10000\n\n    const v0, 0x6bad5ee0\n\n    invoke-static {v2, v1, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
    'DIAG-red-47l-swipenav')
```

### 5c. Expected Outcomes

After building + installing + opening Reels tab:

| Observation | Meaning | Action |
|---|---|---|
| **Bar turns RED and STAYS RED** | All 3 patches applied. `47l.run()` IS the last writer (its RED wins). `setStatusBarColor(RED)` from A6/A5 also contributes (but `swipe_navigation_container` RED is what's visible). | Replace `-0x10000` with `0x0` (transparent) in all 3 patches. Done — bar will be transparent, video visible behind. |
| **Bar turns RED briefly then BLACK** | Patches ARE applied, but SOMETHING ELSE overrides `swipe_navigation_container` background AFTER `47l.run()`. Candidates: `2ZS.A0B` (Reels exit — but shouldn't fire on entry), `0bQ.A04` (B2-smali catches), or another `0cW.A0R` caller. | Trace further: add RED markers to other `0cW.A0R` callers in `2ZS.A0A`/`A0B` and `0bQ.A04`/`A09`/`A0A`. |
| **Bar stays BLACK from start** | Patches are NOT applied to the running APK (build pipeline issue). The `47l` and `1fC.A04` and A6 hooks are all unpatched. | Verify: decompile the BUILT APK (not source) and grep `2ZS.smali` / `1fC.smali` / `47l.smali` for `InstaTrueReel` markers. If absent, fix the build pipeline. |
| **Bar turns RED at top, BLACK at bottom (or vice versa)** | A6/A5 RED applies to status bar (top), `47l` RED applies to `swipe_navigation_container` (which may not cover full screen). Indicates `swipe_navigation_container` does NOT extend to the very top — something ELSE is painting the top BLACK. | Investigate `Window.setBackgroundDrawable` (theme `windowBackground`) and other `0cW.A0R` callers in `BaseFragmentActivity.smali:4269, 4334, 4791, 4885`. |

### 5d. Production Fix (After RED Test Confirms `47l` is the Culprit)

Once RED-3 confirms `47l.run()` is the last writer, replace the RED with transparent:

```python
# A7 (NEW): zero swipe_navigation_container bg in 47l.run().
# This is the LAST WRITER for the visible "black bar" on Android 15+.
run_l = find_smali(decoded, '47l.smali')
patch_text(run_l,
    '    iget v1, p0, LX/47l;->A00:I\n\n    const v0, 0x6bad5ee0\n\n    invoke-static {v2, v1, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
    '    iget v1, p0, LX/47l;->A00:I\n\n    # InstaTrueReel: transparent swipe_nav bg (was BLACK)\n    const/4 v1, 0x0\n\n    const v0, 0x6bad5ee0\n\n    invoke-static {v2, v1, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
    'A7-transparent-swipenav')
```

**Alternative (broader):** Patch `2ZS.A00` to force `p1=0` (catches ALL callers of `2ZS.A00`, not just the `47l` Runnable):

```python
# A7-alt: zero p1 in 2ZS.A00 so EVERY 47l posting uses transparent color.
patch_text(zs,
    '.method public static final A00(Landroid/app/Activity;I)V\n    .locals 1\n    .annotation build Ldalvik/annotation/optimization/NeverInline;\n    .end annotation\n\n    new-instance v0, LX/47l;',
    '.method public static final A00(Landroid/app/Activity;I)V\n    .locals 1\n    .annotation build Ldalvik/annotation/optimization/NeverInline;\n    .end annotation\n\n    # InstaTrueReel: force transparent swipe_nav bg\n    const/4 p1, 0x0\n\n    new-instance v0, LX/47l;',
    'A7-alt-transparent-swipenav')
```

---

## STEP 6: COMPLETE ORDERED CALL SEQUENCE (Cheat Sheet)

For Reels tab onResume on **Android 15+** (the problematic case):

| # | Time | Caller | Call | Effect | Patched? |
|---|---|---|---|---|---|
| 1 | T0 | `InstagramMainActivity.onCreate` → `A0h` | `decorView.setSystemUiVisibility(0x700)` | LAYOUT_STABLE \| LAYOUT_FULLSCREEN \| LAYOUT_HIDE_NAVIGATION | (no patch needed) |
| 2 | T0 | `A0h:12890` | `0cW.A0R(0ne.A0E, color, hash)` | Paints nav-related view | ✗ (not status bar area) |
| 3 | T0 | `A0h:12916` | `0cW.A0R(0jS.A0O, color, hash)` | Paints nav-related view | ✗ (not status bar area) |
| 4 | T1 | `InstagramMainActivity.A1z` (onResume) | `1fC.A03(activity, BLACK)` → `1fC.A04(BLACK)` | `setStatusBarColor(0)` (A5 catches) | ✓ A5 |
| 5 | T1 | `A1z:35546` | `1fI.A01(activity)` | Sets NAV bar + light icons (deferred via 9A4) | ✗ (NAV bar, not status bar) |
| 6 | T1 | `A1z:36756` → `A0m:21071` | `1fC.A03(activity, BLACK)` → `1fC.A04(BLACK)` | `setStatusBarColor(0)` (A5 catches) | ✓ A5 |
| 7 | T2 | `ClipsTabFragment.onResume:2598` → `2ZS.A02:336` → `2ZS.A01` | **A6 patch runs first** | `setStatusBarColor(0)`, `setNavigationBarColor(0)`, `decorView.setSystemUiVisibility(0x500)`, `decorView.setBackgroundColor(0)` | ✓ A6 |
| 8 | T2 | `2ZS.A01:167` (if `1fI.A05==true`) | `1fI.A04(activity, BLACK)` | Sets NAV bar (deferred via ktp→3mE) | ✗ (NAV bar) |
| 9 | T2 | `2ZS.A01:171` | `1fI.A05(activity, false)` | DARK icons via `0Xm.A00(false)` | ✗ (icons, not bar) |
| 10 | T2 | `2ZS.A01:194` | `2ZS.A08(activity):Z` → returns FALSE (Android 15+, view found) | — | — |
| 11 | T2 | `2ZS.A01:211` (`:cond_5`) | `2ZS.A00(activity, BLACK)` → `8ug.A06(activity, new 47l(activity, BLACK))` | Posts `47l` Runnable | ✗ **NOT PATCHED** |
| 12a | T2 (sync) OR T2+1frame (deferred) | `47l.run()` | `0cW.A0R(swipe_navigation_container, BLACK, 0x6bad5ee0)` | **`swipe_navigation_container.setBackgroundColor(BLACK)` ★★★ LAST WRITER ★★★** | ✗ **NOT PATCHED** |
| 13 | T2 | `2ZS.A01:278` (`:cond_b`) | `1fC.A06(decorView, window, true)` | Sets LAYOUT_FULLSCREEN on decorView (re-applies) | (no patch needed) |
| 14 | T2 | `2ZS.A01:283` (`:cond_c`) | `1fC.A04(activity, BLACK)` | `setStatusBarColor(0)` (A5 catches) | ✓ A5 |
| 15 | T2 | `2ZS.A01:286` (`:cond_d`) | `1fC.A05(activity, false)` | DARK icons via `0Xm.A01(false)` | ✗ (icons, not bar) |
| 16 | T2 | `2ZS.A01` returns | — | — | — |
| 17 | T2+1frame | `ktp.doFrame` → `3mE.A00` (if defer ON) | `setStatusBarColor(fCi.A01.intValue()=0)` | `setStatusBarColor(0)` ✓ | ✓ A5 (indirect) |

**Final state at T2+1frame:**
- `setStatusBarColor` value: **0 (TRANSPARENT)** ✓
- `decorView` background: **0 (TRANSPARENT)** ✓ (from A6)
- `swipe_navigation_container` background: **BLACK** ✗ (from `47l.run()`, NOT patched)
- decorView system UI visibility: **0x500** (LAYOUT_STABLE | LAYOUT_FULLSCREEN) ✓
- Status bar icons: **DARK** (from `1fC.A05(false)` at line 286, overrides A6's transparent+dark combo)

**Visible result:** Status bar AREA is BLACK (because `swipe_navigation_container` is BLACK and extends into the status bar area due to LAYOUT_FULLSCREEN). The status bar COLOR itself is transparent. The user perceives a "black status bar".

---

## STEP 7: SUMMARY TABLE

| # | Question | Answer | Confidence |
|---|---|---|---|
| Q1 | Is `setStatusBarColor` being called with BLACK? | **NO** — A5 forces `p1=0` in `1fC.A04`, so every `setStatusBarColor` call resolves to `0` (transparent). | HIGH |
| Q2 | Is `setStatusBarColor` being called at all? | **YES** — at `1fC.smali:322` (sync) or `3mE.smali:322` (deferred). Final value: 0. | HIGH |
| Q3 | What is the LAST `setStatusBarColor` call? | `1fC.A04(activity, 0)` at `2ZS.A01:283` (with A5 patch). If defer ON, `3mE.A00` fires next frame with `fCi.A01=0`. | HIGH |
| Q4 | What is the LAST writer for the VISIBLE "black bar"? | **`47l.run()`** — paints `swipe_navigation_container` (id `0x7f0b3f31`) BLACK via `0cW.A0R(view, BLACK, 0x6bad5ee0)`. Called from `2ZS.A00` posted at `2ZS.A01:211` (Android 15+ path only). | HIGH |
| Q5 | Why does `47l.run()` only fire on Android 15+? | `2ZS.A08(activity):Z` returns FALSE on Android 15+ (because `3sA.A02()` returns TRUE and `swipe_navigation_container` view is found in MainActivity). On Android 10-14, A08 returns TRUE → falls through to line 202 (A1 patch catches) + line 204 (A2 patch catches), and `2ZS.A00` is NOT called. | HIGH |
| Q6 | Is `47l.run()` caught by any current patch? | **NO** — A1 catches line 202 (decorView), A2 catches `2ZS.A05` (contentView), A3 catches `6BM` top inset, A5 catches `1fC.A04` (status bar color), A6 catches `2ZS.A01` start. NONE catch `47l.run()` or `2ZS.A00`. | HIGH |
| Q7 | Does A6 patch run? | **YES** — confirmed by 7-b. A6 is at the start of `2ZS.A01`, which is called unconditionally from `ClipsTabFragment.onResume:2598` → `2ZS.A02:336`. | HIGH |
| Q8 | Does A5 patch catch the `1fC.A04(BLACK)` at `2ZS.A01:283`? | **YES** — A5 inserts `const/4 p1, 0x0` at the start of `1fC.A04`, BEFORE the `:goto_0` label. So `p1` is forced to 0 regardless of caller. | HIGH |
| Q9 | What about `2ZS.A0B` (which also calls `2ZS.A00` at line 998, 1029)? | `2ZS.A0B` is called from `AFt.onStop:2664` (Reels EXIT) and other places — NOT from Reels ENTRY. So it doesn't fire on Reels onResume. | HIGH |
| Q10 | What about `IgFragmentActivity.A1j` (which paints decorView BLACK)? | `A1j` is called from `6BM.Fji($t=0)` Runnable. But `InstagramMainActivity.A1k()` is OVERRIDDEN to no-op (line 25596-25601), so `6BM($t=0)` is NEVER posted for MainActivity. `A1j` does NOT fire. | HIGH |
| Q11 | What about `onWindowFocusChanged`? | Verified by 7-b: ZERO status bar calls in `onWindowFocusChanged` (line 50512-50662). | HIGH |
| Q12 | What about `A1p` (onConfigurationChanged)? | Verified: ZERO status bar calls in `A1p` (line 28488+). | HIGH |

---

## STEP 8: FILE-LINE CHEAT SHEET

| File | Line | What |
|---|---|---|
| `apply_patches.py` | 49-52 | A1 patch (decorView bg, line 202 of 2ZS.A01) |
| `apply_patches.py` | 55-58 | A2 patch (contentView bg, in 2ZS.A05) |
| `apply_patches.py` | 60-65 | A3 patch (top inset in 6BM) |
| `apply_patches.py` | 77-99 | A6 patch (edge-to-edge at start of 2ZS.A01) |
| `apply_patches.py` | 105-112 | A5 patch (zero p1 in 1fC.A04) |
| `2ZS.smali` | 45-57 | `2ZS.A00(activity, p1)` — posts `47l` Runnable via `8ug.A06` |
| `2ZS.smali` | 59-307 | `2ZS.A01` method (A6 patch target, contains the `:cond_5` branch at line 210) |
| `2ZS.smali` | 194-198 | `2ZS.A08(activity):Z` check — returns FALSE on Android 15+ with swipe_nav view |
| `2ZS.smali` | 200-202 | `0cW.A0R(decorView, BLACK)` — **A1 PATCH CATCHES** (Android 10-14 only) |
| `2ZS.smali` | 204 | `2ZS.A05(activity, userSession, BLACK)` — calls `0cW.A0R(contentView, BLACK)` (A2 catches) |
| `2ZS.smali` | 210-211 (`:cond_5`) | `2ZS.A00(activity, BLACK)` — **★ POSTS `47l` RUNNABLE — NOT PATCHED ★** |
| `2ZS.smali` | 278 | `1fC.A06(decorView, window, true)` — sets LAYOUT_FULLSCREEN |
| `2ZS.smali` | 283 | `1fC.A04(activity, BLACK)` — A5 catches → `setStatusBarColor(0)` |
| `2ZS.smali` | 286 | `1fC.A05(activity, false)` — DARK icons |
| `2ZS.smali` | 309-339 | `2ZS.A02` (delegates to A01) |
| `2ZS.smali` | 341-369 | `2ZS.A03` (delegates to A01) |
| `2ZS.smali` | 389-414 | `2ZS.A05(activity, userSession, p2)` — paints `android.R.id.content` first child |
| `2ZS.smali` | 458-483 | `2ZS.A08(activity):Z` — Android-version-dependent gate |
| `47l.smali` | 16-26 | `47l.<init>(activity, color)` — stores activity + color |
| `47l.smali` | 30-51 | `47l.run()` — **★ PAINTS `swipe_navigation_container` BLACK ★** |
| `47l.smali` | 35 | `const v0, 0x7f0b3f31` — `swipe_navigation_container` view id |
| `47l.smali` | 47 | `0cW.A0R(view, BLACK, 0x6bad5ee0)` — **THE LAST WRITER (not patched)** |
| `8ug.smali` | 691-857 | `8ug.A06(activity, runnable)` — runs sync OR deferred |
| `8ug.smali` | 710-722 | Sync path: if `A07:I != -1 && A06:I != -1` → `runnable.run()` immediately |
| `8ug.smali` | 730-839 | Deferred path: wraps in `1cK` or `B9l`, adds to list |
| `0cW.smali` | 333-343 | `0cW.A0R(view, color, hash)` — wrapper for `view.setBackgroundColor(color)` |
| `1fC.smali` | 212-334 | `1fC.A04(activity, p1)` — **A5 PATCH TARGET** |
| `1fC.smali` | 215 | `:goto_0` label — A5 inserts `const/4 p1, 0x0` before this |
| `1fC.smali` | 322 | `setStatusBarColor(p1)` — sync path (defer OFF) |
| `1fC.smali` | 286-308 | Deferred Choreographer scheduling (defer ON) |
| `1fC.smali` | 393-429 | `1fC.A06(view, window, Z)` — sets LAYOUT_FULLSCREEN (Z=true) or FLAG_FULLSCREEN (Z=false) |
| `3mE.smali` | 322 | `setStatusBarColor(v0)` — deferred callback (defer ON, next frame) |
| `1fI.smali` | 260-428 | `1fI.A04(activity, p1)` — NAV bar color (NOT status bar) |
| `1fI.smali` | 430-479 | `1fI.A05(activity, Z)` — icon appearance via `0Xm.A00(Z)` |
| `1fI.smali` | 481-562 | `1fI.A06(activity, Z, I)` — `setNavigationBarContrastEnforced` |
| `0Xm.smali` | 94-108 | `0Xm.A00(Z)` — calls `0Xf.A03(Z)` (icon appearance) |
| `AFt.smali` | 2564-2624 | `ClipsTabFragment.onResume()` |
| `AFt.smali` | 2598 | `invoke-static ... 2ZS.A02(...)` — ungated call |
| `AFt.smali` | 2626-2685 | `ClipsTabFragment.onStop()` — calls `2ZS.A0B` (Reels EXIT, not entry) |
| `InstagramMainActivity.smali` | 10288 | `A0h` (onCreate helper) — `setSystemUiVisibility(0x700)` at line 13087 |
| `InstagramMainActivity.smali` | 12890, 12916 | `0cW.A0R` on `0ne.A0E`, `0jS.A0O` (nav-related, not status bar) |
| `InstagramMainActivity.smali` | 14952 | `A0i` (onCreate helper) — `setSystemUiVisibility(0x700)` at line 17489 |
| `InstagramMainActivity.smali` | 19664 | `A0m` (called from A1z:36756) |
| `InstagramMainActivity.smali` | 20250, 21071 | `1fC.A03` calls in A0m (transparent / BLACK branch) |
| `InstagramMainActivity.smali` | 25596-25601 | `A1k` override — NO-OP (prevents `6BM($t=0)` posting) |
| `InstagramMainActivity.smali` | 28488 | `A1p` (onConfigurationChanged) — ZERO chrome calls |
| `InstagramMainActivity.smali` | 34709 | `A1z` (onResume) start |
| `InstagramMainActivity.smali` | 35535, 36397 | `1fC.A03` calls in A1z (transparent / BLACK branch) |
| `InstagramMainActivity.smali` | 36756 | `A0m` call at end of A1z |
| `InstagramMainActivity.smali` | 50512-50662 | `onWindowFocusChanged` — ZERO chrome calls |
| `IgFragmentActivity.smali` | 1192-1244 | `A1j` — paints decorView BLACK + `1fC.A04(BLACK)`. NOT called for MainActivity. |
| `IgFragmentActivity.smali` | 1246-1273 | `A1k` — posts `6BM($t=0)` Runnable. OVERRIDDEN in MainActivity. |
| `IgFragmentActivity.smali` | 3661, 3832 | `A1z` (onResume) calls `A1k` — but MainActivity's A1z overrides this |
| `6BM.smali` | 32-295 | `6BM.Fji(p1, p2)` — `:pswitch_3` branch ($t=0) calls `A1j` if `A26()` returns true |
| `6BM.smali` | 131-192 | `:pswitch_3` (the $t=0 case) — A3 patch target (zeroes p1 top inset) |
| `6BM.smali` | 185 | `invoke-virtual {v3}, IgFragmentActivity;->A1j()V` — would fire if not overridden |
| `9Wz.smali` | (various) | ClipsViewer — not entered for basic Reels TAB |
| `2Ib.smali` | 11-90 | `2Ib.A01(window, Z)` — API 30+ edge-to-edge helper (NOT used by current A6) |
| `3sA.smali` | 186-213 | `3sA.A02():Z` — returns TRUE on Android 15+ (SDK 35+) |

---

## STEP 9: OPEN QUESTIONS FOR NEXT AGENT

1. **Verify `47l.run()` is the culprit with RED-3 diagnostic.** Apply the 3 RED patches in §5b, build, install, observe. Expected: bar turns RED (confirming `47l` is the last writer). Then change RED to 0 (transparent) in `47l.smali` — bar should become transparent with video visible behind.

2. **Determine user's Android version.** Critical for diagnosis:
   - Android 10-14: A1+A2 patches SHOULD work (no `47l` posting). If still BLACK → patches not applied.
   - Android 15+: `47l` Runnable fires, requires the new A7 patch (§5d).

3. **`1fI.A05(false)` at `2ZS.A01:286` overrides A6's icon setup.** Even after fixing the BLACK background, icons will be DARK (not white). To get white floating icons (TikTok-style), need a separate patch to either:
   - Change `v2` from 0 to 1 at line 286 of `2ZS.A01` (so `1fC.A05(activity, true)` is called → light icons)
   - OR patch `1fC.A05` to force `p1=true` (light icons) regardless of caller
   - OR patch `0Xm.A00(Z)` to ignore `p1` and always set light icons
   
   Not in scope for this trace but flagged for next agent.

4. **Verify `8ug.A07:I` and `8ug.A06:I` runtime values.** Determines whether `47l.run()` is sync or deferred. Either way it fires, but sync means it runs INSIDE `2ZS.A01` (before line 278's `1fC.A06`), while deferred means it runs after `2ZS.A01` returns. Affects the exact "last writer" timing but not the final state.

5. **If RED-3 shows bar turns RED briefly then BLACK:** Some OTHER writer overrides `swipe_navigation_container` AFTER `47l.run()`. Candidates to investigate:
   - `2ZS.A0A:695` (paints decorView, not swipe_nav — but check)
   - `2ZS.A0B:993, 1020` (paints decorView — but Reels exit path, shouldn't fire on entry)
   - `0bQ.A04:444, 455, 478, 500` (paints tab containers `0x7f0b3f67`, `0x7f0b248e`, `0x7f0b3f68`, `0x7f0b248f` — B2-smali catches)
   - `BaseFragmentActivity.smali:4269, 4334, 4791, 4885` (paints various views — investigate)
   - Theme `windowBackground` (set in AndroidManifest.xml — binary, can't easily read; may need `aapt dump` to inspect)

6. **If patches are confirmed applied AND `47l` RED shows RED bar, but bar still has BLACK at very top edge:** The `Window` background (theme `windowBackground`) may be BLACK and showing through. Add `window.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT))` to A6 patch (requires constructing a `ColorDrawable` in smali — more complex).

READ-ONLY exploration complete. No patch code was written to the codebase. Diagnostic recommendations only.
