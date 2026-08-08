#!/usr/bin/env python3
"""
InstaPatchedTrueReel — patcher (v2)
Forces Instagram Reels to play at true full-screen 9:16 (stretch, no crop),
video behind the overlay bars, immersive edge-to-edge, + a TikTok-style
fullscreen toggle button for horizontal videos.

ROOT CAUSE (found by reading jadx-decompiled Java source):
  IG's reels video surface is `Lcom/instagram/ui/simplevideolayout/SimpleVideoLayout;`
  (id `clips_video_layout` / `clips_video_container`), which extends `LX/7ky;`
  (AbstractC210917ky, "VideoFrameLayout"). The base class LX/7ky overrides
  `onSizeChanged(IIII)V` to compute the inner TextureView's width/height via
  `LX/25U;->A00(...)` based on the VIDEO ASPECT RATIO, then sets
  `FrameLayout.LayoutParams(w, h)` + translation X/Y on the TextureView.

  For a 9:16 video (aspect 0.5625) on a 9:19.5 screen (aspect 0.4615):
    - "fit" mode returns width=1080, height=1080/0.5625=1920
    - centered on a 1080x2400 screen -> 240px gap top + 240px gap bottom
    - THIS is the visible gap above & below the reel that the user reported.

  The previous patch versions targeted the WRONG classes (media3 PlayerView,
  IgProgressImageView.onMeasure) — those don't control the reels video surface
  size. IgProgressImageView is just the poster image; the actual video surface
  is the TextureView inside SimpleVideoLayout, sized by LX/7ky.onSizeChanged.

THE FIX:
  Rewrite `LX/7ky;->onSizeChanged(IIII)V` to set the TextureView (field A02)
  layout params to MATCH_PARENT × MATCH_PARENT (FrameLayout.LayoutParams(-1,-1))
  with translation X/Y = 0, bypassing the aspect-ratio math entirely. This
  stretches the video to fill the SimpleVideoLayout (which already fills C3EO,
  which fills ReelViewGroup, which fills the screen) edge-to-edge — TikTok-style.

  Also inject immersive flags into LX/7ky.onAttachedToWindow (the actual video
  surface attach hook — not media3 PlayerView which isn't used by reels feed).

Pipeline:
  1. apktool d -r            (decompile DEX -> smali; resources kept raw)
  2. ripgrep for targets
  3. smali patches:
       - LX/7ky;->onSizeChanged(IIII)V -> TextureView MATCH_PARENT x MATCH_PARENT  [KEY]
       - LX/7ky;->onAttachedToWindow()V -> inject immersive flags                 [KEY]
       - (kept, harmless) setAspectRatio(F)V -> no-op
       - (kept, harmless) setResizeMode(I)V -> const/4 p1, 3
       - (kept, harmless) IgProgressImageView.onMeasure -> super (poster image)
       - media3 PlayerView.onAttachedToWindow -> TrueReelsHelper hook (fullscreen btn)
  4. apktool b               (reassemble)
  5. merge precompiled helper.dex as an extra classesN.dex
  6. uber-apk-signer         (zipalign + sign)

Usage:
  python3 patch.py --apk <input.apk> --out <out_dir> [--helper-dex helper.dex]
                   [--apktool path] [--signer path]
"""
import argparse, os, re, shutil, subprocess, sys, zipfile

# ---------------------------------------------------------------------------
# subprocess helpers
# ---------------------------------------------------------------------------
def run(cmd, cwd=None, timeout=None):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, timeout=timeout,
                          capture_output=True, text=True)

def rg(pattern, root, name=False):
    """ripgrep: list files matching. name=True -> match filename; else content."""
    if shutil.which("rg"):
        args = ["rg", "-l", "--no-heading"] if not name else ["rg", "--files", "-g"]
        args = args + ([pattern] if not name else [pattern, root])
        r = run(args + ([root] if not name else []), timeout=180)
        if r.returncode not in (0, 1):
            return []
        return [l.strip() for l in r.stdout.splitlines() if l.strip()]
    # fallback: os.walk
    out = []
    for dp, _, fns in os.walk(root):
        if name:
            for f in fns:
                if f == pattern:
                    out.append(os.path.join(dp, f))
        else:
            for f in fns:
                fp = os.path.join(dp, f)
                if f.endswith(".smali"):
                    try:
                        if pattern in open(fp, encoding="utf-8", errors="ignore").read():
                            out.append(fp)
                    except Exception:
                        pass
    return out

def first_line(text, prefix):
    for l in text.splitlines():
        if l.startswith(prefix):
            return l
    return None

# ---------------------------------------------------------------------------
# smali patch functions
# ---------------------------------------------------------------------------
def get_class_type(content):
    """Extract just the L...; class type from the .class line."""
    m = re.search(r'^\.class\s+.*?(L[^;]+;)', content, re.M)
    return m.group(1).strip() if m else None

