package app.truereels;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ImageView;
import java.lang.reflect.Method;
import java.lang.reflect.Field;

/**
 * InstaPatchedTrueReel runtime helper (v5).
 *
 * v5 is a COMPLETE SIMPLIFICATION based on v4 user feedback:
 *   - v4 caused flickering on home feed scroll, comment open, and some 16:9 reels.
 *   - Root cause: LX/7ky (AbstractC210917ky) is the base class for ALL IG video
 *     surfaces (feed, stories, reels, ads). v4 ran setSystemUiVisibility +
 *     makeBarsTransparent on EVERY video attach, breaking the home feed.
 *   - v5 ONLY acts when inside the reels context (detected by finding a
 *     TouchInterceptorFrameLayout ancestor, which is reels-specific).
 *
 * What v5 does (ONLY in reels context):
 *   1. setSystemUiVisibility(0x16ff) — hide status + nav bar (immersive sticky).
 *      This is what makes the video reach the top edge (confirmed working in v4).
 *   2. Fullscreen toggle button for horizontal (16:9) videos — toggles between
 *      STRETCH (fill screen, distorted) and FIT (correct ratio, letterboxed).
 *
 * What v5 does NOT do (removed from v4):
 *   - NO makeBarsTransparent (caused home feed flicker — walked entire decorView)
 *   - NO makeReelsRootOpaque (caused black bottom — BLACK showed through transparent bars)
 *   - NO makeAncestorsMatchParent (may cause layout conflicts / flicker on scroll)
 *   - NO applyImmersiveWindow / FLAG_LAYOUT_NO_LIMITS (caused v3 flicker)
 *
 * The smali onSizeChanged patch (TextureView MATCH_PARENT) still applies to all
 * video surfaces, but that's safe — it just makes the video fill its container,
 * which is the correct behavior everywhere.
 */
public class TrueReelsHelper {

    // 0x16ff = FULLSCREEN | HIDE_NAV | LAYOUT_STABLE | LAYOUT_FULLSCREEN |
    //          LAYOUT_HIDE_NAV | IMMERSIVE_STICKY
    private static final int FLAG_IMMERSIVE = 0x1 | 0x2 | 0x100 | 0x200 | 0x400 | 0x1000;

    private static final String TAG_BTN = "truereels_fs_btn";

    /**
     * Called from LX/7ky.onAttachedToWindow (smali-injected).
     * Runs on EVERY video surface attach (feed, stories, reels, ads).
     * MUST check isInReelsContext() before doing anything, to avoid breaking
     * the home feed and other surfaces.
     */
    public static void onPlayerAttached(View videoView) {
        try {
            // CRITICAL: Only act in the reels context. If this is a feed video,
            // story, ad, etc., do NOTHING — don't hide system bars, don't add
            // buttons, don't touch the view tree.
            if (!isInReelsContext(videoView)) {
                return;
            }

            // 1. Hide status + nav bar (immersive sticky). This makes the video
            //    reach the top edge of the screen (confirmed working in v3/v4).
            try {
                videoView.setSystemUiVisibility(FLAG_IMMERSIVE);
            } catch (Throwable t) {}

            // 2. Fullscreen toggle button for horizontal (16:9) videos.
            ensureFullscreenButton(videoView);
        } catch (Throwable t) {
            // never crash the host
        }
    }

    // -----------------------------------------------------------------------
    // Reels context detection
    // -----------------------------------------------------------------------
    /**
     * Check if this video view is inside the reels viewer by walking up the
     * ancestor chain looking for TouchInterceptorFrameLayout (the reels root,
     * reel_viewer_root) or ReelViewGroup. If neither is found within 15 hops,
     * this is NOT reels (it's feed, stories, ads, etc.) → return false.
     */
    private static boolean isInReelsContext(View view) {
        View v = view;
        int hops = 0;
        while (v != null && hops < 15) {
            hops++;
            String className = v.getClass().getSimpleName();
            if ("TouchInterceptorFrameLayout".equals(className)) {
                return true; // reels root found
            }
            if ("ReelViewGroup".equals(className)) {
                return true; // reels view group found
            }
            if (v.getParent() instanceof View) {
                v = (View) v.getParent();
            } else {
                break;
            }
        }
        return false; // not in reels
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

    /**
     * Toggle between STRETCH (fill screen, distorted) and FIT (correct ratio,
     * letterboxed with black bars). Uses setScaleY on the TextureView —
     * in STRETCH mode scaleY=1 (video fills screen). In FIT mode scaleY<1
     * (video is compressed vertically to show at correct aspect ratio).
     */
    private static void toggleZoom(View videoView, View btn) {
        try {
            TextureView tv = findTextureView(videoView);
            if (tv == null) return;

            int[] wh = getVideoSize(videoView);
            if (wh == null || wh[0] <= 0 || wh[1] <= 0) return;

            float videoAspect = (float) wh[0] / (float) wh[1]; // >1 for horizontal
            float currentScaleY = tv.getScaleY();

            if (Math.abs(currentScaleY - 1.0f) < 0.01f) {
                // Currently STRETCH (scaleY=1) → switch to FIT
                // Scale Y so the video shows at its correct aspect ratio.
                // For a 16:9 video on a 9:16 screen:
                //   screenAspect = screenWidth / screenHeight (e.g. 0.45)
                //   videoAspect = 16/9 = 1.78
                //   fitScaleY = screenAspect / videoAspect = 0.45 / 1.78 = 0.253
                // This makes the video height = screenHeight * 0.253 = correct 16:9 ratio
                float screenAspect = (float) videoView.getWidth() / (float) videoView.getHeight();
                float fitScaleY = screenAspect / videoAspect;
                // Clamp to reasonable range
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
     * Walks the superclass chain to find inherited field A04 (declared in
     * AbstractC210917ky, the parent of the runtime SimpleVideoLayout class).
     * Reads the cached public Double A03 field on C160765mH first (instant),
     * then falls back to A02() method.
     * Returns int[]{width, height} proportional (aspect*100, 100).
     * Caller checks wh[0] > wh[1] for horizontal detection.
     */
    private static int[] getVideoSize(View videoView) {
        try {
            // 1) Walk up the class hierarchy to find field A04.
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

            // 4) Last resort: A03(Context, boolean).
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
