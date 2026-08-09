# 06 — Design Brainstorm (PRELIMINARY, not a final plan)

> ⚠️ This is brainstorming only. Concrete patch steps get written **after**
> source exploration fills in the file:line refs. Everything here is a
> hypothesis to test against the real code.

## Overall strategy
- Patch on top of the already-patched APK (`...-patches-v3.8.0.apk`) using
  **apktool** (decode → Smali + res edits → build → zipalign → sign) inside a
  GitHub Actions workflow.
- Use jadx output **only to read** the code and find the exact methods to edit.
- Keep changes surgical and reversible; one feature per patch step so we can
  bisect if something breaks.

---

## Feature A — Transparent status bar (video behind it)
**Hypothesis:** Instagram's Reels Activity/Fragment either
  (i) sets `window.statusBarColor = black` + `fitsSystemWindows=true` on root, or
  (ii) targets a pre-35 API and doesn't call edge-to-edge, leaving the default
       black window background showing in the inset area.

**Likely patch:**
- In the Reels Activity's `onCreate` (Smali), call
  `WindowCompat.setDecorFitsSystemWindows(getWindow(), false)` (or set
  `FLAG_LAYOUT_NO_LIMITS` as a fallback), and set `statusBarColor = 0x00000000`.
- Set the root container's `fitsSystemWindows=false` (or remove the top padding
  it applies from system insets).
- Ensure status-bar icon tint = light (white) so icons show over video:
  `WindowInsetsControllerCompat.setAppearanceLightNavigationBars(false)` etc.
- If the theme owns the black `windowBackground`, override it for the Reels
  activity theme to transparent.

**Risk:** other overlays (the "Reels/Friends" header) may rely on the inset
padding; may need to re-pad just the header, not the video.

---

## Feature B — Floating main bottom nav (Home/Reels/Create/Search/Profile)
**Hypothesis:** a `BottomNavigationView` (or custom `IgTabBar`) with
`android:background="@color/black"` (or a black drawable) + opaque icons.

**Likely patch (prefer minimal first):**
- Edit the nav's layout XML (apktool `res/`): set `android:background="@null"`
  or a 60% black translucent drawable; set icon tint to white.
- OR in the nav view class (Smali): override background set; call
  `setBackgroundColor(0x00000000)`.
- Make sure the nav's parent container lets the video draw behind it (no
  bottom padding on the Reels root equal to nav height). This ties into
  Feature A's `fitsSystemWindows=false`.
- Add a subtle bottom gradient drawable behind the icons for readability
  (matches TikTok's faint dark gradient).

**Fallback (Q5-b "recreate"):** if the existing nav can't be made clean,
  hide it (`View.GONE`) and add a new overlay `FrameLayout` with 5 minimal
  `ImageView`s (white outline icons) at the bottom of the Reels container,
  wired to the same nav intents. More work; only if needed.

---

## Feature C — Translucent comment overlay (frosted glass)
**Hypothesis:** a `BottomSheetDialogFragment` (or custom sheet) whose root
background is a solid black drawable; the "black thing beneath the input box"
is the sheet's own background above the input.

**Likely patch:**
- Change the sheet's background drawable to a **translucent blur**:
  - Android 12+ has `RenderEffect.createBlurEffect` — can apply to a view.
  - Cross-version: use a semi-transparent `#CC000000` drawable (cheap, not true
    blur) as a first pass; true frosted glass (blur of video behind) is harder
    and may need a snapshot blur view. TikTok's look may be acceptable with just
    ~80% black translucency. Decide fidelity vs effort.
- Ensure the sheet's container doesn't crop the video: the video (Feature A/B
  already full-screen) stays behind the now-translucent sheet.
- The "Add comment..." input box: keep its rounded translucent dark style
  (already close to TikTok).

**Risk:** Instagram's sheet might be a full-screen-ish panel, not a true
overlay; may need layout param changes so it floats rather than pushes content.

---

## Feature D — Horizontal-video fullscreen (TikTok-style)
**Step 0:** confirm what the existing expand button does (Q1).
**If enhance needed, likely patch:**
- In the expand button's `onClick` handler (Smali):
  - `setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE)`.
  - Hide the side-action column (`View.GONE`/`INVISIBLE`).
  - Hide the bottom nav + caption row.
  - Switch the player's resize mode to fill landscape (`RESIZE_MODE_ZOOM` or
    `FIT` depending on exact aspect).
  - Show a seekbar: if ExoPlayer `PlayerView`, set `use_controller=true` +
    `show_controller()`; or add a custom `SeekBar` bound to the player's
    position (poll `getCurrentPosition`/`getDuration`).
  - Add a "exit fullscreen" affordance (back button or tap) → restore
    portrait + UI.
- Decide button placement: TikTok = middle-bottom; Instagram's existing =
  upper-right. Keep Instagram's placement (less churn) or move to match
  TikTok? → ask user (probably keep existing, just make behavior TikTok-like).

---

## Build pipeline (workflow) sketch — `workflows/build-patched-apk.yml`
1. checkout (LFS).
2. setup JDK 21.
3. install apktool 2.9+, uber-apk-signer, Android build-tools (for zipalign).
4. `apktool d Instagram-...apk -o decoded`.
5. apply patches (a script that copies edited Smali/layout files from
   `InstaTrueReel/patches/` into `decoded/`).
6. `apktool b decoded -o patched-unsigned.apk`.
7. `zipalign -v 4 patched-unsigned.apk patched-aligned.apk`.
8. sign with debug key (or secret keystore) → `InstaTrueReel-<sha>.apk`.
9. upload artifact.

Iteration loop: edit patch files → re-run workflow → download APK → install →
screenshot → compare to target → repeat.

---

## Patch representation in `patches/`
Each feature = one folder of "overlay" files mirroring apktool's decoded tree:
```
patches/
├── A-statusbar/
│   ├── smali_classes2/com/instagram/reels/ReelsActivity.smali   (edited)
│   └── res/values/themes.xml                                    (edited)
├── B-bottomnav/
│   └── res/layout/ig_bottom_nav.xml                             (edited bg)
├── C-commentsheet/
│   └── res/drawable/comment_sheet_bg.xml                        (new translucent)
└── D-fullscreen/
    └── smali_classes3/com/instagram/clips/ExpandButtonHopper.smali (edited handler)
```
A small `apply.sh` overlays these onto the apktool-decoded tree before rebuild.
This keeps patches reviewable and version-controlled (no binary diffs).
