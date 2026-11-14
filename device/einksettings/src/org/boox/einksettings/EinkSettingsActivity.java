package org.boox.einksettings;

import android.app.ActionBar;
import android.app.Activity;
import android.os.Bundle;

/** Host for the preference screen. Settings launches it from the tile in Display. */
public class EinkSettingsActivity extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        ActionBar bar = getActionBar();
        if (bar != null) bar.setDisplayHomeAsUpEnabled(true);
        if (state == null) {
            getFragmentManager().beginTransaction()
                    .replace(android.R.id.content, new EinkFragment())
                    .commit();
        }
    }

    @Override
    public boolean onNavigateUp() {
        finish();
        return true;
    }
}