# ===========================================================================
# THE KEY PATCH (v2): LX/7ky;->onSizeChanged -> TextureView MATCH_PARENT
# ===========================================================================
def patch_onsizechanged_stretch(content, class_type="LX/7ky;"):
    """Rewrite LX/7ky;->onSizeChanged(IIII)V to set the inner TextureView
    (field A02) to MATCH_PARENT x MATCH_PARENT with zero translation.

    Original method computes TextureView size via LX/25U;->A00(...) based on
    video aspect ratio, producing a letterboxed view (e.g. 1080x1920 centered
    on 1080x2400 screen -> 240px gaps top+bottom). This patch bypasses the
    aspect-ratio math entirely and stretches the TextureView to fill its
    parent (SimpleVideoLayout -> C3EO -> ReelViewGroup -> screen), giving
    true edge-to-edge 9:16 (stretched, no crop) — TikTok-style.
    """
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(".method") and "onSizeChanged(IIII)V" in line:
            if re.search(r"\b(abstract|native)\b", line):
                continue
            j = i + 1
            while j < len(lines) and not lines[j].startswith(".end method"):
                j += 1
            if j >= len(lines):
                continue
            # New body:
            #   call super.onSizeChanged(p1,p2,p3,p4)  (required)
            #   if A02 (TextureView) == null, return
            #   else: set A02.layoutParams = FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT)
            #         set A02.translationX = 0, translationY = 0
            #         A02.requestLayout()
            #
            # Register usage (4 locals):
            #   v0 = TextureView (A02) / temp
            #   v1 = LayoutParams / 0.0f
            #   p0 = this, p1..p4 = width, height, oldWidth, oldHeight
            body = [
                "    .locals 2",
                "",
                "    # call super first (required by contract)",
                "    invoke-super {p0, p1, p2, p3, p4}, Landroid/view/View;->onSizeChanged(IIII)V",
                "",
                "    # iget A02 (TextureView field) into v0",
                "    iget-object v0, p0, " + class_type + "->A02:Landroid/view/TextureView;",
                "    if-eqz v0, :cond_done",
                "",
                "    # create FrameLayout.LayoutParams(MATCH_PARENT=-1, MATCH_PARENT=-1)",
                "    new-instance v1, Landroid/widget/FrameLayout$LayoutParams;",
                "    const/4 v0, -0x1",
                "    invoke-direct {v1, v0, v0}, Landroid/widget/FrameLayout$LayoutParams;-><init>(II)V",
                "",
                "    # re-fetch A02 (was clobbered) and set its layout params",
                "    iget-object v0, p0, " + class_type + "->A02:Landroid/view/TextureView;",
                "    invoke-virtual {v0, v1}, Landroid/view/TextureView;->setLayoutParams(Landroid/view/ViewGroup$LayoutParams;)V",
                "",
                "    # zero out translation X and Y (cancel the centering offset)",
                "    iget-object v0, p0, " + class_type + "->A02:Landroid/view/TextureView;",
                "    const/4 v1, 0x0",
                "    invoke-virtual {v0, v1}, Landroid/view/TextureView;->setTranslationX(F)V",
                "",
                "    iget-object v0, p0, " + class_type + "->A02:Landroid/view/TextureView;",
                "    const/4 v1, 0x0",
                "    invoke-virtual {v0, v1}, Landroid/view/TextureView;->setTranslationY(F)V",
                "",
                "    # force the TextureView to re-measure/re-layout at MATCH_PARENT",
                "    iget-object v0, p0, " + class_type + "->A02:Landroid/view/TextureView;",
                "    invoke-virtual {v0}, Landroid/view/TextureView;->requestLayout()V",
                "",
                "    :cond_done",
                "    return-void",
            ]
            new_lines = lines[:i+1] + body + lines[j:]
            return "\n".join(new_lines), True
    return content, False

# ===========================================================================
# PHASE B (v8): Bar background smali patches
# Patches found by 4 parallel subagents (SA-A, SA-B, SA-C, SA-D) that explored
# the jadx-decompiled Instagram source. These patches permanently neutralize
# bar backgrounds at the source (smali) — Litho cannot undo them.
#
# Resource IDs (from com/instagram/android/R.java):
#   0x7f080408 = clips_composer_background
#   0x7f080409 = clips_composer_background_direct
#   0x7f08042b = clips_viewer_action_bar_gradient_background
#   0x7f08042f = clips_viewer_comment_bar_background
#   0x7f0802cf = bg_legibility_gradient_top
#   0x7f08200d = igds_bottom_sheet_background_prism
#   0x7f060058 = bds_black_50_transparent (status bar tint when sheet opens)
#   0x7f0600a9 = bds_transparent
# ===========================================================================

