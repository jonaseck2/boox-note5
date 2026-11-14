package org.boox.einksettings;

import android.app.Activity;
import android.os.Bundle;
import android.preference.ListPreference;
import android.preference.Preference;
import android.preference.PreferenceCategory;
import android.preference.PreferenceFragment;
import android.preference.PreferenceScreen;
import android.preference.SwitchPreference;
import android.widget.Toast;

import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * The E-ink preference screen. The source of truth is the system properties that
 * device/epdcshim reads live on every loop or commit; nothing is stored in the app.
 * See docs/runbooks/eink-interface.md.
 */
public class EinkFragment extends PreferenceFragment implements Preference.OnPreferenceChangeListener {
    static final String LUT_ENABLE = "persist.boox.lut.enable";
    static final String LUT_BLACK = "persist.boox.lut.black";
    static final String LUT_WHITE = "persist.boox.lut.white";
    static final String CLEAN_MODE = "persist.boox.epdc.clean_mode";
    static final String CLEAN_AFTER = "persist.boox.epdc.clean_after";
    static final String LIST_MODE = "persist.boox.epdc.list_mode";
    static final String LUT_ADAPTIVE = "persist.boox.lut.adaptive";
    static final String LUT_BOLD = "persist.boox.lut.bold";

    /** Shim defaults (epdcshim.c prop_int fallbacks). */
    private static final Map<String, Integer> DEFAULTS = new LinkedHashMap<>();
    static {
        DEFAULTS.put(LUT_ENABLE, 1);
        DEFAULTS.put(LUT_BLACK, 40);
        DEFAULTS.put(LUT_WHITE, 235);
        DEFAULTS.put(CLEAN_MODE, 16);   // 0x10: full update, the only mode that cleans ghosting
        DEFAULTS.put(CLEAN_AFTER, 30);
        DEFAULTS.put(LIST_MODE, 2308);
        DEFAULTS.put(LUT_ADAPTIVE, 1);
        DEFAULTS.put(LUT_BOLD, 1);
    }

    /**
     * Interaction waveforms. ONLY these three: waveform-2 mode words panic the kernel.
     * Flash areas from the 2026-11-14 camera measurement in the runbook.
     */
    private static final String[] WF_VALUES = {"2308", "2305", "2307"};
    private static final String[] WF_NAMES = {
            "Waveform 4: least flash (default)",
            "Waveform 1",
            "Waveform 3: whitest whites, most flash"};

    private static final String[] BLACK_VALUES = {"0", "16", "24", "32", "40", "48", "56", "64", "80", "96"};
    private static final String[] WHITE_VALUES = {"160", "176", "192", "208", "224", "235", "245", "255"};
    private static final String CLEAN_OFF = "off";
    private static final String[] CLEAN_VALUES = {CLEAN_OFF, "10", "20", "30", "50", "100"};

    /** Minimum gap between black and white point, so the tone curve stays usable. */
    private static final int MIN_GAP = 64;

    private static final String REFRESH_SCRIPT =
            "cat /sys/class/sepdc/debug/panel_clean >/dev/null; sleep 1; "
            + "setprop sys.boox.epdc.force $(date +%s)";

    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final Map<String, Integer> current = new HashMap<>(DEFAULTS);

    private Preference status;
    private SwitchPreference lutEnable, adaptive, bold;
    private ListPreference black, white, clean, waveform;
    private Preference refresh, reset, update;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        Activity a = getActivity();
        PreferenceScreen s = getPreferenceManager().createPreferenceScreen(a);
        setPreferenceScreen(s);

        status = new Preference(a);
        status.setTitle("Root access");
        status.setSummary("Reading current values…");
        status.setSelectable(false);
        s.addPreference(status);

