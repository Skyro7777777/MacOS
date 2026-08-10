#!/usr/bin/env python3
"""
InstaTrueReelStatusBar — apply_patches.py
Forked from InstaTrueReel/patches/apply_patches.py.

Runs AFTER `apktool d -r` (resources kept as binary), BEFORE `apktool b`.
Usage: python3 apply_patches.py <decoded_dir>

Adds CS1: Force transparent navigation bar for ALL bottom sheets (THE FIX for
the comments bar black strip). This is the new patch that InstaTrueReel's B4
was missing — B4 made the bottom_sheet_container background transparent, but
the window's navigationBarColor (BLACK) still showed through the G28 inset
padding gap. CS1 patches BottomSheetFragment.A05() to call A0R(0) (transparent)
instead of A0R(255) (sentinel → early-return → BLACK), so the nav bar becomes
transparent whenever a bottom sheet (comments, story, etc.) is shown.
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
    with open(filepath) as f: c = f.read()
    if old in c:
        c = c.replace(old, new, 1)
        with open(filepath, 'w') as f: f.write(c)
        print(f"  + {label}: applied")
        return True
    print(f"  ~ {label}: pattern not found (may already be patched)")
    return False

def main():
    decoded = sys.argv[1] if len(sys.argv) > 1 else 'decoded'
    print("=" * 60 + "\nInstaTrueReelStatusBar — applying patches\n" + "=" * 60)

    # == Feature A: transparent status bar =================================
    print("\n-- Feature A: transparent status bar --")
    zs = find_smali(decoded, '2ZS.smali')

    # A1: zero decorView background (v3->0 before A0R)
    patch_text(zs,
        '    const v0, -0x92e8ab6\n\n    invoke-static {v1, v3, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        '    const v0, -0x92e8ab6\n\n    # InstaTrueReelStatusBar: decorView transparent\n    const/4 v3, 0x0\n\n    invoke-static {v1, v3, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        'A1-decorView')

    # A2: zero android.R.id.content background (p2->0 before A0R)
    patch_text(zs,
        '    const v0, -0x7ff859fd\n\n    invoke-static {p0, p2, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        '    const v0, -0x7ff859fd\n\n    # InstaTrueReelStatusBar: content transparent\n    const/4 p2, 0x0\n\n    invoke-static {p0, p2, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        'A2-content')

    # A3: zero top inset before setPadding in C6BM (pswitch_3 -> cond_3 branch)
    bm = find_smali(decoded, '6BM.smali')
    patch_text(bm,
        '    invoke-static {v2, p1, p2}, LX/6wm;->A0w(Landroid/view/View;II)V',
        '    # InstaTrueReelStatusBar: zero top inset\n    const/4 p1, 0x0\n\n    invoke-static {v2, p1, p2}, LX/6wm;->A0w(Landroid/view/View;II)V',
        'A3-top-inset')

    # A6: edge-to-edge using LEGACY API (works on Android 10/API 29+).
    patch_text(zs,
        '.method public static final A01(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;IZZZ)V\n    .locals 7',
        '.method public static final A01(Landroid/app/Activity;Landroidx/fragment/app/Fragment;Lcom/instagram/common/session/UserSession;IZZZ)V\n    .locals 7\n\n'
        '    # InstaTrueReelStatusBar: edge-to-edge (legacy API, Android 10+)\n'
        '    invoke-virtual {p0}, Landroid/app/Activity;->getWindow()Landroid/view/Window;\n'
        '    move-result-object v0\n'
        '    if-eqz v0, :itre_skip\n'
        '    const/high16 v1, 0xc000000\n'
        '    invoke-virtual {v0, v1}, Landroid/view/Window;->clearFlags(I)V\n'
        '    const/high16 v1, -0x80000000\n'
        '    invoke-virtual {v0, v1}, Landroid/view/Window;->addFlags(I)V\n'
        '    const/4 v1, 0x0\n'
        '    invoke-virtual {v0, v1}, Landroid/view/Window;->setStatusBarColor(I)V\n'
        '    invoke-virtual {v0, v1}, Landroid/view/Window;->setNavigationBarColor(I)V\n'
        '    invoke-virtual {v0}, Landroid/view/Window;->getDecorView()Landroid/view/View;\n'
        '    move-result-object v0\n'
        '    if-eqz v0, :itre_skip\n'
        '    const/16 v1, 0x500\n'
        '    invoke-virtual {v0, v1}, Landroid/view/View;->setSystemUiVisibility(I)V\n'
        '    const/4 v1, 0x0\n'
        '    invoke-virtual {v0, v1}, Landroid/view/View;->setBackgroundColor(I)V\n'
        '    :itre_skip',
        'A6-edge-to-edge-legacy')

    # A5: zero p1 in 1fC.A04 so EVERY setStatusBarColor call uses transparent.
    fc = find_smali(decoded, '1fC.smali')
    patch_text(fc,
        '.method public static final A04(Landroid/app/Activity;I)V\n    .locals 4\n\n    :goto_0',
        '.method public static final A04(Landroid/app/Activity;I)V\n    .locals 4\n\n'
        '    # InstaTrueReelStatusBar: force transparent status bar color\n'
        '    const/4 p1, 0x0\n\n'
        '    :goto_0',
        'A5-force-transparent-statusbar')

    # A7: zero p1 in 2ZS.A00 so 47l Runnable gets transparent color.
    patch_text(zs,
        '.method public static final A00(Landroid/app/Activity;I)V\n    .locals 1\n    .annotation build Ldalvik/annotation/optimization/NeverInline;\n    .end annotation\n\n    new-instance v0, LX/47l;',
        '.method public static final A00(Landroid/app/Activity;I)V\n    .locals 1\n    .annotation build Ldalvik/annotation/optimization/NeverInline;\n    .end annotation\n\n'
        '    # InstaTrueReelStatusBar: force transparent swipe_nav bg (47l Runnable)\n'
        '    const/4 p1, 0x0\n\n'
        '    new-instance v0, LX/47l;',
        'A7-transparent-swipenav')

    # == Feature B: floating bottom nav ====================================
    print("\n-- Feature B: floating bottom nav --")

    # B1: zero swipeable_tab_view_pager bottomMargin
    ima = os.path.join(decoded, 'smali/com/instagram/mainactivity/InstagramMainActivity.smali')
    if os.path.exists(ima):
        with open(ima) as f: content = f.read()
        lines = content.split('\n')
        SWIPEABLE = '0x7f0b3f45'
        patched = 0
        i = 0
        while i < len(lines):
            if SWIPEABLE in lines[i]:
                for j in range(i+1, min(i+50, len(lines))):
                    m = re.match(r'^(\s*)iput (v\d+), (v\d+), Landroid/view/ViewGroup\$MarginLayoutParams;->bottomMargin:I', lines[j])
                    if m:
                        indent, reg = m.group(1), m.group(2)
                        already = any('InstaTrueReelStatusBar' in lines[k] for k in range(max(0, j-3), j))
                        if not already:
                            lines[j] = f'{indent}# InstaTrueReelStatusBar: zero bottomMargin\n{indent}const/4 {reg}, 0x0\n{lines[j]}'
                            patched += 1
                        break
            i += 1
        if patched:
            with open(ima, 'w') as f: f.write('\n'.join(lines))
        print(f"  {'+' if patched else '~'} B1-bottomMargin: {patched} patched")
    else:
        print("  X B1: InstagramMainActivity.smali not found")

    # B2-smali: patch 0bQ.A04 to zero the color before each setBackgroundColor
    bq = find_smali(decoded, '0bQ.smali')
    if bq:
        with open(bq) as f: c = f.read()
        method_start = c.find('.method public static final A04(')
        if method_start >= 0:
            method_end = c.find('.end method', method_start)
            method_body = c[method_start:method_end]
            new_body = re.sub(
                r'(    const v0, -?(?:0x)?[0-9a-fA-F]+\n\n    )(invoke-static \{v\d, v1, v0\}, LX/0cW;->A0R\(Landroid/view/View;II\)V)',
                r'\1# InstaTrueReelStatusBar: transparent bg\n    const/4 v1, 0x0\n\n    \2',
                method_body
            )
            if new_body != method_body:
                c = c[:method_start] + new_body + c[method_end:]
                with open(bq, 'w') as f: f.write(c)
                count = new_body.count('InstaTrueReelStatusBar: transparent bg')
                print(f"  + B2-smali: zeroed {count} bgcolor calls in 0bQ.A04")
            else:
                print("  ~ B2-smali: no A0R patterns found in A04")
        else:
            print("  ~ B2-smali: A04 method not found in 0bQ.smali")
    else:
        print("  X B2-smali: 0bQ.smali not found")

    # B4: transparent comment input bar (bottom_sheet_container, C6BM.pswitch_6)
    if bm:
        patch_text(bm,
            '    invoke-static {v1, p1}, LX/6wm;->A0p(Landroid/view/View;I)V\n\n    :cond_5',
            '    invoke-static {v1, p1}, LX/6wm;->A0p(Landroid/view/View;I)V\n\n'
            '    # InstaTrueReelStatusBar: transparent comment composer bar\n'
            '    const/4 v3, 0x0\n\n'
            '    invoke-virtual {v1, v3}, Landroid/view/View;->setBackgroundColor(I)V\n\n'
            '    :cond_5',
            'B4-1-comment-bar')
        patch_text(bm,
            '    invoke-static {v0, p1}, LX/6wm;->A0p(Landroid/view/View;I)V\n\n    goto :goto_1',
            '    invoke-static {v0, p1}, LX/6wm;->A0p(Landroid/view/View;I)V\n\n'
            '    # InstaTrueReelStatusBar: transparent comment composer bar\n'
            '    const/4 v3, 0x0\n\n'
            '    invoke-virtual {v0, v3}, Landroid/view/View;->setBackgroundColor(I)V\n\n'
            '    goto :goto_1',
            'B4-2-comment-bar')

    # == Feature C: translucent comment sheet ==============================
    print("\n-- Feature C: translucent comment sheet --")

    # C1: zero ALL dimming alpha calls (0cW.A05) in EPN.smali
    epn = find_smali(decoded, 'EPN.smali')
    if epn:
        with open(epn) as f: c = f.read()
        lines = c.split('\n')
        patched = 0
        for i, line in enumerate(lines):
            if 'LX/0cW;->A05(Landroid/view/View;FI)V' in line:
                m = re.match(r'\s*invoke-static \{([^}]+)\},', line)
                if m:
                    regs = [x.strip() for x in m.group(1).split(',')]
                    if len(regs) >= 2:
                        alpha_reg = regs[1]
                        indent = line[:len(line)-len(line.lstrip())]
                        already = any('InstaTrueReelStatusBar' in lines[k] for k in range(max(0, i-3), i))
                        if not already:
                            lines[i] = f'{indent}# InstaTrueReelStatusBar: zero dimming alpha\n{indent}const/high16 {alpha_reg}, 0x0\n{line}'
                            patched += 1
        if patched:
            with open(epn, 'w') as f: f.write('\n'.join(lines))
        print(f"  {'+' if patched else '~'} C1-EPN-dimming: {patched} alpha(s) zeroed")
    else:
        print("  X C1: EPN.smali not found")

    # C2: make BottomSheetFragment panel translucent (setColorFilter -> 80% black)
    bsr = find_smali(decoded, 'BottomSheetFragment.smali')
    if bsr:
        with open(bsr) as f: c = f.read()
        lines = c.split('\n')
        patched = 0
        for i, line in enumerate(lines):
            if 'setColorFilter(ILandroid/graphics/PorterDuff$Mode;' in line:
                m = re.match(r'\s*invoke-virtual \{([^}]+)\},', line)
                if m:
                    regs = [x.strip() for x in m.group(1).split(',')]
                    if len(regs) >= 2:
                        color_reg = regs[1]
                        indent = line[:len(line)-len(line.lstrip())]
                        already = any('InstaTrueReelStatusBar' in lines[k] for k in range(max(0, i-3), i))
                        if not already:
                            lines[i] = f'{indent}# InstaTrueReelStatusBar: translucent panel\n{indent}const {color_reg}, -0x34000000    # 0xCC000000\n{line}'
                            patched += 1
        if patched:
            with open(bsr, 'w') as f: f.write('\n'.join(lines))
        print(f"  {'+' if patched else '~'} C2-sheet-panel: {patched} setColorFilter(s) patched")
    else:
        print("  X C2: BottomSheetFragment.smali not found")

    # ========================================================================
    # == Feature CS: NEW — Transparent navigation bar for bottom sheets =======
    # ========================================================================
    # THIS IS THE KEY FIX for the comments bar black strip.
    #
    # Root cause (verified by reading decompiled Java):
    #   BottomSheetFragment.A05() computes a color and calls navigator.A0R(color).
    #   For the comments sheet, the config (C50186J5g) has no explicit color set,
    #   so color = 255 (sentinel). AbstractC109183lH.A0R(255) checks a config flag
    #   (C109193lI.A0I) which returns FALSE for comments -> EARLY RETURN -> the
    #   nav bar is NEVER set to transparent -> it stays BLACK (the MainActivity's
    #   default navigationBarColor).
    #
    #   Meanwhile, G28 inset listener adds bottom padding = nav-bar-height to
    #   bottomSheetContainer, creating a gap. Through that gap, the BLACK nav bar
    #   shows -> the "black strip beneath the Add Comments... box" the user sees.
    #
    # Fix: Patch A05() to call A0R(0) (transparent) instead of A0R(color).
    #   When A0R receives i=0 (not 255), it skips the early-return and calls
    #   C54511fI.A04(activity, 0) -> window.setNavigationBarColor(0) -> TRANSPARENT.
    #   The nav bar area now shows the video behind it (edge-to-edge).
    #
    # Combined with B4 (transparent container bg) and A6 (edge-to-edge window),
    # the comments bar becomes fully transparent — video shows edge-to-edge.
    # ========================================================================
    print("\n-- Feature CS: transparent nav bar for bottom sheets (NEW) --")

    if bsr:
        with open(bsr) as f: c = f.read()
        # Find the A05 method boundary (flexible: matches any access flags)
        method_match = re.search(r'\.method[^\n]*A05\(\)V', c)
        if method_match:
            method_start = method_match.start()
            method_end = c.find('.end method', method_start)
            if method_end > method_start:
                method_body = c[method_start:method_end]
                # Within A05, find the A0R(I)V invoke-virtual call.
                # Pattern: invoke-virtual {vN, vM}, L<class>;->A0R(I)V
                # We capture vM (the color register) and zero it before the call.
                invoke_match = re.search(
                    r'(    invoke-virtual \{v\d+, (v\d+)\}, L[^;]+;->A0R\(I\)V)',
                    method_body
                )
                if invoke_match:
                    full_line = invoke_match.group(1)
                    color_reg = invoke_match.group(2)
                    insertion = (
                        f'    # InstaTrueReelStatusBar: force transparent nav bar for bottom sheet\n'
                        f'    const/4 {color_reg}, 0x0\n\n'
                    )
                    # Only patch if not already patched
                    if 'InstaTrueReelStatusBar: force transparent nav bar' not in method_body:
                        new_body = method_body.replace(full_line, insertion + full_line, 1)
                        c = c[:method_start] + new_body + c[method_end:]
                        with open(bsr, 'w') as f: f.write(c)
                        print(f"  + CS1-transparent-navbar: zeroed A0R color arg in BottomSheetFragment.A05 (reg={color_reg})")
                    else:
                        print("  ~ CS1-transparent-navbar: already patched")
                else:
                    print("  ~ CS1: A0R(I)V invoke-virtual not found in A05 method")
                    # Fallback: search the entire file for A0R(I)V calls on a navigator
                    # (in case jadx method name doesn't match smali)
                    all_matches = list(re.finditer(
                        r'(    invoke-virtual \{v\d+, (v\d+)\}, L[^;]+;->A0R\(I\)V)', c
                    ))
                    print(f"    (found {len(all_matches)} A0R(I)V invoke-virtual calls in entire file)")
            else:
                print("  ~ CS1: A05 method end not found")
        else:
            print("  ~ CS1: A05 method not found in BottomSheetFragment.smali")
    else:
        print("  X CS1: BottomSheetFragment.smali not found")

    # == Feature D: TikTok-style horizontal fullscreen ======================
    print("\n-- Feature D: TikTok-style horizontal fullscreen --")
    vbp = find_smali(decoded, 'VBP.smali')

    # D1: FSS — rotate to landscape (0) on fullscreen enter
    patch_text(vbp,
        '.method public final FSS(II)V\n    .locals 21\n\n    move-object/from16 v2, p0',
        '.method public final FSS(II)V\n    .locals 21\n\n'
        '    # InstaTrueReelStatusBar: rotate to landscape\n'
        '    move-object/from16 v0, p0\n'
        '    iget-object v0, v0, LX/VBP;->A02:LX/RE7;\n'
        '    iget-object v0, v0, LX/RE7;->A0B:LX/9eY;\n'
        '    iget-object v0, v0, LX/9eY;->A04:Landroidx/fragment/app/FragmentActivity;\n'
        '    const/4 v1, 0x0\n'
        '    invoke-static {v0, v1}, LX/6mW;->A00(Landroid/app/Activity;I)V\n\n'
        '    move-object/from16 v2, p0',
        'D1-FSS-landscape')

    # D2: EvT — restore orientation to USER (14) on fullscreen exit
    patch_text(vbp,
        '.method public final EvT(LX/950;)V\n    .locals 5\n\n    const/4 v2, 0x0',
        '.method public final EvT(LX/950;)V\n    .locals 5\n\n'
        '    # InstaTrueReelStatusBar: restore orientation\n'
        '    move-object/from16 v0, p0\n'
        '    iget-object v0, v0, LX/VBP;->A02:LX/RE7;\n'
        '    iget-object v0, v0, LX/RE7;->A0B:LX/9eY;\n'
        '    iget-object v0, v0, LX/9eY;->A04:Landroidx/fragment/app/FragmentActivity;\n'
        '    const/16 v1, 0xe\n'
        '    invoke-static {v0, v1}, LX/6mW;->A00(Landroid/app/Activity;I)V\n\n'
        '    const/4 v2, 0x0',
        'D2-EvT-portrait')

    # D3: force-show the scrubber (seekbar) overlay on reels
    g3 = find_smali(decoded, '33g.smali')
    if g3:
        patch_text(g3,
            '    invoke-virtual {v6, v1}, LX/0XG;->A00(LX/2Yc;)V\n\n    iget-boolean v1, v0, LX/33g;->A0x:Z\n\n    const/4 v4, 0x0',
            '    invoke-virtual {v6, v1}, LX/0XG;->A00(LX/2Yc;)V\n\n'
            '    # InstaTrueReelStatusBar: force-show scrubber\n'
            '    const/4 v1, 0x1\n\n'
            '    const/4 v4, 0x0',
            'D3-force-scrubber')

    print("\n" + "=" * 60 + "\nInstaTrueReelStatusBar — done\n" + "=" * 60)

if __name__ == '__main__':
    main()