# Map of resource-id-hex -> replacement (0 = null the resource so getDrawable returns null)
# NOTE: bg_legibility_gradient_top (0x7f0802cf) was REMOVED in v8.2 — it's NOT a bar
# background, it's a legibility gradient used in many non-bar contexts (Litho component
# gradients, filter overlays, Reels ad cards). Nulling it crashed the app after login.
BAR_RESOURCE_REPLACEMENTS = {
    "0x7f080408": "0x0",  # clips_composer_background
    "0x7f080409": "0x0",  # clips_composer_background_direct
    "0x7f08042b": "0x0",  # clips_viewer_action_bar_gradient_background
    "0x7f08042f": "0x0",  # clips_viewer_comment_bar_background
    "0x7f08200d": "0x0",  # igds_bottom_sheet_background_prism
}

def patch_bar_resource_ids(content):
    """Replace bar-background resource ID constants with 0x0 across ALL smali files.

    For each const instruction loading a known bar-background drawable resource ID,
    replace the immediate value with 0x0 so Context.getDrawable(0) returns null.
    Handles both `const/16 vN, 0x7f08XXXX` and `const vN, 0x7f08XXXX` forms.

    This is a broad sweep — it catches every call site that loads these resource IDs.
    Safe because getDrawable(0) simply returns null (resource 0 is invalid).
    NOTE: Only run this on TARGETED files (files the subagents analyzed). The broad
    sweep over ALL smali files was REMOVED in v8.2 because it patched files that
    used these resource IDs for non-bar purposes (legibility gradients, ad cards)
    which caused runtime crashes.
    """
    changed_count = 0
    lines = content.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Match: const vN, 0x7f08XXXX  OR  const/16 vN, 0x7f08XXXX
        # CRITICAL: capture the register (vN) so we preserve it in the replacement.
        # Smali requires the exact register — writing v0 when the original used v3 is a syntax error.
        m = re.match(r"^(\s*)(const(?:/16|/4)?\s+)(v\d+)(,\s+)(0x7f080[0-9a-f]{3})\s*$", stripped)
        if m:
            indent_prefix = line[:len(line) - len(line.lstrip())]
            instr_keyword = m.group(2).strip()  # 'const' or 'const/16' or 'const/4'
            reg = m.group(3)                   # the register, e.g. 'v3'
            comma = m.group(4)
            res_id = m.group(5)
            if res_id in BAR_RESOURCE_REPLACEMENTS:
                replacement = BAR_RESOURCE_REPLACEMENTS[res_id]
                # Use const/4 for small values (0x0 fits in 4 bits), but only if
                # the register is v0-v15 (const/4 only works for those). const/16 works for any register.
                # Safest: keep the original instruction keyword. const/16 vN, 0x0 is valid smali.
                # Actually const/4 vN, 0x0 is valid for v0-v15. For v16+ we must use const/16.
                reg_num = int(reg[1:])
                if int(replacement, 16) <= 7 and reg_num <= 15:
                    new_instr = "const/4"
                else:
                    new_instr = instr_keyword if instr_keyword in ("const", "const/16", "const/4") else "const/16"
                lines[i] = f"{indent_prefix}{new_instr} {reg}{comma}{replacement}  # PATCHED: was {res_id}"
                changed_count += 1
    return "\n".join(lines), changed_count

def patch_status_bar_tint_color(content):
    """In BottomSheetFragment.onResume, replace the status-bar tint color
    0x7f060058 (bds_black_50_transparent) with 0x7f0600a9 (bds_transparent).

    This makes the status bar fully transparent when the comment sheet opens,
    instead of a 50% black tint.
    """
    lines = content.split("\n")
    changed = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "const" in stripped and "0x7f060058" in stripped:
            indent_prefix = line[:len(line) - len(line.lstrip())]
            # Replace the color resource ID with bds_transparent
            # CRITICAL: preserve the original register (vN)
            m = re.match(r"^(\s*)(const(?:/16|/4)?\s+)(v\d+)(,\s+)0x7f060058\s*$", stripped)
            if m:
                instr_keyword = m.group(2).strip()
                reg = m.group(3)
                comma = m.group(4)
                # 0x7f0600a9 is a 16-bit value — need const or const/16. Keep original keyword.
                # If original was const/4, upgrade to const (since 0x7f0600a9 > 7).
                if instr_keyword == "const/4":
                    new_instr = "const"
                else:
                    new_instr = instr_keyword
                lines[i] = f"{indent_prefix}{new_instr} {reg}{comma}0x7f0600a9  # PATCHED: was 0x7f060058 (bds_black_50_transparent) -> bds_transparent"
                changed += 1
    return "\n".join(lines), changed

