#!/usr/bin/env python3
"""
InstaTrueReel — apply_diagnostic.py  (STATUS-BAR MULTI-COLOR DIAGNOSTIC BUILD)

Runs AFTER `apktool d -r` (resources kept as binary), BEFORE `apktool b`.
Usage: python3 apply_diagnostic.py <decoded_dir>

WHY THIS BUILD EXISTS
--------------------
The prior builds (main `apply_patches.py` + `instatruereelsstatusbar/apply_patches.py`)
both left the status-bar region BLACK/white even though `setStatusBarColor(RED)`
proved our code runs and the status bar itself can be made transparent.

Two distinct root-cause bugs were identified by reading the real smali
(smali-extraction artifact) of `X/2ZS.smali`:

  1. MAIN script bug: `A-NO_LIMITS` sets `window.setBackgroundDrawable(null)` +
     `decorView.setBackgroundColor(0)` at the START of `2ZS.A01`, but the
     ORIGINAL A01 body then RE-PAINTS decorView at line :202 via
     `0cW.A0R(decorView, v3=themeColor, hash)` and content at :410 (via A05).
     On Android 10 `2ZS.A08()` returns TRUE (it returns FALSE only on SDK35+
     when a specific view exists), so the :202/:410 paints DO run and overwrite
     the transparent setup.  -> decorView ends up DARK  -> black strip.

  2. STATUSBAR script bug: it HAS the A1/A2 intercepts (zero v3 before :202,
     zero p2 before :410) so decorView+content become transparent — BUT its
     A6 block never calls `window.setBackgroundDrawable(null)`. So the theme's
     `windowBackground` (igds_color_primary_background = #ff0c1014, dark)
     shows through the now-transparent decorView/content in the status-bar
     region. -> dark strip.

  THE COMPLETE FIX = A1 (decorView :202 -> 0) + A2 (content :410 -> 0)
  + window.setBackgroundDrawable(null) + A3 + A5 + A7 + B1 + B2.

  BUT even the complete fix may still show BLACK if the video view does NOT
  actually extend into the status-bar region (inset/padding pushes it down) —
  in that case all bg layers are transparent and you see the bare window
  surface (black).  Or it may show BLACK if the video DOES extend but a 9:16
  video letterboxed into a ~20:9 screen leaves a black bar at the top.

THIS DIAGNOSTIC BUILD
--------------------
Same as the complete fix, BUT `window bg = RED ColorDrawable` (0xFFFF0000)
instead of null.  Then ONE screenshot of a reel playing tells us exactly
which case we are in:

  * RED strip in status-bar region
      -> A1/A2 applied correctly (decorView+content transparent) AND the
         video does NOT reach the status-bar region.
      -> NEXT: find & zero the inset/padding that pushes the video down
         (the A3 6BM patch is insufficient or wrong target; hunt the real
         OnApplyWindowInsetsListener / fitsSystemWindows on the reels root).

  * DARK (theme color #0c1014, NOT red)
      -> A1 and/or A2 FAILED to apply (find-replace pattern mismatch).
      -> NEXT: re-check the smali patterns, fix the patch.

  * BLACK (pure #000000) strip
      -> A1/A2 applied, video DOES reach the status-bar region, but the
         video itself is black there (letterboxed 9:16 in a taller screen,
         or a black overlay view on top).
      -> NEXT: force-fill / center-crop the video (setForceFillTextureScaling)
         OR hunt a black overlay view.

  * The reel video is visible edge-to-edge behind the (transparent) status bar
      -> DONE — switch window bg back to null and ship.

This build also keeps B1 + B2 (the WORKING main bottom-nav patches) so the
main nav stays transparent during the test.

Patch set:
  A-DIAG : 2ZS.A01 start  -> window bg = RED, statusbar 0, FLAG_LAYOUT_NO_LIMITS
  A1     : 2ZS.A01 :202   -> const/4 v3, 0x0  (decorView 0cW.A0R -> transparent)
  A2     : 2ZS.A05 :410   -> const/4 p2, 0x0  (content  0cW.A0R -> transparent)
  A3     : 6BM Fji        -> zero top inset before setPadding
  A5     : 1fC.A04 start  -> const/4 p1, 0x0  (all setStatusBarColor -> 0)
  A7     : 2ZS.A00 start  -> const/4 p1, 0x0  (47l swipe_nav painter -> 0)
  B1     : InstagramMainActivity -> zero swipeable_tab_view_pager bottomMargin
  B2     : 0bQ.A04        -> const/4 v1, 0x0 before each 0cW.A0R (tab bar bg)
(SKIP C / D / CS1 — focus on the status-bar diagnostic.)
"""

import os, re, sys, glob


def find_smali(decoded, name):
    """Find a .smali file by name across all smali_classes dirs."""
    for d in sorted(glob.glob(os.path.join(decoded, 'smali*'))):
        for root, _, files in os.walk(d):
            if name in files:
                return os.path.join(root, name)
    return None


