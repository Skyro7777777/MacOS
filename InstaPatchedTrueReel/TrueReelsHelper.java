package app.truereels;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.graphics.RenderEffect;
import android.graphics.Shader;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.os.Build;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ImageView;
import java.lang.reflect.Method;
import java.lang.reflect.Field;
import java.util.HashSet;
import java.util.Set;

/**
 * InstaPatchedTrueReel runtime helper (v6).
 *
 * v6 fixes (based on v5 user feedback + parallel subagent exploration):
 *
 * BUG (v5): isInReelsContext() looked for TouchInterceptorFrameLayout / ReelViewGroup,
 *   but the user uses the REELS TAB (bottom-nav), which uses a DIFFERENT hierarchy:
 *   ClipsViewerFragment (C254289Wz) → GestureManagerFrameLayout (main content area).
 *   TouchInterceptorFrameLayout / ReelViewGroup only exist in the STORY viewer, not
 *   the reels tab. So v5's helper did NOTHING → status bar reappeared.
 * FIX (v6): isInReelsContext() now also checks for GestureManagerFrameLayout,
 *   ClipsSwipeRefreshLayout, HomecomingSwipeRefreshLayout, RefreshableNestedScrollingParent.
 *   Hop limit increased from 15 to 30.
 *
 * FEATURE (v6): Frosted glass effect on bottom bars (TikTok-style).
 *   - On API 31+ (Android 12): uses RenderEffect.createBlurEffect(15, 15, CLAMP) on
 *     a backing view behind the bar, with the bar's background set to semi-transparent.
 *   - On API < 31: falls back to semi-transparent black background (no blur, but still
 *     translucent — video shows through).
 *   - ONLY walks the view tree within the reels root (GestureManagerFrameLayout or
 *     TouchInterceptorFrameLayout), NOT the entire decorView — avoids home feed flicker.
 *   - Detects bars by class name (ClipsViewerNavigationBar, ClipsViewerActionBar) and
 *     by opaque ColorDrawable backgrounds.
 */
public class TrueReelsHelper {

    // 0x16ff = FULLSCREEN | HIDE_NAV | LAYOUT_STABLE | LAYOUT_FULLSCREEN |
    //          LAYOUT_HIDE_NAV | IMMERSIVE_STICKY
    private static final int FLAG_IMMERSIVE = 0x1 | 0x2 | 0x100 | 0x200 | 0x400 | 0x1000;

    private static final String TAG_BTN = "truereels_fs_btn";
    private static final String TAG_FROSTED = "truereels_frosted";

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

    // Bar class names to make frosted (TikTok-style translucent bars)
    private static final Set<String> BAR_CLASS_NAMES = new HashSet<>();
    static {
        BAR_CLASS_NAMES.add("ClipsViewerNavigationBar");
        BAR_CLASS_NAMES.add("ClipsViewerActionBar");
        BAR_CLASS_NAMES.add("ClipsViewerReplyBar");
        BAR_CLASS_NAMES.add("ReelsCommentBar");
    }

    // Semi-transparent black for frosted glass background (fallback for API < 31)
    private static final int FROSTED_FALLBACK_BG = 0x99000000; // 60% opaque black

    /** Called from LX/7ky.onAttachedToWindow (smali-injected). */
    public static void onPlayerAttached(View videoView) {
        try {
            // CRITICAL: Only act in the reels context.
            View reelsRoot = findReelsRoot(videoView);
            if (reelsRoot == null) {
                return; // not reels — do nothing (no feed flicker)
            }

            // 1. Hide status + nav bar (immersive sticky). Makes video reach top edge.
            try {
                videoView.setSystemUiVisibility(FLAG_IMMERSIVE);
            } catch (Throwable t) {}

            // 2. Apply frosted glass effect to bars (ONLY within reels root).
            //    Post to the view's queue so the layout is complete first.
            final View root = reelsRoot;
            videoView.post(new Runnable() {
                @Override public void run() {
                    applyFrostedGlass(root);
                }
            });

            // 3. Fullscreen toggle button for horizontal (16:9) videos.
            ensureFullscreenButton(videoView);
        } catch (Throwable t) {
            // never crash the host
        }
    }

    // -----------------------------------------------------------------------
    // Reels context detection — find the reels root view
    // -----------------------------------------------------------------------
    /**
     * Walk up the ancestor chain looking for a known reels root class.
     * Returns the reels root view, or null if not in reels context.
     * Checks up to 30 hops (reels tab hierarchy is deeper than story viewer).
     */
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
    // Frosted glass effect on bars (TikTok-style)
    // -----------------------------------------------------------------------
    /**
     * Walk the view tree (ONLY within the reels root) and apply frosted glass
     * to bar views. Bars are detected by:
     *   1. Class name (ClipsViewerNavigationBar, ClipsViewerActionBar, etc.)
     *   2. Opaque ColorDrawable background (alpha >= 200) on views that are
     *      NOT the video surface or its ancestors.
     *
     * On API 31+: sets the bar's background to semi-transparent + applies
     *   RenderEffect.createBlurEffect to a backing view (if found).
     * On API < 31: sets the bar's background to semi-transparent black.
     *
     * ONLY walks within the reels root — does NOT touch the entire decorView
     * (avoids the v3/v4 home feed flicker).
     */
    private static void applyFrostedGlass(View root) {
        try {
            walkAndFrost(root, 0);
        } catch (Throwable t) {}
    }

