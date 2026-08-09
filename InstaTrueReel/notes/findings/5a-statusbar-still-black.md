# 5-a — Why is the status bar STILL black after patches A1/A2/A3?

**Agent:** Explore (sub-agent)
**Task:** Diagnose why the Reels status bar is still a solid black strip after
the three Feature-A patches (A1 zeroed decorView bg in C2ZS.A01; A2 zeroed
android.R.id.content bg in C2ZS.A05; A3 zeroed top inset in C6BM.Fji pswitch_3).

## TL;DR (root cause)

**All three patches are bypassed at runtime for the Reels tab.** The bug is
that patch A1 was inserted in the WRONG BRANCH of `C2ZS.A01`:

- `C2ZS.A01` (smali `X/2ZS.smali:59-310`) has a 2-way branch at line 198:
  `if-eqz v0, :cond_5` where `v0 = 2ZS.A08(activity)`.
- `2ZS.A08` (line 464-489) returns **0** (false) when the activity contains
  view `R.id.swipe_navigation_container` (id `0x7f0b3f31`, decoded earlier
  from `/tmp/insta-res-only/res/values/public.xml` — full apktool decode
  performed during this exploration; temp dir was cleaned after capture to
  free inodes).
- `swipe_navigation_container` is the top-level container of
  InstagramMainActivity (confirmed in
  `/tmp/insta-res-only/res/layout/layout_activity_main_coordinator_layout_viewpager2.xml:4`).
- Therefore `A08` ALWAYS returns 0 for InstagramMainActivity → control flow
  ALWAYS jumps to `:cond_5` (line 213) → our A1 patch at line 202-203
  (`const/4 v3, 0x0` inserted before `0cW.A0R`) is **NEVER executed**.

The bypassed patch means `v3` keeps its original value (`igds_color_primary_background`
= BLACK, resolved at line 87-91 from attr `0x7f0407af`). This BLACK `v3` then:

1. **Repaints the activity content BLACK** at line 214:
   `invoke-static {p0, v3}, LX/2ZS;->A00(Landroid/app/Activity;I)V` — which
   posts `X/47l.run()` (`/home/z/insta-orig/smali_classes17/X/47l.smali:30-51`)
   that calls `0cW.A0R(findViewById(0x7f0b3f31), color, ...)` = paints
   `swipe_navigation_container` BLACK.
2. **Sets the status bar color BLACK** at line 286:
   `invoke-static {p0, v3}, LX/1fC;->A04(Landroid/app/Activity;I)V` — which
   calls `window.setStatusBarColor(p1)` (`X/1fC.smali:322`).

Patch A2 (in `C2ZS.A05`) is similarly dead — `A05` is only called from
`C2ZS.A01:207` (inside the same bypassed cond_4 fall-through) and from
`C2ZS.A0A:1001,1028` (only during tab swipe gestures, not on Reels onResume).

