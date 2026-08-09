# 4-a — Reel player instance + seekbar feasibility

**Task ID:** 4-a
**Agent:** Explore (player instance + seekbar)
**Scope:** Locate the actual media player instance behind the Reels video
view, find its playback-control API, and decide whether to reuse IG's
existing scrubber UI for Feature D.

---

## TL;DR — verdict up front

1. **IG ALREADY HAS a TikTok-style seekbar** for clips/reels:
   `com.instagram.p132ui.mediaactions.VideoScrubberSeekBar`
   (extends `AppCompatSeekBar`, implements `OnSeekBarChangeListener`).
   It ships with keyframe/chapter markers, a preview-thumbnail view, and a
   timestamps container. It is wired into the clips viewer via the Litho
   mount-spec `p002X/C30423BTc` ("LegacyClipsAttachedScrubberComponent"),
   but is gated behind MobileConfig flags and `ClipsProgressUiState`
   duration checks — that is why it doesn't show by default.
2. **IG's player interface ALREADY exposes a scrubbing API**:
   - `C3HU.setScrubbingModeEnabled(boolean)`  / `isScrubbingModeEnabled()`
   - `C3HU.GzY(float normalizedPos, int flag)` — seekTo (0..1)
   - `C50741Yd.BbK()` → `int` current position MS
   - `C50741Yd.A0P()` → `int` duration MS
3. **Feature D recommendation:** REUSE the existing
   `VideoScrubberSeekBar` + `C30423BTc` component (just flip its
   MobileConfig gate) and bind to `C3HU` / `C50741Yd` via the
   `C257899eY` controller. NO custom SeekBar needed. NO media3
   `PlayerView` overlay needed.

---

## Q1 — The player object that drives the reel video

### Call chain (view → controller → per-reel player → concrete player)

```
ClipsViewerFragment (C254289Wz, 113k lines, 3-a finding)
        │
        │  owns
        ▼
C257899eY  ← "ClipsVideoPlayerController"
   p002X/C257899eY.java:48  (class header)
   p002X/C257899eY.java:64  field C257849eT A0F  (telemetry)
   p002X/C257899eY.java:66  field C257889eX A0H
   p002X/C257899eY.java:73  field C257909eZ A0O  (per-reel player map holder)
        │
        │  field A0O.A01 is a Map<C937233l viewholder, C3HU player>
        │  e.g. p002X/C257899eY.java:137, 1062, 1405, 1466, 1477, 1539,
        │       1560, 1636, 1681, 2459, 2514, 2709, 2719, 2727
        ▼
C3HU  ← per-reel player INTERFACE  (p002X/C3HU.java)
        │
        │  impl
        ▼
C89843a5W  ← "ClipsVideoPlayer" (concrete per-reel player wrapper)
   p002X/C89843a5W.java:22  class header:
        public final class C89843a5W extends AbstractC108032llX
                                     implements InterfaceC35048DAz
   p002X/C89843a5W.java:23  field C50741Yd A00;   ← THE actual player
   p002X/C89843a5W.java:25  field SH7 A02;        ← video view holder
        │
        │  created lazily in G6v():
        │  p002X/C89843a5W.java:369
        │      c50741YdA00 = AbstractC50731Yc.A00(context, super.A02,
        │                              this.A09, this, abstractC91822yN.getModuleName());
        ▼
C50741Yd  ← concrete media-player wrapper ("VideoPlayerImpl")
   p002X/C50741Yd.java:50  class header (4747 lines total):
        public final class C50741Yd implements C5W8, InterfaceC34564Cwn,
        InterfaceC35936Ddp, InterfaceC67117Pnc, InterfaceC30605Ba2,
        InterfaceC33388Cdp, InterfaceC35709DaA
   p002X/C50741Yd.java:3998  c57069Lpw.A03 = "VideoPlayerImpl"  (self-identifies)
   p002X/C50741Yd.java:70  field C50301Wl A0J;   ← Groot player core
        │
        ▼
C50301Wl  ← Groot player wrapper  (p002X/C50301Wl.java, 4369 lines)
   p002X/C50301Wl.java:4082  C21630Ke.A0M("IgGrootPlayer", ...)  ← self-identifies
   p002X/C50301Wl.java:1059 constructs C52551c8 (the player surface holder)
        │
        ▼
C52551c8  ← holds the underlying C52701cN player
   (jadx failed to fully decompile C52701cN.java — see error in file:
    p002X/C52701cN.java:1-57 is just a JadxRuntimeException stack trace.
    But its public methods are referenced from C50301Wl.)
        │
        ▼
C52701cN  ← underlying media player (FB Groot / ExoPlayer fork)
   p002X/C52701cN.java:20  "handleMessage(android.os.Message)" — message-based API
   (typical of FB Groot, which is a fork of ExoPlayer with a Handler API)
```

### Key quote: controller → per-reel player lookup

`p002X/C257899eY.java:2755-2763`:
```java
public final boolean A11() {
    C3HU c3hu;
    C27477ADu c27477ADuA0S = A0S();
    C937233l c937233lA04 = c27477ADuA0S.A04(c27477ADuA0S.A00());
    if (c937233lA04 == null || (c3hu = (C3HU) this.A0O.A01.get(c937233lA04)) == null) {
        return false;
    }
    return c3hu.isScrubbingModeEnabled();
}
```

### Does C3EO / its binder receive/set a player instance?

