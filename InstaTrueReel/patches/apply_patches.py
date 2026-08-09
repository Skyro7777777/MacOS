#!/usr/bin/env python3
"""
InstaTrueReel — apply_patches.py
Runs AFTER apktool decode, BEFORE apktool build.

Usage: python3 apply_patches.py <decoded_dir>
"""

import os, re, sys, glob

def find_smali(decoded, name):
    """Find a .smali file by name (fast: check known smali_classes dirs)."""
    for d in sorted(glob.glob(os.path.join(decoded, 'smali*'))):
        for root, _, files in os.walk(d):
            if name in files:
                return os.path.join(root, name)
    return None

def patch_text(filepath, old, new, label):
    """Single find-and-replace. Returns True if applied."""
    if not filepath or not os.path.exists(filepath):
        print(f"  ❌ {label}: file not found")
        return False
    with open(filepath) as f: c = f.read()
    if old in c:
        c = c.replace(old, new, 1)
        with open(filepath, 'w') as f: f.write(c)
        print(f"  ✅ {label}: applied")
        return True
    print(f"  ⚠️ {label}: pattern not found")
    return False

def main():
    decoded = sys.argv[1] if len(sys.argv) > 1 else 'decoded'
    print("=" * 60 + "\nInstaTrueReel — applying patches\n" + "=" * 60)

    # ── Feature A: transparent status bar ──────────────────────
    print("\n── Feature A: transparent status bar ──")
    zs = find_smali(decoded, '2ZS.smali')

    # A1: zero decorView background (v3→0 before A0R)
    patch_text(zs,
        '    const v0, -0x92e8ab6\n\n    invoke-static {v1, v3, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        '    const v0, -0x92e8ab6\n\n    # InstaTrueReel: decorView transparent\n    const/4 v3, 0x0\n\n    invoke-static {v1, v3, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        'A1-decorView')

    # A2: zero android.R.id.content background (p2→0 before A0R)
    patch_text(zs,
        '    const v0, -0x7ff859fd\n\n    invoke-static {p0, p2, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        '    const v0, -0x7ff859fd\n\n    # InstaTrueReel: content transparent\n    const/4 p2, 0x0\n\n    invoke-static {p0, p2, v0}, LX/0cW;->A0R(Landroid/view/View;II)V',
        'A2-content')

    # A3: zero top inset before setPadding in C6BM
    bm = find_smali(decoded, '6BM.smali')
    patch_text(bm,
        '    invoke-static {v2, p1, p2}, LX/6wm;->A0w(Landroid/view/View;II)V',
        '    # InstaTrueReel: zero top inset\n    const/4 p1, 0x0\n\n    invoke-static {v2, p1, p2}, LX/6wm;->A0w(Landroid/view/View;II)V',
        'A3-top-inset')

    # ── Feature B: floating bottom nav ─────────────────────────
    print("\n── Feature B: floating bottom nav ──")

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
                        already = any('InstaTrueReel' in lines[k] for k in range(max(0, j-3), j))
                        if not already:
                            lines[j] = f'{indent}# InstaTrueReel: zero bottomMargin\n{indent}const/4 {reg}, 0x0\n{lines[j]}'
                            patched += 1
                        break
            i += 1
        if patched:
            with open(ima, 'w') as f: f.write('\n'.join(lines))
        print(f"  {'✅' if patched else '⚠️'} B1-bottomMargin: {patched} patched")
    else:
        print("  ❌ B1: InstagramMainActivity.smali not found")

    # B0: fix Bloks-encoded layout entries that break aapt compilation
    # These exist in res/values*/layouts.xml across multiple config dirs
    layouts_files = glob.glob(os.path.join(decoded, 'res/values*/layouts.xml'))
    total_fixed = 0
    for layouts_xml in layouts_files:
        with open(layouts_xml) as f: c = f.read()
        lines = c.split('\n')
        fixed = 0
        for i, line in enumerate(lines):
            if '<item type="layout"' in line and '>L|' in line:
                lines[i] = re.sub(r'>L\|[^<]*<', '>@layout/abc_action_bar_title_item<', line)
                fixed += 1
        if fixed:
            with open(layouts_xml, 'w') as f: f.write('\n'.join(lines))
            total_fixed += fixed
    if total_fixed:
        print(f"  ✅ B0-layouts: fixed {total_fixed} Bloks entries across {len(layouts_files)} files")
    elif layouts_files:
        print("  ✅ B0-layouts: no Bloks entries found")
    else:
        print("  ⚠️ B0-layouts: no layouts.xml files found")

    # B2: resource patch — transparent clips tab bar background
    styles = os.path.join(decoded, 'res/values/styles.xml')
    if os.path.exists(styles):
        with open(styles) as f: c = f.read()
        old = '<item name="igds_color_clips_tab_bar_background">@color/igds_prism_black</item>'
        new = '<item name="igds_color_clips_tab_bar_background">#00000000</item>'
        cnt = c.count(old)
        if cnt:
            with open(styles, 'w') as f: f.write(c.replace(old, new))
            print(f"  ✅ B2-styles: {cnt} replacement(s)")
        else:
            print("  ⚠️ B2-styles: pattern not found")
    else:
        print("  ⚠️ B2-styles: styles.xml not found (will use smali fallback)")

    # ── Feature C: translucent comment sheet ───────────────────
    print("\n── Feature C: translucent comment sheet ──")

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
                        already = any('InstaTrueReel' in lines[k] for k in range(max(0, i-3), i))
                        if not already:
                            lines[i] = f'{indent}# InstaTrueReel: zero dimming alpha\n{indent}const/high16 {alpha_reg}, 0x0\n{line}'
                            patched += 1
        if patched:
            with open(epn, 'w') as f: f.write('\n'.join(lines))
        print(f"  {'✅' if patched else '⚠️'} C1-EPN-dimming: {patched} alpha(s) zeroed")
    else:
        print("  ❌ C1: EPN.smali not found")

    # C2: make BottomSheetFragment panel translucent (setColorFilter → 80% black)
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
                        already = any('InstaTrueReel' in lines[k] for k in range(max(0, i-3), i))
                        if not already:
                            lines[i] = f'{indent}# InstaTrueReel: translucent panel\n{indent}const {color_reg}, -0x34000000    # 0xCC000000\n{line}'
                            patched += 1
        if patched:
            with open(bsr, 'w') as f: f.write('\n'.join(lines))
        print(f"  {'✅' if patched else '⚠️'} C2-sheet-panel: {patched} setColorFilter(s) patched")
    else:
        print("  ❌ C2: BottomSheetFragment.smali not found")

    # ── Feature D: TikTok-style horizontal fullscreen ──────────
    print("\n── Feature D: TikTok-style horizontal fullscreen ──")
    vbp = find_smali(decoded, 'VBP.smali')

    # D1: FSS — rotate to landscape (0) on fullscreen enter
    patch_text(vbp,
        '.method public final FSS(II)V\n    .locals 21\n\n    move-object/from16 v2, p0',
        '.method public final FSS(II)V\n    .locals 21\n\n'
        '    # InstaTrueReel: rotate to landscape\n'
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
        '    # InstaTrueReel: restore orientation\n'
        '    move-object/from16 v0, p0\n'
        '    iget-object v0, v0, LX/VBP;->A02:LX/RE7;\n'
        '    iget-object v0, v0, LX/RE7;->A0B:LX/9eY;\n'
        '    iget-object v0, v0, LX/9eY;->A04:Landroidx/fragment/app/FragmentActivity;\n'
        '    const/16 v1, 0xe\n'
        '    invoke-static {v0, v1}, LX/6mW;->A00(Landroid/app/Activity;I)V\n\n'
        '    const/4 v2, 0x0',
        'D2-EvT-portrait')

    print("\n" + "=" * 60 + "\nInstaTrueReel — done\n" + "=" * 60)

if __name__ == '__main__':
    main()