def patch_reply_bar_alpha(content):
    """In C47965IHv.FDA (reply bar controller), replace alpha=204 (0xcc) with 0.

    The inactive reply bar has alpha=204 (80% opaque). Patch to 0 (fully transparent).
    Only patches the const/16 vX, 0xcc instruction (the inactive-state alpha).
    """
    lines = content.split("\n")
    changed = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Match: const/16 vX, 0xcc  (alpha = 204)
        # CRITICAL: preserve the original register (vN)
        m = re.match(r"^(\s*)(const/16\s+)(v\d+)(,\s+)0xcc\s*$", stripped)
        if m:
            indent_prefix = line[:len(line) - len(line.lstrip())]
            reg = m.group(3)
            comma = m.group(4)
            reg_num = int(reg[1:])
            # 0x0 fits in 4 bits — use const/4 if register is v0-v15, else const/16
            if reg_num <= 15:
                new_instr = "const/4"
            else:
                new_instr = "const/16"
            lines[i] = f"{indent_prefix}{new_instr} {reg}{comma}0x0  # PATCHED: was 0xcc (alpha=204) -> 0 (transparent)"
            changed += 1
    return "\n".join(lines), changed

def find_smali_file(smali_dirs, relpath):
    """Find a smali file by its relative path (e.g. 'X/7ky.smali') across all
    smali_classes* directories. Returns the full path or None."""
    for d in smali_dirs:
        candidate = os.path.join(d, relpath)
        if os.path.exists(candidate):
            return candidate
    return None

def patch_bar_backgrounds_phase_b(smali_dirs, decompiled):
    """Phase B v8: Patch ALL bar-background resource IDs across the entire APK.

    Strategy: scan EVERY .smali file in EVERY smali_classes* dir for const
    instructions loading the known bar-background drawable resource IDs, and
    replace them with 0x0. This is a broad sweep that catches every call site.

    Also patches:
      - Status bar tint color (0x7f060058 -> 0x7f0600a9) in BottomSheetFragment
      - Reply bar alpha (0xcc -> 0x0) in C47965IHv
    """
    total_res = 0
    total_tint = 0
    total_alpha = 0
    files_touched = set()

    # Targeted files first (the ones we know about from subagent exploration)
    # NOTE: X/2Iv.smali uses bg_legibility_gradient_top (0x7f0802cf) which was REMOVED
    # from BAR_RESOURCE_REPLACEMENTS in v8.2. It still uses clips_viewer_action_bar_gradient_background
    # (0x7f08042b) which IS in the list, so the patch still hits the action bar fallback.
    targeted_files = [
        # (relpath, description)
        ("X/XIU.smali", "Comment Litho bar bg (clips_viewer_comment_bar_background)"),
        ("X/2Iv.smali", "Action bar bg source (A03 method)"),
        ("X/ANg.smali", "Reels comment bar controller"),
        ("X/IHv.smali", "Reply bar controller (alpha patch)"),
        ("X/331.smali", "Reply bar composer dynamic bg override"),
        ("X/ZZ0.smali", "DM composer bg"),
        ("X/Jst.smali", "Merged feeds action bar bg"),
        ("X/IHG.smali", "Stories draft preview gradient"),
        ("instagram/features/clips/viewer/navigationbar/ClipsViewerNavigationBar.smali", "Bottom nav bar gradient"),
        ("instagram/features/clips/viewer/actionbar/ClipsViewerActionBar.smali", "Action bar bg"),
        ("com/instagram/igds/components/bottomsheet/BottomSheetFragment.smali", "Comment sheet bg + status bar tint"),
    ]

    print("\n[*] === PHASE B: Bar background smali patches (v8.2) ===")

    # 1. Targeted files
    for relpath, desc in targeted_files:
        f = find_smali_file(smali_dirs, relpath)
        if f is None:
            print(f"    [!] NOT FOUND: {relpath} ({desc})")
            continue
        try:
            content = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        orig = content

        # Apply resource-ID replacement
        content, c1 = patch_bar_resource_ids(content)

        # Apply status-bar tint replacement (only BottomSheetFragment)
        if "BottomSheetFragment" in relpath:
            content, c2 = patch_status_bar_tint_color(content)
            total_tint += c2
        else:
            c2 = 0

        # Apply reply-bar alpha replacement (only C47965IHv / IHv.smali)
        if relpath == "X/IHv.smali":
            content, c3 = patch_reply_bar_alpha(content)
            total_alpha += c3
        else:
            c3 = 0

        if content != orig:
            open(f, "w", encoding="utf-8").write(content)
            total_res += c1
            files_touched.add(f)
            print(f"    [PATCHED] {os.path.relpath(f, decompiled)} ({desc}): {c1} res, {c2} tint, {c3} alpha")
        else:
            print(f"    [no-op]   {os.path.relpath(f, decompiled)} ({desc}): no matching consts")

    # 2. Broad sweep: REMOVED in v8.2.
    # The broad sweep scanned ALL smali files for resource IDs and nulled them.
    # This crashed the app because bg_legibility_gradient_top (0x7f0802cf) was used
    # in non-bar contexts (Litho component gradients, filter overlays, Reels ad cards).
    # Even after removing 0x7f0802cf from BAR_RESOURCE_REPLACEMENTS, the broad sweep
    # is still risky — other resource IDs might also be used in non-bar contexts.
    # Only targeted patches (files analyzed by subagents) are safe.
    broad_count = 0
    print(f"[*] Phase B broad sweep: SKIPPED (v8.2 — broad sweep caused runtime crashes)")
    print(f"[*] Phase B total: {total_res + broad_count} resource IDs, {total_tint} status-bar tints, {total_alpha} reply-bar alphas")
    return total_res + broad_count, total_tint, total_alpha

