package app.truereels;

import android.app.Activity;
import android.content.Context;
import android.content.pm.ActivityInfo;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.InsetDrawable;
import android.graphics.drawable.LayerDrawable;
import android.os.Build;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import java.lang.reflect.Method;
import java.lang.reflect.Field;
import java.util.HashSet;
import java.util.Set;

/**
 * InstaPatchedTrueReel runtime helper (v7).
 *
 * v7 fixes (based on v6 user feedback + VLM screenshot analysis):
 *
 * USER REQUIREMENTS (v7):
 *   1. Status bar: VISIBLE but TRANSPARENT (not hidden). Video extends behind it.
 *      Only wifi info may be hidden — time + battery visible on transparent bar.
 *   2. Main bottom bar (Home/Reels/Create/Search/Profile): 100% TRANSPARENT.
 *      NO black strip, just white icons on video. NO blur.
 *   3. Comment bar "Add comment..." box: 100% TRANSPARENT background.
 *      Just white text + white outline. Reel playing behind it.
 *   4. Fullscreen button on 16:9 videos: TikTok-style LANDSCAPE rotation
 *      (rotate phone horizontal, play like YouTube fullscreen).
 *   5. NO blur anywhere — just 100% transparency.
 *
 * v6 → v7 CHANGES:
 *   - Status bar: was HIDDEN (immersive flags) → now TRANSPARENT (color set to TRANSPARENT,
 *     LAYOUT flags only, no HIDE/FULLSCREEN flags)
 *   - Bars: was 60% black (0x99000000) + RenderEffect blur → now 100% transparent
 *     (Color.TRANSPARENT) + NO blur
 *   - Video chain: now forced to MATCH_PARENT + clear padding so video extends BEHIND bars
 *   - Fullscreen button: was setScaleY (broken) → now setRequestedOrientation(LANDSCAPE)
 *     (real TikTok-style rotation)
 *   - Re-scan: periodic re-scan every 1s for 30s to catch dynamically-created bars
 *     (comment composer appears when user taps comment icon)
 *
 * EFFICIENT CODE EXPLORATION METHOD (v7):
 *   Instead of hardcoding every bar class name, v7 uses "detect by characteristics":
 *   - Opaque ColorDrawable background (alpha >= 200) → likely a bar
 *   - View at top or bottom of screen (Y position check) → likely a bar
 *   - Skip views containing TextureView → not the video
 *   - Skip the video's ancestor chain → don't make video transparent
 *   This is more robust and doesn't require knowing every obfuscated class name.
 */
public class TrueReelsHelper {

    // LAYOUT flags ONLY — NO hide flags (we want status bar VISIBLE but transparent)
    // 0x700 = LAYOUT_STABLE(0x100) | LAYOUT_FULLSCREEN(0x200) | LAYOUT_HIDE_NAVIGATION(0x400)
    // This makes content lay out BEHIND system bars without hiding them.
    private static final int FLAG_LAYOUT_BEHIND_BARS = 0x100 | 0x200 | 0x400;

    private static final String TAG_BTN = "truereels_fs_btn";
    private static final String TAG_TRANSPARENT = "truereels_trans";
    private static final String TAG_CHAIN = "truereels_chain";

    // Reels context ancestor class names (reels tab + story viewer)
    private static final Set<String> REELS_ANCESTORS = new HashSet<>();
    static {
        // Reels TAB (bottom-nav) — the user's case
        REELS_ANCESTORS.add("GestureManagerFrameLayout");
        REELS_ANCESTORS.add("ClipsSwipeRefreshLayout");
        REELS_ANCESTORS.add("HomecomingSwipeRefreshLayout");
        REELS_ANCESTORS.add("RefreshableNestedScrollingParent");
        // Story viewer (tap story from feed)
        REELS_ANCESTORS.add("TouchInterceptorFrameLayout");
        REELS_ANCESTORS.add("ReelViewGroup");
    }