**No.** `C3EO` (p002X/C3EO.java) only allocates a `SimpleVideoLayout A00`
at line 27 and exposes getters. The Litho binder `C3BT` only constructs
the `C3EO` view holder — `p002X/C3BT.java:63`:

```java
return new C3EO(context, this.A00.A01);
```

Grepping `C3BT.java` and `C3EO.java` for `setPlayer|getPlayer|mPlayer|
MediaPlayer|ExoPlayer|VideoPlayer|ClipsPlayer` returns **ZERO matches**.
The player is created lazily OUT-OF-BAND by the controller
`C257899eY` via `C89843a5W.G6v()` (p002X/C89843a5W.java:349-429).

### What does SimpleVideoLayout delegate playback to?

`SimpleVideoLayout` (com/instagram/p132ui/simplevideolayout/SimpleVideoLayout.java)
is a 62-line stub. It extends `AbstractC210917ky` (VideoFrameLayout) and
implements `InterfaceC36365Dkk` (attach/detach helpers) + `CAJ`
(`getEnforceTextureView()`). It does NOT hold any player field — it is
just a FrameLayout that hosts a TextureView (added via
`AbstractC210917ky.addView` at p002X/AbstractC210917ky.java:97-107,
which captures the TextureView into `this.A02`).

The actual playback surface binding happens through
`AbstractC210917ky.setVideoSource(InterfaceC51283Jeo, C8GC, UserSession, C0I9)`
at p002X/AbstractC210917ky.java:30-75 — but `InterfaceC51283Jeo` is a
video-source descriptor, NOT a player. The player attaches its surface to
the TextureView through the `C252819Ri` "zero-module" helper
(p002X/AbstractC210917ky.java:91 — `new C252819Ri(context2, this)`) and
through `A0A.Fys(this, this.A04, c8gc.getModuleName())` at line 57.

**Conclusion:** `SimpleVideoLayout`/`AbstractC210917ky` is purely a
TextureView host. The player is owned by `C257899eY` (controller) →
`C89843a5W` (per-reel) → `C50741Yd` (concrete) → `C50301Wl` (Groot
wrapper) → `C52701cN` (FB Groot player).

---

## Q2 — Playback-control methods on the concrete player

### Per-reel player interface — `C3HU` (p002X/C3HU.java, 71 lines)

Full method list with quoted signatures:

| Method | File:line | Purpose |
|---|---|---|
| `boolean isScrubbingModeEnabled()` | p002X/C3HU.java:68 | scrubbing mode query |
| `void setScrubbingModeEnabled(boolean z)` | p002X/C3HU.java:70 | enable/disable scrubbing mode |
| `void GzY(float f, int i)` | p002X/C3HU.java:66 | **seekTo (normalized 0..1 + flag)** |
| `void GnW(float f)` | p002X/C3HU.java:60 | set playback speed |
| `boolean GQt()` | p002X/C3HU.java:54 | has alt audio track |
| `C105713fg Dag()` | p002X/C3HU.java:14 | get playback info/state |
| `boolean Do5()` | p002X/C3HU.java:20 | is looping |
| `boolean EFv()/EFw()/EFx()` | p002X/C3HU.java:22-26 | state booleans |
| `boolean Ddq()` | p002X/C3HU.java:18 | alt audio is playing |
| `boolean EXr(C56811j0, C937233l)` | p002X/C3HU.java:28 | should-replay check |
| `void ACY(C257899eY)` / `void GEj(C257899eY)` | p002X/C3HU.java:6, 42 | register/unregister controller listener |
| `C937233l DbO()` | p002X/C3HU.java:16 | get view holder |
| `C56811j0 BaV()` | p002X/C3HU.java:12 | get media |
| `C38790v2 BaU()` | p002X/C3HU.java:10 | get alt-audio tracks |

### Concrete per-reel player impl — `C89843a5W` (p002X/C89843a5W.java)

`isScrubbingModeEnabled()` at p002X/C89843a5W.java:554-562:
```java
@Override // p002X.C3HU
public final boolean isScrubbingModeEnabled() {
    C50301Wl c50301Wl;
    C50741Yd c50741Yd = this.A00;
    if (c50741Yd == null || (c50301Wl = c50741Yd.A0J) == null) {
        return false;
    }
    return c50301Wl.A07.A0A.A0O.get();   // AtomicBoolean on the underlying player
}
```

`setScrubbingModeEnabled(boolean)` at p002X/C89843a5W.java:564-570:
```java
@Override // p002X.C3HU
public final void setScrubbingModeEnabled(boolean z) {
    C50741Yd c50741Yd = this.A00;
    if (c50741Yd != null) {
        c50741Yd.A0m(z);
    }
}
```

`GzY(float, int)` (seekTo normalized) at p002X/C89843a5W.java:538-552:
```java
@Override // p002X.C3HU
public final void GzY(float f, int i) {
    InterfaceC113319nxw interfaceC113319nxw = super.A03;
    if (interfaceC113319nxw != null) {
        interfaceC113319nxw.GzZ(f);     // notify the SurfaceTexture/visual layer
    }
    C50741Yd c50741Yd = this.A00;
    if (c50741Yd != null) {
        c50741Yd.A0V(f, i);             // delegate to the concrete player
    }
    C105713fg c105713fg = this.A03;
    if (c105713fg != null) {
        c105713fg.A01 = AnonymousClass084.A1H((f > 0.0f ? 1 : (f == 0.0f ? 0 : -1)));
    }
}
```

