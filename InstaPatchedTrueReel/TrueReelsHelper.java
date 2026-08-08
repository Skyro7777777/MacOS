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
 * InstaPatchedTrueReel runtime helper — complete clean rewrite.
 *
 * Companion to two smali patches only:
 *   1. LX/7ky;->onSizeChanged(IIII)V  -> TextureView MATCH_PARENT x MATCH_PARENT (video stretch)
 *   2. LX/7ky;->onAttachedToWindow()V -> invoke-static TrueReelsHelper.onPlayerAttached(view)
 *
 * Everything else (bars transparency, status bar, fullscreen) is handled here at runtime
 * so we never touch bar-background resource IDs in smali (the v8 approach of nulling
 * 0x7f08042f crashed XIU's Litho component because LX/4rT;->A0N throws on resource 0).
 *
 * FOUR PROBLEMS THIS HELPER SOLVES (each mapped to a verified root cause):
 *
 *  (1) STATUS BAR BLACK STRIP
 *      Root cause: InstagramMainActivity.onResume sets window status bar color to
 *      igds_color_primary_background (= BLACK in dark theme), overriding any prior
 *      setStatusBarColor(TRANSPARENT). Fix: re-apply window transparency on EVERY
 *      layout pass + every rescan tick, so IG's onResume override is defeated within
 *      ~200ms. Flag combo: LAYOUT_STABLE|LAYOUT_FULLSCREEN|LAYOUT_HIDE_NAVIGATION = 0x700
 *      (layout-only, NEVER 0x4 FULLSCREEN / 0x2 HIDE_NAVIGATION which hide icons).
 *
 *  (2) MAIN BOTTOM NAV BAR ~80% TRANSPARENCY (want 100%)
 *      Root cause: the tab bar is a plain FrameLayout (no custom class) looked up by
 *      ID R.id.tab_bar (0x7f0b3f67) / R.id.ls_nav_bar (0x7f0b248e). Background is
 *      setBackgroundColor(igds_color_clips_tab_bar_background) which resolves to a
 *      ~80%-opaque black color (alpha ~51). The old helper missed it because (a) it's
 *      a generic FrameLayout not in BAR_CLASS_NAMES, and (b) hasOpaqueBackground
 *      required alpha >= 150. Fix: add explicit ID-based lookup + lower threshold to 1.
 *
 *  (3) COMMENT BAR "Add comment..." BLACK STRIP (want transparent, KEEP white outline)
 *      Root cause: XIU is a Litho component whose background = a single <shape>
 *      drawable (clips_viewer_comment_bar_background) containing BOTH the black
 *      <solid> fill AND the white <stroke>. The old setAlpha(0)/setBackgroundColor
 *      calls killed BOTH. Fix: detect GradientDrawable and call setColor(TRANSPARENT)
 *      which clears the fill while preserving the stroke. Do NOT call setAlpha(0) or
 *      setBackgroundColor on GradientDrawable backgrounds.
 *
 *  (4) FULLSCREEN BUTTON "does nothing" (want TikTok-style landscape fullscreen)
 *      Root cause: old code called setRequestedOrientation(LANDSCAPE) but the activity
 *      is portrait-locked in the manifest, so rotation was ignored / layout broke.
 *      Fix: do NOT rotate the activity. Instead, transform the TextureView in-place
 *      (setRotation(90) + setScaleX/Y) so the video renders landscape-filling on the
 *      portrait screen, lock the ViewPager2 vertical swipe, hide IG overlay UI, and
 *      add a decorView overlay with exit button + left/right tap zones for prev/next
 *      reel (scrollable landscape feed, TikTok-style).
 *
 * d8 compiler note: only single-level anonymous inner classes are used (no anonymous
 * class nested inside another anonymous class) — d8/dx fails on deeply nested ones.
 */
public class TrueReelsHelper {

    // Window layout flags ONLY — NO hide flags.
    // 0x100 = LAYOUT_STABLE, 0x200 = LAYOUT_FULLSCREEN, 0x400 = LAYOUT_HIDE_NAVIGATION
    // These let the video render BEHIND the status/nav bars (bars still VISIBLE + TRANSPARENT).
    // NEVER include 0x4 (FULLSCREEN), 0x2 (HIDE_NAVIGATION), 0x800/0x1000 (IMMERSIVE) — those
    // HIDE the bars / icons, which is the cause of the "only wifi info hidden" symptom.
    private static final int FLAG_LAYOUT_BEHIND_BARS = 0x100 | 0x200 | 0x400;

    private static final String TAG_BTN = "truereels_fs_btn";
    private static final String TAG_OVERLAY = "truereels_overlay";
    private static final String TAG_TRANSPARENT = "truereels_trans";
    private static final String TAG_HIDDEN = "truereels_hidden";

    // Reels context ancestor class names (reels TAB + story viewer).
    private static final Set<String> REELS_ANCESTORS = new HashSet<>();
    static {
        REELS_ANCESTORS.add("GestureManagerFrameLayout");
        REELS_ANCESTORS.add("ClipsSwipeRefreshLayout");
        REELS_ANCESTORS.add("HomecomingSwipeRefreshLayout");
        REELS_ANCESTORS.add("RefreshableNestedScrollingParent");
        REELS_ANCESTORS.add("TouchInterceptorFrameLayout");
        REELS_ANCESTORS.add("ReelViewGroup");
    }

    // Known bar class names (for transparency + fullscreen UI hiding).
    private static final Set<String> BAR_CLASS_NAMES = new HashSet<>();
    static {
        BAR_CLASS_NAMES.add("ClipsViewerNavigationBar");
        BAR_CLASS_NAMES.add("ClipsViewerActionBar");
        BAR_CLASS_NAMES.add("ClipsViewerReplyBar");
        BAR_CLASS_NAMES.add("ClipsViewerCommentBar");
        BAR_CLASS_NAMES.add("ReelsCommentBar");
        BAR_CLASS_NAMES.add("ClipsViewerBottomBar");
        BAR_CLASS_NAMES.add("ClipsBottomBar");
        BAR_CLASS_NAMES.add("ClipsCommentComposerBar");
        BAR_CLASS_NAMES.add("BottomTabBar");
        BAR_CLASS_NAMES.add("IgTabBar");
        BAR_CLASS_NAMES.add("MainTabBar");
        BAR_CLASS_NAMES.add("TabBar");
        BAR_CLASS_NAMES.add("MainBottomTabBar");
        BAR_CLASS_NAMES.add("NavigationTabBar");
        BAR_CLASS_NAMES.add("IgBottomTabBar");
        BAR_CLASS_NAMES.add("CommentComposer");
        BAR_CLASS_NAMES.add("ClipsCommentComposer");
        BAR_CLASS_NAMES.add("CommentComposerBar");
        BAR_CLASS_NAMES.add("BottomSheetDialog");
        BAR_CLASS_NAMES.add("BottomSheetFragment");
        BAR_CLASS_NAMES.add("MergedFeedsActionBar");
    }

    // View IDs for the main bottom tab bar (from R.java, verified by SA-A).
    // These are the FrameLayouts that hold Home/Reels/Create/Search/Profile icons.
    private static final int ID_TAB_BAR = 0x7f0b3f67;
    private static final int ID_LS_NAV_BAR = 0x7f0b248e;
    private static final int ID_TAB_BAR_SHADOW = 0x7f0b3f68;
    private static final int ID_LS_NAV_BAR_SHADOW = 0x7f0b248f;

    // Fullscreen state
    private static boolean sIsLandscape = false;
    private static View sButton = null;
    private static View sOverlay = null;
    private static View sCurrentVideo = null;       // the video view currently in fullscreen
    private static Object sViewPager2 = null;        // reflected ViewPager2 instance
    private static int sSavedViewPagerCurrent = -1;

    // =====================================================================
    // MAIN ENTRY — called from LX/7ky.onAttachedToWindow (smali-injected)
    // =====================================================================
    public static void onPlayerAttached(View videoView) {
        try {
            // Only act in the reels context (reels tab + story viewer).
            View reelsRoot = findReelsRoot(videoView);
            if (reelsRoot == null) {
                return;
            }

            // 1. Window transparency (status bar + nav bar TRANSPARENT, video behind).
            //    Re-applied on every call + every layout pass — defeats IG's onResume override.
            makeWindowTransparent(videoView);

            // 2. Make the video's ancestor chain fill the ENTIRE screen.
            makeVideoChainFillScreen(videoView, reelsRoot);

            // 3. Runtime bar transparency — walk the view tree on every layout change.
            installLayoutListener(videoView, reelsRoot);
            final View video = videoView;
            videoView.post(new Runnable() {
                @Override public void run() { makeBarsTransparent(video); }
            });
            startRescan(videoView);

            // 4. If we're already in fullscreen (user swiped to next reel), re-apply
            //    the transform to the NEW TextureView. Also auto-exit if new video
            //    is not 16:9.
            if (sIsLandscape) {
                int[] wh = getVideoSize(videoView);
                if (wh == null || wh[0] <= wh[1]) {
                    // new video is portrait (not 16:9) — auto-exit fullscreen
                    exitFullscreen(videoView);
                } else {
                    sCurrentVideo = videoView;
                    applyFullscreenTransform(videoView);
                }
            }

            // 5. Fullscreen toggle button for horizontal (16:9) videos.
            ensureFullscreenButton(videoView);
        } catch (Throwable t) {
            // never crash the host
        }
    }

    // =====================================================================
    // Reels context detection — find the reels root view
    // =====================================================================
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

    // =====================================================================
    // (1) Window transparency — status bar + nav bar TRANSPARENT, video behind
    // =====================================================================
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

    // =====================================================================
    // Make video's ancestor chain fill the entire screen
    // =====================================================================
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
                    // allow children to draw outside bounds (needed for fullscreen transform)
                    if (v instanceof ViewGroup) {
                        try { ((ViewGroup) v).setClipChildren(false); } catch (Throwable t) {}
                        try { ((ViewGroup) v).setClipToPadding(false); } catch (Throwable t) {}
                    }
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
                if (reelsRoot instanceof ViewGroup) {
                    try { ((ViewGroup) reelsRoot).setClipChildren(false); } catch (Throwable t) {}
                    try { ((ViewGroup) reelsRoot).setClipToPadding(false); } catch (Throwable t) {}
                }
            } catch (Throwable t) {}
        } catch (Throwable t) {}
    }

    // =====================================================================
    // Layout listener — re-scan on every layout change (catches Litho re-mounts
    // AND re-applies window transparency to defeat IG's onResume override)
    // =====================================================================
    private static void installLayoutListener(final View videoView, View reelsRoot) {
        try {
            if (reelsRoot == null) return;
            final View video = videoView;
            ViewTreeObserver vto = reelsRoot.getViewTreeObserver();
            if (vto != null) {
                vto.addOnGlobalLayoutListener(new ViewTreeObserver.OnGlobalLayoutListener() {
                    @Override public void onGlobalLayout() {
                        try {
                            makeWindowTransparent(video);
                            if (findReelsRoot(video) != null) {
                                makeBarsTransparent(video);
                            }
                        } catch (Throwable t) {}
                    }
                });
            }
            Activity activity = findActivity(videoView);
            if (activity != null) {
                View decor = activity.getWindow().getDecorView();
                if (decor != null) {
                    ViewTreeObserver dvto = decor.getViewTreeObserver();
                    if (dvto != null) {
                        dvto.addOnGlobalLayoutListener(new ViewTreeObserver.OnGlobalLayoutListener() {
                            @Override public void onGlobalLayout() {
                                try {
                                    makeWindowTransparent(video);
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

    // =====================================================================
    // Periodic re-scan — aggressive 200ms for first 10s (defeats IG onResume)
    // =====================================================================
    private static void startRescan(View videoView) {
        try {
            final View video = videoView;
            final int[] count = {0};
            final Runnable rescan = new Runnable() {
                @Override public void run() {
                    try {
                        makeWindowTransparent(video);
                        if (findReelsRoot(video) != null) {
                            makeBarsTransparent(video);
                        }
                    } catch (Throwable t) {}
                    count[0]++;
                    if (count[0] < 50) {            // 50 x 200ms = 10s
                        video.postDelayed(this, 200);
                    }
                }
            };
            videoView.postDelayed(rescan, 200);
        } catch (Throwable t) {}
    }

    // =====================================================================
    // (2)+(3) Make all bar-like views transparent
    // =====================================================================
    private static void makeBarsTransparent(View videoView) {
        try {
            Activity activity = findActivity(videoView);
            if (activity == null) return;
            View decorView = activity.getWindow().getDecorView();
            if (!(decorView instanceof ViewGroup)) return;

            // First: explicit ID-based lookup for the main bottom tab bar (Problem 2).
            // These are plain FrameLayouts — missed by class-name + missed by the old
            // alpha>=150 threshold because their bg alpha is ~51.
            int[] barIds = { ID_TAB_BAR, ID_LS_NAV_BAR, ID_TAB_BAR_SHADOW, ID_LS_NAV_BAR_SHADOW };
            for (int id : barIds) {
                View bar = decorView.findViewById(id);
                if (bar != null) {
                    setBarTransparent(bar);
                }
            }

            // Then: recursive walk for all other bars (Problem 1 top gradient + Problem 3 comment bar).
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
        if (viewGroup == null || depth > 50) return;
        try {
            int count = viewGroup.getChildCount();
            for (int i = 0; i < count; i++) {
                View child = viewGroup.getChildAt(i);
                if (child == null) continue;

                if (TAG_BTN.equals(child.getTag()) || TAG_OVERLAY.equals(child.getTag())) continue;
                if (child instanceof TextureView) continue;

                boolean shouldMakeTransparent = false;
                String className = child.getClass().getSimpleName();
                if (className != null && BAR_CLASS_NAMES.contains(className)) {
                    shouldMakeTransparent = true;
                }
                if (!shouldMakeTransparent && hasOpaqueBackground(child)) {
                    shouldMakeTransparent = isAtTopOrBottom(child);
                }

                if (shouldMakeTransparent) {
                    // During fullscreen, HIDE bars (INVISIBLE) so the rotated video
                    // overlay stays clean — don't just make them transparent (icons
                    // would still show over the landscape video).
                    if (sIsLandscape) {
                        if (!TAG_HIDDEN.equals(child.getTag())) {
                            child.setTag(TAG_HIDDEN);
                            child.setVisibility(View.INVISIBLE);
                        }
                    } else {
                        setBarTransparent(child);
                    }
                }

                if (child instanceof ViewGroup) {
                    makeBarsTransparentRecursive((ViewGroup) child, videoChain, depth + 1);
                }
            }
        } catch (Throwable t) {}
    }

    /**
     * Detect opaque / semi-opaque backgrounds.
     * Threshold lowered from 150 to 1 (Problem 2 fix: tab_bar bg alpha is ~51).
     */
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
                return alpha >= 1;          // <-- lowered threshold (was 150)
            }
            if (bg instanceof GradientDrawable) {
                return true;                // gradients used by bars are opaque/semi-opaque
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
     * Make a single bar view transparent — CRITICAL: preserve GradientDrawable stroke.
     *
     * Problem 3 fix: the comment bar's background is a single <shape> drawable with
     * BOTH a black <solid> fill AND a white <stroke>. The old setAlpha(0) /
     * setBackgroundColor(TRANSPARENT) calls killed BOTH. Here we detect GradientDrawable
     * and call setColor(TRANSPARENT) which clears the fill while KEEPING the stroke.
     */
    private static void setBarTransparent(View bar) {
        try {
            Object existingTag = bar.getTag();
            if (TAG_HIDDEN.equals(existingTag)) {
                return; // hidden for fullscreen — leave it
            }
            bar.setTag(TAG_TRANSPARENT);

            Drawable bg = bar.getBackground();
            if (bg != null) {
                Drawable inner = bg;
                try { bg = bg.mutate(); } catch (Throwable t) {}
                inner = bg;
                if (inner instanceof InsetDrawable) {
                    Drawable d = ((InsetDrawable) inner).getDrawable();
                    if (d != null) inner = d;
                }
                if (inner instanceof LayerDrawable) {
                    LayerDrawable ld = (LayerDrawable) inner;
                    if (ld.getNumberOfLayers() > 0) {
                        inner = ld.getDrawable(0);
                    }
                }
                // PROBLEM 3 FIX: GradientDrawable — clear fill color, KEEP stroke.
                if (inner instanceof GradientDrawable) {
                    try {
                        ((GradientDrawable) inner).setColor(Color.TRANSPARENT);
                        bar.setBackground(bg);
                        // Also clear children (comment composer box fill)
                        clearChildrenGradientFill(bar);
                        return;             // DO NOT setAlpha(0) / setBackgroundColor — kills stroke
                    } catch (Throwable t) {}
                }
                // Non-gradient: mutate + setAlpha(0) preserves drawable, invisible.
                try {
                    bg.setAlpha(0);
                    bar.setBackground(bg);
                } catch (Throwable t) {}
            }
            // belt-and-suspenders for non-gradient
            try { bar.setBackgroundColor(Color.TRANSPARENT); } catch (Throwable t) {}

            if (Build.VERSION.SDK_INT >= 31) {
                try { bar.setRenderEffect(null); } catch (Throwable t) {}
            }
            clearChildrenGradientFill(bar);
        } catch (Throwable t) {}
    }

    /** Clear the fill color of GradientDrawable children (e.g. comment composer box). */
    private static void clearChildrenGradientFill(View bar) {
        if (!(bar instanceof ViewGroup)) return;
        try {
            ViewGroup vg = (ViewGroup) bar;
            for (int i = 0; i < vg.getChildCount(); i++) {
                View child = vg.getChildAt(i);
                if (child == null) continue;
                Drawable cbg = child.getBackground();
                if (cbg != null) {
                    Drawable inner = cbg;
                    try { cbg = cbg.mutate(); } catch (Throwable t) {}
                    inner = cbg;
                    if (inner instanceof InsetDrawable) {
                        Drawable d = ((InsetDrawable) inner).getDrawable();
                        if (d != null) inner = d;
                    }
                    if (inner instanceof GradientDrawable) {
                        try {
                            ((GradientDrawable) inner).setColor(Color.TRANSPARENT);
                            child.setBackground(cbg);
                        } catch (Throwable t) {}
                    } else if (inner instanceof ColorDrawable) {
                        try {
                            cbg.setAlpha(0);
                            child.setBackground(cbg);
                        } catch (Throwable t) {}
                    }
                }
            }
        } catch (Throwable t) {}
    }

    // =====================================================================
    // (4) Fullscreen toggle button — on Activity's WINDOW DECORVIEW
    // =====================================================================
    private static void ensureFullscreenButton(final View videoView) {
        try {
            final Activity activity = findActivity(videoView);
            if (activity == null) return;
            final Window window = activity.getWindow();
            if (window == null) return;

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

        btn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                if (sIsLandscape) {
                    exitFullscreen(videoView);
                } else {
                    enterFullscreen(videoView);
                }
            }
        });

        // Poll video size — show button only for landscape (16:9) videos.
        final int[] polls = {0};
        final Runnable poll = new Runnable() {
            @Override public void run() {
                polls[0]++;
                if (sIsLandscape) {
                    btn.setVisibility(View.VISIBLE);
                    return;
                }
                int[] wh = getVideoSize(videoView);
                if (wh != null && wh[0] > 0 && wh[1] > 0) {
                    if (wh[0] > wh[1] * 1.15f) {       // landscape (16:9 or wider)
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

    // =====================================================================
    // ENTER FULLSCREEN — transform TextureView in-place (NO activity rotation)
    // =====================================================================
    private static void enterFullscreen(View videoView) {
        try {
            sIsLandscape = true;
            sCurrentVideo = videoView;

            // Find + lock the ViewPager2 so vertical swipe doesn't fight the overlay.
            sViewPager2 = findViewPager2(videoView);
            if (sViewPager2 != null) {
                try {
                    Method m = sViewPager2.getClass().getMethod("setUserInputEnabled", boolean.class);
                    m.invoke(sViewPager2, Boolean.FALSE);
                } catch (Throwable t) {}
            }

            // Apply the video transform (rotation + scale to fill screen landscape).
            applyFullscreenTransform(videoView);

            // Hide IG overlay UI (bars + side action column).
            hideOverlayUI(videoView, true);

            // Add the fullscreen control overlay (exit + prev/next tap zones).
            Activity activity = findActivity(videoView);
            if (activity != null) {
                addFullscreenOverlay(videoView, activity);
            }

            // Update button icon to "exit fullscreen"
            if (sButton instanceof ImageView) {
                ((ImageView) sButton).setImageResource(android.R.drawable.ic_menu_close_clear_cancel);
                sButton.setAlpha(1f);
            }
        } catch (Throwable t) {}
    }

    /**
     * Apply the landscape transform to the TextureView (A02 field of X/7ky).
     *
     * Math (verified): TextureView is screenW x screenH (portrait, fills screen).
     *   setRotation(90) + setScaleX(screenH/screenW) + setScaleY(screenW/screenH)
     * with default pivot (center) makes the rotated+scaled quad fill the screen
     * exactly, rendering the video in landscape orientation.
     */
    private static void applyFullscreenTransform(View videoView) {
        try {
            TextureView tex = getTextureView(videoView);
            if (tex == null) return;

            int screenW = videoView.getContext().getResources().getDisplayMetrics().widthPixels;
            int screenH = videoView.getContext().getResources().getDisplayMetrics().heightPixels;
            if (screenW <= 0 || screenH <= 0) return;

            tex.setPivotX(tex.getWidth() / 2f);
            tex.setPivotY(tex.getHeight() / 2f);
            tex.setRotation(90f);
            tex.setScaleX((float) screenH / (float) screenW);
            tex.setScaleY((float) screenW / (float) screenH);
            tex.setTranslationX(0f);
            tex.setTranslationY(0f);

            // ensure ancestors don't clip the transformed video
            View p = (View) tex.getParent();
            int hops = 0;
            while (p != null && hops < 12) {
                if (p instanceof ViewGroup) {
                    try { ((ViewGroup) p).setClipChildren(false); } catch (Throwable t) {}
                    try { ((ViewGroup) p).setClipToPadding(false); } catch (Throwable t) {}
                }
                if (p.getParent() instanceof View) {
                    p = (View) p.getParent();
                } else {
                    break;
                }
                hops++;
            }
        } catch (Throwable t) {}
    }

    /** Restore the TextureView to its normal (portrait) state. */
    private static void restoreVideoTransform(View videoView) {
        try {
            TextureView tex = getTextureView(videoView);
            if (tex == null) return;
            tex.setRotation(0f);
            tex.setScaleX(1f);
            tex.setScaleY(1f);
            tex.setTranslationX(0f);
            tex.setTranslationY(0f);
        } catch (Throwable t) {}
    }

    // =====================================================================
    // EXIT FULLSCREEN
    // =====================================================================
    private static void exitFullscreen(View videoView) {
        try {
            sIsLandscape = false;

            // Unlock ViewPager2
            if (sViewPager2 != null) {
                try {
                    Method m = sViewPager2.getClass().getMethod("setUserInputEnabled", boolean.class);
                    m.invoke(sViewPager2, Boolean.TRUE);
                } catch (Throwable t) {}
            }

            // Restore video transform
            restoreVideoTransform(videoView);

            // Show IG overlay UI again
            hideOverlayUI(videoView, false);

            // Remove the fullscreen overlay
            Activity activity = findActivity(videoView);
            if (activity != null && sOverlay != null) {
                try {
                    ((ViewGroup) activity.getWindow().getDecorView()).removeView(sOverlay);
                } catch (Throwable t) {}
                sOverlay = null;
            }

            // Update button icon to "enter fullscreen"
            if (sButton instanceof ImageView) {
                ((ImageView) sButton).setImageResource(android.R.drawable.ic_menu_crop);
                sButton.setAlpha(0.55f);
            }
        } catch (Throwable t) {}
    }

    // =====================================================================
    // Fullscreen control overlay — exit button + prev/next tap zones
    // =====================================================================
    private static void addFullscreenOverlay(final View videoView, final Activity activity) {
        try {
            if (sOverlay != null && sOverlay.getParent() != null) return;
            final ViewGroup decorView = (ViewGroup) activity.getWindow().getDecorView();

            final FrameLayout overlay = new FrameLayout(videoView.getContext());
            overlay.setTag(TAG_OVERLAY);

            // Exit button (top-right)
            View exitBtn = makeButton(videoView.getContext());
            exitBtn.setImageResource(android.R.drawable.ic_menu_close_clear_cancel);
            FrameLayout.LayoutParams exitLp = new FrameLayout.LayoutParams(
                    dp(videoView, 40), dp(videoView, 40),
                    Gravity.TOP | Gravity.END);
            exitLp.topMargin = dp(videoView, 24);
            exitLp.rightMargin = dp(videoView, 24);
            overlay.addView(exitBtn, exitLp);
            exitBtn.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View v) {
                    exitFullscreen(videoView);
                }
            });

            // Prev zone (left 40%)
            View prevZone = new View(videoView.getContext());
            FrameLayout.LayoutParams prevLp = new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    Gravity.START);
            prevLp.width = (int) (videoView.getContext().getResources().getDisplayMetrics().widthPixels * 0.4);
            overlay.addView(prevZone, 0, prevLp);
            prevZone.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View v) {
                    advanceReel(videoView, -1);
                }
            });

            // Next zone (right 40%)
            View nextZone = new View(videoView.getContext());
            FrameLayout.LayoutParams nextLp = new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    Gravity.END);
            nextLp.width = (int) (videoView.getContext().getResources().getDisplayMetrics().widthPixels * 0.4);
            overlay.addView(nextZone, 0, nextLp);
            nextZone.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View v) {
                    advanceReel(videoView, 1);
                }
            });

            decorView.addView(overlay, new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT));
            overlay.bringToFront();
            sOverlay = overlay;
        } catch (Throwable t) {}
    }

    /** Advance to the next/prev reel via the reflected ViewPager2. */
    private static void advanceReel(View videoView, int delta) {
        try {
            Object vp = sViewPager2;
            if (vp == null) vp = findViewPager2(videoView);
            if (vp == null) return;
            Method getCurrent = vp.getClass().getMethod("getCurrentItem");
            int cur = (Integer) getCurrent.invoke(vp);
            Method setCurrent = vp.getClass().getMethod("setCurrentItem", int.class, boolean.class);
            setCurrent.invoke(vp, cur + delta, Boolean.TRUE);
        } catch (Throwable t) {
            try {
                Object vp = sViewPager2 != null ? sViewPager2 : findViewPager2(videoView);
                if (vp == null) return;
                Method getCurrent = vp.getClass().getMethod("getCurrentItem");
                int cur = (Integer) getCurrent.invoke(vp);
                Method setCurrent = vp.getClass().getMethod("setCurrentItem", int.class);
                setCurrent.invoke(vp, cur + delta);
            } catch (Throwable t2) {}
        }
    }

    // =====================================================================
    // Hide / show IG overlay UI for fullscreen
    // =====================================================================
    private static void hideOverlayUI(View videoView, boolean hide) {
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
            setOverlayUIVisibilityRecursive((ViewGroup) decorView, videoChain, hide, 0);
        } catch (Throwable t) {}
    }

    private static void setOverlayUIVisibilityRecursive(ViewGroup vg, Set<View> videoChain, boolean hide, int depth) {
        if (vg == null || depth > 50) return;
        try {
            for (int i = 0; i < vg.getChildCount(); i++) {
                View child = vg.getChildAt(i);
                if (child == null) continue;
                if (TAG_BTN.equals(child.getTag()) || TAG_OVERLAY.equals(child.getTag())) continue;
                if (child instanceof TextureView) continue;
                if (videoChain.contains(child)) {
                    if (child instanceof ViewGroup) {
                        setOverlayUIVisibilityRecursive((ViewGroup) child, videoChain, hide, depth + 1);
                    }
                    continue;
                }

                boolean isBar = false;
                String cn = child.getClass().getSimpleName();
                if (cn != null && BAR_CLASS_NAMES.contains(cn)) isBar = true;
                if (!isBar && hasOpaqueBackground(child) && isAtTopOrBottom(child)) isBar = true;
                // also hide by known IDs
                int id = child.getId();
                if (id == ID_TAB_BAR || id == ID_LS_NAV_BAR || id == ID_TAB_BAR_SHADOW || id == ID_LS_NAV_BAR_SHADOW) {
                    isBar = true;
                }

                if (isBar) {
                    if (hide) {
                        if (child.getVisibility() != View.GONE) {
                            child.setTag(TAG_HIDDEN);
                            child.setVisibility(View.INVISIBLE);
                        }
                    } else {
                        if (TAG_HIDDEN.equals(child.getTag())) {
                            child.setTag(TAG_TRANSPARENT);
                            child.setVisibility(View.VISIBLE);
                        }
                    }
                }

                if (child instanceof ViewGroup) {
                    setOverlayUIVisibilityRecursive((ViewGroup) child, videoChain, hide, depth + 1);
                }
            }
        } catch (Throwable t) {}
    }

    // =====================================================================
    // Helpers — find ViewPager2, TextureView, Activity, video size
    // =====================================================================

    /** Walk up the parent chain to find a ViewPager2 instance (by class name). */
    private static Object findViewPager2(View view) {
        try {
            View v = view;
            int hops = 0;
            while (v != null && hops < 25) {
                String cn = v.getClass().getName();
                if (cn != null && cn.equals("androidx.viewpager2.widget.ViewPager2")) {
                    return v;
                }
                if (v.getParent() instanceof View) {
                    v = (View) v.getParent();
                } else {
                    break;
                }
                hops++;
            }
        } catch (Throwable t) {}
        return null;
    }

    /** Reflect on the video view's class hierarchy to get field A02 (TextureView). */
    private static TextureView getTextureView(View videoView) {
        try {
            Class<?> cls = videoView.getClass();
            while (cls != null && cls != View.class) {
                try {
                    Field f = cls.getDeclaredField("A02");
                    f.setAccessible(true);
                    Object o = f.get(videoView);
                    if (o instanceof TextureView) {
                        return (TextureView) o;
                    }
                } catch (NoSuchFieldException ignored) {
                } catch (Throwable t) {}
                cls = cls.getSuperclass();
            }
        } catch (Throwable t) {}
        return null;
    }

    /**
     * Get video size [width, height] via reflection on the mediaInfo (A04 field).
     * A04 is C160765mH which has field A03 (cached Double aspect) + method A02().
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

            // cached public Double A03 field
            Class<?> mc = mediaInfo.getClass();
            while (mc != null && mc != Object.class) {
                try {
                    Field fA03 = mc.getDeclaredField("A03");
                    fA03.setAccessible(true);
                    Object cached = fA03.get(mediaInfo);
                    if (cached instanceof Double) {
                        double val = (Double) cached;
                        if (val > 0.0) aspect = val;
                    }
                    break;
                } catch (NoSuchFieldException ignored) {
                    mc = mc.getSuperclass();
                }
            }

            // A02() method
            if (aspect <= 0.0) {
                mc = mediaInfo.getClass();
                while (mc != null && mc != Object.class) {
                    try {
                        Method m = mc.getDeclaredMethod("A02");
                        m.setAccessible(true);
                        Object r = m.invoke(mediaInfo);
                        if (r instanceof Double) {
                            double val = (Double) r;
                            if (val > 0.0) aspect = val;
                        }
                        break;
                    } catch (NoSuchMethodException ignored) {
                        mc = mc.getSuperclass();
                    }
                }
            }

            // A03(Context, boolean)
            if (aspect <= 0.0) {
                mc = mediaInfo.getClass();
                while (mc != null && mc != Object.class) {
                    try {
                        Method m = mc.getDeclaredMethod("A03", Context.class, boolean.class);
                        m.setAccessible(true);
                        Object r = m.invoke(mediaInfo, videoView.getContext(), Boolean.FALSE);
                        if (r instanceof Double) {
                            double val = (Double) r;
                            if (val > 0.0) aspect = val;
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
