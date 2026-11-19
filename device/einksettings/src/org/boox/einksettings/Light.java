package org.boox.einksettings;

/**
 * Front-light warmth. device/epdcshim/module/service.sh applies persist.boox.light.warmth to
 * /sys/class/backlight/onyx_bl_ct (0 = cold .. 24 = warm) every 2 s, and Night Light can only raise it.
 * The root script also writes the sysfs node, so a change shows at once. Background thread only.
 */
final class Light {
    static final String WARMTH = "persist.boox.light.warmth";
    static final int MAX = 24;
    /** Quick Settings tile steps. */
    static final int[] STEPS = {0, 8, 16, 24};

    private Light() {}

    static int read() {
        Root.Result r = Root.run("getprop " + WARMTH);
        try {
            return clamp(Integer.parseInt(r.out.trim()));
        } catch (NumberFormatException e) {
            return 0;   // unset: cold, as service.sh treats it
        }
    }

    static Root.Result write(int v) {
        v = clamp(v);
        return Root.run("set -e\nsetprop " + WARMTH + " " + v
                + "\necho " + v + " > /sys/class/backlight/onyx_bl_ct/brightness");
    }

    static int next(int v) {
        for (int s : STEPS) if (s > v) return s;
        return STEPS[0];
    }

    static String label(int v) {
        return v == 0 ? "Cold" : v >= MAX ? "Warmest" : "Warm " + v + "/" + MAX;
    }

    static int clamp(int v) {
        return Math.max(0, Math.min(MAX, v));
    }
}
