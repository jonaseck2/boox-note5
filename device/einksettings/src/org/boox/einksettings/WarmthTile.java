package org.boox.einksettings;

import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

/** Quick Settings tile: each tap steps the front-light warmth through Light.STEPS. */
public class WarmthTile extends TileService {
    @Override
    public void onStartListening() {
        new Thread(() -> show(Light.read())).start();
    }

    @Override
    public void onClick() {
        new Thread(() -> {
            int v = Light.next(Light.read());
            if (Light.write(v).ok()) show(v);
        }).start();
    }

    private void show(int v) {
        Tile t = getQsTile();
        if (t == null) return;
        t.setLabel("Light warmth");
        t.setSubtitle(Light.label(v));
        t.setState(v > 0 ? Tile.STATE_ACTIVE : Tile.STATE_INACTIVE);
        t.updateTile();
    }
}