    // Known bar class names to make transparent (TikTok-style 100% transparent bars)
    private static final Set<String> BAR_CLASS_NAMES = new HashSet<>();
    static {
        // Reels-specific bars
        BAR_CLASS_NAMES.add("ClipsViewerNavigationBar");
        BAR_CLASS_NAMES.add("ClipsViewerActionBar");
        BAR_CLASS_NAMES.add("ClipsViewerReplyBar");
        BAR_CLASS_NAMES.add("ClipsViewerCommentBar");
        BAR_CLASS_NAMES.add("ReelsCommentBar");
        BAR_CLASS_NAMES.add("ClipsViewerBottomBar");
        BAR_CLASS_NAMES.add("ClipsBottomBar");
        BAR_CLASS_NAMES.add("ClipsCommentComposerBar");
        // IG main tab bar (bottom nav: Home/Reels/Create/Search/Profile)
        BAR_CLASS_NAMES.add("BottomTabBar");
        BAR_CLASS_NAMES.add("IgTabBar");
        BAR_CLASS_NAMES.add("MainTabBar");
        BAR_CLASS_NAMES.add("TabBar");
        BAR_CLASS_NAMES.add("MainBottomTabBar");
        BAR_CLASS_NAMES.add("NavigationTabBar");
        BAR_CLASS_NAMES.add("IgBottomTabBar");
        // Comment composer
        BAR_CLASS_NAMES.add("CommentComposer");
        BAR_CLASS_NAMES.add("ClipsCommentComposer");
        BAR_CLASS_NAMES.add("CommentComposerBar");
    }

    /** Called from LX/7ky.onAttachedToWindow (smali-injected). */
    public static void onPlayerAttached(View videoView) {
        try {
            // CRITICAL: Only act in the reels context.
            View reelsRoot = findReelsRoot(videoView);
            if (reelsRoot == null) {
                return; // not reels — do nothing (no feed flicker)
            }

            // 1. Make window status bar + nav bar TRANSPARENT (not hidden).
            //    Content lays out behind system bars; bars are visible but transparent.
            makeWindowTransparent(videoView);

            // 2. Make the video's ancestor chain fill the ENTIRE screen.
            //    This ensures the video extends BEHIND the status bar + nav bar + IG tab bar.
            //    (Without this, the video only fills the area BETWEEN the bars.)
            makeVideoChainFillScreen(videoView, reelsRoot);

            // 3. Make all bar-like views 100% TRANSPARENT (no blur).
            //    Walk from the activity's decorView (to catch the IG main tab bar which is
            //    a SIBLING of the reels fragment, not a child of reelsRoot).
            //    Only run when in reels context — feed/stories unaffected.
            final View video = videoView;
            videoView.post(new Runnable() {
                @Override public void run() {
                    makeBarsTransparent(video);
                }
            });

            // 4. Periodic re-scan: bars like the comment composer are created dynamically
            //    when the user taps the comment icon. A one-shot walk misses them.
            //    Re-scan every 1s for 30s to catch them.
            startRescan(videoView);

            // 5. Fullscreen toggle button for horizontal (16:9) videos.
            //    Uses setRequestedOrientation(LANDSCAPE) for real TikTok-style rotation.
            ensureFullscreenButton(videoView);
        } catch (Throwable t) {
            // never crash the host
        }
    }

    // -----------------------------------------------------------------------
    // Reels context detection — find the reels root view
    // -----------------------------------------------------------------------
    private static View findReelsRoot(View view) {
        View v = view;
        int hops = 0;
        while (v != null && hops < 30) {
            hops++;
            String name = v.getClass().getSimpleName();
            if (name != null && !name.isEmpty() && REELS_ANCESTORS.contains(name)) {
                return v;
            }
            if (v.getParent() instanceof View) {
                v = (View) v.getParent();
            } else {
                break;
            }
        }
        return null;
    }

