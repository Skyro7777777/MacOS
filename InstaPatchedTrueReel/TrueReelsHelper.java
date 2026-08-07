package app.truereels;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.os.Build;
import android.util.TypedValue;
import android.view.Gravity;
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
 * InstaPatchedTrueReel runtime helper (v2).
 *
 * Called from a patched hook in LX/7ky (AbstractC210917ky / "VideoFrameLayout" —
 * the ACTUAL reels video surface base class) onAttachedToWindow().
 *
 * Responsibilities:
 *   1. Ensure the video view AND all its ancestors fill the screen (MATCH_PARENT).
 *      This makes the video stretch edge-to-edge behind the bars (TikTok-style).
 *   2. Apply immersive sticky system-UI flags on the Activity's window so the
 *      video reaches the physical status bar + nav bar (no black gap at top).
 *   3. Walk the view tree from the Activity's root and make all overlay bars
 *      (comment composer, reply bar, nav bar, top header, bottom shadow)
 *      TRANSPARENT so the video shows through them (TikTok-style translucent bars).
 *   4. Detect horizontal (16:9-ish) videos and show a TikTok-style "fullscreen"
 *      toggle button that switches between FILL (stretch) and ZOOM (crop-to-fill).
 *
 * Everything is best-effort and wrapped in try/catch so a failure here never
 * crashes Instagram.
 */
public class TrueReelsHelper {

    private static final int RESIZE_MODE_FILL = 3;  // stretch (distort) to fill
    private static final int RESIZE_MODE_ZOOM = 4;  // crop to fill

    // 0x16ff = FULLSCREEN | HIDE_NAV | LAYOUT_STABLE | LAYOUT_FULLSCREEN |
    //          LAYOUT_HIDE_NAV | IMMERSIVE_STICKY
    private static final int FLAG_IMMERSIVE = 0x1 | 0x2 | 0x100 | 0x200 | 0x400 | 0x1000;

    // Tags we add to views we've already processed (avoid double-processing)
    private static final String TAG_FILLED = "truereels_filled";
    private static final String TAG_BTN = "truereels_fs_btn";

    // Classes we want to make transparent (by simple name) — these are the
    // overlay bars that cover the video in the reels UI.
    private static final Set<String> TRANSPARENT_CLASS_NAMES = new HashSet<>();
    static {
        // Bottom comment composer / reply bar
        TRANSPARENT_CLASS_NAMES.add("ClipsViewerReplyBar");      // layout_clips_viewer_reply_bar
        // Bottom navigation bar (the main IG tab bar shown over reels)
        TRANSPARENT_CLASS_NAMES.add("ClipsViewerNavigationBar");
        // Top action bar
        TRANSPARENT_CLASS_NAMES.add("ClipsViewerActionBar");
        // Bottom shadow gradient
        // (these are generic Views/ImageViews with gradient drawables — handled by tag/id walk)
    }

    /** Called from LX/7ky.onAttachedToWindow (smali-injected). */
    public static void onPlayerAttached(View videoView) {
        try {
            // 1. Fill this view + all ancestors to MATCH_PARENT (so video fills screen)
            makeAncestorsMatchParent(videoView);

            // 2. Apply immersive + edge-to-edge window flags
            applyImmersiveWindow(videoView);

            // 3. Walk the view tree and make overlay bars transparent
            Activity activity = findActivity(videoView);
            if (activity != null) {
                View decor = activity.getWindow().getDecorView();
                makeBarsTransparent(decor);
            }

            // 4. Fullscreen button for horizontal videos
            ensureFullscreenButton(videoView);
        } catch (Throwable t) {
            // never crash the host
        }
    }