# ===========================================================================
# TrueReelsHelper hook injected into LX/7ky;->onAttachedToWindow
# ===========================================================================
def patch_immersive_on_attach_v2(content, class_type="LX/7ky;", helper_desc="Lapp/truereels/TrueReelsHelper;", use_helper=True):
    """Inject into onAttachedToWindow()V of LX/7ky (the video surface base class).

    When use_helper=True (helper dex available):
      - ONLY inject: invoke-static TrueReelsHelper->onPlayerAttached(p0)
      - The helper checks isInReelsContext() before doing anything, so it's safe
        to run on ALL video surfaces (feed, stories, reels, ads). In reels it
        hides system bars + shows fullscreen button. In feed/stories it does nothing.

    When use_helper=False (--no-helper, no dex):
      - Inject: setSystemUiVisibility(0x16ff) directly (no helper, no context check)
      - This is less safe (hides system bars on ALL video surfaces, not just reels)
        but it's a fallback if the helper fails to compile.

    If the method exists, inject after .locals; if not, add a new override.
    """
    flags = 0x16ff
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(".method") and "onAttachedToWindow()V" in line:
            if re.search(r"\b(abstract|native)\b", line):
                continue
            k = i + 1
            while k < len(lines) and not lines[k].startswith(".end method"):
                m = re.match(r"^(\s*)\.locals\s+(\d+)", lines[k])
                if m:
                    indent = m.group(1)
                    n = max(int(m.group(2)), 1)
                    lines[k] = f"{indent}.locals {n}"
                    if use_helper:
                        # Only inject the helper hook — it does everything conditionally.
                        lines.insert(k+1, f"{indent}invoke-static {{p0}}, {helper_desc}->onPlayerAttached(Landroid/view/View;)V")
                    else:
                        # No helper — inject setSystemUiVisibility directly.
                        lines.insert(k+1, f"{indent}const/16 v0, {flags}")
                        lines.insert(k+2, f"{indent}invoke-virtual {{p0, v0}}, Landroid/view/View;->setSystemUiVisibility(I)V")
                    return "\n".join(lines), True
                k += 1
    # not found: append a new override
    if use_helper:
        new_method = [
            "",
            "# auto-injected by InstaPatchedTrueReel (helper hook on video surface)",
            ".method public onAttachedToWindow()V",
            "    .locals 0",
            "    invoke-super {p0}, Landroid/view/View;->onAttachedToWindow()V",
            f"    invoke-static {{p0}}, {helper_desc}->onPlayerAttached(Landroid/view/View;)V",
            "    return-void",
            ".end method",
        ]
    else:
        new_method = [
            "",
            "# auto-injected by InstaPatchedTrueReel (immersive flags, no helper)",
            ".method public onAttachedToWindow()V",
            "    .locals 1",
            "    invoke-super {p0}, Landroid/view/View;->onAttachedToWindow()V",
            f"    const/16 v0, {flags}",
            "    invoke-virtual {p0, v0}, Landroid/view/View;->setSystemUiVisibility(I)V",
            "    return-void",
            ".end method",
        ]
    return "\n".join(lines + new_method), True

# ===========================================================================
# Legacy patches (kept, harmless — they target classes that don't control the
# reels video surface, but neutralising them doesn't hurt and may help feed
# thumbnails / other surfaces behave consistently).
# ===========================================================================
def patch_set_aspect_noop(content, inject_immersive=False, class_type=None):
    """Neutralise setAspectRatio(F)V. (Legacy: targets media3 AspectRatioFrameLayout
    which reels feed doesn't use, but harmless.)"""
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(".method") and "setAspectRatio(F)V" in line:
            if re.search(r"\b(abstract|native)\b", line):
                continue
            j = i + 1
            while j < len(lines) and not lines[j].startswith(".end method"):
                j += 1
            if j >= len(lines):
                continue
            if inject_immersive:
                body = [
                    "    .locals 1",
                    "    const/16 v0, 0x16ff",
                    "    invoke-virtual {p0, v0}, Landroid/view/View;->setSystemUiVisibility(I)V",
                    "    return-void",
                ]
            else:
                body = ["    .locals 0", "    return-void"]
            new_lines = lines[:i+1] + body + lines[j:]
            return "\n".join(new_lines), True
    return content, False

