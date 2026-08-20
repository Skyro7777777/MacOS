# InstaTrueReel — Living Plan & Debug Log

## CURRENT STATE (2026-08-12, after v11 build)

### What WORKS:
- ✅ **Main bottom nav bar** is transparent (floating white icons over video)
  - This was achieved in v2 with B1 (zero bottomMargin) + B2 (zero 0bQ.A04 bgcolor)
  - Has NOT broken since — these patches are stable

### What DOESN'T WORK:
- ❌ **Status bar** — still shows black strip (dark mode) / white strip (light mode)
- ❌ **Comment input bar** ("Add Comments..." that replaces main bar) — still black/gray

### What I've tried for status bar (11 builds, ALL failed):
1. v1-3: setStatusBarColor(0) — didn't work (content didn't draw behind bar)
2. v4: A5 zero 1fC.A04 p1 — didn't work (deferred Choreographer overrode)
3. v5: A6 call 2Ib.A01 — CRASHED (setDecorFitsSystemWindows is API 30+, user on Android 10)
4. v6: A6 legacy API (clearFlags + setSystemUiVisibility + setBackgroundColor) — didn't work
5. v7: A7 zero 2ZS.A00 p1 (47l Runnable) — didn't work
6. v8: FLAG_LAYOUT_NO_LIMITS — didn't work
7. v9: RED diagnostic — **STATUS BAR TURNED RED** (proved code runs!)
8. v10: RED → transparent(0) — showed black/white (window background showing through)
9. v11: window.setBackgroundDrawable(null) — **STILL shows black/white**

### THE KEY INSIGHT I'M MISSING:
The RED diagnostic (v9) proved:
- Our code DOES execute
- setStatusBarColor(RED) makes the bar RED
- FLAG_LAYOUT_NO_LIMITS works (content draws behind)

But transparent(0) shows black/white. This means:
- setStatusBarColor(0) IS being set (transparent)
- BUT something BEHIND the status bar is painted black/white
- window.setBackgroundDrawable(null) should have fixed it — but DIDN'T
- decorView.setBackgroundColor(0) should have fixed it — but DIDN'T

## WHAT I'M COMPROMISING / NOT DOING:

### 1. I'm not verifying what ACTUALLY happens at runtime
I'm guessing what's behind the status bar. I should:
- Do ANOTHER diagnostic: set window background to RED, decorView to RED,
  status bar to RED, AND 47l to RED — ALL at once. If ALL are red, then
  something ELSE is painting on top. If only some are red, we know which
  layer is the problem.

### 2. I'm not checking if setBackgroundDrawable(null) actually executes
The smali for `setBackgroundDrawable(Landroid/graphics/drawable/Drawable;)V`
takes an object parameter. I'm passing `v1` which is `0x0` (null int). But
smali needs `const/4 v1, 0x0` for an object null reference, and the invoke
must be `invoke-virtual {v0, v1}, ...->setBackgroundDrawable`. Let me verify
this is correct — maybe the null isn't being passed properly.

### 3. I'm not exploring the RIGHT code path
Agent 7-a found that on Android 10, `3sA.A02()` returns FALSE (needs SDK 35+).
So `2ZS.A08` returns 1 (OLD path). The old path goes to `:cond_5` which calls
`2ZS.A00(activity, v3)`. Our A7 zeros p1 in A00. BUT — does A00 actually run?
The RED test showed the status bar IS red, so our A-NO_LIMITS patch in A01
runs. But maybe A00 runs AFTER and re-paints? No — A7 zeros A00's p1, so
even if A00 runs, it gets 0.

### 4. I haven't checked: is there a VIEW literally drawn ON TOP of the status bar?
The RED test proved the STATUS BAR COLOR is red. But maybe there's a VIEW
(a black/white rectangle) drawn on top of the status bar area, covering the red.
This would explain why RED shows (the bar itself is red) but transparent shows
black (the view on top is black). I need to find this view.

### 5. I'm not using subagents anymore for the status bar
I dispatched subagents for v7 but then stopped. I should dispatch a subagent
specifically to find: "Is there a View overlay drawn on top of the status bar
area in the Reels viewer?"

## ACTION PLAN FOR NEXT BUILD:

### Step 1: Full RED diagnostic (ALL layers red)
Set ALL of these to RED simultaneously:
- window.setStatusBarColor(RED)
- window.setBackgroundDrawable(RED ColorDrawable) — not null, RED
- decorView.setBackgroundColor(RED)
- 1fC.A04 p1 = RED (catches all setStatusBarColor)
- 2ZS.A00 p1 = RED (catches 47l swipe_nav painter)
- 0bQ.A04 bgcolor = RED (catches main nav painter)

If the ENTIRE screen is red → we control everything, change to transparent
If only status bar is red but rest is black → a VIEW is on top, find it
If nothing is red → build pipeline issue

### Step 2: Find the overlay view (if Step 1 shows a view on top)
Dispatch subagent to find any View that:
- Has height = status_bar_height
- Is positioned at the top of the screen
- Has a black/white background
- Is added in the Reels viewer layout

### Step 3: For comment bar
The comment input bar ("Add Comments...") is a DIFFERENT view from the comment
sheet. Agent 5-c found it's `bottom_sheet_container` (0x7f0b06b2/0x7f0b06b3).
B4 patches C6BM.pswitch_6 to setBackgroundColor(0) on these. But it's still
black. The background might be set via XML layout (which we can't patch with
-r decode). Need to find where it's set in code OR do a full resource decode
for just that layout.

## LESSONS LEARNED:
1. The RED diagnostic was the most useful thing I did — it proved the code runs
2. I should have done it at v3, not v9
3. I keep guessing instead of verifying each layer
4. I need to test ALL layers at once, not one at a time
5. The main nav bar worked because B1+B2 were simple and correct from the start
6. Status bar is complex because MULTIPLE layers are involved (window bg,
   decorView bg, status bar color, view overlays)

---

## 2026-08-18 — STEP 12 (fresh pass): real-smali root-cause + DIAGNOSTIC build

### What this pass did differently
- Read the ACTUAL smali (smali-extraction artifact 9026348046, ~580 KB) for
  `X/2ZS.smali`, `X/1fC.smali`, `X/1fI.smali`, `X/6BM.smali`, `X/0bQ.smali`
  instead of trusting the (suspect) prior notes for status/comment bar.
- Confirmed the A1/A2/A3/A5/A7 patch patterns actually exist in the smali
  (dry-run of `apply_diagnostic.py` against the real smali: all 6 Feature-A
  patches + B2 applied cleanly).
- Re-read `2ZS.A08` carefully: **CORRECTED the prior note.** `A08` returns
  TRUE on Android 10 (it only returns FALSE on SDK35+ AND when view
  `0x7f0b3f31` exists). So on Android 10 the :202 (decorView paint) and :204
  →A05 (:410 content paint) code paths DO run. A1/A2 are NOT no-ops on
  Android 10. (The prior "A08 returns FALSE on Android 10" claim was wrong.)

### Two distinct root-cause bugs (confirmed from smali)
1. **MAIN `apply_patches.py` bug:** `A-NO_LIMITS` sets `window bg = null` +
   `decorView = 0` at the START of `2ZS.A01`, but the original A01 body then
   RE-PAINTS decorView at :202 (`0cW.A0R(decorView, v3=themeColor, hash)`)
   and content at :410 (via `2ZS.A05`). A1 (intercept :202 → v3=0) and A2
   (intercept :410 → p2=0) are MISSING from the main script. → decorView &
   content end up DARK (theme `#0c1014`). → black strip.
2. **`instatruereelsstatusbar/apply_patches.py` bug:** HAS A1/A2 (so
   decorView + content become transparent) BUT its A6 block never calls
   `window.setBackgroundDrawable(null)`. → theme `windowBackground`
   (`igds_color_primary_background = #ff0c1014`) shows through the
   now-transparent decorView/content. → dark strip.

### The complete fix (untested yet)
A1 + A2 + `window.setBackgroundDrawable(null)` + A3 + A5 + A7 + B1 + B2.
**BUT** even this may still show BLACK: if all bg layers are transparent and
the video view does NOT extend into the status-bar region (inset/padding
pushes it down) you see the bare window surface (black); OR the video DOES
extend but a 9:16 video letterboxed into a ~20:9 screen leaves a black bar.

