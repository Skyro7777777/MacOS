#!/usr/bin/env python3
"""
InstaTrueReel — apply_diagnostic_v2.py  (CORRECTED status-bar diagnostic)

The v1 diagnostic put the RED window-bg block in 2ZS.A01 (Reels-only).
3 parallel subagents analyzing the REAL jadx Java source (156k files) found:
  - 2ZS.A01 is NOT called by InstagramMainActivity at startup.
  - The ACTUAL startup chrome path is:
      InstagramMainActivity.A1z() (onResumePostSuper, Java line ~7232)
        -> AbstractC54451fC.A03(activity, color)   [1fC.A03]
             -> A04(activity, color)                [sets statusBarColor]
             -> A05(activity, z)                    [sets systemUiVisibility]
  - A5 (1fC.A04 -> p1=0) IS working: the status bar IS transparent.
  - BUT the theme's windowBackground = ?igds_color_primary_background
    = bds_black = #000000 (pure black, NOT #0c1014 — prior notes were wrong).
  - So the transparent status bar shows the BLACK window background beneath it.
    That is the black strip the user sees on ALL screens.

v2 CORRECTION: move the window-bg-RED + FLAG_LAYOUT_NO_LIMITS block from
2ZS.A01 into 1fC.A04 (which runs on EVERY screen — home feed + Reels).
Combined with A5 (p1=0, already in A04), this makes:
  - status bar = transparent (A5)
  - window bg = RED ColorDrawable (diagnostic)
  - FLAG_LAYOUT_NO_LIMITS (content draws behind status bar)
  - decorView = transparent

EXPECTED RESULT (one screenshot, ANY screen):
  * RED strip in status-bar region
      -> 1fC.A04 runs + window bg IS the layer showing through the transparent
         status bar. FIX = null window bg (not RED) + FLAG_LAYOUT_NO_LIMITS
         (so content fills the status bar region instead of the window bg).
  * BLACK strip (no red)
      -> 1fC.A04 is NOT called (deeper investigation), OR a view/flag covers
         the window bg (e.g. FLAG_FULLSCREEN from 1fC.A05(false) hides the bar).
  * Video shows edge-to-edge behind status bar
      -> DONE (switch RED back to null, ship).
"""

import os, re, sys, glob


def find_smali(decoded, name):
    for d in sorted(glob.glob(os.path.join(decoded, 'smali*'))):
        for root, _, files in os.walk(d):
            if name in files:
                return os.path.join(root, name)
    return None


def patch_text(filepath, old, new, label):
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


RED_WIN_BG_SMALI = (
    '    # InstaTrueReel DIAG v2: window bg = RED ColorDrawable (0xFFFF0000)\n'
    '    new-instance v1, Landroid/graphics/drawable/ColorDrawable;\n'
    '    const v2, 0xffff0000\n'
    '    invoke-direct {v1, v2}, Landroid/graphics/drawable/ColorDrawable;-><init>(I)V\n'
    '    invoke-virtual {v0, v1}, Landroid/view/Window;->setBackgroundDrawable(Landroid/graphics/drawable/Drawable;)V\n'
)


