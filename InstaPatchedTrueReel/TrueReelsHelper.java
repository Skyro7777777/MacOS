package app.truereels;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.ImageView;
import java.lang.reflect.Method;
import java.lang.reflect.Field;
import java.util.HashSet;
import java.util.Set;

/**
 * InstaPatchedTrueReel runtime helper (v4).
 *
 * Called from a patched hook in LX/7ky (AbstractC210917ky / "VideoFrameLayout" —
 * the ACTUAL reels video surface base class) onAttachedToWindow().
 *
 * v4 fixes (based on v3 user feedback):
 *   - v3 used FLAG_LAYOUT_NO_LIMITS which disabled the window's theme background.
 *     Combined with the transparent reels root view, this caused the home feed
 *     (sibling fragment below reels) to show through behind the comment bar +
 *     flickering on scroll. v4 REMOVES FLAG_LAYOUT_NO_LIMITS.
 *   - v4 makes the reels fragment root (TouchInterceptorFrameLayout) OPAQUE BLACK
 *     so the home feed never shows through.
 *   - v4 fixes the fullscreen-button video-size detection: v3 used
 *     getDeclaredField("A04") which fails because A04 is declared in the parent
 *     AbstractC210917ky, not the runtime class SimpleVideoLayout. v4 walks the
 *     superclass chain to find inherited fields.
 *   - v4 makes makeAncestorsMatchParent less aggressive: stops at the
 *     TouchInterceptorFrameLayout (reels root) to avoid breaking the comment
 *     composer's positioning.
 */
public class TrueReelsHelper {

    private static final int RESIZE_MODE_FILL = 3;
    private static final int RESIZE_MODE_ZOOM = 4;

    // 0x16ff = FULLSCREEN | HIDE_NAV | LAYOUT_STABLE | LAYOUT_FULLSCREEN |
    //          LAYOUT_HIDE_NAV | IMMERSIVE_STICKY
    private static final int FLAG_IMMERSIVE = 0x1 | 0x2 | 0x100 | 0x200 | 0x400 | 0x1000;

    private static final String TAG_BTN = "truereels_fs_btn";

    // Bar class names to make transparent (TikTok-style translucent bars)
    private static final Set<String> TRANSPARENT_CLASS_NAMES = new HashSet<>();
    static {
        TRANSPARENT_CLASS_NAMES.add("ClipsViewerReplyBar");
        TRANSPARENT_CLASS_NAMES.add("ClipsViewerNavigationBar");
        TRANSPARENT_CLASS_NAMES.add("ClipsViewerActionBar");
    }

    /** Called from LX/7ky.onAttachedToWindow (smali-injected). */
    public static void onPlayerAttached(View videoView) {
        try {
            // 1. Make the video view + its ancestors (up to the reels root) fill the screen.
            //    STOP at TouchInterceptorFrameLayout (the reels root) to avoid breaking the
            //    comment composer's positioning relative to the activity content.
            makeAncestorsMatchParent(videoView);

            // 2. Make the reels fragment root OPAQUE BLACK so the home feed (sibling
            //    fragment below reels in the same activity) never shows through. This is
            //    the fix for the v3 flicker / feed-showing-through issue.
            makeReelsRootOpaque(videoView);

            // 3. Apply immersive flags (hide system bars). Do NOT use FLAG_LAYOUT_NO_LIMITS
            //    (that was the v3 flicker root cause). The activity already lays out behind
            //    system bars via setSystemUiVisibility(1792) on its decorView.
            applyImmersiveFlags(videoView);

            // 4. Walk the view tree and make overlay bars transparent (TikTok-style).
            Activity activity = findActivity(videoView);
            if (activity != null) {
                View decor = activity.getWindow().getDecorView();
                makeBarsTransparent(decor);
            }

            // 5. Fullscreen button for horizontal videos.
            ensureFullscreenButton(videoView);
        } catch (Throwable t) {
            // never crash the host
        }
    }

