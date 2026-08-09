# 04 — Source Exploration Roadmap

The decompiled source is ~150,000 Java files (jadx output, artifact
`instagram-decompiled-java`). We can't grep it locally (too big for the
sandbox). Plan: a GitHub Actions workflow that either re-runs jadx **with
resources** or downloads the existing artifact, then runs targeted `ripgrep`
queries and commits a findings report back to the repo (or uploads as artifact).

## 4.1 Exploration workflow design (to be created in `workflows/`)

`InstaTrueReel/workflows/explore-source.yml` (stub, not built yet):
- trigger: `workflow_dispatch` with inputs (regex list).
- checkout repo (LFS for APK).
- setup JDK 21.
- **option A:** re-run jadx **with resources** (`-r` not set → keep `res/`,
  and also `--export-gradle` maybe) — heavier but gives us layout XML + themes.
  Alternatively use **apktool** to decode `res/` properly (jadx resource
  decoding is weaker).
- **option B:** download the existing `instagram-decompiled-java` artifact via
  the Actions API (faster, but no resources).
- run a battery of `rg` queries (below), save hits to `InstaTrueReel/notes/findings/<step>-<topic>.md`.
- commit findings back to `main` (using the token) OR upload as artifact.

Probably best: **apktool decode** (gives Smali + res) **AND** jadx (gives
readable Java) side by side, both in Actions. Smali is what we actually patch.

## 4.2 Search targets (the grep battery)

### Reels / Clips UI classes
```
rg -li "clipsfragment|reelsfragment|reelviewer|clipsviewer|reelsurfaceview|clipsplayer" --type java
rg -li "class .*Reel.*Fragment" --type java
rg -li "class .*Clip.*Fragment" --type java
rg "ReelsActivity|ClipsActivity" --type java -l
```

### Bottom navigation
```
rg -li "bottomnav|bottomnavigationview|tabbar|MainTabBar|IgBottomNav" --type java
rg "HomeReelsCreateSearchProfile|TabBar.*Fragment" --type java -l
rg -i "setSelectedTab.*reels|nav.*reels" --type java -l
```
Plus layout XML (apktool): `grep -rl "BottomNavigation" res/` and look at
`res/layout/*tab*`, `res/layout/*bottom*`.

### Comment overlay / BottomSheet
```
rg -li "CommentBottomSheet|ReelsCommentFragment|ClipsComment|commentSheet" --type java
rg -li "BottomSheetDialog|BottomSheetBehavior" --type java | head
rg "Add comment" res/values/strings.xml   # string id → trace usages
```

### Edge-to-edge / insets / immersive (the core)
```
rg -n "setDecorFitsSystemWindows|setFitsSystemWindows|fitsSystemWindows" --type java
rg -n "FLAG_TRANSLUCENT_STATUS|FLAG_TRANSLUCENT_NAVIGATION|FLAG_LAYOUT_NO_LIMITS" --type java
rg -n "SYSTEM_UI_FLAG_|setSystemUiVisibility" --type java
rg -n "WindowInsetsControllerCompat|enableEdgeToEdge|WindowCompat" --type java
rg -n "IMMERSIVE_STICKY|BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE" --type java
```
Filter to Reels/Clips scope afterward.

### Black backgrounds (windowBackground, themes)
```
rg -n "windowBackground|statusBarColor|navigationBarColor" res/values/themes.xml res/values/styles.xml
rg -n "android:background=\"#000|@color/black" res/layout/*reel* res/layout/*clip*
```

### Existing fullscreen / expand button (Feature D)
```
rg -li "fullscreen|full_screen|enterFullscreen|expand.*video|landscape.*video" --type java
rg -li "setRequestedOrientation|ORIENTATION_LANDSCAPE" --type java
rg -n "RESIZE_MODE_|setResizeMode" --type java   # ExoPlayer aspect handling
rg "fullscreen" res/values/strings.xml
```
Then read the click handler of the expand icon found in screenshot F.

### Video player
```
rg -li "PlayerView|ExoPlayer|ClipsPlayer|SimpleExoPlayer|StyledPlayerView" --type java
rg -n "setResizeMode|RESIZE_MODE_FIT|RESIZE_MODE_ZOOM|RESIZE_MODE_FILL" --type java
```

## 4.3 Per-feature exploration goals (what "done" looks like for exploration)

- **Feature A (status bar):** identify the exact Activity/Fragment + line where
  Reels gets a non-edge-to-edge window / black statusBarColor, and the theme
  attribute driving it. Output: `findings/A-statusbar.md` with file:line refs.
- **Feature B (bottom nav):** identify the nav view class + layout XML + its
  background drawable/color. Output: `findings/B-bottomnav.md`.
- **Feature C (comment sheet):** identify the comment BottomSheet class + its
  background style (solid black vs theme). Output: `findings/C-commentsheet.md`.
- **Feature D (horizontal fullscreen):** locate the existing expand button,
  read its handler, determine current behavior. Output: `findings/D-fullscreen.md`.

## 4.4 Proposed exploration order (cheap → expensive)

1. Strings + resource grep (cheap, narrows scope): find "Reels", "Add comment",
   "fullscreen" string IDs.
2. Class-name grep for Reels/Clips/BottomNav/CommentSheet.
3. Inset/system-bar grep, then filter to the Reels classes found in step 2.
4. Read the 3–5 key classes in full (jadx Java) + their layouts (apktool res).
5. Locate Feature D's expand button handler; decide build-new vs enhance.

Each step appends to `THINK_LOG.md` and writes a `findings/*.md`.