        PreferenceCategory contrast = category(s, "Contrast");
        lutEnable = new SwitchPreference(a);
        lutEnable.setKey(LUT_ENABLE);
        lutEnable.setTitle("Contrast curve");
        lutEnable.setSummaryOn("Greys are stretched between the black and white points");
        lutEnable.setSummaryOff("Off: the panel shows the original greys");
        add(contrast, lutEnable);
        adaptive = new SwitchPreference(a);
        adaptive.setKey(LUT_ADAPTIVE);
        adaptive.setTitle("Photo-aware contrast");
        adaptive.setSummaryOn("Photos get a gentler curve, text and UI the strong one");
        adaptive.setSummaryOff("One curve for everything");
        add(contrast, adaptive);
        bold = new SwitchPreference(a);
        bold.setKey(LUT_BOLD);
        bold.setTitle("Bolder text in all apps");
        bold.setSummaryOn("Thin strokes are thickened by one pixel, also in web pages");
        bold.setSummaryOff("Text as the app draws it");
        add(contrast, bold);
        black = list(contrast, LUT_BLACK, "Black point",
                "Greys at or below this level show as black. Higher = darker text.",
                BLACK_VALUES, BLACK_VALUES);
        white = list(contrast, LUT_WHITE, "White point",
                "Greys at or above this level show as white. Lower = whiter backgrounds.",
                WHITE_VALUES, WHITE_VALUES);

        PreferenceCategory refreshCat = category(s, "Refresh");
        waveform = list(refreshCat, LIST_MODE, "Waveform for interaction", null, WF_NAMES, WF_VALUES);
        String[] cleanNames = new String[CLEAN_VALUES.length];
        for (int i = 0; i < CLEAN_VALUES.length; i++) {
            cleanNames[i] = CLEAN_OFF.equals(CLEAN_VALUES[i]) ? "Off" : "After " + CLEAN_VALUES[i] + " updates";
        }
        clean = list(refreshCat, CLEAN_AFTER, "Ghosting clean",
                "One deliberate full flash after this many fast updates, once the screen is idle",
                cleanNames, CLEAN_VALUES);

        refresh = new Preference(a);
        refresh.setTitle("Refresh screen now");
        refresh.setSummary("Full-panel flash that removes all ghosting");
        refresh.setOnPreferenceClickListener(p -> {
            runRoot(REFRESH_SCRIPT, "Screen refreshed");
            return true;
        });
        add(refreshCat, refresh);

        reset = new Preference(a);
        reset.setTitle("Reset to defaults");
        reset.setSummary("Black 40, white 235, photo-aware, bold, waveform 4, clean after 30");
        reset.setOnPreferenceClickListener(p -> {
            write(DEFAULTS, "Defaults restored");
            return true;
        });
        add(refreshCat, reset);

        PreferenceCategory upd = category(s, "Updates");
        update = new Preference(a);
        update.setTitle("Check for updates");
        update.setSummary("Display shim and module from github.com/jonaseck2/boox-note5 releases");
        update.setOnPreferenceClickListener(p -> {
            checkUpdate();
            return true;
        });
        add(upd, update);

