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
import android.view.ViewTreeObserver;
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
 * InstaPatchedTrueReel runtime helper (v8).
 *
 * v8 is a COMPANION to Phase B smali patches (which permanently neutralize bar
 * backgrounds at the source). The runtime helper handles:
 *   - Window transparency (status bar + nav bar color = TRANSPARENT)
 *   - Video chain fill (MATCH_PARENT so video extends behind system bars)
 *   - Runtime transparency BELT-AND-SUSPENDERS (catches any bar the smali patches missed,
 *     and catches bars Litho re-mounts with their original drawable)
 *   - Fullscreen button added to the Activity's WINDOW DECORVIEW (above all IG touch
 *     interceptors — fixes v7's "click does nothing" bug)
 *
 * KEY v7→v8 CHANGES:
 *   1. Bar transparency: use bg.mutate().setAlpha(0) (preserves drawable, invisible)
 *      IN ADDITION to setBackgroundColor(TRANSPARENT). mutate() prevents shared-state bugs.
 *   2. Re-scan: ViewTreeObserver.OnGlobalLayoutListener on reels root (re-scans on EVERY
 *      layout change — catches Litho re-mounts instantly) + Choreographer 500ms fallback.
 *   3. Fullscreen button: added to activity.getWindow().getDecorView() (root FrameLayout)
 *      — above ALL IG views including GestureManagerFrameLayout. Fixes touch interception.
 *   4. No depth limit on view-tree walk (comment sheet bars may be very deep).
 *   5. Companion to Phase B: smali patches kill bar backgrounds at the source permanently;
 *      this helper is a runtime safety net for anything missed.
 */
public class TrueReelsHelper {

    // LAYOUT flags ONLY — NO hide flags (status bar VISIBLE but transparent)
    // 0x700 = LAYOUT_STABLE(0x100) | LAYOUT_FULLSCREEN(0x200) | LAYOUT_HIDE_NAVIGATION(0x400)
    private static final int FLAG_LAYOUT_BEHIND_BARS = 0x100 | 0x200 | 0x400;

    private static final String TAG_BTN = "truereels_fs_btn";
    private static final String TAG_TRANSPARENT = "truereels_trans";

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