def main():
    decoded = sys.argv[1] if len(sys.argv) > 1 else 'decoded'
    print("=" * 60 + "\nInstaTrueReel DIAGNOSTIC v2 — corrected hook (1fC.A04, ALL screens)\n" + "=" * 60)

    # == A5v2: THE KEY FIX — window bg=RED + FLAG_LAYOUT_NO_LIMITS in 1fC.A04 ==
    print("\n-- A5v2: 1fC.A04 -> window RED + FLAG_LAYOUT_NO_LIMITS (ALL screens) --")
    fc = find_smali(decoded, '1fC.smali')
    patch_text(fc,
        '.method public static final A04(Landroid/app/Activity;I)V\n    .locals 4\n\n    :goto_0',
        '.method public static final A04(Landroid/app/Activity;I)V\n    .locals 4\n\n'
        '    # === InstaTrueReel DIAG v2: window bg=RED + LAYOUT_NO_LIMITS + statusbar transparent ===\n'
        '    # This method is called on EVERY screen (home feed + Reels) via\n'
        '    # MainActivity.A1z -> 1fC.A03 -> 1fC.A04. v1 wrongly put this in 2ZS.A01\n'
        '    # (Reels-only) so RED never showed. Putting it HERE fires globally.\n'
        '    # RESULT: if RED shows in status-bar strip -> window bg is the layer\n'
        '    # showing through the transparent status bar -> fix = null + LAYOUT_NO_LIMITS.\n'
        '    const/4 p1, 0x0\n'
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
        '    # === END DIAG v2 BLOCK ===\n\n'
        '    :goto_0',
        'A5v2-window-red-in-1fC-A04')

    # == A1: decorView transparent at 2ZS.A01 :202 (Reels) ==
    print("\n-- A1: 2ZS.A01 :202 decorView transparent (Reels) --")
    zs = find_smali(decoded, '2ZS.smali')
    patch_text(zs,
        '    const v0, -0x92e8ab6\n\n    invoke-static {v1, v3, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        '    const v0, -0x92e8ab6\n\n    # InstaTrueReel DIAG v2: decorView transparent\n    const/4 v3, 0x0\n\n    invoke-static {v1, v3, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        'A1-decorView-transparent')

    # == A2: content transparent at 2ZS.A05 :410 (Reels) ==
    print("\n-- A2: 2ZS.A05 :410 content transparent (Reels) --")
    patch_text(zs,
        '    const v0, -0x7ff859fd\n\n    invoke-static {p0, p2, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        '    const v0, -0x7ff859fd\n\n    # InstaTrueReel DIAG v2: content transparent\n    const/4 p2, 0x0\n\n    invoke-static {p0, p2, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        'A2-content-transparent')

    # == A3: zero top inset (6BM.Fji, Reels) ==
    print("\n-- A3: 6BM.Fji zero top inset (Reels) --")
    bm = find_smali(decoded, '6BM.smali')
    patch_text(bm,
        '    invoke-static {v2, p1, p2}, LX/6wm;->A0w(Landroid/view/View;II)V',
        '    # InstaTrueReel DIAG v2: zero top inset\n    const/4 p1, 0x0\n\n    invoke-static {v2, p1, p2}, LX/6wm;->A0w(Landroid/view/View;II)V',
        'A3-top-inset')

    # == A7: 47l swipe_nav transparent (2ZS.A00, Reels) ==
    print("\n-- A7: 2ZS.A00 swipe_nav transparent (Reels) --")
    patch_text(zs,
        '.method public static final A00(Landroid/app/Activity;I)V\n    .locals 1\n    .annotation build Ldalvik/annotation/optimization/NeverInline;\n    .end annotation\n\n    new-instance v0, LX/47l;',
        '.method public static final A00(Landroid/app/Activity;I)V\n    .locals 1\n    .annotation build Ldalvik/annotation/optimization/NeverInline;\n    .end annotation\n\n'
        '    # InstaTrueReel DIAG v2: force transparent swipe_nav (47l Runnable)\n'
        '    const/4 p1, 0x0\n\n'
        '    new-instance v0, LX/47l;',
        'A7-swipenav-transparent')

    # == B1: zero swipeable_tab_view_pager bottomMargin ==
    print("\n-- B1: InstagramMainActivity zero bottomMargin --")
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
                            lines[j] = f'{indent}# InstaTrueReel DIAG v2: zero bottomMargin\n{indent}const/4 {reg}, 0x0\n{lines[j]}'
                            patched += 1
                        break
            i += 1
        if patched:
            with open(ima, 'w') as f:
                f.write('\n'.join(lines))
        print(f"  {'+' if patched else '~'} B1-bottomMargin: {patched} patched")
    else:
        print("  X B1: InstagramMainActivity.smali not found")

    # == B2: 0bQ.A04 transparent tab bar bg ==
    print("\n-- B2: 0bQ.A04 transparent tab bar bg --")
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
                r'\1# InstaTrueReel DIAG v2: transparent bg\n    const/4 v1, 0x0\n\n    \2',
                method_body
            )
            if new_body != method_body:
                c = c[:method_start] + new_body + c[method_end:]
                with open(bq, 'w') as f:
                    f.write(c)
                count = new_body.count('InstaTrueReel DIAG v2: transparent bg')
                print(f"  + B2-smali: zeroed {count} bgcolor calls in 0bQ.A04")
            else:
                print("  ~ B2-smali: no A0R patterns found in A04")
        else:
            print("  ~ B2-smali: A04 method not found in 0bQ.smali")
    else:
        print("  X B2: 0bQ.smali not found")

    print("\n" + "=" * 60 + "\nInstaTrueReel DIAGNOSTIC v2 — done.\n" + "=" * 60)
    print("KEY CHANGE from v1: RED window-bg block moved from 2ZS.A01 (Reels-only)")
    print("to 1fC.A04 (called on EVERY screen via MainActivity.A1z).")
    print("")
    print("EXPECTED STATUS-BAR STRIP COLOR (on ANY screen — home feed or Reels):")
    print("  RED   -> 1fC.A04 runs + window bg is the layer -> fix = null + LAYOUT_NO_LIMITS")
    print("  BLACK -> 1fC.A04 not called OR FLAG_FULLSCREEN hides bar -> deeper dig")
    print("  video -> DONE")


if __name__ == '__main__':
    main()
