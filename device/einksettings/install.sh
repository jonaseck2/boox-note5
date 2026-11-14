#!/bin/sh
# Install the E-ink Settings app as a system app through the Magisk module boox_einksettings.
#   ./install.sh          stage the APK into the module (takes effect on the next boot)
#   ./install.sh grant    after that boot: pre-grant Magisk su to the app, skipping the prompt
# Root via /debug_ramdisk/su, same as device/epdcshim/install.sh. See README.md.
set -eu
cd "$(dirname "$0")"
S=${BOOX_SERIAL:-$(head -n1 ~/.config/boox/serial 2>/dev/null)}; [ -n "$S" ] || { echo "set BOOX_SERIAL or write the serial to ~/.config/boox/serial" >&2; exit 1; }
export ADB_LIBUSB=1
A="adb -s $S"
PKG=org.boox.einksettings
APK=build/EinkSettings.apk

if [ "${1:-}" = grant ]; then
  $A shell '/debug_ramdisk/su -c "
set -e
uid=\$(pm list packages -U '$PKG' | sed -n \"s/^package:'$PKG' uid://p\")
[ -n \"\$uid\" ] || { echo '$PKG' not installed, reboot first; exit 1; }
M=/data/adb/magisk/magisk; [ -x \$M ] || M=magisk
# policies(uid, policy, until, logging, notification): policy 2 = allow, until 0 = forever
\$M --sqlite \"REPLACE INTO policies (uid,policy,until,logging,notification) VALUES(\$uid,2,0,1,0)\"
\$M --sqlite \"SELECT * FROM policies WHERE uid=\$uid\"
"'
  exit 0
fi

[ -e "$APK" ] || { echo "run ./build.sh first" >&2; exit 1; }
H=$(shasum -a 256 "$APK" | cut -d' ' -f1)
$A push "$APK" /data/local/tmp/EinkSettings.apk >/dev/null
$A shell '/debug_ramdisk/su -c "
set -e
# the staged file sits in shell-writable /data/local/tmp: verify the hash before copying
[ \"\$(sha256sum /data/local/tmp/EinkSettings.apk | cut -d\" \" -f1)\" = '"$H"' ] || { echo HASH MISMATCH; exit 1; }
M=/data/adb/modules/boox_einksettings
D=\$M/system/app/EinkSettings
mkdir -p \$D
cp /data/local/tmp/EinkSettings.apk \$D/EinkSettings.apk.new
mv -f \$D/EinkSettings.apk.new \$D/EinkSettings.apk
rm -f /data/local/tmp/EinkSettings.apk
printf \"id=boox_einksettings\nname=Boox E-ink Settings\nversion=v1\nversionCode=1\nauthor=boox\ndescription=E-ink entry in Settings > Display (system app)\n\" > \$M/module.prop
chmod 755 \$M/system \$M/system/app \$D
chmod 644 \$D/EinkSettings.apk
chcon -R u:object_r:system_file:s0 \$M/system
rm -f \$M/disable \$M/remove
ls -lZR \$M/system
"'
# PackageManager rescans /system APKs only when the build fingerprint changes, so a replaced APK keeps
# its old package record (version, permissions) until then. Installing the same, identically signed APK
# as an update of the system package applies it now and keeps the SYSTEM flag (the Settings tile stays).
if $A shell pm path org.boox.einksettings >/dev/null 2>&1; then
  $A install -r "$APK" | tail -1
fi
echo "staged. First install only: reboot, then run: $0 grant"