def patch_set_resize_fill(content, mode=3):
    """Force setResizeMode(I)V to use `mode` (3=FILL stretch). (Legacy.)"""
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(".method") and "setResizeMode(I)V" in line:
            if re.search(r"\b(abstract|native)\b", line):
                continue
            k = i + 1
            while k < len(lines) and not lines[k].startswith(".end method"):
                m = re.match(r"^(\s*)\.locals\s+(\d+)", lines[k])
                if m:
                    indent = m.group(1)
                    const = f"{indent}const/4 p1, {mode}" if mode <= 7 else f"{indent}const/16 p1, {mode}"
                    lines.insert(k+1, const)
                    return "\n".join(lines), True
                k += 1
    return content, False

def patch_onmeasure_fill(content, class_type=None):
    """Rewrite onMeasure(II)V to call super.onMeasure(p1, p2). (Legacy — targets
    IgProgressImageView which is just the poster image; doesn't affect video.)"""
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(".method") and "onMeasure(II)V" in line:
            if re.search(r"\b(abstract|native)\b", line):
                continue
            j = i + 1
            while j < len(lines) and not lines[j].startswith(".end method"):
                j += 1
            if j >= len(lines):
                continue
            body = [
                "    .locals 0",
                "    invoke-super {p0, p1, p2}, Landroid/widget/FrameLayout;->onMeasure(II)V",
                "    return-void",
            ]
            new_lines = lines[:i+1] + body + lines[j:]
            return "\n".join(new_lines), True
    return content, False

