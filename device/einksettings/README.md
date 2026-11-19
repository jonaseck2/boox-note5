# E-ink Settings

An "E-ink" entry in **Settings > Display** on the Boox Note5 (LineageOS 23.2, Android 16 GSI).
The screen sets the properties that `device/epdcshim` reads live. Pipeline details:
[docs/runbooks/eink-interface.md](../../docs/runbooks/eink-interface.md).

| Control | Property | Values |
|---|---|---|
| Contrast curve | `persist.boox.lut.enable` | 1 / 0 |
| Black point | `persist.boox.lut.black` | 0–96, default 40 |
| White point | `persist.boox.lut.white` | 160–255, default 235. Must be at least 64 above black. |
| Waveform for interaction | `persist.boox.epdc.list_mode` | 2308 (wf4, default), 2305 (wf1), 2307 (wf3). No other value. Waveform-2 mode words panic the kernel. |
| Ghosting clean | `persist.boox.epdc.clean_after`, `persist.boox.epdc.clean_mode` | Off = `clean_mode=0`. A count N = `clean_after=N`, `clean_mode=16`. |
| Refresh screen now | — | `cat /sys/class/sepdc/debug/panel_clean`, then bumps `sys.boox.epdc.force` |
| Reset to defaults | all of the above | shim defaults |
| Light warmth (slider) | `persist.boox.light.warmth` | 0 (cold) – 24 (warmest), default 0. Not touched by Reset. `service.sh` applies it to `onyx_bl_ct` every 2 s. Night Light can only raise it. |

**Quick Settings tile "Light warmth"** (`WarmthTile`): each tap steps the warmth 0 → 8 → 16 → 24 → 0. Add it from the
Quick Settings editor (pencil icon). SystemUI destroys a custom tile whose service has no manifest icon, so the app ships one
resource, `res/drawable/ic_warmth.xml`.

"Off" for the ghosting clean writes `clean_mode=0`, never `clean_after=0`. With `clean_after=0` the shim's
test `u_n >= clean_after` is always true, so it would send a clean on every idle tick.

## Build (macOS)

```sh
device/einksettings/build.sh
```

Output: `device/einksettings/build/EinkSettings.apk`. The script uses aapt2, javac, d8, zipalign and apksigner, with no Gradle and no
libraries beyond the framework.

- On first run it downloads build-tools 36.1 and platform 36 into `~/boox-backups/tools/android-sdk`. It checks each zip's SHA-1
  against Google's repository index.
- It needs a JDK. The default is `/opt/homebrew/opt/openjdk`. Set `JAVA_HOME` to use another one.
- The signing key is `~/boox-backups/tools/einksettings.keystore`. The script creates it on first run. Keep it: an update signed
  with a different key fails to install over the old one.

## Install (controller, on the device)

1. Build the APK: `device/einksettings/build.sh`.
2. Stage it into the Magisk module: `device/einksettings/install.sh`.
   The script writes `/data/adb/modules/boox_einksettings/system/app/EinkSettings/EinkSettings.apk`, labels it `system_file` and
   prints the tree.
3. Reboot the device: `adb -s $BOOX_SERIAL reboot`.
4. Pre-grant root to the app: `device/einksettings/install.sh grant`.
   The output shows one row for the app uid with policy `2`.
   NOTE: Without this step, Magisk shows a grant prompt the first time the screen opens. Tapping "Grant" has the same effect.
5. Check the install:
   - `adb shell pm path org.boox.einksettings` prints `package:/system/app/EinkSettings/EinkSettings.apk`.
   - `adb shell dumpsys package org.boox.einksettings | grep -m1 flags=` shows `SYSTEM`.
6. Open Settings > Display. The list contains "E-ink". Open it. The first row reads "Root access: Granted".
7. Set the black point to 96. The text on screen gets darker within one frame. Tap "Reset to defaults".

To remove the app: `su -c touch /data/adb/modules/boox_einksettings/remove`, then reboot.

## How the Settings injection works

- Settings builds its injected tiles in SettingsLib `TileUtils.getCategories()`. Source checked:
  `frameworks/base/packages/SettingsLib/Tile/src/com/android/settingslib/drawer/TileUtils.java`, branch `android16-release`.
- It queries activities for the action `com.android.settings.action.IA_SETTINGS` (and `EXTRA_SETTINGS`), with meta-data.
  It does this only when `Settings.Global.DEVICE_PROVISIONED` is 1.
- `loadActivityTiles()` skips every result with `ResolveInfo.system == false`. An app installed with `adb install` therefore
  never shows. The app must live in a system partition, which is why the Magisk module overlays it into `/system/app`.
  A privileged location (`/system/priv-app`) or the platform key is not needed.
- `com.android.settings.category` selects the parent page. `com.android.settings.category.ia.display` maps to `DisplaySettings`
  (`DashboardFragmentRegistry`). Use `com.android.settings.category.ia.homepage` for a top-level entry. A homepage tile also
  needs an icon (`com.android.settings.icon`).
- `com.android.settings.title`, `com.android.settings.summary` and `com.android.settings.order` set the row text and position.
- Settings caches tiles. A newly installed tile appears after Settings restarts. A reboot also does it.

## Why root goes through Magisk su

- The `persist.boox.*` properties have no entry in AOSP `property_contexts`, so they get the SELinux type `default_prop`
  (not checked on the device: `getprop -Z persist.boox.lut.black`).
  App domains (`untrusted_app`, `priv_app`, `system_app`) cannot set `default_prop`.
- The platform key of the GSI is not available, so the app cannot run as `system_app` in any case.
- The app therefore runs each change as a short script through `/debug_ramdisk/su` (fallback: `su` on `PATH`).
  Every `setprop` goes through one method that accepts only the six known keys and only the three waveform values.
