#!/usr/bin/env python3
"""
InstaPatchedTrueReel — patcher (complete clean rewrite)

Forces Instagram Reels to play TikTok-style:
  - Edge-to-edge video (behind status bar + nav bar)
  - Transparent overlay bars (main nav bar, comment bar) — handled by runtime helper
  - TikTok-style fullscreen button for 16:9 videos — handled by runtime helper

DESIGN PHILOSOPHY (clean rewrite):
  The previous versions (v2–v8) accumulated harmful smali patches:
    - nulling 0x7f08042f (clips_viewer_comment_bar_background) CRASHED XIU's Litho
      component (LX/4rT;->A0N throws on resource 0) → whole comment bar vanished.
    - injecting 0x16ff immersive flags hid status bar icons ("only wifi info hidden").
    - broad bar-resource sweeps risked crashing non-bar contexts.

  This rewrite does the MINIMUM in smali (2 patches, both verified against the
  jadx-decompiled source) and pushes ALL bar-transparency + fullscreen logic into
  the runtime helper (TrueReelsHelper.java), which can walk the live view tree and
  handle Litho re-mounts dynamically.

THE 2 SMALI PATCHES (both evidence-backed from jadx source):

  (A) LX/7ky;->onSizeChanged(IIII)V  ->  TextureView MATCH_PARENT x MATCH_PARENT
      ROOT CAUSE (confirmed in AbstractC210917ky.java line 146):
        IG's reels video surface is SimpleVideoLayout (extends LX/7ky / jadx
        AbstractC210917ky). Its onSizeChanged computes the inner TextureView
        (field A02) size via C25U.A00 based on the VIDEO ASPECT RATIO, producing
        a letterboxed view (e.g. 1080x1920 centered on 1080x2400 screen -> 240px
        gaps top+bottom). This patch bypasses the aspect math and stretches the
        TextureView to MATCH_PARENT x MATCH_PARENT — edge-to-edge, TikTok-style.

  (B) LX/7ky;->onAttachedToWindow()V  ->  invoke-static TrueReelsHelper.onPlayerAttached
      Hooks the runtime helper on the REAL video surface (not media3 PlayerView,
      which reels doesn't use). The helper checks isInReelsContext() and does:
        - window transparency (status/nav bar TRANSPARENT, re-applied every layout)
        - video chain fill (MATCH_PARENT so video extends behind system bars)
        - bar transparency (GradientDrawable stroke-preserving, ID-based tab_bar lookup)
        - fullscreen button (TextureView in-place transform for 16:9 videos)

Pipeline:
  1. apktool d -r            (decompile DEX -> smali; resources kept raw)
  2. ripgrep for LX/7ky target
  3. 2 smali patches (A + B)
  4. apktool b               (reassemble)
  5. merge precompiled helper.dex as an extra classesN.dex
  6. uber-apk-signer         (zipalign + sign)

Usage:
  python3 patch.py --apk <input.apk> --out <out_dir> [--helper-dex helper.dex]
                   [--apktool path] [--signer path] [--java path]
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
        if name:
            r = run(["rg", "--files", "-g", pattern, root], timeout=180)
        else:
            r = run(["rg", "-l", "--no-heading", pattern, root], timeout=180)
        if r.returncode not in (0, 1):
            return []
        return [l.strip() for l in r.stdout.splitlines() if l.strip()]
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

def get_class_type(content):
    """Extract just the L...; class type from the .class line."""
    m = re.search(r'^\.class\s+.*?(L[^;]+;)', content, re.M)
    return m.group(1).strip() if m else None


# ===========================================================================
# PATCH (A): LX/7ky;->onSizeChanged -> TextureView MATCH_PARENT x MATCH_PARENT
# ===========================================================================
def patch_onsizechanged_stretch(content, class_type="LX/7ky;"):
    """Rewrite LX/7ky;->onSizeChanged(IIII)V to set the inner TextureView
    (field A02) to MATCH_PARENT x MATCH_PARENT with zero translation.

    Original method (AbstractC210917ky.java line 146) computes TextureView size
    via C25U.A00 based on video aspect ratio, producing a letterboxed view.
    This patch bypasses the aspect-ratio math entirely and stretches the
    TextureView to fill its parent edge-to-edge.
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
            # Register usage:
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
# PATCH (B): LX/7ky;->onAttachedToWindow -> TrueReelsHelper.onPlayerAttached hook
# ===========================================================================
def patch_helper_hook_on_attach(content, class_type="LX/7ky;",
                                helper_desc="Lapp/truereels/TrueReelsHelper;"):
    """Inject a call to TrueReelsHelper.onPlayerAttached(p0) at the start of
    LX/7ky;->onAttachedToWindow()V.

    The helper checks isInReelsContext() before doing anything, so it's safe
    to run on ALL video surfaces (feed, stories, reels, ads). In reels it:
      - makes window status/nav bars TRANSPARENT (video behind)
      - fills the video chain MATCH_PARENT
      - makes bar backgrounds transparent (stroke-preserving for GradientDrawable)
      - shows the fullscreen button for 16:9 videos
    In feed/stories it does nothing.

    If onAttachedToWindow doesn't exist, add a new override.
    """
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
                    lines.insert(k+1, f"{indent}invoke-static {{p0}}, {helper_desc}->onPlayerAttached(Landroid/view/View;)V")
                    return "\n".join(lines), True
                k += 1
    # not found: append a new override
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
    return "\n".join(lines + new_method), True


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--helper-dex", default=None,
                    help="precompiled helper .dex to merge (enables fullscreen button + bar transparency)")
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

    # 1. decompile (no resources — keeps resource IDs stable so runtime helper
    #    findViewById works with the hardcoded 0x7f0bXXXX IDs)
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
    # PATCH (A): LX/7ky;->onSizeChanged -> TextureView MATCH_PARENT  [KEY]
    # =========================================================================
    print("\n[*] === PATCH (A): LX/7ky;->onSizeChanged (TextureView MATCH_PARENT) ===")
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
            # confirm it's the right class (extends FrameLayout, has A02:TextureView, has onSizeChanged)
            if ("LX/7ky;" in content
                    and "A02:Landroid/view/TextureView;" in content
                    and "onSizeChanged(IIII)V" in content):
                new, changed = patch_onsizechanged_stretch(content, class_type="LX/7ky;")
                if changed:
                    open(candidate, "w", encoding="utf-8").write(new)
                    sevenky_count += 1
                    print(f"    [onSizeChanged->STRETCH] {os.path.relpath(candidate, decompiled)}")
            break
    if sevenky_count == 0:
        print("    [!] WARNING: LX/7ky; not found or onSizeChanged not patched — reels won't be full-screen!")
    else:
        print(f"[*] LX/7ky;->onSizeChanged rewritten to TextureView MATCH_PARENT x MATCH_PARENT ({sevenky_count} class)")

    # =========================================================================
    # PATCH (B): LX/7ky;->onAttachedToWindow -> helper hook  [KEY]
    # Only inject if we have a helper dex (otherwise the hook would call a
    # non-existent class and crash at runtime).
    # =========================================================================
    print("\n[*] === PATCH (B): LX/7ky;->onAttachedToWindow -> helper hook ===")
    immersive_count = 0
    if use_helper and sevenky_path and os.path.exists(sevenky_path):
        try:
            content = open(sevenky_path, encoding="utf-8", errors="ignore").read()
            new, changed = patch_helper_hook_on_attach(content, class_type="LX/7ky;")
            if changed:
                open(sevenky_path, "w", encoding="utf-8").write(new)
                immersive_count += 1
                print(f"    [helper hook onAttach] {os.path.relpath(sevenky_path, decompiled)}")
        except Exception as e:
            print(f"    [!] Failed: {e}")
    elif not use_helper:
        print("    [SKIP] no helper dex — helper hook not injected (degraded: video stretch only)")
    print(f"[*] helper hook injected into LX/7ky;->onAttachedToWindow ({immersive_count})")

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

    final = os.path.join(work, "Instagram-true916-patched.apk")
    shutil.copy(signed, final)
    sz = os.path.getsize(final)
    print(f"\n[OK] Done. Patched + signed APK:")
    print(f"    {final}  ({sz/1048576:.1f} MB)")
    print(f"\n[*] Summary of patches applied:")
    print(f"    - LX/7ky;->onSizeChanged  -> TextureView MATCH_PARENT x MATCH_PARENT  [{sevenky_count}]  <-- KEY (video stretch)")
    if use_helper:
        print(f"    - LX/7ky;->onAttachedToWindow -> TrueReelsHelper hook            [{immersive_count}]  <-- KEY (runtime helper)")
        print(f"    - TrueReelsHelper (merged as classesN.dex):")
        print(f"        * window transparency (status/nav bar TRANSPARENT, re-applied every layout)")
        print(f"        * video chain fill (MATCH_PARENT, video behind system bars)")
        print(f"        * bar transparency (GradientDrawable stroke-preserving + ID-based tab_bar lookup)")
        print(f"        * fullscreen button (TextureView in-place transform for 16:9 videos)")
    print(f"    [NO bar-resource nulling — the v8 approach crashed XIU's Litho comment bar]")
    print(f"    [NO immersive flag injection — caused 'only wifi info hidden' symptom]")

if __name__ == "__main__":
    main()