### The DIAGNOSTIC build (this round) — `apply_diagnostic.py`
Same as the complete fix, BUT `window bg = RED ColorDrawable (0xFFFF0000)`
instead of null. ONE screenshot of a reel playing then pinpoints the case:

| Status-bar strip color | Meaning | Next step |
|---|---|---|
| **RED** | A1/A2 applied (decorView+content transparent) + video does NOT reach the bar | Hunt & zero the inset/padding on the reels root (A3/6BM is the wrong target or insufficient); find the real `OnApplyWindowInsetsListener` / `fitsSystemWindows` |
| **DARK (#0c1014, not red)** | A1/A2 patch patterns failed to match | Re-check smali patterns (dry-run already shows they DO match, so this outcome is unlikely) |
| **BLACK (pure #000000)** | Video reaches the status-bar region but is black there (letterboxed 9:16 in taller screen, or a black overlay view) | Force-fill / center-crop (`setForceFillTextureScaling(true)`) OR hunt a black overlay view drawn on top |
| **video shows edge-to-edge** | DONE | Switch window bg back to null, ship |

### Build / artifact
- Workflow: `.github/workflows/insta-diagnostic-build.yml`
- Patch script: `InstaTrueReel/patches/apply_diagnostic.py`
- Artifact name: `InstaTrueReel-diagnostic-apk`
- Patches applied: A-DIAG (window RED) + A1 + A2 + A3 + A5 + A7 + B1 + B2.
  Skipped C / D / CS1 (focused status-bar diagnostic; comment-bar fix is next round).

### Open question still unresolved: what does `47l.run()` paint?
`2ZS.A00` posts a `47l` Runnable with the color (A7 forces it to 0/transparent).
The prior note calls 47l the "swipe_nav painter" (bottom) — if so it doesn't
touch the status-bar region and the diagnostic colors persist there. If 47l
also paints decorView/content, A7 (transparent) would make them transparent,
revealing window RED below — still a valid (RED) signal. Either way the
diagnostic gives usable data. `47l.smali` was NOT in the smali-extraction set;
extract it next round if the diagnostic is inconclusive.

### Comment bar (round 2, after status-bar data)
The CS1 patch (transparent nav bar for bottom sheets via
`BottomSheetFragment.A05 → A0R(0)`) reportedly failed. Likely causes to
investigate next round, AFTER the status-bar diagnostic resolves:
- `AbstractC109183lH.A0R(0)` may STILL early-return (the sentinel check
  might be `i != 0` not `i == 255`; re-read `3lH.smali`).
- The `G28` inset listener adds bottom padding = nav-bar-height to
  `bottomSheetContainer` — even with a transparent nav bar, that padding gap
  shows the window bg (now RED in diagnostic; if the comment-bar strip turns
  RED → confirmed nav-bar-color path; fix = also zero the G28 bottom padding).

### Process status
- Diagnostic workflow will be triggered once committed.
- Awaiting: user installs diagnostic APK, screenshots a reel, reports the
  status-bar strip color. That single data point picks the next branch.
## 2026-08-20 — STEP 13: real jadx analysis (156k Java files) + v2 diagnostic

### What this pass did differently (user feedback)
User pointed out I was "compromising" — working only off the small 580 KB
smali-extraction artifact instead of downloading the MAIN 150 MB jadx artifact
(156k Java files). Corrected: downloaded the jadx artifact (157 MB zip →
192 MB inner zip → 1.1 GB p002X/ Java + com/instagram/), downloaded the actual
APK (240 MB) via LFS media URL, apktool-decoded resources (1.9 GB), and
dispatched 3 PARALLEL subagents (3-A, 3-B, 3-C) to analyze the real Java.

### THE ROOT CAUSE (found from real Java, not prior notes)
3 subagents independently confirmed:
1. **`2ZS.A01` is NOT called by InstagramMainActivity at startup.** It's only
   called by `ClipsTabFragment.onResume` (Reels tab) + 2 rare dialog fragments.
   `InstagramMainActivity.java` (540 KB / 8792 lines) has ZERO references to
   C2ZS. So our v1 A-DIAG block (window bg=RED) in 2ZS.A01 NEVER ran on the
   home feed → no RED → user saw black. [3-A]
2. **The ACTUAL startup chrome path is** `InstagramMainActivity.A1z()`
   (onResumePostSuper, Java ~line 7232):
   ```java
   if (c31610jSB4p == null || !c31610jSB4p.A0D)
       AbstractC54451fC.A03(this, getColor(igds_color_primary_background)); // home feed → BLACK
   else {
       AbstractC54451fC.A03(this, getColor(R.color.bds_transparent));         // Reels → transparent
       AbstractC54451fC.A05(this, false);
   }
   C54511fI.A01(this); // nav bar + scrim
   ```
   `1fC.A03` → calls `1fC.A04` (sets statusBarColor) + `1fC.A05` (sets
   systemUiVisibility). So `1fC.A04` IS called on EVERY screen. [3-A, 3-B]
3. **A5 (1fC.A04 → p1=0) IS working.** The status bar color IS transparent on
   all screens. But the user sees BLACK because the **window background is
   `?igds_color_primary_background = bds_black = #000000` (pure black)** — the
   theme default. The transparent status bar shows the black window bg beneath.
   [3-B, 3-C]
4. **Prior notes were WRONG about the color.** They said `igds_prism_black`
   (#0c1014 dark navy). The actual default is `bds_black` (#000000 pure black),
   applied via the `IgdsSemanticColorsDark` overlay. This matches the user's
   screenshot showing PURE BLACK, not #0c1014. [3-B, 3-C]
5. **No black overlay view exists** in the Reels layout. The
   `layout_activity_main_internal_viewpager2.xml` has `swipeable_tab_view_pager`
   as `match_parent x match_parent` with no top margin/padding/background. The
   black strip is 100% the window background showing through the transparent
   status bar. [3-C]

### v1 failure explained
v1 put `window.setBackgroundDrawable(RED)` in `2ZS.A01` (Reels-only). Since
`2ZS.A01` is NOT called by MainActivity at startup, the window bg stayed
#000000 (theme default) on the home feed. On Reels, A01 IS called, so RED
should have shown — but the user either didn't navigate to Reels, or the
:202/:410 re-paints overrode it. Either way, the hook was wrong.

### v2 CORRECTION: move the RED block to 1fC.A04
`1fC.A04` is called on EVERY screen (home feed + Reels) via
`MainActivity.A1z → 1fC.A03 → 1fC.A04`. Inserting the window-bg-RED +
FLAG_LAYOUT_NO_LIMITS + decorView-transparent block at the START of A04
guarantees it fires globally. Combined with A5 (p1=0, merged into the same
block), this makes the status bar transparent + window bg RED on every screen.

### v2 diagnostic (this round)
- Patch script: `InstaTrueReel/patches/apply_diagnostic_v2.py`
- Workflow: `.github/workflows/insta-diagnostic-v2-build.yml`
- Artifact: `InstaTrueReel-diagnostic-v2-apk`
- Patches: A5v2 (1fC.A04 → window RED + LAYOUT_NO_LIMITS + statusbar 0 +
  decorView 0, ALL screens) + A1 + A2 + A3 + A7 + B1 + B2.
- Dry-run: all patches apply cleanly against real smali.

### EXPECTED v2 result (ANY screen — home feed OR Reels)
- **RED strip** → 1fC.A04 runs + window bg is the layer → fix = null window
  bg + FLAG_LAYOUT_NO_LIMITS (so content fills the status bar region).
- **BLACK strip** → 1fC.A04 not called (unlikely, 3 subagents confirmed it is)
  OR FLAG_FULLSCREEN from 1fC.A05(false) hides the bar → deeper dig.
- **video shows** → DONE.

### Comment bar (CS2) — still pending
The Task 2 subagent found `3lH.A0R(I)V` line 461 unconditionally calls
`1fI.A05(activity, true)` → `setNavigationBarContrastEnforced(true)` → Android
auto-adds a black scrim. Fix = change L461 `const/4 v0, 0x1` → `const/4 v0, 0x0`.
Will ship in the NEXT build (after status-bar v2 diagnostic resolves), combined
with the status-bar fix.