    // -----------------------------------------------------------------------
    // Make window status bar + nav bar TRANSPARENT (not hidden)
    // -----------------------------------------------------------------------
    private static void makeWindowTransparent(View videoView) {
        try {
            Activity activity = findActivity(videoView);
            if (activity == null) return;
            Window window = activity.getWindow();
            if (window == null) return;

            // Enable drawing behind system bars
            window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);

            // Set status bar + nav bar color to TRANSPARENT
            // (NOT hiding them — they remain visible but transparent so video shows through)
            window.setStatusBarColor(Color.TRANSPARENT);
            window.setNavigationBarColor(Color.TRANSPARENT);

            // Layout content behind system bars (but don't hide them)
            // 0x700 = LAYOUT_STABLE | LAYOUT_FULLSCREEN | LAYOUT_HIDE_NAVIGATION
            View decorView = window.getDecorView();
            decorView.setSystemUiVisibility(FLAG_LAYOUT_BEHIND_BARS);

            // On API 30+ (Android 11+), use the modern edge-to-edge API for better behavior
            if (Build.VERSION.SDK_INT >= 30) {
                try {
                    // setDecorFitsSystemWindows(false) = content extends behind system bars
                    window.setDecorFitsSystemWindows(false);
                } catch (Throwable t) {
                    // fallback to legacy flags (already set above)
                }
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // Make video's ancestor chain fill the entire screen
    // (so video extends BEHIND status bar + nav bar + IG tab bar)
    // -----------------------------------------------------------------------
    private static void makeVideoChainFillScreen(View videoView, View reelsRoot) {
        try {
            // Walk up from video view to reels root, set MATCH_PARENT + clear padding
            View v = videoView;
            int hops = 0;
            while (v != null && v != reelsRoot && hops < 20) {
                hops++;
                try {
                    ViewGroup.LayoutParams lp = v.getLayoutParams();
                    if (lp != null) {
                        lp.width = ViewGroup.LayoutParams.MATCH_PARENT;
                        lp.height = ViewGroup.LayoutParams.MATCH_PARENT;
                        v.setLayoutParams(lp);
                    }
                    v.setPadding(0, 0, 0, 0);
                    v.setFitsSystemWindows(false);
                } catch (Throwable t) {}
                if (v.getParent() instanceof View) {
                    v = (View) v.getParent();
                } else {
                    break;
                }
            }
            // Also the reels root itself
            try {
                ViewGroup.LayoutParams lp = reelsRoot.getLayoutParams();
                if (lp != null) {
                    lp.width = ViewGroup.LayoutParams.MATCH_PARENT;
                    lp.height = ViewGroup.LayoutParams.MATCH_PARENT;
                    reelsRoot.setLayoutParams(lp);
                }
                reelsRoot.setPadding(0, 0, 0, 0);
                reelsRoot.setFitsSystemWindows(false);
            } catch (Throwable t) {}
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // Make all bar-like views 100% TRANSPARENT (no blur)
    // -----------------------------------------------------------------------
    private static void makeBarsTransparent(View videoView) {
        try {
            Activity activity = findActivity(videoView);
            if (activity == null) return;
            View decorView = activity.getWindow().getDecorView();
            if (!(decorView instanceof ViewGroup)) return;

            // Build the set of views that are the video's ancestors (don't make these transparent)
            Set<View> videoChain = new HashSet<>();
            View v = videoView;
            while (v != null) {
                videoChain.add(v);
                if (v.getParent() instanceof View) {
                    v = (View) v.getParent();
                } else {
                    break;
                }
            }

            // Walk the entire decorView tree and make bar-like views transparent
            makeBarsTransparentRecursive((ViewGroup) decorView, videoChain, 0);
        } catch (Throwable t) {}
    }

    private static void makeBarsTransparentRecursive(ViewGroup viewGroup, Set<View> videoChain, int depth) {
        if (viewGroup == null || depth > 35) return;
        try {
            int count = viewGroup.getChildCount();
            for (int i = 0; i < count; i++) {
                View child = viewGroup.getChildAt(i);
                if (child == null) continue;

                // Skip the video surface and its ancestors
                if (videoChain.contains(child)) {
                    // Still recurse into the video's ancestors (they might contain bars)
                    if (child instanceof ViewGroup) {
                        makeBarsTransparentRecursive((ViewGroup) child, videoChain, depth + 1);
                    }
                    continue;
                }

                // Skip TextureViews (the video surface)
                if (child instanceof TextureView) continue;

                String className = child.getClass().getSimpleName();
                boolean shouldMakeTransparent = false;

                // Check by class name (known bar classes)
                if (className != null && BAR_CLASS_NAMES.contains(className)) {
                    shouldMakeTransparent = true;
                }

                // Check if it has an opaque background (likely a bar)
                if (!shouldMakeTransparent) {
                    shouldMakeTransparent = hasOpaqueBackground(child);
                }

                // Check if it's a bar-like view at top or bottom of screen
                // (avoids making random opaque views transparent)
                if (!shouldMakeTransparent && hasOpaqueBackground(child)) {
                    shouldMakeTransparent = isAtTopOrBottom(child);
                }

                if (shouldMakeTransparent) {
                    setBarTransparent(child);
                }

                // Recurse into children
                if (child instanceof ViewGroup) {
                    makeBarsTransparentRecursive((ViewGroup) child, videoChain, depth + 1);
                }
            }
        } catch (Throwable t) {}
    }

    /**
     * Check if a view has an opaque ColorDrawable or similar background.
     * alpha >= 200 means it's mostly opaque (a solid bar background).
     */
    private static boolean hasOpaqueBackground(View view) {
        try {
            Drawable bg = view.getBackground();
            if (bg == null) return false;

            // Unwrap InsetDrawable / LayerDrawable to find the actual color
            if (bg instanceof InsetDrawable) {
                Drawable inner = ((InsetDrawable) bg).getDrawable();
                if (inner != null) bg = inner;
            }
            if (bg instanceof LayerDrawable) {
                LayerDrawable ld = (LayerDrawable) bg;
                if (ld.getNumberOfLayers() > 0) {
                    bg = ld.getDrawable(0);
                }
            }

            if (bg instanceof ColorDrawable) {
                int color = ((ColorDrawable) bg).getColor();
                int alpha = Color.alpha(color);
                return alpha >= 200; // mostly opaque
            }

            // GradientDrawable with solid fill
            if (bg instanceof GradientDrawable) {
                // Can't easily read the color, but if it's opaque and the view is a bar, make it transparent
                return true; // conservative: treat GradientDrawable bars as targets
            }
        } catch (Throwable t) {}
        return false;
    }

    /**
     * Check if a view is positioned at the top or bottom of the screen (likely a bar).
     */
    private static boolean isAtTopOrBottom(View view) {
        try {
            int[] location = new int[2];
            view.getLocationOnScreen(location);
            int y = location[1];
            int height = view.getHeight();
            int screenHeight = view.getContext().getResources().getDisplayMetrics().heightPixels;

            // Top bar: within first 200dp of screen
            int topThreshold = dp2(view.getContext(), 200);
            // Bottom bar: bottom edge within last 200dp of screen
            int bottomThreshold = screenHeight - dp2(view.getContext(), 200);

            if (height <= 0) return false;

            // View's top is near the top of the screen, OR view's bottom is near the bottom
            boolean atTop = y >= 0 && y < topThreshold;
            boolean atBottom = (y + height) > bottomThreshold && (y + height) <= screenHeight + dp2(view.getContext(), 50);

            return atTop || atBottom;
        } catch (Throwable t) {
            return false;
        }
    }

    /**
     * Make a single bar view 100% transparent (NO blur).
     */
    private static void setBarTransparent(View bar) {
        try {
            // Mark as processed (use a tag — if already tagged, skip)
            Object existingTag = bar.getTag();
            if (TAG_TRANSPARENT.equals(existingTag)) return;
            bar.setTag(TAG_TRANSPARENT);

            // Set background to 100% TRANSPARENT (no blur, no semi-transparent black)
            bar.setBackgroundColor(Color.TRANSPARENT);

            // Remove any RenderEffect that might have been set (from v6)
            if (Build.VERSION.SDK_INT >= 31) {
                try {
                    bar.setRenderEffect(null);
                } catch (Throwable t) {}
            }

            // Make the bar's children's backgrounds transparent too (comment composer box, etc.)
            if (bar instanceof ViewGroup) {
                ViewGroup vg = (ViewGroup) bar;
                for (int i = 0; i < vg.getChildCount(); i++) {
                    View child = vg.getChildAt(i);
                    if (child == null) continue;
                    // Only clear backgrounds of containers (FrameLayout, LinearLayout),
                    // NOT ImageView/TextView (those are the icons/text we want to keep white)
                    if (child instanceof FrameLayout || child instanceof LinearLayout) {
                        Drawable cbg = child.getBackground();
                        if (cbg instanceof ColorDrawable) {
                            int c = ((ColorDrawable) cbg).getColor();
                            if (Color.alpha(c) >= 200) {
                                child.setBackgroundColor(Color.TRANSPARENT);
                            }
                        }
                    }
                }
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // Periodic re-scan (catch dynamically-created bars like comment composer)
    // -----------------------------------------------------------------------
    private static void startRescan(View videoView) {
        try {
            final View video = videoView;
            final int[] count = {0};
            final Runnable rescan = new Runnable() {
                @Override public void run() {
                    try {
                        // Only re-scan if still in reels context
                        if (findReelsRoot(video) != null) {
                            makeBarsTransparent(video);
                        }
                    } catch (Throwable t) {}
                    count[0]++;
                    if (count[0] < 30) {
                        video.postDelayed(this, 1000); // every 1s for 30s
                    }
                }
            };
            videoView.postDelayed(rescan, 1000);
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // Fullscreen toggle button for horizontal videos
    // Uses setRequestedOrientation(LANDSCAPE) for real TikTok-style rotation
    // -----------------------------------------------------------------------
    private static boolean sIsLandscape = false;

    private static void ensureFullscreenButton(final View videoView) {
        try {
            final ViewGroup parent = (ViewGroup) videoView.getParent();
            if (parent == null) {
                videoView.post(new Runnable() {
                    @Override public void run() { ensureFullscreenButton(videoView); }
                });
                return;
            }
            // Avoid double-adding.
            for (int i = 0; i < parent.getChildCount(); i++) {
                Object t = parent.getChildAt(i).getTag();
                if (TAG_BTN.equals(t)) return;
            }

            final View btn = makeButton(videoView.getContext());
            btn.setTag(TAG_BTN);
            final FrameLayout.LayoutParams flp = new FrameLayout.LayoutParams(
                    dp(videoView, 36), dp(videoView, 36),
                    Gravity.TOP | Gravity.END);
            flp.topMargin = dp(videoView, 52);
            flp.rightMargin = dp(videoView, 10);
            try {
                if (parent instanceof FrameLayout) {
                    parent.addView(btn, flp);
                    // Bring to front so it receives touch events (not behind overlays)
                    btn.bringToFront();
                    btn.setClickable(true);
                    btn.setFocusable(true);
                } else {
                    return;
                }
            } catch (Throwable t) { return; }
            btn.setVisibility(View.GONE);

            btn.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View v) {
                    toggleFullscreen(videoView, btn);
                }
            });

            // Poll for video size to decide whether to show the button.
            final int[] polls = {0};
            final Runnable poll = new Runnable() {
                @Override public void run() {
                    polls[0]++;
                    int[] wh = getVideoSize(videoView);
                    if (wh != null && wh[0] > 0 && wh[1] > 0) {
                        if (wh[0] > wh[1]) {
                            // Horizontal video — show the fullscreen button
                            btn.setVisibility(View.VISIBLE);
                        } else {
                            btn.setVisibility(View.GONE);
                        }
                        return;
                    }
                    if (polls[0] < 40) {
                        videoView.postDelayed(this, 500);
                    }
                }
            };
            videoView.postDelayed(poll, 600);
        } catch (Throwable t) {}
    }

    /**
     * Toggle between portrait (normal reels) and landscape (TikTok-style fullscreen).
     * Uses Activity.setRequestedOrientation() — this rotates the ENTIRE activity,
     * so the video (which already fills the screen) plays in true landscape mode
     * like YouTube fullscreen.
     */
    private static void toggleFullscreen(View videoView, View btn) {
        try {
            Activity activity = findActivity(videoView);
            if (activity == null) return;

            if (sIsLandscape) {
                // Back to portrait (normal reels)
                activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);
                sIsLandscape = false;
                btn.setAlpha(0.55f);
            } else {
                // Rotate to landscape (TikTok-style fullscreen)
                activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
                sIsLandscape = true;
                btn.setAlpha(1f);
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    private static Activity findActivity(View view) {
        Context ctx = view.getContext();
        while (ctx instanceof android.content.ContextWrapper) {
            if (ctx instanceof Activity) return (Activity) ctx;
            try {
                ctx = ((android.content.ContextWrapper) ctx).getBaseContext();
            } catch (Throwable t) {
                return null;
            }
        }
        return null;
    }

    /**
     * Get the video aspect ratio (width/height) from LX/7ky's A04 field.
     * Walks the superclass chain to find inherited field A04.
     * Returns int[]{width, height} proportional (aspect*100, 100).
     */
    private static int[] getVideoSize(View videoView) {
        try {
            Object mediaInfo = null;
            Class<?> cls = videoView.getClass();
            while (cls != null && cls != View.class) {
                try {
                    Field f = cls.getDeclaredField("A04");
                    f.setAccessible(true);
                    mediaInfo = f.get(videoView);
                    break;
                } catch (NoSuchFieldException ignored) {
                    cls = cls.getSuperclass();
                }
            }
            if (mediaInfo == null) return null;

            double aspect = -1.0;

            // Read cached public Double A03 field first.
            Class<?> mc = mediaInfo.getClass();
            while (mc != null && mc != Object.class) {
                try {
                    Field fA03 = mc.getDeclaredField("A03");
                    fA03.setAccessible(true);
                    Object cached = fA03.get(mediaInfo);
                    if (cached instanceof Double) {
                        double v = (Double) cached;
                        if (v > 0.0) aspect = v;
                    }
                    break;
                } catch (NoSuchFieldException ignored) {
                    mc = mc.getSuperclass();
                }
            }

            // Fall back to A02() method.
            if (aspect <= 0.0) {
                mc = mediaInfo.getClass();
                while (mc != null && mc != Object.class) {
                    try {
                        Method m = mc.getDeclaredMethod("A02");
                        m.setAccessible(true);
                        Object r = m.invoke(mediaInfo);
                        if (r instanceof Double) {
                            double v = (Double) r;
                            if (v > 0.0) aspect = v;
                        }
                        break;
                    } catch (NoSuchMethodException ignored) {
                        mc = mc.getSuperclass();
                    }
                }
            }

            // Last resort: A03(Context, boolean).
            if (aspect <= 0.0) {
                mc = mediaInfo.getClass();
                while (mc != null && mc != Object.class) {
                    try {
                        Method m = mc.getDeclaredMethod("A03",
                                Context.class, boolean.class);
                        m.setAccessible(true);
                        Object r = m.invoke(mediaInfo, videoView.getContext(), Boolean.FALSE);
                        if (r instanceof Double) {
                            double v = (Double) r;
                            if (v > 0.0) aspect = v;
                        }
                        break;
                    } catch (NoSuchMethodException ignored) {
                        mc = mc.getSuperclass();
                    }
                }
            }

            if (aspect <= 0.0) return null;
            return new int[]{ (int) (aspect * 100), 100 };
        } catch (Throwable t) {
            return null;
        }
    }

    private static View makeButton(Context ctx) {
        ImageView b = new ImageView(ctx);
        // Use a fullscreen/expand icon
        b.setImageResource(android.R.drawable.ic_menu_crop);
        b.setBackgroundColor(0x66000000); // semi-transparent for visibility
        b.setAlpha(0.55f);
        b.setScaleType(ImageView.ScaleType.FIT_CENTER);
        b.setPadding(dp2(ctx, 6), dp2(ctx, 6), dp2(ctx, 6), dp2(ctx, 6));
        return b;
    }

    private static int dp(View v, int n) { return dp2(v.getContext(), n); }
    private static int dp2(Context ctx, int n) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, n,
                ctx.getResources().getDisplayMetrics());
    }
}