    // -----------------------------------------------------------------------
    // 1. Make ancestors MATCH_PARENT
    // -----------------------------------------------------------------------
    private static void makeAncestorsMatchParent(View view) {
        View v = view;
        while (v != null) {
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
                    if (changed) {
                        v.setLayoutParams(lp);
                    }
                }
                v.setFitsSystemWindows(false);
                v.setPadding(0, 0, 0, 0);
            } catch (Throwable t) {}
            // go up
            if (v.getParent() instanceof View) {
                v = (View) v.getParent();
            } else {
                v = null;
            }
        }
    }

    // -----------------------------------------------------------------------
    // 2. Immersive + edge-to-edge window
    // -----------------------------------------------------------------------
    private static void applyImmersiveWindow(View view) {
        try {
            Activity activity = findActivity(view);
            if (activity == null) return;
            Window window = activity.getWindow();
            if (window == null) return;

            // Set the immersive sticky flags on the decorView (hides status + nav bars)
            View decor = window.getDecorView();
            try {
                decor.setSystemUiVisibility(FLAG_IMMERSIVE);
            } catch (Throwable t) {}

            // Make the window lay out behind the system bars (no black gap)
            // FLAG_LAYOUT_NO_LIMITS (0x200) = window extends behind status + nav bars
            // FLAG_FULLSCREEN (0x400) = hide status bar
            // FLAG_LAYOUT_IN_SCREEN (0x100) = layout within screen bounds
            try {
                window.addFlags(WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                             | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN);
            } catch (Throwable t) {}

            // Also set status + nav bar color to transparent
            try {
                window.setStatusBarColor(Color.TRANSPARENT);
            } catch (Throwable t) {}
            try {
                window.setNavigationBarColor(Color.TRANSPARENT);
            } catch (Throwable t) {}
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // 3. Make overlay bars transparent
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
            // Skip the video view itself (don't make it transparent!)
            // The video view is a TextureView or contains a TextureView.
            // We detect it by checking for our tag or by class name.
            Object tag = view.getTag();
            if (TAG_FILLED.equals(tag)) return;  // already processed

            // Check if this view is a bar we want to make transparent
            String className = view.getClass().getSimpleName();
            boolean shouldTransparentize = false;

            // Check by class name
            if (TRANSPARENT_CLASS_NAMES.contains(className)) {
                shouldTransparentize = true;
            }
            // Check by id name (if it has a reel_viewer/clips id we recognize)
            try {
                int id = view.getId();
                if (id != View.NO_ID && id != 0) {
                    // We can't easily get the id name at runtime, but we can check
                    // for specific known bar view types
                }
            } catch (Throwable t) {}

            // Check if it's a "bar" — views with gradient/solid backgrounds that
            // are overlaying the video. We check for ColorDrawable or known bar patterns.
            if (!shouldTransparentize) {
                try {
                    Drawable bg = view.getBackground();
                    if (bg instanceof ColorDrawable) {
                        int color = ((ColorDrawable) bg).getColor();
                        int alpha = Color.alpha(color);
                        // If it's a solid (high-alpha) dark background, make it transparent
                        // (these are the opaque bars covering the video)
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

            // Recurse into children
            if (view instanceof ViewGroup) {
                ViewGroup vg = (ViewGroup) view;
                for (int i = 0; i < vg.getChildCount(); i++) {
                    walkAndTransparentize(vg.getChildAt(i), depth + 1);
                }
            }
        } catch (Throwable t) {}
    }

    // -----------------------------------------------------------------------
    // 4. Fullscreen toggle button for horizontal videos
    // -----------------------------------------------------------------------
    private static void ensureFullscreenButton(final View videoView) {
        final ViewGroup parent = (ViewGroup) videoView.getParent();
        if (parent == null) {
            videoView.post(new Runnable() {
                @Override public void run() { ensureFullscreenButton(videoView); }
            });
            return;
        }
        // Avoid double-adding
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

        // poll for video size to decide whether to show the button
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
                if (polls[0] < 20) {
                    videoView.postDelayed(this, 500);
                }
            }
        };
        videoView.postDelayed(poll, 600);
    }

    private static void toggleZoom(View videoView, View btn) {
        try {
            // Find the TextureView inside the video view (A02 field on LX/7ky)
            TextureView tv = findTextureView(videoView);
            if (tv == null) return;
            // Toggle between FIT_CENTER (show whole video, letterboxed) and
            // FIT_XY (stretch to fill). We use setTransform with a Matrix.
            android.graphics.Matrix m = tv.getTransform(new android.graphics.Matrix());
            float[] values = new float[9];
            m.getValues(values);
            float scaleX = values[android.graphics.Matrix.MSCALE_X];
            // If currently stretched (scaleX > 1.5), switch to fit; else stretch
            if (scaleX > 1.5f) {
                // Reset to identity (fit)
                tv.setTransform(new android.graphics.Matrix());
                btn.setAlpha(0.55f);
            } else {
                // Stretch: scale to fill (compute scale from video view to texture)
                float sx = (float) videoView.getWidth() / (float) tv.getWidth();
                float sy = (float) videoView.getHeight() / (float) tv.getHeight();
                android.graphics.Matrix stretch = new android.graphics.Matrix();
                stretch.setScale(sx, sy);
                tv.setTransform(stretch);
                btn.setAlpha(1f);
            }
        } catch (Throwable t) {}
    }

    private static android.view.TextureView findTextureView(View view) {
        if (view instanceof android.view.TextureView) {
            return (android.view.TextureView) view;
        }
        if (view instanceof ViewGroup) {
            ViewGroup vg = (ViewGroup) view;
            for (int i = 0; i < vg.getChildCount(); i++) {
                android.view.TextureView tv = findTextureView(vg.getChildAt(i));
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

    private static int[] getVideoSize(View videoView) {
        try {
            // For LX/7ky, the video size is in field A04 (C160765mH). Try reflection.
            Field fA04 = videoView.getClass().getDeclaredField("A04");
            fA04.setAccessible(true);
            Object mediaInfo = fA04.get(videoView);
            if (mediaInfo == null) return null;
            // C160765mH.A02() returns Double (aspect ratio)
            try {
                Method mA02 = mediaInfo.getClass().getDeclaredMethod("A02");
                Object aspect = mA02.invoke(mediaInfo);
                if (aspect instanceof Double) {
                    double ar = (Double) aspect;
                    if (ar > 0) {
                        // aspect = width / height. If > 1, it's horizontal.
                        return new int[]{ (int) (ar * 100), 100 };
                    }
                }
            } catch (Throwable t) {}
        } catch (Throwable t) {}
        return null;
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
