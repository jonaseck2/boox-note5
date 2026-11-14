#!/bin/sh
# Android settings for the e-ink panel (all camera- or owner-verified on 2026-11-14, see
# docs/runbooks/eink-interface.md). Idempotent. Usage: device/eink-settings.sh [serial]
set -eu
S=${1:-${BOOX_SERIAL:-$(head -n1 ~/.config/boox/serial 2>/dev/null)}}; [ -n "$S" ] || { echo "set BOOX_SERIAL or write the serial to ~/.config/boox/serial" >&2; exit 1; }
export ADB_LIBUSB=1
adb -s "$S" shell '
cmd uimode night no                                         # light theme: dark UI is low-contrast on e-ink
settings put global window_animation_scale 0                # animation frames leave ghost traces
settings put global transition_animation_scale 0
settings put global animator_duration_scale 0
settings put secure font_weight_adjustment 300              # Bold text: thin Material strokes vanish on e-ink
settings put secure high_text_contrast_enabled 0            # its white text halos show as grey patches
settings put global stay_on_while_plugged_in 7
settings put secure contrast_level 1.0                      # Color contrast: High (system palette)
settings put secure theme_customization_overlay_packages \'{"android.theme.customization.color_source":"preset","android.theme.customization.theme_style":"MONOCHROMATIC","android.theme.customization.system_palette":"FF808080","android.theme.customization.accent_color":"FF808080","android.theme.customization.color_both":"1"}\'
                                                            # monochrome palette: accents become greys
content insert --uri content://lineagesettings/system --bind name:s:double_tap_sleep_gesture --bind value:s:0
                                                            # slow e-ink taps on the status bar slept the display
echo done
'
# Plain white wallpaper (owner: the grey default was hard to read and ghosted). No API for this from
# adb: write the image files as root, drop the stale colour hints, reboot to apply.
if [ "${WALLPAPER:-0}" = 1 ]; then
  W=$(mktemp -d)/white.png
  python3 -c "import zlib,struct;w,h=1872,1404;raw=b''.join(b'\\x00'+b'\\xff'*3*w for _ in range(h));c=lambda t,d:struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d));open('$W','wb').write(b'\\x89PNG\\r\\n\\x1a\\n'+c(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+c(b'IDAT',zlib.compress(raw,9))+c(b'IEND',b''))"
  adb -s "$S" push "$W" /data/local/tmp/white.png >/dev/null
  adb -s "$S" shell '/debug_ramdisk/su -c "for f in wallpaper wallpaper_orig wallpaper_lock wallpaper_lock_orig; do cp /data/local/tmp/white.png /data/system/users/0/\$f; chown system:system /data/system/users/0/\$f; chmod 600 /data/system/users/0/\$f; done; restorecon /data/system/users/0/wallpaper*; rm -f /data/system/users/0/wallpaper_info.xml"'
  echo "white wallpaper installed: reboot to apply"
fi