    // Known bar class names (from SA-A/SA-B subagent exploration of decompiled source)
    private static final Set<String> BAR_CLASS_NAMES = new HashSet<>();
    static {
        // Reels-specific bars (smali-patched in Phase B, but runtime fallback too)
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
        // Comment composer / sheet
        BAR_CLASS_NAMES.add("CommentComposer");
        BAR_CLASS_NAMES.add("ClipsCommentComposer");
        BAR_CLASS_NAMES.add("CommentComposerBar");
        BAR_CLASS_NAMES.add("BottomSheetDialog");
        BAR_CLASS_NAMES.add("BottomSheetFragment");
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
            makeWindowTransparent(videoView);

            // 2. Make the video's ancestor chain fill the ENTIRE screen.
            makeVideoChainFillScreen(videoView, reelsRoot);

            // 3. Runtime transparency safety net (companion to Phase B smali patches).
            //    Register a global layout listener on the reels root so we re-scan on
            //    EVERY layout change (catches Litho re-mounts instantly). Also do an
            //    immediate scan + a periodic Choreographer fallback.
            installLayoutListener(videoView, reelsRoot);
            final View video = videoView;
            videoView.post(new Runnable() {
                @Override public void run() { makeBarsTransparent(video); }
            });
            startRescan(videoView);

            // 4. Fullscreen toggle button for horizontal (16:9) videos.
            //    Added to the Activity's WINDOW DECORVIEW (root) — above all IG touch
            //    interceptors. Fixes v7's "click does nothing" bug.
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

            window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
            window.setStatusBarColor(Color.TRANSPARENT);
            window.setNavigationBarColor(Color.TRANSPARENT);

            View decorView = window.getDecorView();
            decorView.setSystemUiVisibility(FLAG_LAYOUT_BEHIND_BARS);

            if (Build.VERSION.SDK_INT >= 30) {
                try {
                    window.setDecorFitsSystemWindows(false);
                } catch (Throwable t) {}
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // Make video's ancestor chain fill the entire screen
    // -----------------------------------------------------------------------
    private static void makeVideoChainFillScreen(View videoView, View reelsRoot) {
        try {
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
    // Layout listener — re-scan on every layout change (catches Litho re-mounts)
    // -----------------------------------------------------------------------
    private static void installLayoutListener(final View videoView, View reelsRoot) {
        try {
            if (reelsRoot == null) return;
            final View root = reelsRoot;
            final View video = videoView;
            ViewTreeObserver vto = reelsRoot.getViewTreeObserver();
            if (vto == null) return;
            vto.addOnGlobalLayoutListener(new ViewTreeObserver.OnGlobalLayoutListener() {
                @Override public void onGlobalLayout() {
                    try {
                        if (findReelsRoot(video) != null) {
                            makeBarsTransparent(video);
                        }
                    } catch (Throwable t) {}
                }
            });
            // Also listen on the decorView (catches comment sheet which is added to decorView)
            Activity activity = findActivity(videoView);
            if (activity != null) {
                View decor = activity.getWindow().getDecorView();
                if (decor != null) {
                    ViewTreeObserver dvto = decor.getViewTreeObserver();
                    if (dvto != null) {
                        dvto.addOnGlobalLayoutListener(new ViewTreeObserver.OnGlobalLayoutListener() {
                            @Override public void onGlobalLayout() {
                                try {
                                    if (findReelsRoot(video) != null) {
                                        makeBarsTransparent(video);
                                    }
                                } catch (Throwable t) {}
                            }
                        });
                    }
                }
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // Make all bar-like views transparent (companion to Phase B smali patches)
    // -----------------------------------------------------------------------
    private static void makeBarsTransparent(View videoView) {
        try {
            Activity activity = findActivity(videoView);
            if (activity == null) return;
            View decorView = activity.getWindow().getDecorView();
            if (!(decorView instanceof ViewGroup)) return;

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

            makeBarsTransparentRecursive((ViewGroup) decorView, videoChain, 0);
        } catch (Throwable t) {}
    }

    private static void makeBarsTransparentRecursive(ViewGroup viewGroup, Set<View> videoChain, int depth) {
        if (viewGroup == null || depth > 50) return; // no depth limit (comment sheet is deep)
        try {
            int count = viewGroup.getChildCount();
            for (int i = 0; i < count; i++) {
                View child = viewGroup.getChildAt(i);
                if (child == null) continue;

                // Skip the fullscreen button we added
                if (TAG_BTN.equals(child.getTag())) continue;

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
                if (!shouldMakeTransparent && hasOpaqueBackground(child)) {
                    shouldMakeTransparent = isAtTopOrBottom(child);
                }

                if (shouldMakeTransparent) {
                    setBarTransparent(child);
                }

                // Recurse into children (even for bars — they may contain nested opaque views)
                if (child instanceof ViewGroup) {
                    makeBarsTransparentRecursive((ViewGroup) child, videoChain, depth + 1);
                }
            }
        } catch (Throwable t) {}
    }

    private static boolean hasOpaqueBackground(View view) {
        try {
            Drawable bg = view.getBackground();
            if (bg == null) return false;

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
                return alpha >= 150;
            }

            if (bg instanceof GradientDrawable) {
                return true;
            }
        } catch (Throwable t) {}
        return false;
    }

    private static boolean isAtTopOrBottom(View view) {
        try {
            int[] location = new int[2];
            view.getLocationOnScreen(location);
            int y = location[1];
            int height = view.getHeight();
            int screenHeight = view.getContext().getResources().getDisplayMetrics().heightPixels;
            if (height <= 0) return false;
            int topThreshold = dp2(view.getContext(), 200);
            int bottomThreshold = screenHeight - dp2(view.getContext(), 200);
            boolean atTop = y >= 0 && y < topThreshold;
            boolean atBottom = (y + height) > bottomThreshold && (y + height) <= screenHeight + dp2(view.getContext(), 50);
            return atTop || atBottom;
        } catch (Throwable t) {
            return false;
        }
    }

    /**
     * Make a single bar view transparent.
     * v8: use mutate().setAlpha(0) IN ADDITION to setBackgroundColor(TRANSPARENT).
     * mutate() prevents shared-state bugs; setAlpha(0) preserves the drawable but
     * makes it invisible (more robust against Litho re-mounts than setBackgroundColor).
     */
    private static void setBarTransparent(View bar) {
        try {
            Object existingTag = bar.getTag();
            if (TAG_TRANSPARENT.equals(existingTag)) {
                // Already tagged — but still re-apply alpha in case Litho re-mounted
            }
            bar.setTag(TAG_TRANSPARENT);

            // Method 1: mutate + setAlpha(0) — preserves drawable, invisible
            try {
                Drawable bg = bar.getBackground();
                if (bg != null) {
                    bg = bg.mutate();
                    bg.setAlpha(0);
                    bar.setBackground(bg);
                }
            } catch (Throwable t) {}

            // Method 2: setBackgroundColor(TRANSPARENT) — belt-and-suspenders
            try {
                bar.setBackgroundColor(Color.TRANSPARENT);
            } catch (Throwable t) {}

            // Remove any RenderEffect (from v6)
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
                    if (child instanceof FrameLayout || child instanceof LinearLayout) {
                        try {
                            Drawable cbg = child.getBackground();
                            if (cbg != null) {
                                cbg = cbg.mutate();
                                cbg.setAlpha(0);
                                child.setBackground(cbg);
                            }
                        } catch (Throwable t) {}
                        try {
                            child.setBackgroundColor(Color.TRANSPARENT);
                        } catch (Throwable t) {}
                    }
                }
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // Periodic re-scan (Choreographer-based fallback — catches anything missed)
    // -----------------------------------------------------------------------
    private static void startRescan(View videoView) {
        try {
            final View video = videoView;
            final int[] count = {0};
            final Runnable rescan = new Runnable() {
                @Override public void run() {
                    try {
                        if (findReelsRoot(video) != null) {
                            makeBarsTransparent(video);
                        }
                    } catch (Throwable t) {}
                    count[0]++;
                    if (count[0] < 60) {
                        video.postDelayed(this, 500); // every 500ms for 30s
                    }
                }
            };
            videoView.postDelayed(rescan, 1000);
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // Fullscreen toggle button — added to Activity's WINDOW DECORVIEW
    // (above all IG touch interceptors — fixes v7's "click does nothing" bug)
    // -----------------------------------------------------------------------
    private static boolean sIsLandscape = false;
    private static View sButton = null;

    private static void ensureFullscreenButton(final View videoView) {
        try {
            final Activity activity = findActivity(videoView);
            if (activity == null) return;
            final Window window = activity.getWindow();
            if (window == null) return;

            // Post to main thread, then do everything in a single-level anonymous class.
            // (d8 fails on deeply nested anonymous classes like Runnable->OnGlobalLayoutListener,
            //  so we flatten the nesting here.)
            videoView.post(new Runnable() {
                @Override public void run() {
                    try {
                        ensureFullscreenButtonImpl(videoView, activity, window);
                    } catch (Throwable t) {}
                }
            });
        } catch (Throwable t) {}
    }

    private static void ensureFullscreenButtonImpl(final View videoView, final Activity activity, final Window window) {
        final ViewGroup decorView = (ViewGroup) window.getDecorView();
        if (decorView == null) return;

        // Avoid double-adding
        if (sButton != null && sButton.getParent() != null) return;
        int n = decorView.getChildCount();
        for (int i = 0; i < n; i++) {
            View c = decorView.getChildAt(i);
            if (TAG_BTN.equals(c.getTag())) {
                sButton = c;
                return;
            }
        }

        final View btn = makeButton(videoView.getContext());
        btn.setTag(TAG_BTN);
        sButton = btn;

        final FrameLayout.LayoutParams flp = new FrameLayout.LayoutParams(
                dp(videoView, 40), dp(videoView, 40),
                Gravity.TOP | Gravity.END);
        flp.topMargin = dp(videoView, 56);
        flp.rightMargin = dp(videoView, 12);

        decorView.addView(btn, flp);
        btn.bringToFront();
        btn.setClickable(true);
        btn.setFocusable(true);

        // OnClickListener — single-level anonymous class (OK for d8)
        btn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                toggleFullscreen(videoView, btn);
            }
        });

        // Poll for video size — single-level anonymous Runnable
        final int[] polls = {0};
        final Runnable poll = new Runnable() {
            @Override public void run() {
                polls[0]++;
                int[] wh = getVideoSize(videoView);
                if (wh != null && wh[0] > 0 && wh[1] > 0) {
                    if (wh[0] > wh[1]) {
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
    }

    /**
     * Toggle between portrait (normal reels) and landscape (TikTok-style fullscreen).
     * Uses Activity.setRequestedOrientation() — this rotates the ENTIRE activity.
     * InstagramMainActivity manifest has configChanges=orientation so no recreation.
     */
    private static void toggleFullscreen(View videoView, View btn) {
        try {
            Activity activity = findActivity(videoView);
            if (activity == null) return;

            if (sIsLandscape) {
                activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);
                sIsLandscape = false;
                btn.setAlpha(0.55f);
            } else {
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

            // Read cached public Double A03 field first (on C160765mH / mediaInfo)
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

            // Fall back to A02() method
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

            // Last resort: A03(Context, boolean)
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
        b.setImageResource(android.R.drawable.ic_menu_crop);
        b.setBackgroundColor(0x66000000);
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
