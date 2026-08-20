# Task 4-b Findings — Popup-Menu "Fullscreen" Action Path + VBP Activity Access

**Agent:** Explore (Task ID 4-b)
**Scope:** Confirm the popup-menu "Fullscreen View" action path; confirm how `VBP` reaches the host Activity (needed for `setRequestedOrientation` in Feature D).

---

## Q1. Does `I34.run()` case 33 invoke `VBP.FSS`?

### Answer: **NO.** Case 33 is fully decompiled (3-e was wrong about it being truncated). It calls `InterfaceC113486oAK.FGC(c56811j0, c11r)`, which is implemented in `C14U.FGC` (deprecated path) and `C107910ljY.FGC` (stub) to do nothing more than store state + fire analytics. Neither path reaches `VBP.FSS`.

### Evidence (file:line)

**`p002X/I34.java:234-239` — case 33 IS decompiled (3-e's "un-decompiled tail" claim was wrong):**
```java
case 33:
    C2OR c2or2 = (C2OR) this.A00;
    InterfaceC113486oAK interfaceC113486oAK2 = c2or2.A09;
    C56811j0 c56811j4 = c2or2.A05;
    interfaceC113486oAK2.FGC(c56811j4, c2or2.A08.A08(c56811j4));
    return C4SE.A00;
```
(All 44 cases 0..44 are present in `I34.java:40-277` — none is missing.)

**`p002X/InterfaceC113486oAK.java:17` — FGC signature:**
```java
void FGC(C56811j0 c56811j0, C11R c11r);
```

**`p002X/C14U.java:461-472` — the deprecated/real impl of FGC** (C14U is `@Deprecated`, marked at `C14U.java:32`):
```java
@Override // p002X.InterfaceC113486oAK
public final void FGC(C56811j0 c56811j0, C11R c11r) {
    C109103l9.A0R(c11r);
    this.A00 = c56811j0;                          // store current "fullscreen target" clip
    this.A01 = c11r;                              // store clips-item-state
    ((C14Z) this.A0Z.getValue()).GLH(c56811j0, c11r);  // also store in C14Z
    A8Q a8q = this.A0P;
    if (c11r.A0v) {                               // isFullscreenViewActive per-reel flag
        a8q.Dij(c56811j0, EnumC93916bLv.OVERFLOW_MENU);  // analytics "set target"
    } else {
        a8q.Dik(EnumC93916bLv.OVERFLOW_MENU);     // analytics "no target"
    }
}
```
`C14Z.GLIH` (`p002X/C14Z.java:366-370`) just stores `c56811j0`/`c11r` and returns. `A8Q.Dij/Dik` (`p002X/A8Q.java:745-753`) delegate to `C27190A2t.Dij/Dik` (`p002X/C27190A2t.java:12-26`) which invokes a registered `Function1`/`InterfaceC115518piL` callback. The callbacks are registered in `C27335A8i.java:632-633` (`a8q.GZr(new C28732Akv(this, 18)); a8q.GZs(new C50317JAi(this, 45));`) and are analytics-only (no FSS call in `C27335A8i.java` — confirmed by `rg "\.FSS\(|\.EvT\(" C27335A8i.java` returning no matches).

**`p002X/C107910ljY.java:78-79` — alternative FGC impl (stub):**
```java
public final void FGC(C56811j0 c56811j0, C11R c11r) {
}   // empty no-op
```

### Newer IA5 path also does NOT call VBP.FSS

The newer popup-menu callback is `IA5.F6G()` (`p002X/IA5.java:26-29`):
```java
public final void F6G() {
    C15T.A09(MediaOption$Option.FULLSCREEN_VIEW, this.A00);
}
```
`C15T.A09` (`p002X/C15T.java:531-537`) → `Handler.postDelayed(RunnableC48619Icv, 350L)` → `c15t.A0N(FULLSCREEN_VIEW)` (`p002X/C15T.java:3045-3060`) → for ordinal 114 (FULLSCREEN_VIEW), falls into `default` → `A0F(this, iOrdinal)` (`p002X/C15T.java:3289`).

`A0F` (`p002X/C15T.java:1036`) switches on `i`, and **case 114 is `case FilterIds.LAGOS /* 114 */`** at `p002X/C15T.java:1211-1225`:
```java
case FilterIds.LAGOS /* 114 */:
    C90202vl.A01(295472);                              // QPL marker log
    AbstractC91822yN abstractC91822yN2 = c15t.A07;
    UserSession userSession4 = c15t.A0C;
    InterfaceC30633BaU interfaceC30633BaU2 = c15t.A0D;
    Media media20 = c15t.A02;
    ...
    TGH.A02(abstractC91822yN2, userSession4, interfaceC30633BaU2, new H3U(media20.GCZ(1444641751)), AnonymousClass006.A01, null, null, str3);
    return;
```
Just a server-side analytics log (`TGH.A02` is a GraphQL pando logger). NO VBP.FSS, NO rotation, NO seekbar.

### So who actually calls `VBP.FSS`?

`VBP` is registered as the clips-viewer `InterfaceC113320nxx` gesture listener (constructed via `p002X/E4I.java:575-576` for case 285: `return new VBP((RE7) this.A00);`). `VBP.FSS` is called by gesture/scroll broadcasters, NOT by the popup menu:

- **`p002X/AnonymousClass940.java:548`** — scroll/translate callback (`Fjg(C37850tW)`); iterates `c109193lI.A1b` (the gesture-listener set) and calls `FSS(iA05, i)` on each:
  ```java
  Iterator it = c109193lI.A1b.iterator();
  while (it.hasNext()) {
      ((InterfaceC113320nxx) it.next()).FSS(iA05, i);
  }
  ```
- **`p002X/C106638kpe.java:128-133`** — composite broadcaster; forwards FSS to all child listeners.
- **`p002X/C106635kpb.java:70-72`** and **`p002X/C106420kle.java:79-82`** — adapter forwards (delegate to inner listener).
- `p002X/C71799Rgy.java:150` and `p002X/C117346vPR.java:46` — these are the **BrowserLiteFragment** path (in-app browser WebChromeClient fullscreen), NOT reels. Dead-end for Reels.

### Q1 Conclusion

The popup-menu "Fullscreen View" tap does **NOT** trigger `VBP.FSS`. It only:
1. Logs the click via QPL marker (`C90202vl.A01(295472)` in newer path).
2. Sends a server analytics event (`TGH.A02(...)` / `A8Q.Dij/Dik`).
3. (Deprecated path only) sets C14U.A00/A01 + C14Z.A00/A01 = current "fullscreen target" clip — but no consumer of these fields calls VBP.FSS either (no `\.FSS\(` or `\.EvT\(` references in C14U.java, C14Z.java, or C27335A8i.java).

`VBP.FSS` is invoked ONLY by the gesture/scroll path (AnonymousClass940.Fjg → broadcaster → listener-set).

**Implication for Feature D patch design:** Hooking `VBP.FSS`/`VBP.EvT` covers only the **gesture-driven** hide-ufi toggle, NOT the popup-menu "Fullscreen View" action. If the patch wants the popup-menu button to also rotate+seekbar, it must add a SECOND hook in `C15T.A0F` case 114 (and/or `C14U.FGC`) — OR redirect the popup-menu tap to call VBP.FSS directly. The cleanest single hook is still VBP.FSS/EvT (covers the gesture path which is the more common UX), and a second hook in `C15T.A0F:1211` (case 114) for the menu path.

---

## Q2. How does `VBP` get the Activity / Context?

### VBP constructor + fields (`p002X/VBP.java:10-17`):
```java
public final class VBP implements InterfaceC113320nxx {
    public boolean A00;
    public boolean A01;
    public final /* synthetic */ RE7 A02;

    public VBP(RE7 re7) {
        this.A02 = re7;
    }
```
VBP is a plain object (not a Fragment, not a View). It holds a single reference to `RE7` (`p002X/RE7.java`), which is the clips-viewer gesture host.

### RE7 exposes a `C27468ADl` clips-item container (`p002X/RE7.java:24, 27-40`):
```java
public final C27468ADl A0C;            // field
...
public RE7(ClipsViewerSource clipsViewerSource, UserSession userSession, ... C27468ADl c27468ADl) {
    ...
    this.A0C = c27468ADl;
    ...
}
```

### VBP accesses the clips-item View via `AnonymousClass955.A06(re7.A0C)`:
- `p002X/VBP.java:124` (inside FSS): `View viewA06 = AnonymousClass955.A06(re7.A0C);`
- `p002X/VBP.java:146, 153` (inside FSS): same pattern.
- `p002X/VBP.java:55, 62` (inside EvT): same pattern.

**`p002X/AnonymousClass955.java:66-68` — A06 returns a View:**
```java
public static View A06(C27468ADl c27468ADl) {
    return c27468ADl.A0J(c27468ADl.A0E());
}
```

### How to get the Activity from VBP

A standard Android View's `getContext()` typically returns the hosting Activity — but in IG the View may be wrapped in a `ContextWrapper` (for theme or night-mode). The proper way is to unwrap:

**`p002X/AbstractC106081keV.java:14-24` — the Activity-from-Context unwrapper (already used by `AbstractC104253ij1.A00` at line 22):**
```java
public static final Activity A00(Context context) {
    if (context instanceof Activity) {
        return (Activity) context;
    }
    if (!(context instanceof ContextWrapper)) {
        return null;
    }
    Context baseContext = ((ContextWrapper) context).getBaseContext();
    C109103l9.A0D(baseContext);
    return A00(baseContext);
}
```

### VBP does NOT currently access any Context/Activity

`rg "getContext|requireActivity|Activity\s*\)" p002X/VBP.java` returns ZERO matches. VBP only touches View objects (`AnonymousClass955.A06(re7.A0C)` → View) and uses `View.findViewById(R.id.clips_ufi_component)` (`VBP.java:63, 154`). No Activity is held; no setRequestedOrientation is currently called.

### Q2 Conclusion — cleanest way to obtain the Activity inside `VBP.FSS` / `VBP.EvT`

```java
View v = AnonymousClass955.A06(this.A02.A0C);
if (v != null) {
    Activity act = AbstractC106081keV.A00(v.getContext());
    // act is now the hosting FragmentActivity (the MainActivity for Reels)
}
```

Note: `C14U.A05` is a `FragmentActivity` field (`p002X/C14U.java:39`: `public final FragmentActivity A05;`), and `C15T.A06` is also a `FragmentActivity` (`p002X/C15T.java:3130, 3194`, etc.). The unwrapped View context will resolve to the same FragmentActivity.

---

## Q3. The `setRequestedOrientation` helpers — which to reuse?

3-e flagged two helpers (`C99744f1m.A01` and `AbstractC186396mW.A00`). Reading both + the other 3 (`AbstractC104253ij1`, `C45773HVn`, `SF7`) for completeness:

### A. `AbstractC186396mW.A00(Activity, int)` — **RECOMMENDED** ✅
`p002X/AbstractC186396mW.java:7-20` (full file):
```java
public abstract class AbstractC186396mW {
    public static final void A00(Activity activity, int i) {
        if (activity != null) {
            try {
                activity.setRequestedOrientation(i);
            } catch (IllegalStateException e) {
                if (!"Only fullscreen activities can request orientation".equals(e.getMessage())) {
                    throw e;
                }
                C21630Ke.A0K("FixedOrientationCompat", "%s hit fixed orientation exception", e, AbstractC178105m.A00(activity.getClass()));
            }
        }
    }
}
```
- **Signature:** `static void A00(Activity activity, int orientation)`.
- **Side effects:** NONE — pure wrapper around `setRequestedOrientation`. No system-UI flag changes, no View tree mutation, no config-change override, no persistent lock state. The activity config will rebuild itself (Android will recreate the Activity if orientation actually changes — standard behavior).
- **Bonus:** swallows the `IllegalStateException("Only fullscreen activities can request orientation")` thrown on Android 8.0+ when the activity isn't `windowIsFullScreen=true` in its theme. This is the single most common failure mode for `setRequestedOrientation` and is silently logged (not rethrown).
- **Best for:** VBP.FSS hook — minimal footprint, no surprises.

### B. `C99744f1m.A02(String)` — NOT recommended (stateful + view-tree side effects)
`p002X/C99744f1m.java:13-19` — fields:
```java
public final class C99744f1m {
    public Activity A00;
    public InterfaceC116563twl A01;
    public InterfaceC116596ua2 A02;
    public InterfaceC116137qxn A03;
    public WeakHashMap A04;
```
`p002X/C99744f1m.java:95-139` — `A02(String)`:
- Takes a string `"LANDSCAPE"` or `"PORTRAIT"` (not an int).
- Stateful: requires `A00` (Activity) to be set externally before invocation (constructor not shown; instantiation site sets the field).
- **Side effect:** also calls `A01(str, collection)` (`C99744f1m.java:36-87`) which **mutates the layout**: walks a `Collection<ViewGroup>`, finds `LinearLayout` children, sets `setOrientation(1)` for portrait / `setOrientation(0)` for landscape, and adjusts `topMargin` of children — saving originals into `WeakHashMap A04`. This is meant for IG's in-app browser "desktop mode" toggle that reorients a LinearLayout layout, NOT for Reels.
- Also notifies an `InterfaceC116596ua2` callback with a string resource id for the rotation icon (`GTw(i)` at lines 119, 134).
- **NOT clean for our use case:** would touch unrelated LinearLayouts in the Reels view tree.

### C. `AbstractC104253ij1.A01(...)` — NOT recommended (over-invasive)
`p002X/AbstractC104253ij1.java:43-88` builds a fullscreen `C103394hoZ` config — reads window flags, system UI visibility, creates `FrameLayout` + `ImageView`, reads `Settings.System.accelerometer_rotation`. Meant for IGTV/in-app browser "true fullscreen" rendering. Way too invasive for our Reels rotation hook.

### D. `C45773HVn` (line 138, 434) and `SF7` (line 239, 249)
Both are state-machine controllers for "fixed orientation lock" features (used for IGTV / Story composer / capture flows). They keep an `A0M`/`A0C` boolean state and call `setRequestedOrientation(14)` (USER) for "lock current" and `setRequestedOrientation(0)` for "force landscape". Heavier than needed; `AbstractC186396mW.A00` is a strict subset.

### Orientation constant reference (from `android.content.pm.ActivityInfo`)
| Constant | Int | Meaning |
|---|---|---|
| `SCREEN_ORIENTATION_LANDSCAPE` | 0 | Force landscape |
| `SCREEN_ORIENTATION_PORTRAIT` | 1 | Force portrait |
| `SCREEN_ORIENTATION_SENSOR_LANDSCAPE` | 6 | Sensor landscape (both directions) |
| `SCREEN_ORIENTATION_USER` | 14 | Respect user's auto-rotate setting (good for "unlock") |

These constants are used as raw ints throughout `C99744f1m.java:104, 106, 122` (0, 1, 6), `C45773HVn.java:434` (14), `SF7.java:249` (14).

### Q3 Conclusion

**Reuse `AbstractC186396mW.A00(activity, orientation)` from `p002X/AbstractC186396mW.java:8`.**

Reasons:
- Static method, no instance state to set up.
- Takes `Activity` + raw int orientation — direct match for our use case.
- Catches the only common runtime exception (`IllegalStateException` for non-fullscreen activity theme) — critical because IG's main Activity theme is unlikely to be `windowIsFullScreen=true`, so without this guard the patch would crash on every Reels tap.
- Zero side effects beyond the orientation change itself.

---

## Q4. Does IG's manifest lock the Reels activity to portrait?

### Risk: UNVERIFIED — must be checked via apktool.

The jadx dump at `/home/z/insta-src/jadx-out/sources/` does NOT include `AndroidManifest.xml` (jadx was run with `--no-res`). If the Reels host Activity (likely `com.instagram.mainactivity.MainActivity` per 3-e's notes) has `android:screenOrientation="portrait"` in the manifest, then ANY `setRequestedOrientation(...)` call from code will be silently overridden by the manifest declaration on Android 8.0+ (the manifest wins for `screenOrientation` unless the activity theme allows fullscreen + the manifest value is `unspecified` or `user`).

### What to verify (next agent / apktool phase)
1. Decode the APK with apktool: `apktool d instagram.apk -o ig-apktool`.
2. Open `ig-apktool/AndroidManifest.xml`.
3. Search for the Activity that hosts the Reels fragment (`com.instagram.mainactivity.MainActivity` is the prime suspect — confirmed in `com/instagram/mainactivity/maintab/` per worklog line 31).
4. Check the `android:screenOrientation` attribute on that Activity.
   - If `portrait` or `userPortrait` → **MUST also patch the manifest** (flip to `unspecified` or `user` or remove the attribute) for our `setRequestedOrientation(LANDSCAPE)` to take effect.
   - If `unspecified`/`user`/absent → no manifest patch needed; `setRequestedOrientation` will work.
5. Also check `android:configChanges` — if `orientation|screenSize` is NOT declared, the Activity will be destroyed+recreated on rotation (which may reset the Reels pager state). If it IS declared, the Activity handles the config change itself.

### Mitigation options if manifest locks portrait
- **Option 1 (preferred):** Patch the manifest via apktool — set `android:screenOrientation="unspecified"` on the Reels host Activity, and add `orientation|screenSize` to `android:configChanges` to prevent Activity recreation.
- **Option 2 (fallback):** Use `Activity.setRequestedOrientation(SCREEN_ORIENTATION_USER_LANDSCAPE)` (int = 8) which can sometimes bypass manifest portrait lock — but unreliable.
- **Option 3 (last resort):** Render Reels in a forced-landscape overlay Dialog/Window — much more invasive.

**Action for next agent:** Run apktool on the original APK and inspect the manifest BEFORE writing the VBP.FSS rotation hook, otherwise the hook may be a no-op.

---

## Feature D Rotation Hook Verdict

### One-liner rotation hooks (Smali-style pseudocode, ready for patch translation)

**At `p002X/VBP.java:116` (entering `FSS(int i, int i2)`):**
```java
// Feature D rotation enter hook — paste at top of VBP.FSS, BEFORE the `if (!this.A00)` guard
View __v = AnonymousClass955.A06(this.A02.A0C);
if (__v != null) {
    android.app.Activity __act = AbstractC106081keV.A00(__v.getContext());
    if (__act != null) {
        // 0 = SCREEN_ORIENTATION_LANDSCAPE; 6 = SENSOR_LANDSCAPE (allows 180° flip)
        AbstractC186396mW.A00(__act, 0);
    }
}
```

**At `p002X/VBP.java:47` (entering `EvT(AnonymousClass950)`):**
```java
// Feature D rotation exit hook — paste at top of VBP.EvT
View __v = AnonymousClass955.A06(this.A02.A0C);
if (__v != null) {
    android.app.Activity __act = AbstractC106081keV.A00(__v.getContext());
    if (__act != null) {
        // 14 = SCREEN_ORIENTATION_USER (back to user's auto-rotate setting)
        // OR 1 = SCREEN_ORIENTATION_PORTRAIT if we want to force portrait on exit
        AbstractC186396mW.A00(__act, 14);
    }
}
```

### Why these specific lines
- `VBP.java:116` is the **first executable line** of `FSS(int i, int i2)` — guaranteed to run on every fullscreen-enter gesture. Placing the hook before `if (!this.A00)` means rotation happens even if the UFI-hide state is already active (so re-tap doesn't un-rotate — `setRequestedOrientation` is idempotent on the same value).
- `VBP.java:47` is the **first executable line** of `EvT(AnonymousClass950)` — guaranteed to run on every fullscreen-exit gesture.

### Required imports for the patched VBP.java (if patching in Java first then Smali):
```java
import android.app.Activity;
// AnonymousClass955.A06 + AbstractC106081keV.A00 + AbstractC186396mW.A00 are in same package p002X — no import needed
```

### Landscape gate (per 3-e's recommendation)
Add BEFORE the rotation call inside FSS:
```java
// Only rotate for horizontal (16:9) videos — gate by player video dimensions
// (requires access to the player; see 3-e open gap #1 — C257899eY / C3BT)
// Placeholder: gate on a static helper that checks videoWidth > videoHeight
if (__should_rotate_for_this_reel(this.A02)) {  // TODO: implement per 3-e open gap #1
    AbstractC186396mW.A00(__act, 0);
}
```
For EvT, always restore (`14`) — never gate exit, so a misclassified reel still un-rotates.

### Coverage gap (IMPORTANT)
These VBP hooks cover ONLY the **gesture path** (scroll/double-tap trigger). They do NOT cover the **popup-menu "Fullscreen View" tap**, which goes through `IA3.F6G → I34 case 33 → C14U.FGC` or `IA5.F6G → C15T.A0F case 114` — neither of which calls VBP.FSS.

If we want the popup-menu button to also rotate, add a second hook:

**At `p002X/C15T.java:1211` (case `FilterIds.LAGOS /* 114 */`, inside `A0F`):**
```java
// After C90202vl.A01(295472); — before TGH.A02(...):
FragmentActivity __fa = c15t.A06;
if (__fa != null) {
    AbstractC186396mW.A00(__fa, 0);  // rotate to landscape
    // And explicitly invoke the VBP hide-ufi path so UFI also hides:
    // (would need a reference to RE7 or the gesture listener set — see RE7.CaC())
}
```

`C15T.A06` is already a `FragmentActivity` (confirmed at `p002X/C15T.java:3130`: `FragmentActivity fragmentActivity = this.A06;`). So no Context unwrapping needed — direct call.

### Open items for next agent
1. Verify IG manifest `android:screenOrientation` for the Reels host Activity (Q4 above) via apktool — if locked portrait, the rotation hooks are no-ops.
2. Locate the player instance (3-e open gap #1) to implement the landscape gate.
3. Implement the seekbar overlay (3-e open gap: hook at `VBP.FSS` after line 131 for show, `VBP.EvT` line 47 for hide).
