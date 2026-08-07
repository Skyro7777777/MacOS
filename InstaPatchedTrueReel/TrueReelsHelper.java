package app.truereels;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
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

/**
 * InstaPatchedTrueReel runtime helper.
 *
 * Called from a patched hook in media3 PlayerView.onAttachedToWindow().
 * Responsibilities:
 *   1. Ensure the PlayerView fills its parent (MATCH_PARENT) so the video
 *      stretches edge-to-edge BEHIND the overlay bars (TikTok-style).
 *   2. Apply immersive sticky system-UI flags so the video reaches the
 *      physical status bar + nav bar.
 *   3. Detect horizontal (16:9-ish) videos and show a TikTok-style
 *      "fullscreen" toggle button that switches the reels frame between
 *      RESIZE_MODE_FILL (stretch) and RESIZE_MODE_ZOOM (crop-to-fill).
 *
 * Everything is best-effort and wrapped in try/catch so a failure here
 * never crashes Instagram. media3 classes are accessed via reflection
 * because IG shades them under fb/androidx/media3/.
 */
public class TrueReelsHelper {

    private static final int RESIZE_MODE_FILL = 3;  // stretch (distort) to fill
    private static final int RESIZE_MODE_ZOOM = 4;  // crop to fill

    private static final int FLAG_IMMERSIVE = 0x1 | 0x2 | 0x100 | 0x200 | 0x400 | 0x1000; // 0x16ff

    /** Called from PlayerView.onAttachedToWindow (smali-injected). */
    public static void onPlayerAttached(View playerView) {
        try {
            // 1. fill parent
            ViewGroup.LayoutParams lp = playerView.getLayoutParams();
            if (lp != null) {
                lp.width = ViewGroup.LayoutParams.MATCH_PARENT;
                lp.height = ViewGroup.LayoutParams.MATCH_PARENT;
                playerView.setLayoutParams(lp);
            }
            playerView.setFitsSystemWindows(false);

            // 2. immersive on the view's window
            try {
                playerView.setSystemUiVisibility(FLAG_IMMERSIVE);
            } catch (Throwable t) {}

            // 3. fullscreen button for horizontal videos
            ensureFullscreenButton(playerView);
        } catch (Throwable t) {
            // never crash the host
        }
    }

    // -----------------------------------------------------------------------
    // Fullscreen toggle button for horizontal videos
    // -----------------------------------------------------------------------
    private static void ensureFullscreenButton(final View playerView) {
        final ViewGroup parent = (ViewGroup) playerView.getParent();
        if (parent == null) {
            playerView.post(new Runnable() {
                @Override public void run() { ensureFullscreenButton(playerView); }
            });
            return;
        }
        // Avoid double-adding: look for an existing button tagged "truereels_fs_btn"
        for (int i = 0; i < parent.getChildCount(); i++) {
            Object t = parent.getChildAt(i).getTag();
            if ("truereels_fs_btn".equals(t)) return;
        }

        final View btn = makeButton(playerView.getContext());
        btn.setTag("truereels_fs_btn");
        final FrameLayout.LayoutParams flp = new FrameLayout.LayoutParams(
                dp(playerView, 40), dp(playerView, 40),
                Gravity.TOP | Gravity.END);
        flp.topMargin = dp(playerView, 56);
        flp.rightMargin = dp(playerView, 12);
        try {
            if (parent instanceof FrameLayout) {
                parent.addView(btn, flp);
            } else {
                return; // not an overlay-capable parent; skip
            }
        } catch (Throwable t) { return; }
        btn.setVisibility(View.GONE); // hidden until a horizontal video is detected

        btn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                toggleZoom(playerView, btn);
            }
        });

        // poll for video size to decide whether to show the button
        final int[] polls = {0};
        final Runnable poll = new Runnable() {
            @Override public void run() {
                polls[0]++;
                int[] wh = getVideoSize(playerView);
                if (wh != null && wh[0] > 0 && wh[1] > 0) {
                    if (wh[0] > wh[1]) {
                        // horizontal video -> show fullscreen button
                        btn.setVisibility(View.VISIBLE);
                    } else {
                        btn.setVisibility(View.GONE);
                    }
                    return;
                }
                if (polls[0] < 20) {
                    playerView.postDelayed(this, 500);
                }
            }
        };
        playerView.postDelayed(poll, 600);
    }

    private static void toggleZoom(View playerView, View btn) {
        try {
            Object arfl = findAspectRatioFrameLayout(playerView);
            if (arfl == null) return;
            Class<?> cls = arfl.getClass();
            // read current resizeMode
            int cur = RESIZE_MODE_FILL;
            try {
                Method g = cls.getMethod("getResizeMode");
                cur = (Integer) g.invoke(arfl);
            } catch (Throwable t) {}
            int next = (cur == RESIZE_MODE_ZOOM) ? RESIZE_MODE_FILL : RESIZE_MODE_ZOOM;
            try {
                Method s = cls.getMethod("setResizeMode", int.class);
                s.invoke(arfl, next);
            } catch (Throwable t) {}
            // update button look
            btn.setAlpha(next == RESIZE_MODE_ZOOM ? 1f : 0.55f);
        } catch (Throwable t) {}
    }

    private static Object findAspectRatioFrameLayout(View playerView) {
        // PlayerView contains an internal AspectRatioFrameLayout (the content frame).
        // Find it by class name, or via getContentFrame() reflection.
        try {
            Method g = playerView.getClass().getMethod("getContentFrame");
            Object f = g.invoke(playerView);
            if (f != null) return f;
        } catch (Throwable t) {}
        // fallback: walk children
        if (playerView instanceof ViewGroup) {
            ViewGroup g = (ViewGroup) playerView;
            for (int i = 0; i < g.getChildCount(); i++) {
                View c = g.getChildAt(i);
                if (c.getClass().getName().contains("AspectRatioFrameLayout")) return c;
            }
        }
        return null;
    }

    private static int[] getVideoSize(View playerView) {
        try {
            Method gp = playerView.getClass().getMethod("getPlayer");
            Object player = gp.invoke(playerView);
            if (player == null) return null;
            Method gvs = player.getClass().getMethod("getVideoSize");
            Object vs = gvs.invoke(player);
            if (vs == null) return null;
            Field wf = vs.getClass().getField("width");
            Field hf = vs.getClass().getField("height");
            return new int[]{ wf.getInt(vs), hf.getInt(vs) };
        } catch (Throwable t) {
            return null;
        }
    }

    // -----------------------------------------------------------------------
    private static View makeButton(Context ctx) {
        ImageView b = new ImageView(ctx);
        b.setImageResource(android.R.drawable.ic_menu_crop);  // built-in crop icon
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