Patch A3 (in `C6BM.Fji pswitch_3`) DOES run for MainActivity
(`IgFragmentActivity.A1k` at smali line 1267 registers `6BM(this, 0)` →
pswitch_3), so the top inset IS being zeroed. But zeroing the top inset
alone does NOT make the video extend behind the status bar, because
(a) the status bar color is still being set BLACK (see #2 above), and
(b) `setDecorFitsSystemWindows(true)` was reset by `AIQ` at activity creation
(per worklog 3-b), so the content area is still constrained to NOT extend
under the status bar — even with zero top padding.

## Q1 — Does C2ZS.A01 actually run for the Reels tab?

**YES, A01 runs, but our patch inside A01 is bypassed.**

`ClipsTabFragment.onResume` (`/home/z/insta-orig/smali_classes16/X/AFt.smali:2564`)
calls at line 2598:
```
invoke-static {v3, p0, v2, v1, v0}, LX/2ZS;->A02(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;ZZ)V
```
with `v1=1, v0=0` (line 2594-2596).

`C2ZS.A02` (`X/2ZS.smali:312-342`) is a thin delegator that resolves
`igds_color_clips_tab_bar_icon` (attr `0x7f040714`) to a color int (line 325-331)
and calls `C2ZS.A01` at line 339 with:
- `p3 = color int` (status bar / chrome color)
- `p4 = 1` (clips bg flag — set from A02.p3)
- `p5 = 0` (set from A02.p4)
- `p6 = 0` (hardcoded at A02:317)

So A02 → A01 with `p5=0, p6=0`. A01 DOES run on Reels onResume.

Inside A01, the relevant control flow (line numbers are smali line numbers in
`/home/z/insta-orig/smali_classes17/X/2ZS.smali`):

```
 59: .method public static final A01(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;IZZZ)V
...
 87:    const v0, 0x7f0407af           # igds_color_primary_background attr
 89:    invoke-static {v1, v0}, LX/0bF;->A0W(Landroid/content/Context;I)I
 91:    move-result v3                 # v3 = BLACK igds_color_primary_background
...
165:    if-eqz v0, :cond_7             # if 1fI.A05==false (default), goto cond_7
...
223:    :cond_7
224:    invoke-static {}, LX/3sA;->A02()Z
228:    if-eqz v0, :cond_8             # gated on 3sA.A02() (likely "is prod")
...
257:    const/high16 v0, -0x80000000   # FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS
259:    invoke-virtual {v1, v0}, Landroid/view/Window;->addFlags(I)V
...
267:    if-eq v0, v3, :cond_3          # if navBarColor==v3, skip setNavigationBarColor
269:    :cond_a
270:    invoke-virtual {v1, v3}, Landroid/view/Window;->setNavigationBarColor(I)V
272:    goto :goto_0
...
169:    :cond_3
170:    :goto_0
171:    invoke-static {p0, v2}, LX/1fI;->A05(Landroid/app/Activity;Z)V   # nav bar icons
173:    invoke-virtual {p0}, Landroid/app/Activity;->getWindow()Landroid/view/Window;
175:    move-result-object v6
177:    if-eqz v6, :cond_e
179:    invoke-virtual {v6}, Landroid/view/Window;->getDecorView()Landroid/view/View;
181:    move-result-object v1
...
193:    :cond_4
194:    invoke-static {p0}, LX/2ZS;->A08(Landroid/app/Activity;)Z   # check swipe_nav exists
196:    move-result v0
198:    if-eqz v0, :cond_5         # ★ if A08==0 (swipe_nav EXISTS), JUMP to cond_5
                                     # ★ For InstagramMainActivity, A08==0 ALWAYS → JUMP

# === cond_4 fall-through (SKIPPED for MainActivity) ===
200:    const v0, -0x92e8ab6
202:    # InstaTrueReel: decorView transparent     ← OUR A1 PATCH (DEAD!)
203:    const/4 v3, 0x0
205:    invoke-static {v1, v3, v0}, LX/0cW;->A0R(Landroid/view/View;II)V   # decorView=0
207:    invoke-static {p0, p2, v3}, LX/2ZS;->A05(...)V                     # A05 with v3=0
209:    sget-boolean v0, LX/1un;->A00:Z
211:    if-eqz v0, :cond_6         # if 1un.A00==false, skip A00 call

# === cond_5 (TAKEN for MainActivity) ===
213:    :cond_5
214:    invoke-static {p0, v3}, LX/2ZS;->A00(Landroid/app/Activity;I)V     # ★ paints swipe_nav with v3=BLACK
216:    :cond_6
217:    if-eqz p5, :cond_b         # p5=0 (Reels A02 path) → JUMP to cond_b
219:    invoke-static {v1, v6, v2}, LX/1fC;->A06(...)V                     # SKIPPED (p5=0)
221:    return-void

# === cond_b (Reels path) ===
274:    :cond_b
275:    invoke-static {v1, v6}, LX/1fC;->A09(...)Z   # query: status bar already transparent?
277:    move-result v0
279:    if-nez v0, :cond_c         # if A09==1 (status bar NOT transparent), SKIP A06
281:    invoke-static {v1, v6, v4}, LX/1fC;->A06(...)V   # SKIPPED (A09 returns 1 by default)
283:    :cond_c
284:    if-nez p6, :cond_d         # p6=0 → fall through to A04 call
286:    invoke-static {p0, v3}, LX/1fC;->A04(Landroid/app/Activity;I)V   # ★ setStatusBarColor(v3=BLACK)
288:    :cond_d
289:    invoke-static {p0, v2}, LX/1fC;->A05(Landroid/app/Activity;Z)V   # set icons (v2=0)
291:    return-void
```

So for Reels onResume, the actual sequence is:
1. **Line 214**: `2ZS.A00(activity, v3=BLACK)` → posts `47l.run()` that calls
   `0cW.A0R(findViewById(0x7f0b3f31), BLACK, 0x6bad5ee0)` →
   `swipe_navigation_container.setBackgroundColor(BLACK)`.
2. **Line 286**: `1fC.A04(activity, v3=BLACK)` → eventually calls
   `window.setStatusBarColor(BLACK)` (deferred via `9wE` Choreographer callback
   in `1fC.smali:296-308`, OR directly at `1fC.smali:322` if `1fC.A01==false`).

Both call sites use `v3` which was NEVER zeroed because our patch was inserted
in the bypassed cond_4 fall-through.

## Q2 — Where is `setStatusBarColor` called?

All paths funnel through `1fC.A04(activity, color)` (smali
`/home/z/insta-orig/smali_classes13/X/1fC.smali:212-334`). At line 322:
`invoke-virtual {v3, p1}, Landroid/view/Window;->setStatusBarColor(I)V`.

The deferer (`1fC.A01==true` branch, lines 237-308) wraps the call in a
Choreographer frame callback via `9wE` and `ktp` — but the end result is the
same: `window.setStatusBarColor(p1)`.

**Direct `1fC.A04` callers** (rg `LX/1fC;->A04\(`):
| File:line | Caller context | Color passed |
|-----------|---------------|--------------|
| `X/2ZS.smali:286` | **C2ZS.A01 Reels enter (cond_b → cond_d)** | `v3 = BLACK` (because A1 patch bypassed) |
| `X/2ZS.smali:724` | C2ZS.A0A swipe interpolator | `v2 = interpolated color` |
| `X/2ZS.smali:1038` | C2ZS.A0B exit Reels | `v4 = igds_color_primary_background (BLACK)` |
| `IgFragmentActivity.smali:1223` | `A1j` (gated on `A26()`==true, which is FALSE for MainActivity) | `v2 = BLACK` |
| `X/fcx.smali:331`, `X/lti.smali:33`, `X/qfa.smali:2220`, `X/IlS.smali:496,689`, `X/IbC.smali:874`, `X/BvI.smali:713` | Various feature code | mixed |
| `LoggedOutAppActivity.smali:298,516`, `OnBoardingExperienceTransparentModalActivity.smali:91` | Logged-out / onboarding | various |
| `StatusBarAnimationEffectKt$...$3$1.smali:96` | Status bar animation effect | animated color |

**Indirect `1fC.A03` callers** (A03 wraps A04, also calls `1fC.A05` for icons):

The 4 InstagramMainActivity calls (jadx lines 3256, 7234 per worklog 3-b):
| Smali file:line | Method | Color | Gate |
|-----------------|--------|-------|------|
| `InstagramMainActivity.smali:20254` | `A0m` (static helper) | `bds_transparent` (`0x7f0600a9`) | `0jS.A0D == 1` |
| `InstagramMainActivity.smali:21075` | `A0m` (fall-through) | `igds_color_primary_background` (BLACK) | `0jS.A0D != 1` |
| `InstagramMainActivity.smali:35539` | `A1z` (= internalOnResume) | `bds_transparent` | `0jS.A0D == 1` |
| `InstagramMainActivity.smali:36401` | `A1z` (fall-through) | `igds_color_primary_background` (BLACK) | `0jS.A0D != 1` |

Color resource `0x7f0600a9` is `bds_transparent = #00000000` (verified earlier
in `/tmp/insta-res-only/res/values/colors.xml` — temp dir cleaned after capture).
Color attr `0x7f0407af` is `igds_color_primary_background` (BLACK in dark theme,
verified earlier in `/tmp/insta-res-only/res/values/public.xml`).
Helper `0bF.A0O(context)` (smali `X/0bF.smali:351-361`) returns the color
resource ID for attr `0x7f0407af`.

**Critical finding: `0jS.A0D`** (smali `/home/z/insta-orig/smali_classes13/X/0jS.smali:33`):
- Set to `true` by `0jS.A15(int)` (smali line 5697-5702: `const/4 v0, 0x1; iput-boolean v0, p0, LX/0jS;->A0D:Z`).
- `0jS.A15` is called from:
  - `6BM.smali:43` — the DEFAULT case of `Fji`'s packed-switch (when `$t > 7`).
  - `6BM.smali:223` — `pswitch_5` (when `$t == 5`).
  - `X/Esf.smali:169`, `X/2Iv.smali:2244` — direct callers.
- `pswitch_5` is registered by `X/2Iv.smali:2151` (`new 6BM(this, 5)`).
  `2Iv` is the **ClipsViewer presenter** (has field `A0o:Lcom/instagram/clips/intf/ClipsViewerConfig;` at line 2159).
- BUT `2Iv.A0A` (which registers the `6BM(this, 5)` listener) is gated on `9Wz.EEr()` (line 2137).
  `EEr()` (smali `X/9Wz.smali:36584`) checks three flags: `ClipsViewerConfig.A2g`,
  `ClipsViewerConfig.A3H`, and MobileConfig `0x8109d400023873`. If ALL are false
  (likely the basic Reels-tab case), `EEr()` returns false → `2Iv.A0A` goes to
  cond_0 (line 2158) which has further conditions on `is_cold_start_reel_tab`,
  `2IW.A0i`, etc.

**Conclusion for Q2:** For the basic Reels-tab case where `0jS.A0D` never gets
set to `true`, `InstagramMainActivity.A1z` (onResume) calls
`1fC.A03(activity, BLACK)` at line 36401 — setting the status bar BLACK.
Even when `0jS.A0D == 1` (Reels viewer with proper config), `A1z` sets the
status bar to `bds_transparent` — but then `ClipsTabFragment.onResume` runs
AFTER `A1z` (Fragment.onResume comes after Activity.onResume), and
`C2ZS.A01:286` RE-PAINTS the status bar BLACK via `1fC.A04(activity, v3=BLACK)`.
So `C2ZS.A01:286` is the LAST writer, and it ALWAYS writes BLACK (because our
A1 patch is bypassed).

## Q3 — Where is the top inset applied?

**Patch A3 IS in the right place for the IgFragmentActivity case** — but
zeroing the top inset alone is insufficient.

- `IgFragmentActivity.A1k` (smali `/home/z/insta-orig/smali/com/instagram/base/activity/IgFragmentActivity.smali:1246-1273`)
  registers `new 6BM(this, 0)` at line 1265-1267. `$t = 0` → `pswitch_3` in
  `Fji`.
- `6BM.Fji` (smali `/home/z/insta-orig/smali_classes15/X/6BM.smali:32-298`):
  `pswitch_3` is at line 131. Flow:
  ```
  131: :pswitch_3
  132: iget-object v3, p0, LX/6BM;->A00:Ljava/lang/Object;
  134: check-cast v3, Lcom/instagram/base/activity/IgFragmentActivity;
  136: const v0, 0x1020002                # android.R.id.content
  138: invoke-virtual {v3, v0}, ...->findViewById(I)Landroid/view/View;
  140: move-result-object v1              # v1 = content view
  146: check-cast v1, Landroid/view/ViewGroup;
  148: const/4 v0, 0x0
  150: invoke-virtual {v1, v0}, Landroid/view/ViewGroup;->getChildAt(I)Landroid/view/View;
  152: move-result-object v2              # v2 = first child of content
  154: if-eqz v2, :cond_2
  156: instance-of v0, v3, Lcom/instagram/modal/ModalActivity;
  158: if-eqz v0, :cond_3                 # NOT ModalActivity → cond_3
  ...
  189: :cond_3
  190: # InstaTrueReel: zero top inset    ← OUR A3 PATCH (CORRECTLY PLACED)
  191: const/4 p1, 0x0
  193: invoke-static {v2, p1, p2}, LX/6wm;->A0w(Landroid/view/View;II)V
                                             # setPadding(left, 0=top, right, bottom)
  195: goto :goto_0
  ...
  178: :cond_2
  179: :goto_0
  179: invoke-virtual {v3}, Lcom/instagram/base/activity/IgFragmentActivity;->A26()Z
  183: if-eqz v0, :cond_0                 # if A26==false, return (don't call A1j)
  185: invoke-virtual {v3}, ...->A1j()V
  187: return-void
  ```

- `6wm.A0w(view, p1, p2)` (smali `/home/z/insta-orig/smali_classes2/X/6wm.smali:3386-3420`)
  calls `view.setPadding(left, p1, right, p2)` (line 3414). So our A3 patch
  zeroes the TOP padding of the content view's first child. ✓ Correct.

- `IgFragmentActivity.A26` (smali `IgFragmentActivity.smali:4480-4530`) checks
  theme attrs `windowBackground` (`0x1010054`) and `statusBarColor` (`0x1010058`).
  Returns TRUE only if `statusBarColor == 0` (transparent in theme). For
  Theme.Instagram (`statusBarColor = ?igds_color_primary_background` = BLACK),
  `A26` returns FALSE → `A1j` is NOT called from `6BM.Fji`.

- `IgFragmentActivity.A1j` (smali line 1192-1244) paints BOTH the status bar
  (via `1fC.A04` at line 1223) AND the decorView (via `0cW.A0R` at line 1236
  with hash `0x4fc7fdb0`) BLACK. But since `A26==false` for MainActivity, `A1j`
  is NOT called from `6BM.Fji`. (A1j may be called from elsewhere — but
  rg shows no other callers in IgFragmentActivity itself; only `6BM.Fji:185`.)

- **OTHER inset listeners** (rg `invoke-direct.*LX/6BM;-><init>`):
  - `X/JAi.smali:2033` — `$t`=? (need to verify; class is in smali_classes18)
  - `X/4b8.smali:94` — `$t`=? (4b8 is Story viewer base)
  - `DirectAggregatedMediaViewerController.smali:688, 2339` — `$t`=? (Direct media viewer)
  - `ModalActivity.smali:353` — `$t`=? (ModalActivity)
  - `X/7xj.smali:1598` — `$t`=? (class in smali_classes16)
  - `X/2Iv.smali:2151` — `$t=5` → pswitch_5 → `0jS.A15(topInset)` (ClipsViewer presenter)
  - `X/0zL.smali:464` — `$t`=? (class in smali_classes13)
  - `IgFragmentActivity.smali:1267` — `$t=0` → pswitch_3 (our A3 target)
- For the Reels TAB specifically, the only relevant listener is `IgFragmentActivity`'s
  (`$t=0` → pswitch_3, our A3 patch). The `2Iv` listener (`$t=5`) only registers
  when `9Wz.EEr()` returns true (clips viewer config flags), which is NOT the
  default Reels-tab case.

**Conclusion for Q3:** A3 is correctly placed. But zeroing top padding alone
is insufficient because:
- The system still applies the top inset as padding to `decorView`'s content
  child (because `setDecorFitsSystemWindows(true)` was reset by `AIQ`).
- The content view's first child (`swipe_navigation_container`) is painted
  BLACK by `2ZS.A00` (line 214, which our A1 patch was supposed to prevent
  but doesn't).

## Q4 — What does the activity theme set?

Decoded earlier from `/tmp/insta-res-only/res/values/styles.xml` (full apktool
decode of `insta.apk`; temp dir cleaned after capture to free inodes):

```
<style name="Theme.Instagram" ...>
    <item name="android:statusBarColor">?igds_color_primary_background</item>  # BLACK
    <item name="android:colorBackground">?igds_color_primary_background</item> # BLACK
    <item name="android:windowBackground">?igds_color_primary_background</item># BLACK
    ...
</style>
```

(Manifest theme chain per worklog 4-e: `Base.Theme.Launcher` → `Theme.Instagram`.)

So at startup:
- `window.statusBarColor` = BLACK (from theme).
- `window.windowBackground` = BLACK (from theme) — paints behind everything
  if nothing else covers it.
- `window.colorBackground` = BLACK.

Runtime overrides needed:
- `window.setStatusBarColor(0)` — to clear the BLACK status bar color.
- `decorView.setBackgroundColor(0)` — to clear any BLACK on the decorView.
- `setDecorFitsSystemWindows(false)` — to let the content view extend under
  the status bar (otherwise the status bar area shows the window's BLACK
  background even when `statusBarColor == 0`).

IG already has a helper that does ALL of this:
`AbstractC72042Ib.A01` (smali `X/2Ib.smali:38-84`):
```
38: .method public static final A01(Landroid/view/Window;Z)V
...
43:    const/high16 v0, 0xc000000            # FLAG_TRANSLUCENT_STATUS|FLAG_TRANSLUCENT_NAVIGATION
45:    invoke-virtual {p0, v0}, Landroid/view/Window;->clearFlags(I)V
47:    const/high16 v0, -0x80000000          # FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS
49:    invoke-virtual {p0, v0}, Landroid/view/Window;->addFlags(I)V
51:    const/4 v2, 0x0
53:    invoke-virtual {p0, v1=0}, Landroid/view/Window;->setDecorFitsSystemWindows(Z)V   # false
55:    invoke-virtual {p0, v1=0}, Landroid/view/Window;->setStatusBarColor(I)V           # 0 (transparent)
57:    invoke-virtual {p0, v1=0}, Landroid/view/Window;->setNavigationBarColor(I)V       # 0 (transparent)
59:    invoke-virtual {p0, v1=0}, Landroid/view/Window;->setStatusBarContrastEnforced(Z)V
61:    invoke-virtual {p0, v1=0}, Landroid/view/Window;->setNavigationBarContrastEnforced(Z)V
...
80:    invoke-interface {v1, v2, v0=0x18}, ...->setSystemBarsAppearance(II)V              # APPEARANCE_LIGHT_STATUS_BARS | NAVIGATION_BARS (white icons)
```

This is the SAME helper used by IG's splash screen (`AbstractC72042Ib.A01`,
per worklog 3-b). It's the official IG way to enable full edge-to-edge.
**We can call it from `ClipsTabFragment.onResume` to re-enable edge-to-edge
that `AIQ` reset.**

Note: passing `p1=false` (the second arg) makes `v2 = 0x18` (LIGHT icons,
i.e., white icons on dark background — what we want for Reels). Passing `p1=true`
makes `v2 = 0` (dark icons).

## Q5 — The REAL fix: minimal set of additional smali patches

### PATCH 1 (NEW, critical): Move A1 zeroing to BEFORE the cond_5 branch.

**File:** `/home/z/insta-orig/smali_classes17/X/2ZS.smali`
**Current A1 patch location:** lines 202-203 (inside the cond_4 fall-through,
which is bypassed for MainActivity).

**Proposed change:** insert `const/4 v3, 0x0` between line 196 and line 198,
i.e., immediately BEFORE `if-eqz v0, :cond_5`:

```diff
 193:    :cond_4
 194:    invoke-static {p0}, LX/2ZS;->A08(Landroid/app/Activity;)Z
 195:
 196:    move-result v0
 197:
+        # InstaTrueReel: zero chrome color so both branches paint transparent
+        const/4 v3, 0x0
+
 198:    if-eqz v0, :cond_5
```

**Effect:**
- v3 is now 0 regardless of which branch is taken.
- Line 214 (cond_5, taken for MainActivity): `2ZS.A00(activity, 0)` → 47l.run()
  paints `swipe_navigation_container` TRANSPARENT instead of BLACK. ✓
- Line 286 (cond_b → cond_d): `1fC.A04(activity, 0)` → `window.setStatusBarColor(0)`
  → status bar TRANSPARENT. ✓
- Lines 200-205 (cond_4 fall-through, dead for MainActivity but still active
  for other activities that lack `swipe_navigation_container`): unchanged —
  our existing patch is now redundant but harmless.
- Lines 87-91 still resolve `v3 = igds_color_primary_background` (BLACK) —
  but it's overwritten to 0 before use. (No need to remove the resolve.)

**Optional cleanup:** remove the redundant `const/4 v3, 0x0` at line 203
(our existing A1 patch), since v3 is now zeroed earlier. Leaving it is harmless.

### PATCH 2 (NEW, required for "video behind status bar"): Enable edge-to-edge.

Pick ONE of:

**Option 2a (cleanest, recommended):** Call `2Ib.A01(window, false)` at the
start of `ClipsTabFragment.onResume` (before `2ZS.A02`).
**File:** `/home/z/insta-orig/smali_classes16/X/AFt.smali`
**Method:** `onResume` (line 2564)
**Insert after line 2580** (`invoke-super {p0}, LX/2yN;->onResume()V`)
and before line 2598 (`invoke-static {v3, p0, v2, v1, v0}, LX/2ZS;->A02(...)`):

```smali
    # InstaTrueReel: enable edge-to-edge (transparent system bars + content under status bar)
    invoke-virtual {v3}, Landroid/app/Activity;->getWindow()Landroid/view/Window;
    move-result-object v0
    const/4 v1, 0x0
    invoke-static {v0, v1}, LX/2Ib;->A01(Landroid/view/Window;Z)V
```

This single helper call:
- `setDecorFitsSystemWindows(false)` — content extends under status bar.
- `setStatusBarColor(0)` — status bar transparent.
- `setNavigationBarColor(0)` — nav bar transparent.
- Sets white icons (LIGHT appearance).
- Clears `FLAG_TRANSLUCENT_*`, adds `FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS`.

After this call, `2ZS.A02` runs and re-paints some things (swipe_nav bg,
status bar color) — but with PATCH 1 applied, those re-paints use `v3=0`
(transparent), so they don't undo the edge-to-edge setup.

**Option 2b (alternative, no new helper call):** Force `1fC.A06(decorView,
window, true)` to be called in `C2ZS.A01` cond_b. Change line 279
`if-nez v0, :cond_c` to a no-op (e.g., `if-eqz v0, :cond_c` reversed, OR
just delete the `if-nez` so A06 always runs). This sets
`setSystemUiVisibility(FLAG_LAYOUT_FULLSCREEN)` on decorView (legacy
equivalent of `setDecorFitsSystemWindows(false)`).

Option 2a is preferred because it's a single helper call that does
everything correctly on all API levels, and it matches what IG itself does
during the splash screen.

### PATCH 3 (NEW, optional but recommended): Prevent InstagramMainActivity.A1z from re-painting BLACK on next onResume.

Even with PATCH 1 + PATCH 2, when the user leaves Reels and comes back,
`InstagramMainActivity.A1z` (onResume) runs BEFORE `ClipsTabFragment.onResume`,
and at line 36401 it calls `1fC.A03(activity, BLACK)` (because `0jS.A0D` may
not be set to true for the Reels tab). This re-paints the status bar BLACK
momentarily until `ClipsTabFragment.onResume` runs PATCH 2 and resets it.

**File:** `/home/z/insta-orig/smali/com/instagram/mainactivity/InstagramMainActivity.smali`
**Method:** `A1z` (line 34713+)

Three sub-options:

**Option 3a (cleanest):** At smali line 35521 (`if-ne v1, v0, :cond_17`),
change the comparison so the transparent branch (line 35526-35539) is always
taken. Specifically change `if-ne v1, v0, :cond_17` to `goto :cond_16` (skip
the `0jS.A0D` check entirely, fall through to the transparent branch). The
transparent branch resolves `0x7f0600a9` = `bds_transparent` and calls
`1fC.A03(activity, bds_transparent)`.

**Option 3b:** Patch `0jS.A15` to be called unconditionally early — but this
requires finding the right place to trigger it (e.g., from
`IgFragmentActivity.A1k` after registering the `6BM` listener).

**Option 3c (broadest):** Patch `1fC.A04` itself to always call
`window.setStatusBarColor(0)` regardless of the `p1` argument. This is a
chokepoint — ALL callers (C2ZS.A01:286, A0B:1038, A0A:724, IgFragmentActivity.A1j:1223,
InstagramMainActivity.A1z, etc.) get transparent status bar. **CAVEAT:** this
affects ALL activities (login, modal, direct, etc.) — may break other UI
flows that depend on opaque status bar. Not recommended unless PATCH 1 + 2 + 3a
prove insufficient.

### PATCH 4 (existing A2): Can be removed.

Patch A2 (zero `p2` in `C2ZS.A05`) is dead code for the Reels path — `A05`
is only called from `C2ZS.A01:207` (inside the bypassed cond_4 fall-through)
and from `C2ZS.A0A:1001,1028` (during swipe). Safe to leave in place
(no effect) or remove.

### PATCH 5 (existing A3): Keep as-is.

Patch A3 (zero `p1` in `C6BM.Fji pswitch_3`) is correctly placed and DOES
run for MainActivity. With PATCH 2 (edge-to-edge enabled), `setDecorFitsSystemWindows(false)`
means the system no longer auto-applies the top inset as padding — so zeroing
`p1` is redundant but harmless. Keep it as a belt-and-suspenders measure
(in case `setDecorFitsSystemWindows(true)` is re-enabled by some other code path).

## Summary table: why each patch did/didn't work

| Patch | Target | Did it run for Reels? | Why |
|-------|--------|-----------------------|-----|
| A1 (zero v3 in C2ZS.A01) | `2ZS.smali:202-203` (inside cond_4 fall-through) | **NO** | `2ZS.A08` returns 0 for MainActivity (swipe_navigation_container exists) → control flow jumps to cond_5 (line 213), SKIPPING the patched block. |
| A2 (zero p2 in C2ZS.A05) | `2ZS.smali:413-414` | **NO** | `A05` is only called from `A01:207` (inside the bypassed cond_4) and from `A0A:1001,1028` (swipe gestures). Not called on Reels onResume. |
| A3 (zero p1 in C6BM.Fji pswitch_3) | `6BM.smali:190-191` | **YES** | `IgFragmentActivity.A1k:1267` registers `6BM(this, 0)` → pswitch_3 (line 131). Correctly placed. But alone insufficient — `setDecorFitsSystemWindows(true)` was reset by `AIQ`, so content still doesn't extend under status bar, AND `swipe_navigation_container` is still painted BLACK by `2ZS.A00` (line 214). |

## Concrete smali patches needed (file:line summary)

1. **`X/2ZS.smali:197` (insert before line 198)** — Add `const/4 v3, 0x0` before
   `if-eqz v0, :cond_5`. Makes both branches of A01 use v3=0, so:
   - line 214: `swipe_navigation_container` painted transparent.
   - line 286: `window.setStatusBarColor(0)`.
2. **`X/AFt.smali:2580` (insert after super.onResume, before 2ZS.A02)** — Add
   call to `2Ib.A01(window, false)` to enable full edge-to-edge
   (`setDecorFitsSystemWindows(false)` + transparent system bars + white icons).
3. **`InstagramMainActivity.smali:35521` (modify)** — Change the
   `if-ne v1, v0, :cond_17` gate to always take the transparent branch
   (line 35526-35539) so A1z doesn't re-paint BLACK on next onResume.
4. Existing A2 patch (`2ZS.smali:413-414`): **leave in place** (harmless, dead code).
5. Existing A3 patch (`6BM.smali:190-191`): **leave in place** (correctly placed, redundant after PATCH 2).

## Key resource IDs / hashes referenced

| ID | Name | Source |
|----|------|--------|
| `0x7f0b3f31` | `R.id.swipe_navigation_container` | `/tmp/insta-res-only/res/values/public.xml` (cleaned after capture) |
| `0x7f0b3f45` | `R.id.swipeable_tab_view_pager` | same |
| `0x7f0b3f67` | `R.id.tab_bar` | same |
| `0x1020002` | `android.R.id.content` | Android framework |
| `0x7f0407af` | `?igds_color_primary_background` (attr, BLACK) | same |
| `0x7f040713` | `?igds_color_clips_tab_bar_background` (attr, BLACK) | same |
| `0x7f040714` | `?igds_color_clips_tab_bar_icon` (attr, white-ish) | same |
| `0x7f0600a9` | `R.color.bds_transparent` = `#00000000` | `/tmp/insta-res-only/res/values/colors.xml` (cleaned) |
| `0x1010054` | `android.R.attr.windowBackground` | Android framework |
| `0x1010058` | `android.R.attr.statusBarColor` | Android framework |
| `0x1010451` | `android.R.attr.statusBarColor` (alt) | Android framework (used in `1fC.A00`) |
| `0x10104e0` | `android.R.attr.windowLightStatusBar` | Android framework (used in `1fC.A03`) |

## Smali class name mapping (jadx → smali)

| jadx name | Smali file | smali_classes dir |
|-----------|-----------|-------------------|
| C2ZS | `X/2ZS.smali` | smali_classes17 |
| C6BM | `X/6BM.smali` | smali_classes15 |
| AbstractC54451fC | `X/1fC.smali` | smali_classes13 |
| C54511fI | `X/1fI.smali` | smali_classes13 |
| AbstractC27310cW | `X/0cW.smali` | smali_classes13 |
| AbstractC72042Ib | `X/2Ib.smali` | smali_classes15 |
| C0jS / 0jS | `X/0jS.smali` | smali_classes13 |
| C192756wm | `X/6wm.smali` | smali_classes2 |
| C242418ug | `X/8ug.smali` | smali_classes15 (not verified) |
| ClipsTabFragment (C27528AFt) | `X/AFt.smali` | smali_classes16 |
| 2Iv (ClipsViewer presenter) | `X/2Iv.smali` | smali_classes17 |
| 9Wz (ClipsViewer host) | `X/9Wz.smali` | smali_classes16 |
| 47l (deferred bg paint runnable) | `X/47l.smali` | smali_classes17 |

READ-ONLY exploration complete. No patch code written.