        setControlsEnabled(false);
        load();
    }

    @Override
    public void onDestroy() {
        io.shutdownNow();
        super.onDestroy();
    }

    // ---- building -------------------------------------------------------------------------

    private PreferenceCategory category(PreferenceScreen s, String title) {
        PreferenceCategory c = new PreferenceCategory(getActivity());
        c.setTitle(title);
        s.addPreference(c);
        return c;
    }

    private void add(PreferenceCategory c, Preference p) {
        p.setPersistent(false);
        c.addPreference(p);
        if (p.getKey() != null) p.setOnPreferenceChangeListener(this);
    }

    private ListPreference list(PreferenceCategory c, String key, String title, String hint,
                                String[] names, String[] values) {
        ListPreference p = new ListPreference(getActivity());
        p.setKey(key);
        p.setTitle(title);
        p.setDialogTitle(title);
        p.setEntries(names);
        p.setEntryValues(values);
        p.getExtras().putString("hint", hint);
        add(c, p);
        return p;
    }

    private void setControlsEnabled(boolean on) {
        for (Preference p : new Preference[]{lutEnable, adaptive, bold, black, white, clean, waveform, refresh, reset, update}) {
            p.setEnabled(on);
        }
    }

    // ---- reading --------------------------------------------------------------------------

    private void load() {
        StringBuilder sh = new StringBuilder();
        for (String k : DEFAULTS.keySet()) sh.append("echo \"").append(k).append("=$(getprop ").append(k).append(")\"\n");
        io.execute(() -> {
            Root.Result r = Root.run(sh.toString());
            Map<String, Integer> got = new HashMap<>();
            if (r.ok()) {
                for (String line : r.out.split("\n")) {
                    int eq = line.indexOf('=');
                    if (eq <= 0) continue;
                    String k = line.substring(0, eq).trim();
                    if (!DEFAULTS.containsKey(k)) continue;
                    try {
                        got.put(k, Integer.parseInt(line.substring(eq + 1).trim()));
                    } catch (NumberFormatException e) {
                        // unset prop: the shim uses its default, so do we
                    }
                }
            }
            ui(() -> {
                if (!r.ok()) {
                    status.setSummary("Not granted. Allow \"E-ink\" in Magisk > Superuser, then reopen. ("
                            + r.out.trim() + ")");
                    return;
                }
                current.putAll(DEFAULTS);
                current.putAll(got);
                status.setSummary("Granted. Changes apply immediately.");
                show();
                setControlsEnabled(true);
            });
        });
    }

    private void show() {
        lutEnable.setChecked(current.get(LUT_ENABLE) != 0);
        adaptive.setChecked(current.get(LUT_ADAPTIVE) != 0);
        bold.setChecked(current.get(LUT_BOLD) != 0);
        showList(black, current.get(LUT_BLACK));
        showList(white, current.get(LUT_WHITE));
        if (current.get(CLEAN_MODE) == 0) {
            clean.setValue(CLEAN_OFF);
            clean.setSummary("Off");
        } else {
            showList(clean, current.get(CLEAN_AFTER));
        }
        int wf = current.get(LIST_MODE);
        int i = Arrays.asList(WF_VALUES).indexOf(String.valueOf(wf));
        if (i >= 0) {
            waveform.setValue(WF_VALUES[i]);
            waveform.setSummary(WF_NAMES[i]);
        } else {
            // Show an unexpected value, but never offer it as a choice.
            waveform.setValue(null);
            waveform.setSummary("Current value " + wf + " is not one of the supported waveforms");
        }
    }

    /** Selects v; a value outside the list (set from adb) is added so it stays visible. */
    private void showList(ListPreference p, int v) {
        String s = String.valueOf(v);
        if (p.findIndexOfValue(s) < 0) {
            CharSequence[] e = p.getEntries(), ev = p.getEntryValues();
            CharSequence[] e2 = Arrays.copyOf(e, e.length + 1), ev2 = Arrays.copyOf(ev, ev.length + 1);
            e2[e.length] = p == clean ? "After " + s + " updates" : s;
            ev2[ev.length] = s;
            p.setEntries(e2);
            p.setEntryValues(ev2);
        }
        p.setValue(s);
        String hint = p.getExtras().getString("hint");
        CharSequence name = p.getEntries()[p.findIndexOfValue(s)];
        p.setSummary(hint == null ? name : name + ". " + hint);
    }

    // ---- writing --------------------------------------------------------------------------

    @Override
    public boolean onPreferenceChange(Preference p, Object nv) {
        Map<String, Integer> w = new LinkedHashMap<>();
        String key = p.getKey();
        if (p == lutEnable || p == adaptive || p == bold) {
            w.put(key, Boolean.TRUE.equals(nv) ? 1 : 0);
        } else if (p == clean) {
            if (CLEAN_OFF.equals(nv)) {
                // clean_mode=0 disables the clean. clean_after=0 does NOT: the shim then
                // cleans on every idle tick (u_n >= 0 is always true).
                w.put(CLEAN_MODE, 0);
            } else {
                int n = parse(nv);
                if (n < 1) return false;
                w.put(CLEAN_AFTER, n);
                w.put(CLEAN_MODE, DEFAULTS.get(CLEAN_MODE));
            }
        } else {
            int v = parse(nv);
            if (v < 0) return false;
            int bl = key.equals(LUT_BLACK) ? v : current.get(LUT_BLACK);
            int wh = key.equals(LUT_WHITE) ? v : current.get(LUT_WHITE);
            if (wh - bl < MIN_GAP) {
                toast("White point must be at least " + MIN_GAP + " above black point");
                return false;
            }
            w.put(key, v);
        }
        write(w, null);
        return false;   // the UI updates from current after the root write succeeds
    }

    private static int parse(Object o) {
        try {
            return Integer.parseInt(String.valueOf(o));
        } catch (NumberFormatException e) {
            return -1;
        }
    }

    /** Single choke point for every setprop. Rejects keys and waveform values outside the allowlist. */
    private void write(Map<String, Integer> w, String done) {
        StringBuilder sh = new StringBuilder("set -e\n");
        for (Map.Entry<String, Integer> e : w.entrySet()) {
            String k = e.getKey();
            int v = e.getValue();
            if (!DEFAULTS.containsKey(k)) throw new IllegalArgumentException(k);
            if (k.equals(LIST_MODE) && Arrays.asList(WF_VALUES).indexOf(String.valueOf(v)) < 0) {
                throw new IllegalArgumentException("waveform " + v);
            }
            if (v < 0 || v > 4096) throw new IllegalArgumentException(k + "=" + v);
            sh.append("setprop ").append(k).append(' ').append(v).append('\n');
        }
        io.execute(() -> {
            Root.Result r = Root.run(sh.toString());
            ui(() -> {
                if (!r.ok()) {
                    toast("Failed: " + r.out.trim());
                    return;
                }
                current.putAll(w);
                show();
                if (done != null) toast(done);
            });
        });
    }

    private void checkUpdate() {
        update.setEnabled(false);
        update.setSummary("Checking…");
        io.execute(() -> {
            String msg;
            boolean restart = false;
            try {
                long have = Updater.installedCode();
                Updater.Release rel = Updater.latest();
                if (rel == null) {
                    msg = "No glue release found";
                } else if (Updater.code(rel.version) <= have) {
                    msg = "Up to date (" + rel.version + ")";
                } else {
                    msg = Updater.install(rel, getActivity().getCacheDir());
                    restart = true;
                }
            } catch (Exception e) {
                msg = "Update failed: " + e.getMessage();
            }
            final String m = msg;
            final boolean r = restart;
            ui(() -> {
                update.setEnabled(true);
                update.setSummary(m);
                if (r) {
                    new android.app.AlertDialog.Builder(getActivity())
                            .setTitle("Restart now?")
                            .setMessage(m + " The display shim loads at boot.")
                            .setPositiveButton("Restart", (d, w) -> runRoot("svc power reboot || reboot", "Restarting"))
                            .setNegativeButton("Later", null)
                            .show();
                }
            });
        });
    }

    private void runRoot(String script, String done) {
        io.execute(() -> {
            Root.Result r = Root.run(script);
            ui(() -> toast(r.ok() ? done : "Failed: " + r.out.trim()));
        });
    }

    private void ui(Runnable r) {
        Activity a = getActivity();
        if (a == null) return;
        a.runOnUiThread(() -> {
            if (isAdded()) r.run();
        });
    }

    private void toast(String s) {
        Activity a = getActivity();
        if (a != null) Toast.makeText(a, s, Toast.LENGTH_SHORT).show();
    }
}