def patch_text(filepath, old, new, label):
    """Single find-and-replace. Returns True if applied."""
    if not filepath or not os.path.exists(filepath):
        print(f"  X {label}: file not found")
        return False
    with open(filepath) as f:
        c = f.read()
    if old in c:
        c = c.replace(old, new, 1)
        with open(filepath, 'w') as f:
            f.write(c)
        print(f"  + {label}: applied")
        return True
    print(f"  ~ {label}: pattern not found (may already be patched)")
    return False


# smali snippet: window bg = RED ColorDrawable (0xFFFF0000)
# v0 = window, v1 = ColorDrawable, v2 = color int
RED_WIN_BG_SMALI = (
    '    # InstaTrueReel DIAG: window bg = RED ColorDrawable (0xFFFF0000)\n'
    '    new-instance v1, Landroid/graphics/drawable/ColorDrawable;\n'
    '    const v2, 0xffff0000\n'
    '    invoke-direct {v1, v2}, Landroid/graphics/drawable/ColorDrawable;-><init>(I)V\n'
    '    invoke-virtual {v0, v1}, Landroid/view/Window;->setBackgroundDrawable(Landroid/graphics/drawable/Drawable;)V\n'
)


def main():
    decoded = sys.argv[1] if len(sys.argv) > 1 else 'decoded'
    print("=" * 60 + "\nInstaTrueReel DIAGNOSTIC — applying patches (status-bar probe)\n" + "=" * 60)

    # == Feature A: status-bar diagnostic =================================
    print("\n-- Feature A: status-bar diagnostic --")
    zs = find_smali(decoded, '2ZS.smali')

    # A-DIAG: insert at the very START of 2ZS.A01 (runs unconditionally, before
    # any original painting). Sets: FLAG_LAYOUT_NO_LIMITS, statusbar transparent,
    # window bg = RED ColorDrawable, decorView transparent. Uses only v0/v1/v2
    # (A01 is .locals 7, so v0-v6 are free; original code re-inits v2 next).
    patch_text(zs,
        '.method public static final A01(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;IZZZ)V\n    .locals 7\n\n    const/4 v2, 0x0',
        '.method public static final A01(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;IZZZ)V\n    .locals 7\n\n'
        '    # === InstaTrueReel DIAGNOSTIC: multi-color status-bar probe ===\n'
        '    # window bg=RED, decorView bg=transparent(0); A1/A2 make the :202/:410\n'
        '    # 0cW.A0R paints also transparent. Result in status-bar region:\n'
        '    #   RED   -> A1/A2 worked + video does NOT reach bar (fix insets)\n'
        '    #   DARK  -> A1/A2 failed (fix patch patterns)\n'
        '    #   BLACK -> video reaches but letterboxes (fix force-fill crop)\n'
        '    #   video -> DONE\n'
        '    invoke-virtual {p0}, Landroid/app/Activity;->getWindow()Landroid/view/Window;\n'
        '    move-result-object v0\n'
        '    if-eqz v0, :itre_diag_skip\n'
        '    const/high16 v1, 0x2000000\n'
        '    invoke-virtual {v0, v1, v1}, Landroid/view/Window;->setFlags(II)V\n'
        '    const/4 v1, 0x0\n'
        '    invoke-virtual {v0, v1}, Landroid/view/Window;->setStatusBarColor(I)V\n'
        + RED_WIN_BG_SMALI +
        '    invoke-virtual {v0}, Landroid/view/Window;->getDecorView()Landroid/view/View;\n'
        '    move-result-object v0\n'
        '    if-eqz v0, :itre_diag_skip\n'
        '    const/4 v1, 0x0\n'
        '    invoke-virtual {v0, v1}, Landroid/view/View;->setBackgroundColor(I)V\n'
        '    :itre_diag_skip\n'
        '    # === END DIAGNOSTIC BLOCK ===\n\n'
        '    const/4 v2, 0x0',
        'A-DIAG-window-red')

    # A1: zero v3 before the decorView 0cW.A0R call at 2ZS.A01 :202.
    # (The MAIN script was missing this; without it the original code repaints
    #  decorView with v3=themeColor AFTER our transparent setup.)
    patch_text(zs,
        '    const v0, -0x92e8ab6\n\n    invoke-static {v1, v3, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        '    const v0, -0x92e8ab6\n\n    # InstaTrueReel DIAG: decorView transparent (intercept :202 paint)\n    const/4 v3, 0x0\n\n    invoke-static {v1, v3, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        'A1-decorView-transparent')

    # A2: zero p2 before the content 0cW.A0R call at 2ZS.A05 :410.
    # (A05 is called from A01 :204 with v3 as the color; A05 reassigns p0 to the
    #  content view at :404, then paints it at :410 with p2=color.)
    patch_text(zs,
        '    const v0, -0x7ff859fd\n\n    invoke-static {p0, p2, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        '    const v0, -0x7ff859fd\n\n    # InstaTrueReel DIAG: content transparent (intercept :410 paint)\n    const/4 p2, 0x0\n\n    invoke-static {p0, p2, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        'A2-content-transparent')

    # A3: zero top inset before setPadding in 6BM.Fji
    bm = find_smali(decoded, '6BM.smali')
    patch_text(bm,
        '    invoke-static {v2, p1, p2}, LX/6wm;->A0w(Landroid/view/View;II)V',
        '    # InstaTrueReel DIAG: zero top inset\n    const/4 p1, 0x0\n\n    invoke-static {v2, p1, p2}, LX/6wm;->A0w(Landroid/view/View;II)V',
        'A3-top-inset')

    # A5: zero p1 in 1fC.A04 so EVERY setStatusBarColor call (incl. the deferred
    # WindowChromeColorDeferer Choreographer path) uses transparent.
    fc = find_smali(decoded, '1fC.smali')
    patch_text(fc,
        '.method public static final A04(Landroid/app/Activity;I)V\n    .locals 4\n\n    :goto_0',
        '.method public static final A04(Landroid/app/Activity;I)V\n    .locals 4\n\n'
        '    # InstaTrueReel DIAG: force transparent status bar color\n'
        '    const/4 p1, 0x0\n\n'
        '    :goto_0',
        'A5-statusbar-transparent')

    # A7: zero p1 in 2ZS.A00 so the 47l swipe_nav Runnable paints transparent.
    patch_text(zs,
        '.method public static final A00(Landroid/app/Activity;I)V\n    .locals 1\n    .annotation build Ldalvik/annotation/optimization/NeverInline;\n    .end annotation\n\n    new-instance v0, LX/47l;',
        '.method public static final A00(Landroid/app/Activity;I)V\n    .locals 1\n    .annotation build Ldalvik/annotation/optimization/NeverInline;\n    .end annotation\n\n'
        '    # InstaTrueReel DIAG: force transparent swipe_nav (47l Runnable)\n'
        '    const/4 p1, 0x0\n\n'
        '    new-instance v0, LX/47l;',
        'A7-swipenav-transparent')

    # == Feature B: floating bottom nav (KNOWN WORKING — keep) ============
    print("\n-- Feature B: floating bottom nav (working — keep) --")

    # B1: zero swipeable_tab_view_pager bottomMargin
    ima = os.path.join(decoded, 'smali/com/instagram/mainactivity/InstagramMainActivity.smali')
    if os.path.exists(ima):
        with open(ima) as f:
            content = f.read()
        lines = content.split('\n')
        SWIPEABLE = '0x7f0b3f45'
        patched = 0
        i = 0
        while i < len(lines):
            if SWIPEABLE in lines[i]:
                for j in range(i + 1, min(i + 50, len(lines))):
                    m = re.match(r'^(\s*)iput (v\d+), (v\d+), Landroid/view/ViewGroup\$MarginLayoutParams;->bottomMargin:I', lines[j])
                    if m:
                        indent, reg = m.group(1), m.group(2)
                        already = any('InstaTrueReel' in lines[k] for k in range(max(0, j - 3), j))
                        if not already:
                            lines[j] = f'{indent}# InstaTrueReel DIAG: zero bottomMargin\n{indent}const/4 {reg}, 0x0\n{lines[j]}'
                            patched += 1
                        break
            i += 1
        if patched:
            with open(ima, 'w') as f:
                f.write('\n'.join(lines))
        print(f"  {'+' if patched else '~'} B1-bottomMargin: {patched} patched")
    else:
        print("  X B1: InstagramMainActivity.smali not found")

    # B2-smali: patch 0bQ.A04 to zero the color before each setBackgroundColor
    bq = find_smali(decoded, '0bQ.smali')
    if bq:
        with open(bq) as f:
            c = f.read()
        method_start = c.find('.method public static final A04(')
        if method_start >= 0:
            method_end = c.find('.end method', method_start)
            method_body = c[method_start:method_end]
            new_body = re.sub(
                r'(    const v0, -?(?:0x)?[0-9a-fA-F]+\n\n    )(invoke-static \{v\d, v1, v0\}, LX/0cW;->A0R\(Landroid/view/View;II\)V)',
                r'\1# InstaTrueReel DIAG: transparent bg\n    const/4 v1, 0x0\n\n    \2',
                method_body
            )
            if new_body != method_body:
                c = c[:method_start] + new_body + c[method_end:]
                with open(bq, 'w') as f:
                    f.write(c)
                count = new_body.count('InstaTrueReel DIAG: transparent bg')
                print(f"  + B2-smali: zeroed {count} bgcolor calls in 0bQ.A04")
            else:
                print("  ~ B2-smali: no A0R patterns found in A04")
        else:
            print("  ~ B2-smali: A04 method not found in 0bQ.smali")
    else:
        print("  X B2: 0bQ.smali not found")

    print("\n" + "=" * 60 + "\nInstaTrueReel DIAGNOSTIC — done. Build -> install -> screenshot a reel.\n" + "=" * 60)
    print("EXPECTED STATUS-BAR REGION COLOR (see file header for interpretation):")
    print("  RED   = A1/A2 applied + video does NOT reach bar  -> fix insets")
    print("  DARK  = A1/A2 failed                               -> fix patch patterns")
    print("  BLACK = video reaches but letterboxes             -> fix force-fill crop")
    print("  video = DONE")


if __name__ == '__main__':
    main()