### Concrete player wrapper — `C50741Yd` (p002X/C50741Yd.java, 4747 lines)

| Method | File:line | Signature | Purpose |
|---|---|---|---|
| `BbK()` | 3918 | `public final int BbK()` | **getCurrentPositionMs** — returns 0 if IDLE/PREPARING; sanity-checks `> 86400000` (24h); returns `c50301Wl.A0C()` |
| `A0P()` | 1816 | `public final int A0P()` | **getDurationMs** — returns `(int) c50301Wl.A07.A0A.A0Q()` |
| `A0V(float, int)` | 1897 | `public final void A0V(float f, int i)` | **seekToNormalized(0..1, flag)** — clamps `fMin = Math.min(Math.max(f, 0.0f), 1.0f)`; calls `c50301Wl2.A0M(fMin)` + `this.A1G.A06(...)` + thumbnail update |
| `A0h(boolean)` | 3781 | `public final void A0h(boolean z)` | play/pause |
| `A0m(boolean)` | 3830 | `public final void A0m(boolean z)` | **setScrubbingModeEnabled** — logs "setScrubbingModeEnabled: %s" (line 3835) |
| `A0i(boolean)` | 3790 | `public final void A0i(boolean z)` | set mute |
| `A0l(boolean)` | 3821 | `public final void A0l(boolean z)` | set looping |
| `A0n(boolean)` | 3841 | `public final void A0n(boolean z)` | set GRS flag |
| `A0o()` | 3868 | `public final boolean A0o()` | isPrepared |
| `A0r()` | 3896 | `public final boolean A0r()` | **isPlaying** (state == PLAYING) |
| `A0s()` | 3903 | `public final boolean A0s()` | selectAudioRole |
| `A0U(float)` | 1890 | `public final void A0U(float f)` | set playback speed |
| `A0W(int, boolean)` | 1923 | `public final void A0W(int i, boolean z)` | set volume |

`BbK()` (getCurrentPositionMs) — p002X/C50741Yd.java:3917-3925:
```java
@Override // p002X.InterfaceC34227CrM
public final int BbK() {
    int iA0C;
    C50301Wl c50301Wl = this.A0J;
    if (A02(this) == EnumC114143tH.IDLE || A02(this) == EnumC114143tH.PREPARING
            || this.A0m || c50301Wl == null
            || (iA0C = c50301Wl.A0C()) > 86400000) {
        return 0;
    }
    return iA0C;
}
```

`A0P()` (getDurationMs) — p002X/C50741Yd.java:1816-1827:
```java
public final int A0P() {
    boolean z = this.A0T;
    C50301Wl c50301Wl = this.A0J;
    if (z) {
        if (c50301Wl == null) {
            return 0;
        }
    } else if (c50301Wl == null) {
        throw new IllegalStateException("Required value was null.");
    }
    return (int) c50301Wl.A07.A0A.A0Q();
}
```

`A0V(float, int)` (seekToNormalized) — p002X/C50741Yd.java:1897-1921:
```java
public final void A0V(float f, int i) {
    C51001Zd c51001Zd;
    float fMin = Math.min(Math.max(f, 0.0f), 1.0f);
    boolean z = this.A0T;
    C50301Wl c50301Wl = this.A0J;
    /* ... null checks ... */
    this.A1G.A06(DaZ(), i, fMin);
    C50301Wl c50301Wl2 = this.A0J;
    if (c50301Wl2 != null) {
        c50301Wl2.A0M(fMin);                  // actual seek on Groot player
    }
    this.A02 = fMin;
    /* ... thumbnail update via c51001Zd.GIC(...) ... */
}
```

### Groot player wrapper — `C50301Wl` (p002X/C50301Wl.java, 4369 lines)

| Method | File:line | Purpose |
|---|---|---|
| `A0C()` | 1516 | **getCurrentPositionMs** — `c52551c8.A0A.A0P()` (non-clipped) or `c52701cN.A0N() - offset` (clipped) |
| `A0M(float f)` | 2214 | set normalized seek position; calls `this.A07.A0A.A0a("unknown", f)` |
| `A0N(int i, boolean z)` | 2239 | set volume |
| `A0O(Uri)` | 2251 | set media URI |

`A0C()` — p002X/C50301Wl.java:1516-1528:
```java
public final int A0C() {
    C162105oR c162105oR = this.A0F;
    if (c162105oR == null) {
        return 0;
    }
    C52551c8 c52551c8 = this.A07;
    C52701cN c52701cN = c52551c8.A0A;
    long jMax = 0;
    if (c52701cN.A0c()) {
        jMax = Math.max(0L, c52701cN.A0N()
                - (c52701cN.A0c() ? ((C0X8) c52701cN.A0Q.get()).A08 : 0L));
    }
    return !c162105oR.A04() ? (int) c52551c8.A0A.A0P() : (int) jMax;
}
```

### Underlying player — `C52701cN` (p002X/C52701cN.java)

JADX decompile failed (RemoteException handler — see `C52701cN.java:1-57`
which is just a `JadxRuntimeException` stack trace). Public methods
referenced from C50301Wl:

- `A0N()` → `long` getDurationMs (used at C50301Wl.java:1525)
- `A0P()` → `long` getCurrentPositionMs (used at C50301Wl.java:1527)
- `A0Q()` → `long` duration (used at C50741Yd.java:1826 via `A07.A0A.A0Q()`)
- `A0c()` → `boolean` isSeekable / hasClipOffset (used at C50301Wl.java:1524, 1525)
- `A0a(String, float)` → void setNormalizedSeek (used at C50301Wl.java:2219)
- `A0Q.get()` → `C0X8` (clip offset holder with `.A08`)
- `A0R.get()` → `C0X7` (track info holder with `.A0a`)
- `A0E.obtainMessage(46, 2, ...)` — Message-based API (C50741Yd.java:3913)
- Class self-identifies as **"IgGrootPlayer"** at C50301Wl.java:4082

**This is FB Groot** — Instagram's in-house ExoPlayer fork. The
"Time bar scrubbing is enabled, but player is not an ExoPlayer or
CompositionPlayer instance" log at p002X/C75817TRx.java:100 confirms
that IG's player interface can also wrap a stock ExoPlayer /
CompositionPlayer in some contexts.

### Listener interface for progress updates

`InterfaceC35048DAz` (implemented by `C89843a5W` at line 22) — the
player-event listener. Callbacks (from p002X/C89843a5W.java:132-321):

| Listener method | File:line | Likely semantic |
|---|---|---|
| `EpK()` | 133 | onPrepare |
| `Ere(List)` | 137 | onTracksChanged |
| `ExB()` | 151 | onBufferingUpdate |
| `FBi(boolean)` | 155 | onMuteChanged |
| `FGf(int)` | 159 | onVideoSizeChanged(width) |
| `FTF(C105713fg)` | 170 | onPlaybackInfoChanged |
| `FUy(boolean)` | 181 | onPlayingChanged |
| `FV2(int i, int i2, boolean z)` | 189 | onVideoSizeChanged(w, h, isPortrait) |
| `FfA(long j)` | 200 | **onPositionUpdate(positionMs)** — likely the progress tick |
| `Fl9(String, boolean)` | 204 | onStateChanged |
| `FlH(C105713fg, int)` | 223 | onSegmentChanged |
| `FoI()` | 231 | onCompletion |
| `FoM(C105713fg)` | 235 | onPrepared |
| `FyI(C105713fg, boolean)` | 278 | onPaused |
| `Fyo(int, int, float)` | 293 | onBufferingProgress |
| `Fz1(C105713fg)` | 297 | **onPlaybackStateChanged** (with state enum) |
| `FzB(C105713fg)` | 315 | onBufferingStateChanged |
| `FzJ(C105713fg)` | 319 | onLoading |

Additionally the controller `C257899eY` exposes pass-throughs:
- `A0e(C56811j0)` (line ~1499 region) — onPlaybackInfoChanged
- `A0g(C56811j0, int)` — onVideoSizeChanged
- `A0h(C56811j0, int, int, int, boolean)` — onVideoSizeChanged full
- `A0W()` (line 1522) — flush
- `A0i(C56811j0, C11R, C3HU)` (line 2231) — onPrepared callback
- `A0j(C56811j0, C3HU, boolean)` (line 2243) — onPaused callback
- `A0m(C3HU, boolean)` (line 2389) — onPaused wrap
- `A0q(String)` — onStateChanged

### Controller-level seek + scrubbing entry points

`p002X/C257899eY.java:1230-1243` — controller's seekTo wrapper:
```java
private final void A0E(C3HU c3hu, float f, int i) {
    C193006xB c193006xB;
    c3hu.GzY(f, i);                              // seek the player
    C56811j0 c56811j0A01 = A0S().A01();
    if (c56811j0A01 == null || (c193006xB = A0S().A03(c56811j0A01).A0h) == null) {
        return;
    }
    C105713fg c105713fgA0R = A0R();
    boolean z = c105713fgA0R != null ? c105713fgA0R.A01 : false;
    if (c193006xB.A2k != z) {
        c193006xB.A2k = z;
        C193006xB.A00(c193006xB, 55);
    }
}
```

`p002X/C257899eY.java:1453-1460` — controller's current-position:
```java
@NeverInline
public final int A0P() {
    C193006xB c193006xB;
    C56811j0 c56811j0A01 = A0S().A01();
    if (c56811j0A01 == null
            || (c193006xB = A0S().A03(c56811j0A01).A0h) == null) {
        return 0;
    }
    return c193006xB.A09;          // media playback position MS
}
```

`p002X/C50317JAi.java:723-733` — config-driven scrubbing toggle:
```java
public static Object A0B(Object obj, Object obj2) {
    C3HU c3hu;
    boolean zA0P = C00F.A0P(obj);
    C257899eY c257899eY = ((C2BP) ((AbstractC109063l5) obj2).receiver).A01;
    C27477ADu c27477ADuA0S = c257899eY.A0S();
    C937233l c937233lA04 = c27477ADuA0S.A04(c27477ADuA0S.A00());
    if (c937233lA04 != null
            && (c3hu = (C3HU) c257899eY.A0O.A01.get(c937233lA04)) != null) {
        c3hu.setScrubbingModeEnabled(zA0P);
    }
    return C4SE.A00;
}
```

`p002X/C50317JAi.java:244-250` — listener method signatures (Redex stubs):
```
"onScrubbingModeEnabled(Z)V"
"onScrubbingModeEnabled"
"onSeekWhileScrubbing(I)V"
"onSeekWhileScrubbing"
```

→ IG already has a listener callback `onSeekWhileScrubbing(int positionMs)`
and `onScrubbingModeEnabled(boolean)`.

---

## Q3 — Reusable SeekBar / scrubber / progress bar anywhere in IG