def patch_playerview_hook(content, helper_desc="Lapp/truereels/TrueReelsHelper;"):
    """Inject a call to TrueReelsHelper.onPlayerAttached(p0) in PlayerView.onAttachedToWindow.
    (Legacy — PlayerView isn't used by reels feed, so this is a no-op in practice.
    Kept for the fullscreen-button helper which may still find media3 PlayerView
    instances in other IG surfaces.)"""
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(".method") and "onAttachedToWindow()V" in line:
            if re.search(r"\b(abstract|native)\b", line):
                continue
            k = i + 1
            while k < len(lines) and not lines[k].startswith(".end method"):
                m = re.match(r"^(\s*)\.locals\s+(\d+)", lines[k])
                if m:
                    indent = m.group(1)
                    lines.insert(k+1, indent + "invoke-static {p0}, " + helper_desc + "->onPlayerAttached(Landroid/view/View;)V")
                    return "\n".join(lines), True
                k += 1
    new_method = [
        "",
        "# auto-injected by InstaPatchedTrueReel",
        ".method protected onAttachedToWindow()V",
        "    .locals 0",
        "    invoke-super {p0}, Landroid/view/View;->onAttachedToWindow()V",
        "    invoke-static {p0}, " + helper_desc + "->onPlayerAttached(Landroid/view/View;)V",
        "    return-void",
        ".end method",
    ]
    return "\n".join(lines + new_method), True

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--helper-dex", default=None, help="precompiled helper .dex to merge (enables fullscreen button)")
    ap.add_argument("--apktool", default=os.environ.get("APKTOOL", "apktool"))
    ap.add_argument("--signer", default=os.environ.get("SIGNER", "uber-apk-signer.jar"))
    ap.add_argument("--java", default="java")
    ap.add_argument("--no-helper", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    work = args.out
    decompiled = os.path.join(work, "decompiled")
    unsigned = os.path.join(work, "patched-unsigned.apk")
    signed_dir = os.path.join(work, "signed")

    use_helper = bool(args.helper_dex) and not args.no_helper

    # 1. decompile (no resources)
    print("[*] Decompiling with apktool (no resources)...")
    r = run([args.java, "-jar", args.apktool, "d", "-r", "-f", "-o", decompiled, args.apk], timeout=900)
    print(r.stdout[-2000:] if r.stdout else "")
    if r.stderr: print(r.stderr[-1000:])
    if r.returncode != 0:
        print("[!] apktool decompile failed"); sys.exit(1)

    # find smali dirs
    smali_dirs = [os.path.join(decompiled, d) for d in os.listdir(decompiled)
                  if d.startswith("smali") and os.path.isdir(os.path.join(decompiled, d))]
    print(f"[*] {len(smali_dirs)} smali dir(s)")

    # =========================================================================
    # *** THE KEY PATCH (v2) *** : LX/7ky;->onSizeChanged -> TextureView MATCH_PARENT
    # This is the REAL fix. LX/7ky (AbstractC210917ky / "VideoFrameLayout") is
    # the base class of SimpleVideoLayout (the actual reels video surface). Its
    # onSizeChanged computes the inner TextureView size based on video aspect
    # ratio, letterboxing it (the visible gap). Patching it to set MATCH_PARENT
    # x MATCH_PARENT stretches the video to fill the screen edge-to-edge.
    # =========================================================================
    print("\n[*] === KEY PATCH: LX/7ky;->onSizeChanged (TextureView MATCH_PARENT) ===")
    sevenky_path = None
    sevenky_count = 0
    for d in smali_dirs:
        candidate = os.path.join(d, "X", "7ky.smali")
        if os.path.exists(candidate):
            sevenky_path = candidate
            try:
                content = open(candidate, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            # confirm it's the right class (extends FrameLayout, has A02:TextureView field)
            if "LX/7ky;" in content and "A02:Landroid/view/TextureView;" in content and "onSizeChanged(IIII)V" in content:
                new, changed = patch_onsizechanged_stretch(content, class_type="LX/7ky;")
                if changed:
                    open(candidate, "w", encoding="utf-8").write(new)
                    sevenky_count += 1
                    print(f"    [onSizeChanged->STRETCH] {os.path.relpath(candidate, decompiled)}")
            break
    if sevenky_count == 0:
        print("    [!] WARNING: LX/7ky; not found or onSizeChanged not patched — reels won't be full-screen!")
    else:
        print(f"[*] LX/7ky;->onSizeChanged rewritten to TextureView MATCH_PARENT x MATCH_PARENT in {sevenky_count} class(es)")

    # =========================================================================
    # Immersive flags on LX/7ky;->onAttachedToWindow (the REAL video surface)
    # =========================================================================
    print("\n[*] === Immersive flags on LX/7ky;->onAttachedToWindow ===")
    immersive_count = 0
    if sevenky_path and os.path.exists(sevenky_path):
        try:
            content = open(sevenky_path, encoding="utf-8", errors="ignore").read()
            new, changed = patch_immersive_on_attach_v2(content, class_type="LX/7ky;", use_helper=use_helper)
            if changed:
                open(sevenky_path, "w", encoding="utf-8").write(new)
                immersive_count += 1
                print(f"    [immersive onAttach] {os.path.relpath(sevenky_path, decompiled)}")
        except Exception as e:
            print(f"    [!] Failed: {e}")
    print(f"[*] immersive flags injected into LX/7ky;->onAttachedToWindow ({immersive_count})")

    # =========================================================================
    # Legacy patches (harmless — kept for consistency / other surfaces)
    # =========================================================================
    print("\n[*] === Legacy patches (harmless, kept for consistency) ===")

    # setAspectRatio -> no-op (media3 AspectRatioFrameLayout; not used by reels feed)
    media3_arfl = None
    aspect_count = 0
    for d in smali_dirs:
        for f in rg("setAspectRatio(F)V", d):
            try:
                content = open(f, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            cls = get_class_type(content)
            is_media3 = cls and "media3/ui/AspectRatioFrameLayout" in cls
            new, changed = patch_set_aspect_noop(content, inject_immersive=is_media3, class_type=cls)
            if changed:
                open(f, "w", encoding="utf-8").write(new)
                aspect_count += 1
                if is_media3:
                    media3_arfl = f
                print(f"    [aspect] {os.path.relpath(f, decompiled)}{'  +immersive' if is_media3 else ''}")
    print(f"[*] setAspectRatio neutralised in {aspect_count} class(es)")

    # setResizeMode -> FILL(3)
    resize_count = 0
    for d in smali_dirs:
        for f in rg("setResizeMode(I)V", d):
            try:
                content = open(f, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            new, changed = patch_set_resize_fill(content, mode=3)
            if changed:
                open(f, "w", encoding="utf-8").write(new)
                resize_count += 1
                print(f"    [resize->FILL] {os.path.relpath(f, decompiled)}")
    print(f"[*] setResizeMode forced to FILL(3) in {resize_count} class(es)")

    # IgProgressImageView.onMeasure -> super (poster image; doesn't affect video)
    onmeasure_targets = [
        "IgProgressImageView.smali",
        "FixedAspectRatioVideoLayout.smali",
        "FixedAspectRatioFrameLayout.smali",
        "MediaFrameLayout.smali",
        "SimpleZoomableViewContainer.smali",
        "AspectRatioLinearLayout.smali",
        "AspectRatioFrameLayout.smali",
    ]
    onmeasure_count = 0
    for d in smali_dirs:
        for root, _, fns in os.walk(d):
            for name in onmeasure_targets:
                if name in fns:
                    f = os.path.join(root, name)
                    try:
                        content = open(f, encoding="utf-8", errors="ignore").read()
                    except Exception:
                        continue
                    cls = get_class_type(content)
                    if cls and "media3" in cls:
                        continue
                    new, changed = patch_onmeasure_fill(content, class_type=cls)
                    if changed:
                        open(f, "w", encoding="utf-8").write(new)
                        onmeasure_count += 1
                        print(f"    [onMeasure->super] {os.path.relpath(f, decompiled)}")
    print(f"[*] onMeasure -> super.onMeasure (legacy, poster image) in {onmeasure_count} class(es)")

    # PlayerView.onAttachedToWindow -> helper hook (for fullscreen button; PlayerView
    # isn't used by reels feed but may exist in other IG surfaces)
    hook_count = 0
    if use_helper:
        for d in smali_dirs:
            for f in [os.path.join(root, name) for root, _, fns in os.walk(d) for name in fns if name == "PlayerView.smali"]:
                try:
                    content = open(f, encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                if "media3/ui/PlayerView" not in content:
                    continue
                new, changed = patch_playerview_hook(content)
                if changed:
                    open(f, "w", encoding="utf-8").write(new)
                    hook_count += 1
                    print(f"    [PlayerView hook] {os.path.relpath(f, decompiled)}")
        print(f"[*] PlayerView.onAttachedToWindow hooked in {hook_count} class(es)")

    # =========================================================================
    # PHASE B (v8): Bar background smali patches
    # Permanently neutralize bar backgrounds at the source. Found by 4 parallel
    # subagents exploring the jadx-decompiled Instagram source.
    # =========================================================================
    bar_res_count, bar_tint_count, bar_alpha_count = patch_bar_backgrounds_phase_b(smali_dirs, decompiled)

    # =========================================================================
    # recompile
    # =========================================================================
    print("\n[*] Recompiling with apktool...")
    r = run([args.java, "-jar", args.apktool, "b", "-f", "-o", unsigned, decompiled], timeout=1200)
    if r.stdout: print(r.stdout[-1500:])
    if r.stderr: print(r.stderr[-800:])
    if r.returncode != 0:
        print("[!] apktool build failed"); sys.exit(1)

    # merge helper.dex
    if use_helper and args.helper_dex and os.path.exists(args.helper_dex):
        print("[*] Merging helper.dex into APK...")
        with zipfile.ZipFile(unsigned, "a") as z:
            existing = set(z.namelist())
            max_n = 0
            for n in existing:
                m = re.match(r"classes(\d*)\.dex$", n)
                if m:
                    num = int(m.group(1)) if m.group(1) else 1
                    if num > max_n:
                        max_n = num
            new_name = f"classes{max_n+1}.dex"
            z.write(args.helper_dex, new_name)
            print(f"    helper dex added as {new_name}")

    # sign
    print("[*] Zipaligning + signing with uber-apk-signer...")
    os.makedirs(signed_dir, exist_ok=True)
    r = run([args.java, "-jar", args.signer, "-a", unsigned, "-o", signed_dir, "--allowResign"], timeout=600)
    if r.stdout: print(r.stdout[-1500:])
    if r.stderr: print(r.stderr[-800:])
    if r.returncode != 0:
        print("[!] signing failed"); sys.exit(1)

    # locate signed apk
    signed = None
    for n in os.listdir(signed_dir):
        if n.endswith(".apk") and "aligned" in n and "idsig" not in n:
            signed = os.path.join(signed_dir, n); break
    if not signed:
        for n in os.listdir(signed_dir):
            if n.endswith(".apk") and "idsig" not in n:
                signed = os.path.join(signed_dir, n); break
    if not signed:
        print("[!] signed apk not found"); sys.exit(1)

    # copy to out root with a clean name
    final = os.path.join(work, "Instagram-true916-patched.apk")
    shutil.copy(signed, final)
    sz = os.path.getsize(final)
    print(f"\n[OK] Done. Patched + signed APK:")
    print(f"    {final}  ({sz/1048576:.1f} MB)")
    print(f"\n[*] Summary of patches applied:")
    print(f"    - LX/7ky;->onSizeChanged  -> TextureView MATCH_PARENT x MATCH_PARENT  [{sevenky_count}]  <-- KEY")
    print(f"    - LX/7ky;->onAttachedToWindow -> immersive flags                      [{immersive_count}]  <-- KEY")
    print(f"    - setAspectRatio no-op (legacy)                                       [{aspect_count}]")
    print(f"    - setResizeMode FILL (legacy)                                         [{resize_count}]")
    print(f"    - IgProgressImageView.onMeasure super (legacy, poster)                [{onmeasure_count}]")
    if use_helper:
        print(f"    - PlayerView.onAttachedToWindow helper hook                          [{hook_count}]")
    print(f"    - PHASE B bar bg resource IDs nulled                                [{bar_res_count}]  <-- KEY (v8)")
    print(f"    - PHASE B status-bar tint -> transparent                            [{bar_tint_count}]  <-- KEY (v8)")
    print(f"    - PHASE B reply-bar alpha -> 0                                      [{bar_alpha_count}]  <-- KEY (v8)")

if __name__ == "__main__":
    main()
