package org.boox.einksettings;

import android.content.Context;
import android.preference.Preference;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.SeekBar;

/** A slider row for the front-light warmth. The public SDK has no SeekBarPreference. */
final class WarmthPreference extends Preference {
    interface Listener { void onWarmth(int v); }

    private final Listener listener;
    private int value;

    WarmthPreference(Context c, Listener l) {
        super(c);
        listener = l;
        setPersistent(false);
        setSelectable(false);
    }

    void setValue(int v) {
        value = Light.clamp(v);
        setSummary(Light.label(value) + ". Night Light can make it warmer on its schedule.");
        notifyChanged();
    }

    @Override
    protected View onCreateView(ViewGroup parent) {
        View row = super.onCreateView(parent);
        LinearLayout box = new LinearLayout(getContext());
        box.setOrientation(LinearLayout.VERTICAL);
        box.addView(row);
        SeekBar bar = new SeekBar(getContext());
        bar.setId(android.R.id.progress);
        bar.setMax(Light.MAX);
        int pad = (int) (16 * getContext().getResources().getDisplayMetrics().density);
        bar.setPadding(pad * 2, 0, pad * 2, pad);
        box.addView(bar, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        return box;
    }

    @Override
    protected void onBindView(View view) {
        super.onBindView(view);
        SeekBar bar = view.findViewById(android.R.id.progress);
        bar.setEnabled(isEnabled());
        bar.setOnSeekBarChangeListener(null);
        bar.setProgress(value);
        bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int p, boolean user) {
                if (user) setSummary(Light.label(p));
            }
            @Override public void onStartTrackingTouch(SeekBar s) {}
            @Override public void onStopTrackingTouch(SeekBar s) {
                listener.onWarmth(s.getProgress());   // one root write per drag, not per step
            }
        });
    }
}