### PRIMARY FINDING — `VideoScrubberSeekBar`

**File:** `com/instagram/p132ui/mediaactions/VideoScrubberSeekBar.java` (299 lines)

**Class header** (lines 39-50):
```java
public final class VideoScrubberSeekBar
        extends AppCompatSeekBar
        implements SeekBar.OnSeekBarChangeListener {
    public SeekBar.OnSeekBarChangeListener A00;   // external listener
    public final C3HF A01;                          // keyframe-marker drawer

    public VideoScrubberSeekBar(Context context, AttributeSet attributeSet, int i) {
        super(context, attributeSet, i);
        this.A01 = new C3HF(this);
        super.setOnSeekBarChangeListener(this);
    }
}
```

**Existing features:**
- `setupAdKeyFrameMarkers(Activity, String, List, Long, boolean, C8GC, ...)` (line 74) — set keyframe/chapter markers
- `onProgressChanged(SeekBar, int, boolean)` (line 97) — delegates to `A00` listener + updates keyframe UI
- `onStartTrackingTouch(SeekBar)` (line 109) — delegates + captures initial progress
- `onDraw(Canvas)` (line 87) — draws keyframe markers via `c3hf.A07(canvas)`
- Companion `A00(Activity, int)` (line 77) — shows/hides `R.id.clips_keyframes_container`

**Sibling views in same package:**
- `com.instagram.p132ui.mediaactions.ScrubberPreviewThumbnailView` — the thumbnail preview popup during scrubbing
- `com.instagram.p132ui.mediaactions.MediaActionsView` — the container that hosts the seekbar + thumbnails + keyframe text
- `com.instagram.p132ui.mediaactions.keyframe.VideoKeyframeHighlightsTextView` — chapter markers text

**Other seekbar resources in IG:**
- `R.id.video_seekbar` (0x7f0b455c) — generic video seekbar
- `R.id.scrubber_seekbar` (0x7f0b386e)
- `R.id.middle_seekbar` (0x7f0b2730) — middle seekbar with `middle_seekbar_bottom_cutoff_fade`, `middle_seekbar_fade`, `middle_seekbar_normal` drawables
- `R.id.seekbar` (0x7f0b391b), `R.id.seekbar_divider`, `R.id.seekbar_value`
- `R.id.timebar_recyclerview` (0x7f0b417e)
- `Widget_IgSeekBar`, `Widget_IgSeekBar_Night`, `Widget_BaselSeekBar`, `Widget_BaselSeekBarDimmable` styles
- `IgEditSeekBar` (`com.instagram.p132ui.igeditseekbar.IgEditSeekBar`) — used in lead-ads forms (not relevant)
- `preference_widget_seekbar` / `preference_widget_seekbar_material` — preference seekbars

→ **Use `VideoScrubberSeekBar` directly** — it's purpose-built for video
scrubbing with keyframes and is already wired into clips.

---

## Q4 — Existing progress UI on Reels (thin progress bar)

### A. Display-only segmented bar (the THIN blue bar visible in Reels)

**File:** `com/instagram/p132ui/widget/segmentedprogressbar/SegmentedProgressBar.java` (587 lines)

**Public API:**
| Method | File:line | Purpose |
|---|---|---|
| `setProgress(float f)` | 535 | set 0..1 progress on current segment (clamped) |
| `setSegments(int i)` | 540 | set total segment count |
| `setCurrentSegment(int i)` | 519 | set active segment |
| `getCurrentSegment()` | 305 | get active segment |
| `getSegments()` | 309 | get segment count |
| `A0A(int i, boolean z)` | 283 | set current segment + animate flag |
| `A0B(boolean, boolean)` | 291 | configure dimensions (corner radius, padding, height) |
| `A09()` | 278 | reset progress to 0 |
| `setEllipsisAfterIndex(int)` | 527 | set ellipsis cutoff |
| `setPositionAnchorDelegate(InterfaceC41873FrO)` | 531 | position anchor (for thumbnails) |

**No `onTouchEvent` override** — purely display-only. Cannot be dragged.

**Used in:**
- `p002X/C1458858b.java:210` — `(SegmentedProgressBar) viewInflate2.findViewById(R.id.bottom_scrubber_progress_bar)` (ReelItemView binder, story-style viewer)
- `p002X/C1458858b.java:228` — top story progress bar
- `p002X/ZRL.java:44, 179` — `this.A0J.setProgress(c8zv.A02())` (alternative reel viewer)

The story-style viewer (`C1458858b`) uses the `bottom_scrubber_progress_bar`
inside `R.id.bottom_scrubber_progress_bar_stub` — inflated only when
MobileConfig flag `36332820574529694L` is on (p002X/C1458858b.java:204,
gated by `zBHQ2`).

### B. Clips viewer scrubber (the FULL TikTok-style seekbar — already exists!)

**Litho mount-spec:** `p002X/C30423BTc.java` (121 lines)

**Class header** (lines 18-19):
```java
public final class C30423BTc extends AbstractC76222Yd {
    public static final Drawable A0E = new ColorDrawable(0);
```

**Component name** (line 91):
```java
C2ZW.A02("instagram_features_clips_viewer_adapter_organic_mountspec_LegacyClipsAttachedScrubberComponent");
```

→ This is the "LegacyClipsAttachedScrubberComponent" — the existing IG
scrubber for the clips viewer (note: "Legacy" suggests there may be a
newer one, but this one is fully functional and shipped).

