#!/bin/sh
# Install the Magisk module boox_wifionly: one permissions XML that marks the telephony
# sub-features unavailable (Wi-Fi-only tablet). Takes effect after a reboot.
# Check: adb shell pm list features | grep telephony   -> no output.
# Remove: adb shell /debug_ramdisk/su -c 'touch /data/adb/modules/boox_wifionly/remove'; reboot.
set -eu
cd "$(dirname "$0")"
S=${BOOX_SERIAL:-$(head -n1 ~/.config/boox/serial 2>/dev/null)}; [ -n "$S" ] || { echo "set BOOX_SERIAL" >&2; exit 1; }
export ADB_LIBUSB=1
F=system/etc/permissions/boox-wifi-only.xml
h=$(shasum -a 256 "$F" | cut -d' ' -f1)
adb -s "$S" push "$F" /data/local/tmp/boox-wifi-only.xml >/dev/null
adb -s "$S" shell "/debug_ramdisk/su -c 'set -e; [ \"\$(sha256sum /data/local/tmp/boox-wifi-only.xml | cut -d\" \" -f1)\" = $h ] || { echo HASH MISMATCH; exit 1; }
M=/data/adb/modules/boox_wifionly; D=\$M/system/etc/permissions; mkdir -p \$D
cp /data/local/tmp/boox-wifi-only.xml \$D/boox-wifi-only.xml; chmod 644 \$D/boox-wifi-only.xml
rm -f /data/local/tmp/boox-wifi-only.xml
printf \"id=boox_wifionly\nname=Boox Wi-Fi only\nversion=v1\nversionCode=1\nauthor=boox\ndescription=Marks telephony sub-features unavailable on the Wi-Fi-only Note5\n\" > \$M/module.prop
chcon -R u:object_r:system_file:s0 \$M/system; rm -f \$M/disable \$M/remove; ls -lZ \$D'"
echo "installed; reboot to apply"
