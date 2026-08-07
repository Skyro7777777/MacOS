#!/usr/bin/env python3
"""
InstaPatchedTrueReel — patcher
Forces Instagram Reels to play at true full-screen 9:16 (stretch, no crop),
video behind the overlay bars, immersive edge-to-edge, + a TikTok-style
fullscreen toggle button for horizontal videos.

Pipeline:
  1. apktool d -r            (decompile DEX -> smali; resources kept raw)
  2. ripgrep for targets
  3. smali patches:
       - setAspectRatio(F)V  -> no-op  (frame fills MATCH_PARENT)
       - setResizeMode(I)V   -> const/4 p1, 3  (RESIZE_MODE_FILL = STRETCH, no crop)
       - media3 AspectRatioFrameLayout.setAspectRatio -> also inject immersive flags
       - PlayerView.onAttachedToWindow -> call TrueReelsHelper.onPlayerAttached
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

def patch_set_aspect_noop(content, inject_immersive=False, class_type=None):
    """Neutralise setAspectRatio(F)V. If inject_immersive, also call
    View.setSystemUiVisibility(0x16ff) to hide system bars + lay out edge-to-edge.
    Uses Landroid/view/View; (where setSystemUiVisibility is defined) so the
    invoke-virtual resolves correctly up the hierarchy."""
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(".method") and "setAspectRatio(F)V" in line:
            if re.search(r"\b(abstract|native)\b", line):
                continue
            # find .end method
            j = i + 1
            while j < len(lines) and not lines[j].startswith(".end method"):
                j += 1
            if j >= len(lines):
                continue
            if inject_immersive:
                # setSystemUiVisibility(I)V is defined on android.view.View.
                # invoke-virtual {p0, v0} passes (this, flags). p0 is the view,
                # v0 holds the flags (0x16ff = FULLSCREEN|HIDE_NAV|LAYOUT_STABLE|
                # LAYOUT_FULLSCREEN|LAYOUT_HIDE_NAV|IMMERSIVE_STICKY).
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
    """Force setResizeMode(I)V to use `mode` (3=FILL stretch, 4=ZOOM crop).
    Inject `const/4 p1, <mode>` right after .locals so the p1 param is overridden."""
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
    """Rewrite onMeasure(II)V to just call super.onMeasure(p1, p2).

    This is the KEY patch for true full-screen reels. IG's reels video view
    (com/instagram/feed/widget/IgProgressImageView) overrides onMeasure to
    clamp its height to width/aspectRatio (e.g. 1080/0.5625 = 1920px), which
    is shorter than a modern 9:19.5 screen (~2400px) — leaving the visible gap
    below the video. By delegating to super.onMeasure (FrameLayout default),
    the view honors its layout params (MATCH_PARENT) and fills the entire
    ReelViewGroup (the full-screen FrameLayout root). Since the bars are
    overlaid siblings in that FrameLayout, the video now plays BEHIND them
    like TikTok."""
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

def patch_immersive_on_attach(content):
    """Inject immersive system-UI flags into onAttachedToWindow()V.
    If the method exists, prepend the flags call; if not, add a new override.
    Flags = 0x16ff = FULLSCREEN|HIDE_NAV|LAYOUT_STABLE|LAYOUT_FULLSCREEN|
    LAYOUT_HIDE_NAV|IMMERSIVE_STICKY — hides status + nav bars, lays out
    edge-to-edge, bars reappear transiently on swipe."""
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
                    lines.insert(k+1, f"{indent}const/16 v0, {flags}")
                    lines.insert(k+2, f"{indent}invoke-virtual {{p0, v0}}, Landroid/view/View;->setSystemUiVisibility(I)V")
                    return "\n".join(lines), True
                k += 1
    # not found: append a new override
    new_method = [
        "",
        "# auto-injected by InstaPatchedTrueReel (immersive)",
        ".method protected onAttachedToWindow()V",
        "    .locals 1",
        "    invoke-super {p0}, Landroid/view/View;->onAttachedToWindow()V",
        f"    const/16 v0, {flags}",
        "    invoke-virtual {p0, v0}, Landroid/view/View;->setSystemUiVisibility(I)V",
        "    return-void",
        ".end method",
    ]
    return "\n".join(lines + new_method), True

def patch_playerview_hook(content, helper_desc="Lapp/truereels/TrueReelsHelper;"):
    """Inject a call to TrueReelsHelper.onPlayerAttached(p0) in PlayerView.onAttachedToWindow.
    If the method doesn't exist, add an override."""
    hook = f"    invoke-static {{p0}}, {helper_desc}->onPlayerAttached(Landroid/view/View;)V"
    lines = content.split("\n")
    # look for existing onAttachedToWindow
    for i, line in enumerate(lines):
        if line.startswith(".method") and "onAttachedToWindow()V" in line:
            if re.search(r"\b(abstract|native)\b", line):
                continue
            # find .locals
            k = i + 1
            while k < len(lines) and not lines[k].startswith(".end method"):
                m = re.match(r"^(\s*)\.locals\s+(\d+)", lines[k])
                if m:
                    indent = m.group(1)
                    lines.insert(k+1, indent + "invoke-static {p0}, " + helper_desc + "->onPlayerAttached(Landroid/view/View;)V")
                    return "\n".join(lines), True
                k += 1
    # not found: append a new override method at end of file
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

    # 2. patch setAspectRatio -> no-op (all classes); immersive in media3 one
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

    # 3. patch setResizeMode -> FILL(3)
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

    # 4. *** THE KEY PATCH *** onMeasure -> super.onMeasure on reels video views
    # IG's reels video surface (IgProgressImageView + other aspect-clamped views)
    # overrides onMeasure to clamp height = width/aspectRatio, leaving a gap below
    # the video on taller-than-9:16 screens. Delegating to super.onMeasure makes
    # the view honor MATCH_PARENT and fill the full-screen ReelViewGroup, so the
    # video plays edge-to-edge BEHIND the overlaid bars (TikTok-style).
    onmeasure_targets = [
        "IgProgressImageView.smali",          # THE reels video view (found in ReelViewGroup.onFinishInflate)
        "FixedAspectRatioVideoLayout.smali",  # alt reels/feed video container
        "FixedAspectRatioFrameLayout.smali",  # alt aspect-clamped frame
        "MediaFrameLayout.smali",             # IG's media frame (setAspectRatio clamps it)
        "SimpleZoomableViewContainer.smali",  # zoom container used in some reels
        "AspectRatioLinearLayout.smali",      # aspect-clamped linear (reels variants)
        "AspectRatioFrameLayout.smali",       # IG's own aspect frame (not media3)
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
                    # only patch IG's own classes, not media3's AspectRatioFrameLayout
                    # (media3's has a different onMeasure; we skip it here)
                    cls = get_class_type(content)
                    if cls and "media3" in cls:
                        continue
                    new, changed = patch_onmeasure_fill(content, class_type=cls)
                    if changed:
                        open(f, "w", encoding="utf-8").write(new)
                        onmeasure_count += 1
                        print(f"    [onMeasure->super] {os.path.relpath(f, decompiled)}")
    print(f"[*] onMeasure -> super.onMeasure (fill parent) in {onmeasure_count} class(es)")

    # 4b. Inject immersive flags into IgProgressImageView.onAttachedToWindow.
    # This is the actual reels video view, so when it attaches we hide the
    # system bars (status + nav) for true edge-to-edge.
    immersive_count = 0
    for d in smali_dirs:
        for root, _, fns in os.walk(d):
            if "IgProgressImageView.smali" in fns:
                f = os.path.join(root, "IgProgressImageView.smali")
                content = open(f, encoding="utf-8", errors="ignore").read()
                new, changed = patch_immersive_on_attach(content)
                if changed:
                    open(f, "w", encoding="utf-8").write(new)
                    immersive_count += 1
                    print(f"    [immersive onAttach] {os.path.relpath(f, decompiled)}")
    print(f"[*] immersive flags injected into IgProgressImageView.onAttachedToWindow ({immersive_count})")

    # 4. patch PlayerView.onAttachedToWindow -> helper hook (if helper enabled)
    hook_count = 0
    if use_helper:
        for d in smali_dirs:
            for f in rg("--files", d, name=True) if False else []:
                pass
            # find PlayerView.smali
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

    # 5. recompile
    print("[*] Recompiling with apktool...")
    r = run([args.java, "-jar", args.apktool, "b", "-f", "-o", unsigned, decompiled], timeout=1200)
    if r.stdout: print(r.stdout[-1500:])
    if r.stderr: print(r.stderr[-800:])
    if r.returncode != 0:
        print("[!] apktool build failed"); sys.exit(1)

    # 6. merge helper.dex
    if use_helper and args.helper_dex and os.path.exists(args.helper_dex):
        print("[*] Merging helper.dex into APK...")
        with zipfile.ZipFile(unsigned, "a") as z:
            existing = set(z.namelist())
            # find next classesN.dex number
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

    # 7. sign
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
    print(f"\n[✓] Done. Patched + signed APK:")
    print(f"    {final}  ({sz/1048576:.1f} MB)")

if __name__ == "__main__":
    main()