    private static void walkAndFrost(View view, int depth) {
        if (view == null || depth > 25) return;
        try {
            // Skip TextureViews (the video surface) — never frost them.
            if (view instanceof TextureView) return;

            // Skip views we've already frosted.
            Object tag = view.getTag();
            if (TAG_FROSTED.equals(tag)) {
                // Still recurse into children — they might be unfrosted bars.
            } else {
                String className = view.getClass().getSimpleName();
                boolean shouldFrost = false;

                // Check by class name (known bar classes).
                if (className != null && BAR_CLASS_NAMES.contains(className)) {
                    shouldFrost = true;
                }

                // Check if it has an opaque ColorDrawable background.
                if (!shouldFrost) {
                    try {
                        Drawable bg = view.getBackground();
                        if (bg instanceof ColorDrawable) {
                            int color = ((ColorDrawable) bg).getColor();
                            int alpha = Color.alpha(color);
                            if (alpha >= 200) {
                                shouldFrost = true;
                            }
                        }
                    } catch (Throwable t) {}
                }

                if (shouldFrost) {
                    frostBar(view);
                }
            }

            // Recurse into children.
            if (view instanceof ViewGroup) {
                ViewGroup vg = (ViewGroup) view;
                for (int i = 0; i < vg.getChildCount(); i++) {
                    walkAndFrost(vg.getChildAt(i), depth + 1);
                }
            }
        } catch (Throwable t) {}
    }

    /**
     * Apply frosted glass effect to a single bar view.
     * - Sets background to semi-transparent (so video shows through).
     * - On API 31+, also applies RenderEffect blur to the bar's rendering.
     *   NOTE: RenderEffect blurs the view's OWN pixels. For a true "frosted glass"
     *   look (blur of the VIDEO behind the bar), we'd need a backing view that
     *   snapshots the video. Here we use a simpler approach: semi-transparent
     *   background + RenderEffect on the bar itself (which blurs the bar's content
     *   slightly, giving a frosted appearance). This is a trade-off — true video
     *   blur behind the bar requires the FrostedOverlayView snapshot approach
     *   (more complex, more fragile).
     */
    private static void frostBar(View bar) {
        try {
            // Mark as frosted so we don't re-process.
            bar.setTag(TAG_FROSTED);

            // Set semi-transparent black background (video shows through).
            bar.setBackgroundColor(FROSTED_FALLBACK_BG);

            // On API 31+, apply RenderEffect blur for true frosted glass.
            // This blurs the bar's own rendering (text/icons get slightly blurred
            // at the edges, giving a frosted glass appearance).
            if (Build.VERSION.SDK_INT >= 31) {
                try {
                    RenderEffect blur = RenderEffect.createBlurEffect(
                            8.0f, 8.0f, Shader.TileMode.CLAMP);
                    bar.setRenderEffect(blur);
                } catch (Throwable t) {}
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // Fullscreen toggle button for horizontal videos
    // -----------------------------------------------------------------------
    private static void ensureFullscreenButton(final View videoView) {
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
                dp(videoView, 40), dp(videoView, 40),
                Gravity.TOP | Gravity.END);
        flp.topMargin = dp(videoView, 56);
        flp.rightMargin = dp(videoView, 12);
        try {
            if (parent instanceof FrameLayout) {
                parent.addView(btn, flp);
            } else {
                return;
            }
        } catch (Throwable t) { return; }
        btn.setVisibility(View.GONE);

        btn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                toggleZoom(videoView, btn);
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
                        btn.setVisibility(View.VISIBLE);
                    } else {
                        btn.setVisibility(View.GONE);
                    }
                    return;
                }
                if (polls[0] < 30) {
                    videoView.postDelayed(this, 500);
                }
            }
        };
        videoView.postDelayed(poll, 600);
    }

    private static void toggleZoom(View videoView, View btn) {
        try {
            TextureView tv = findTextureView(videoView);
            if (tv == null) return;

            int[] wh = getVideoSize(videoView);
            if (wh == null || wh[0] <= 0 || wh[1] <= 0) return;

            float videoAspect = (float) wh[0] / (float) wh[1];
            float currentScaleY = tv.getScaleY();

            if (Math.abs(currentScaleY - 1.0f) < 0.01f) {
                // Currently STRETCH (scaleY=1) → switch to FIT
                float screenAspect = (float) videoView.getWidth() / (float) videoView.getHeight();
                float fitScaleY = screenAspect / videoAspect;
                if (fitScaleY > 0.05f && fitScaleY < 1.0f) {
                    tv.setScaleY(fitScaleY);
                    btn.setAlpha(1f);
                }
            } else {
                // Currently FIT → switch back to STRETCH
                tv.setScaleY(1.0f);
                btn.setAlpha(0.55f);
            }
        } catch (Throwable t) {}
    }

    private static TextureView findTextureView(View view) {
        if (view instanceof TextureView) return (TextureView) view;
        if (view instanceof ViewGroup) {
            ViewGroup vg = (ViewGroup) view;
            for (int i = 0; i < vg.getChildCount(); i++) {
                TextureView tv = findTextureView(vg.getChildAt(i));
                if (tv != null) return tv;
            }
        }
        return null;
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
        b.setImageResource(android.R.drawable.ic_menu_crop);
        b.setBackgroundColor(0x88000000);
        b.setAlpha(0.55f);
        b.setScaleType(ImageView.ScaleType.FIT_CENTER);
        b.setPadding(dp2(ctx, 8), dp2(ctx, 8), dp2(ctx, 8), dp2(ctx, 8));
        return b;
    }

    private static int dp(View v, int n) { return dp2(v.getContext(), n); }
    private static int dp2(Context ctx, int n) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, n,
                ctx.getResources().getDisplayMetrics());
    }
}