**Imports** (lines 11-13):
```java
import android.widget.SeekBar;
import com.instagram.common.session.UserSession;
import com.instagram.p132ui.mediaactions.VideoScrubberSeekBar;
```

**Scrubber lookup helper** (lines 71-79):
```java
public static final VideoScrubberSeekBar A01(Activity activity, C56811j0 c56811j0) {
    View childAt;
    View viewFindViewWithTag;
    ViewGroup viewGroup = (ViewGroup) activity.findViewById(R.id.content);
    if (viewGroup == null
            || (childAt = viewGroup.getChildAt(0)) == null
            || (viewFindViewWithTag = childAt.findViewWithTag(
                    AbstractC168601v.A0V("clips_scrubber_", c56811j0.C7D()))) == null) {
        return null;
    }
    return (VideoScrubberSeekBar) viewFindViewWithTag.findViewById(
            com.instagram.android.R.id.scrubber);
}
```

**Height-animator helper** (lines 54-69): `A00(SeekBar seekBar, int i, int i2)` — animates the SeekBar height (collapse/expand) via `ValueAnimator.ofInt(i, i2)` with 150ms duration.

**Layout binding** — `p002X/BT7.java:530-533` sets the tag:
```java
if (this.A01) {
    viewGroup.setTag(AbstractC168601v.A0V("clips_scrubber_",
            ((C30423BTc) this.A00).A04.C7D()));
}
```

**Related view IDs touched** (p002X/BT7.java:539-546):
- `R.id.timestamps_container` — start/end timestamps
- `R.id.scrubber_hairline` — thin line under the seekbar
- `R.id.scrubber_preview_thumbnail_view` — preview thumbnail during scrubbing
- `R.id.clips_keyframe_highlights_text_container` — chapter markers text
- `VideoKeyframeHighlightsTextView` — the chapter text view itself
- `R.id.scrubber` — the VideoScrubberSeekBar itself

**MobileConfig gating** — p002X/C30423BTc.java:109:
```java
C0WS c0wsA19 = AnonymousClass936.A19(
        C00F.A0Q(C00F.A05(this.A05, 0), 36320867680860001L)
            ? BU3.A00 : C87169YnP.A00,
        null, 3, zA1X);
```

Flag `36320867680860001L` selects the layout variant. To enable
the scrubber for all clips, force this config true (or short-circuit
the `C00F.A0Q(...)` call).

### C. ClipsProgressUiState — the scrubber config model

**File:** `p002X/C27533AFy.java` (151 lines, "ClipsProgressUiState")

`toString()` at lines 87-148 reveals every config field:

```
ClipsProgressUiState(
  scrubberAreaPct=...,
  shouldDisableThumbnailOnSmoothScrubber=...,
  shouldIncreaseScrubberDragArea=...,
  dragAreaExtensionTopHeight=30.0,
  dragAreaExtensionBottomHeight=10.0,
  tapAreaExtensionTopHeight=18.0,
  validVideoDurationForScrubberInSeconds=...,
  enableScrubberBasedOnVideoDuration=...,
  enableScrubberBasedOnVideoDurationAdsOnly=...,
  validVideoDurationForUniversalScrubberInSeconds=...,
  validVideoDurationForOrganicScrubberInSeconds=...,
  enableScrubberPassThroughGestureAdsOnly=...,
  enableUniversalScrubberPassThroughGestureAdsOnly=...,
  enableScrubberPassThroughGesture=...,
  enableUniversalScrubberPassThroughGesture=...,
  enableScrubberClickPassthroughToMedia=...,
  enableScrubberClickPassthroughToMediaAdsOnly=...,
  enableUniversalScrubberClickPassthroughToMedia=...,
  enableUniversalScrubberClickPassthroughToMediaAdsOnly=...,
  isScrubberFixEnabled=...,
  isNuclearScrubberFixEnabled=...,
  isSwipeableTabsEnabled=...,
  isReelsFirstEnabled=...,
  isPandroidEnabled=...,
  isKeyframeHighlightsEnabled=...,
  isKeyframeHighlightsTextComponentEnabled=...,
  shouldAdvanceToMidsceneIfScrubberInteracted=...,
  fixScrubberExpandedTouchView=...,
  useUnifiedBottomBarHeight=...)
```

→ IG has a complete scrubber config system with duration-gating,
drag-area-extension, passthrough-gesture, click-passthrough, keyframe
highlights, etc. The scrubber is gated by `validVideoDurationForScrubberInSeconds`
(default not shown but easily flipped).

### D. "clips_scrubber_" tag in use elsewhere

- `p002X/AbstractC936933i.java:69` — same lookup helper as C30423BTc.A01
- `p002X/C3GX.java:497` — `new C3GX("CLIPS_SCRUBBER_INTERACTION", 260, "clips_scrubber_interaction")` — analytics event
- `p002X/D75.java:165, 169` — `R.drawable.clips_scrubber_thumb_active_drawable` — the scrubber thumb drawable

→ The scrubber UI is fully built, has analytics events, has its own
thumb drawable, and is shipped. Just needs to be force-enabled.

### E. HeroServicePlayer — `C0X4.java`

`p002X/C0X4.java` is the "HeroServicePlayer" (line 2555: `"HeroServicePlayer.setScrubbingModeEnabledInternal"`). It is the feed/preload player that also implements `setScrubbingModeEnabled` (line 2560). This is the player used when a reel is preloaded before the user scrolls to it — same scrubbing API.

