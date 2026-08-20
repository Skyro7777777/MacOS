# 02 — Visual Analysis (target vs current)

All screenshots live in the repo root. Analysis done via VLM (glm-5v-turbo)
on the actual pixel data.

## The 4 screenshots the user explicitly pointed to

### TARGET 1 — TikTok, main bottom bar
- File: `Screenshot_20260807-112115.jpg`
- Content: "mega" reel — sunset/sunrise over ocean, fiery orange/red clouds.
- Layout: video plays **edge-to-edge**, full height.
  - **Top status bar** (11:21, wifi, battery): icons are **thin white
    lines/text overlaid directly on the video** — you can see clouds behind
    them. **No black strip.**
  - **Bottom nav** (Home/Friends/Inbox/Profile + center "+" button): white
    outlines and text **overlaid on the video**. The "+" is pink/cyan.
    **No black strip.** Only a subtle dark gradient at the very bottom for
    text readability (a tint, not a solid bar).
- Aspect: fills 100% of screen height. Immersive.

### TARGET 2 — TikTok, comment overlay
- File: `Screenshot_20260807-112049.jpg`
- Content: "mega" reel — flock of sheep in green field, Mont Saint-Michel in
  background.
- Layout: video extends fully behind the status bar (sky visible behind icons).
  - **Comment bar at bottom is a floating/translucent overlay** — frosted-glass
    dark-grey/white blur, grass faintly visible through it. **Not a solid
    panel on black.**
  - "Add comment..." input box = rounded, translucent dark, floating over video.
  - Side action buttons (heart/comment/bookmark/share) = floating white-line
    elements directly on the video.
  - **No black strips anywhere.**

### CURRENT (broken) 3 — Instagram, main bottom bar
- File: `Screenshot_20260807-112503.jpg`
- Content: humanoid robot (Xiaomi CyberOne) in warehouse, paused (big play icon).
- Layout: video is **sandwiched** between two solid black strips.
  - **Top black strip** (~3–4% height): holds status bar (11:25, VoLTE, wifi,
    battery). Below it, the "Reels / Friends" header sits on the video.
  - **Bottom black strip** (~8–10% height): solid opaque black holding
    Home/Reels(active)/Create/Search/Profile. Icons are **on black**, not
    floating over video.
  - Video occupies ~86–89% of screen height — letterboxed top and bottom.

### CURRENT (broken) 4 — Instagram, comment overlay
- File: `Screenshot_20260807-112529.jpg`
- Content: "A hidden Windows feature!" dual-monitor desk setup (Windows 11).
- Layout:
  - **Top:** solid black status-bar strip (~30–40px).
  - Below it: "Reels" header + "Friends" tab on semi-transparent dark.
  - **Bottom:** large rounded "Add comment..." box (dark grey) + a **solid
    black panel** between the video bottom and the input box. The video is
    **completely cut off** there — you can't see the desk/keyboard that should
    be in the frame. The black sheet sits *in front of* the video.
- vs TikTok: TikTok's comment overlay is translucent glass; Instagram's is an
  **opaque solid-black modal sheet** that truncates the video.

## Extra screenshots (classified, may be prior-attempt context)

| File | App | View |
|------|-----|------|
| `Screenshot_20260807-202711.jpg` | Instagram | Reels/feed (vertical) |
| `Screenshot_20260807-203524.jpg` | Instagram | Reels + comment overlay |
| `Screenshot_20260807-212758.jpg` | Instagram | Reels + comment overlay |
| `Screenshot_20260807-221856.jpg` | Instagram | Reels + comment overlay |
| `Screenshot_20260807-221936.jpg` | TikTok | Reels/feed |
| `Screenshot_20260808-145028__01.jpg` | Instagram | Reels **with a fullscreen/expand button visible** ⭐ |
| `Screenshot_20260808-145127.jpg` | Instagram | Reels/feed |
| `Screenshot_20260808-213432.jpg` | Instagram | Reels + comment overlay |
| `Screenshot_20260808-213842.jpg` | Instagram | Comment overlay |

### ⭐ Feature D reference — `Screenshot_20260808-145028__01.jpg`
- Instagram Reels showing a **horizontal (landscape) car-driving video**
  **letterboxed** (pillarboxed: big black bars top & bottom, video only in the
  middle horizontal strip) inside the vertical Reels container.
- An **"expand"/fullscreen icon** is visible in the **upper-right**, just right
  of a blue progress bar. Icon = rectangle with corner brackets + diagonal
  arrow (standard "enter fullscreen / expand to landscape" glyph).
- Side action column present (Like 105K, Comment 292, Repost 4595, Share 12.1K,
  Save 9637, More, profile pic). Creator "btw.kiyo", caption "Drive by Rainy
  Weather!!!".
- **Implication:** Instagram v435 already has *a* fullscreen button for
  horizontal videos. We must verify what tapping it currently does (does it
  rotate to landscape? hide side buttons? show a seekbar?) before deciding
  whether Feature D = "build new" or "enhance existing." → open question.

## Summary table (the one-line mental model)

| Area | TikTok | Instagram now | Instagram wanted |
|------|--------|---------------|------------------|
| Status bar | floating white icons over video | black strip, video cut | floating white icons over video |
| Main bottom nav | floating white icons over video | black strip, video cut | floating white icons over video |
| Comment overlay | translucent glass, video behind | opaque black sheet, video blocked | translucent glass, video behind |
| Horizontal video | Full-Screen btn → landscape + seekbar + no side buttons | has an expand btn (upper-right), behavior TBD | match TikTok |