    // -----------------------------------------------------------------------
    // 1. Make ancestors MATCH_PARENT (up to the reels root, not past it)
    // -----------------------------------------------------------------------
    private static void makeAncestorsMatchParent(View view) {
        View v = view;
        int hops = 0;
        while (v != null && hops < 15) {
            hops++;
            try {
                // Stop at the reels root (TouchInterceptorFrameLayout) — don't touch
                // the activity content / decorView (would break comment composer positioning).
                String className = v.getClass().getSimpleName();
                if ("TouchInterceptorFrameLayout".equals(className)) {
                    // This is the reels root — make it MATCH_PARENT but don't walk past it.
                    setMatchParent(v);
                    break;
                }
                setMatchParent(v);
                v.setFitsSystemWindows(false);
                v.setPadding(0, 0, 0, 0);
            } catch (Throwable t) {}
            if (v.getParent() instanceof View) {
                v = (View) v.getParent();
            } else {
                v = null;
            }
        }
    }

    private static void setMatchParent(View v) {
        try {
            ViewGroup.LayoutParams lp = v.getLayoutParams();
            if (lp != null) {
                boolean changed = false;
                if (lp.width != ViewGroup.LayoutParams.MATCH_PARENT) {
                    lp.width = ViewGroup.LayoutParams.MATCH_PARENT;
                    changed = true;
                }
                if (lp.height != ViewGroup.LayoutParams.MATCH_PARENT) {
                    lp.height = ViewGroup.LayoutParams.MATCH_PARENT;
                    changed = true;
                }
                if (changed) v.setLayoutParams(lp);
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // 2. Make the reels fragment root OPAQUE BLACK (fix for v3 flicker)
    // -----------------------------------------------------------------------
    private static void makeReelsRootOpaque(View videoView) {
        try {
            View v = videoView;
            int hops = 0;
            while (v != null && hops < 15) {
                hops++;
                String className = v.getClass().getSimpleName();
                if ("TouchInterceptorFrameLayout".equals(className)) {
                    // This is the reels root (reel_viewer_root). Make it opaque black
                    // so the home feed below never shows through.
                    v.setBackgroundColor(Color.BLACK);
                    return;
                }
                if (v.getParent() instanceof View) {
                    v = (View) v.getParent();
                } else {
                    v = null;
                }
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // 3. Immersive flags (hide system bars — NO FLAG_LAYOUT_NO_LIMITS)
    // -----------------------------------------------------------------------
    private static void applyImmersiveFlags(View view) {
        try {
            Activity activity = findActivity(view);
            if (activity == null) return;
            Window window = activity.getWindow();
            if (window == null) return;

            // Set the immersive sticky flags on the decorView (hides status + nav bars).
            // 0x16ff includes LAYOUT_STABLE | LAYOUT_FULLSCREEN | LAYOUT_HIDE_NAVIGATION
            // so the content already extends behind system bars (the activity also sets
            // setSystemUiVisibility(1792) which provides the same layout flags).
            View decor = window.getDecorView();
            try {
                decor.setSystemUiVisibility(FLAG_IMMERSIVE);
            } catch (Throwable t) {}

            // Make status + nav bar colors transparent (translucent overlays on video).
            try {
                window.setStatusBarColor(Color.TRANSPARENT);
            } catch (Throwable t) {}
            try {
                window.setNavigationBarColor(Color.TRANSPARENT);
            } catch (Throwable t) {}

            // NOTE: Do NOT add FLAG_LAYOUT_NO_LIMITS — it disables the window theme
            // background, and since the reels root is transparent, the home feed below
            // would show through (causing the v3 flicker). The activity's existing
            // setSystemUiVisibility(1792) already provides edge-to-edge layout.
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // 4. Make overlay bars transparent (TikTok-style translucent bars)
    // -----------------------------------------------------------------------
    private static void makeBarsTransparent(View root) {
        if (root == null) return;
        try {
            walkAndTransparentize(root, 0);
        } catch (Throwable t) {}
    }

    private static void walkAndTransparentize(View view, int depth) {
        if (view == null || depth > 30) return;
        try {
            // Skip TextureViews (the video surface) — never make them transparent.
            if (view instanceof TextureView) return;

            String className = view.getClass().getSimpleName();
            boolean shouldTransparentize = false;

            // Check by class name (known bar classes).
            if (TRANSPARENT_CLASS_NAMES.contains(className)) {
                shouldTransparentize = true;
            }

            // Check if it has an opaque ColorDrawable background (the solid bars).
            if (!shouldTransparentize) {
                try {
                    Drawable bg = view.getBackground();
                    if (bg instanceof ColorDrawable) {
                        int color = ((ColorDrawable) bg).getColor();
                        int alpha = Color.alpha(color);
                        // Only transparentize solid (high-alpha) dark backgrounds.
                        // This catches the comment composer bar, reply bar, etc.
                        if (alpha >= 200) {
                            shouldTransparentize = true;
                        }
                    }
                } catch (Throwable t) {}
            }

            if (shouldTransparentize) {
                try {
                    view.setBackgroundColor(Color.TRANSPARENT);
                } catch (Throwable t) {}
            }

            // Recurse into children.
            if (view instanceof ViewGroup) {
                ViewGroup vg = (ViewGroup) view;
                for (int i = 0; i < vg.getChildCount(); i++) {
                    walkAndTransparentize(vg.getChildAt(i), depth + 1);
                }
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // 5. Fullscreen toggle button for horizontal videos
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
        // Uses the fixed getVideoSize() that walks the superclass chain.
        final int[] polls = {0};
        final Runnable poll = new Runnable() {
            @Override public void run() {
                polls[0]++;
                int[] wh = getVideoSize(videoView);
                if (wh != null && wh[0] > 0 && wh[1] > 0) {
                    if (wh[0] > wh[1]) {
                        // Horizontal video — show fullscreen button.
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
            android.graphics.Matrix m = tv.getTransform(new android.graphics.Matrix());
            float[] values = new float[9];
            m.getValues(values);
            float scaleX = values[android.graphics.Matrix.MSCALE_X];
            if (scaleX > 1.5f) {
                // Currently stretched — reset to identity (fit/letterbox).
                tv.setTransform(new android.graphics.Matrix());
                btn.setAlpha(0.55f);
            } else {
                // Currently fit — stretch to fill.
                float sx = (float) videoView.getWidth() / (float) tv.getWidth();
                float sy = (float) videoView.getHeight() / (float) tv.getHeight();
                android.graphics.Matrix stretch = new android.graphics.Matrix();
                stretch.setScale(sx, sy);
                tv.setTransform(stretch);
                btn.setAlpha(1f);
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
     *
     * v4 FIX: v3 used getDeclaredField("A04") which fails because A04 is declared
     * in the PARENT class AbstractC210917ky, not the runtime class SimpleVideoLayout.
     * getDeclaredField only finds fields in the exact class, not inherited ones.
     * v4 walks the superclass chain to find inherited fields.
     *
     * Returns int[]{width, height} where width/height are proportional (aspect*100, 100).
     * Caller checks wh[0] > wh[1] for horizontal detection.
     */
    private static int[] getVideoSize(View videoView) {
        try {
            // 1) Walk up the class hierarchy to find field A04 (declared in
            //    AbstractC210917ky, the superclass of the runtime SimpleVideoLayout).
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

            // 2) Read the cached public Double A03 field first (instant, no IO).
            //    C160765mH caches the aspect ratio in field A03.
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

            // 3) If not cached, call A02() (no-arg, returns Double aspect = W/H).
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

            // 4) Last resort: A03(Context, boolean) for the A06=false path.
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
            // aspect = width / height. Return as {aspect*100, 100} so caller's
            // wh[0] > wh[1] check works for horizontal detection.
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