`p002X/C0X4.java:429`:
```java
z5 = c41154Ffn.A04.isScrubbingModeEnabled();
```

`p002X/C0X4.java:2557-2560`:
```java
A0c(this, "setScrubbingModeEnabledInternal %s", Boolean.valueOf(z));
/* ... */
c41154Ffn.A04.setScrubbingModeEnabled(z);
```

→ Same scrubbing API surface as the active reels player.

### F. VideoInferenceUtil note

Per 3-e finding, `com.instagram.common.clips.player/` only contains
`VideoInferenceUtil.java` — no Player interface. That directory is a
red herring; the real player is in `p002X/` (as documented above).

---

## Feature D seekbar feasibility verdict

### Approach comparison

| Approach | Effort | Risk | Reuse |
|---|---|---|---|
| **A. Reuse existing `VideoScrubberSeekBar` + `C30423BTc`** (flip MobileConfig flag `36320867680860001L` + ClipsProgressUiState duration gates) | LOW | LOW | 100% — IG-built, IG-tested, ships with keyframes + thumbnail preview + chapter text |
| B. Add a custom SeekBar overlay in `VBP.FSS` (3-e's recommendation) | MEDIUM | MEDIUM (need to wire player polling, lifecycle) | 0% — duplicates IG's existing scrubber |
| C. Overlay FB media3 `PlayerView` controller (3-e mentioned but warned against) | HIGH | HIGH (media3 not wired to clips) | 0% — too invasive |

### Recommended approach: **A — Reuse `VideoScrubberSeekBar` via `C30423BTc`**

Rationale:
1. IG already ships a TikTok-equivalent scrubber for clips (`VideoScrubberSeekBar` + `ScrubberPreviewThumbnailView` + `VideoKeyframeHighlightsTextView`).
2. The Litho mount-spec `C30423BTc` ("LegacyClipsAttachedScrubberComponent") already knows how to bind it per-reel (uses tag `"clips_scrubber_" + mediaId`).
3. The player interface `C3HU` already has `setScrubbingModeEnabled(boolean)` + `GzY(float, int)` (seekTo normalized), and the concrete `C50741Yd` already has `BbK()` (getCurrentPositionMs) + `A0P()` (getDurationMs).
4. The controller `C257899eY` already has a `A0E(C3HU, float, int)` seek wrapper at line 1230 and `A11()` scrubbing-state query at line 2755.
5. The existing listener API `onScrubbingModeEnabled(Z)V` + `onSeekWhileScrubbing(I)V` (p002X/C50317JAi.java:244-250) is already there.

### Concrete binding recipe (for the patching agent — NOT for this turn)

In `VBP.FSS(int i, int i2)` at `p002X/VBP.java:116` (per 3-e), after creating the EPN ufi-fade animator at line 131:

1. **Force-show the existing scrubber** by either:
   - Flipping the MobileConfig gate `36320867680860001L` at `p002X/C30423BTc.java:109` to true (Smali patch), OR
   - Forcing the `ClipsProgressUiState.validVideoDurationForScrubberInSeconds = 0` and `enableScrubberBasedOnVideoDuration = true` (so the scrubber shows for all videos), OR
   - Directly calling `C30423BTc.A01(activity, c56811j0)` (line 71) to fetch the existing `VideoScrubberSeekBar` and making it visible.

2. **Wire `VideoScrubberSeekBar` to the player** — register a `SeekBar.OnSeekBarChangeListener`:
   ```java
   VideoScrubberSeekBar seekBar = C30423BTc.A01(activity, c56811j0);
   C3HU c3hu = (C3HU) c257899eY.A0O.A01.get(c257899eY.A0T());
   C50741Yd player = ((C89843a5W) c3hu).A00;

   seekBar.setMax(player.A0P());                     // duration MS
   seekBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
       public void onStartTrackingTouch(SeekBar s)  { c3hu.setScrubbingModeEnabled(true); }
       public void onProgressChanged(SeekBar s, int p, boolean fromUser) {
           if (fromUser) c3hu.GzY((float) p / s.getMax(), 0);    // 0..1
       }
       public void onStopTrackingTouch(SeekBar s)   { c3hu.setScrubbingModeEnabled(false); }
   });

   // Poll current position at 33ms (already the FB pattern):
   handler.postDelayed(new Runnable() {
       public void run() {
           seekBar.setProgress(player.BbK());
           handler.postDelayed(this, 33);
       }
   }, 33);
   ```

3. **Hide the seekbar in `VBP.EvT()`** at `p002X/VBP.java:47` (per 3-e) — restore the original visibility.

### Concrete player method signatures to bind to

All on `C50741Yd` (concrete player wrapper, p002X/C50741Yd.java) — accessible from `((C89843a5W) c3hu).A00`:

```java
public final int  BbK();                  // getCurrentPositionMs  (p002X/C50741Yd.java:3918)
public final int  A0P();                  // getDurationMs         (p002X/C50741Yd.java:1816)
public final void A0V(float f, int i);    // seekToNormalized 0..1 (p002X/C50741Yd.java:1897)
public final boolean A0r();               // isPlaying             (p002X/C50741Yd.java:3896)
public final boolean A0o();               // isPrepared            (p002X/C50741Yd.java:3868)
public final void A0h(boolean z);         // play/pause            (p002X/C50741Yd.java:3781)
public final void A0m(boolean z);         // setScrubbingModeEnabled (p002X/C50741Yd.java:3830)
```

On the `C3HU` per-reel interface (p002X/C3HU.java) — preferred for
decoupling from the concrete impl:

```java
void   setScrubbingModeEnabled(boolean z);   // p002X/C3HU.java:70
boolean isScrubbingModeEnabled();            // p002X/C3HU.java:68
void   GzY(float f, int i);                  // p002X/C3HU.java:66  seekTo normalized 0..1
void   GnW(float f);                         // p002X/C3HU.java:60  set playback speed
```

On the controller `C257899eY` (p002X/C257899eY.java):

```java
public final int  A0P();                          // line 1453  current position MS (via C193006xB.A09)
public final boolean A11();                       // line 2755  is scrubbing mode on
private final void A0E(C3HU c3hu, float f, int i); // line 1230  seek wrapper (calls c3hu.GzY)
public final C937233l A0T();                      // line 1494  get current viewholder
```

---

## Open gaps for next agent (patching agent)

1. Confirm the MobileConfig flag values to flip — `36320867680860001L`
   (C30423BTc.java:109) and `36332820574529694L` (C1458858b.java:204).
   These need to be forced ON in Smali (override `BHQ`/`BHY` returns).
2. Inspect `ClipsProgressUiState` construction to find the
   `validVideoDurationForScrubberInSeconds` default — needs to be set
   low (e.g., 0 or 1) so all reels qualify.
3. Decompile tail of `C52701cN` (jadx failed) to confirm the exact
   ExoPlayer-style methods if direct ExoPlayer binding is needed (not
   required for approach A — `C50741Yd`'s public methods suffice).
4. Find where `C30423BTc` is mounted in the Litho tree for the clips
   viewer (likely in `C254289Wz` or a sibling component-spec) — to
   confirm the component is actually instantiated (just hidden) or
   whether we also need to mount it.
5. Confirm the 3-e VBP.FSS/EvT hook point is the right show/hide
   trigger for the seekbar (vs. the long-press "FULLSCREEN_VIEW" menu
   path at IA3.F6G/IA5.F6G).

---

## File reference summary (all READ-ONLY)

| File | Lines | Role |
|---|---|---|
| `p002X/C3EO.java` | 72 | Clips video frame layout — holds `SimpleVideoLayout A00` (line 16) |
| `p002X/C3BT.java` | 314 | Litho binder — creates `C3EO` at line 63; no player wiring |
| `com/instagram/p132ui/simplevideolayout/SimpleVideoLayout.java` | 62 | TextureView host stub; no player |
| `p002X/AbstractC210917ky.java` | 251 | "VideoFrameLayout" base — owns TextureView A02, setVideoSource |
| `p002X/C257899eY.java` | 2883 | **ClipsVideoPlayerController** — owns the per-reel player map (A0O.A01) |
| `p002X/C3HU.java` | 71 | **Per-reel player INTERFACE** — has setScrubbingModeEnabled/GzY |
| `p002X/C89843a5W.java` | 571 | "ClipsVideoPlayer" — concrete C3HU; holds C50741Yd A00 (line 23) |
| `p002X/AbstractC108032llX.java` | 48 | Abstract C3HU base (no-op stubs) |
| `p002X/C50741Yd.java` | 4747 | **VideoPlayerImpl** — has BbK (curPos), A0P (dur), A0V (seekTo) |
| `p002X/C50301Wl.java` | 4369 | IgGrootPlayer wrapper — A0C (curPos), A0M (seek) |
| `p002X/C52701cN.java` | — | Underlying FB Groot player (jadx decompile failed) |
| `p002X/C937233l.java` | 213 | Clips viewholder (LithoView + media + state) |
| `p002X/C1458858b.java` | 782 | ReelItemView binder (story-style) — uses SegmentedProgressBar |
| `p002X/ZRL.java` | 235 | Alt reel viewer — `setProgress(c8zv.A02())` at line 179 |
| `com/instagram/p132ui/widget/segmentedprogressbar/SegmentedProgressBar.java` | 587 | Display-only thin bar (no touch) |
| `p002X/C30423BTc.java` | 121 | **LegacyClipsAttachedScrubberComponent** Litho spec — uses VideoScrubberSeekBar |
| `com/instagram/p132ui/mediaactions/VideoScrubberSeekBar.java` | 299 | **THE TikTok-style seekbar** (AppCompatSeekBar + keyframes) |
| `com/instagram/p132ui/mediaactions/ScrubberPreviewThumbnailView.java` | — | Preview thumbnail during scrub |
| `com/instagram/p132ui/mediaactions/MediaActionsView.java` | — | Container |
| `com/instagram/p132ui/mediaactions/keyframe/VideoKeyframeHighlightsTextView.java` | — | Chapter text |
| `p002X/C27533AFy.java` | 151 | ClipsProgressUiState — scrubber config model |
| `p002X/C50317JAi.java` | 2836+ | setScrubbingModeEnabled wiring (line 730); onSeekWhileScrubbing listener (line 249) |
| `p002X/C0X4.java` | — | HeroServicePlayer — same scrubbing API for preload |
| `p002X/BT7.java` | 828 | Sets `clips_scrubber_<id>` tag + wires scrubber subviews |
| `p002X/C3GX.java` | — | "CLIPS_SCRUBBER_INTERACTION" analytics event |
| `p002X/D75.java` | — | `R.drawable.clips_scrubber_thumb_active_drawable` |
