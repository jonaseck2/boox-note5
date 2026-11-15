#!/bin/sh
# Install the e-ink overlays as preinstalled static RROs through the Magisk module boox_overlays
# (/system/product/overlay). Takes effect after a reboot. Remove: touch .../boox_overlays/remove; reboot.
set -eu
cd "$(dirname "$0")"
S=${BOOX_SERIAL:-$(head -n1 ~/.config/boox/serial 2>/dev/null)}; [ -n "$S" ] || { echo "set BOOX_SERIAL" >&2; exit 1; }
export ADB_LIBUSB=1
DIR=${SRC:-build}            # booxctl update glue passes the verified bundle's overlays/ directory
V=${VERSION:-v1}
for t in launcher systemui framework; do
  f=$DIR/BooxEink-$t.apk
  [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
  h=$(shasum -a 256 "$f" | cut -d' ' -f1)
  adb -s "$S" push "$f" "/data/local/tmp/BooxEink-$t.apk" >/dev/null
  adb -s "$S" shell "/debug_ramdisk/su -c 'set -e; [ \"\$(sha256sum /data/local/tmp/BooxEink-$t.apk | cut -d\" \" -f1)\" = $h ] || { echo HASH MISMATCH; exit 1; }
M=/data/adb/modules/boox_overlays; D=\$M/system/product/overlay; mkdir -p \$D
cp /data/local/tmp/BooxEink-$t.apk \$D/BooxEink-$t.apk.new; chmod 644 \$D/BooxEink-$t.apk.new; mv -f \$D/BooxEink-$t.apk.new \$D/BooxEink-$t.apk
rm -f /data/local/tmp/BooxEink-$t.apk
printf \"id=boox_overlays\nname=Boox e-ink overlays\nversion=$V\nversionCode=1\nauthor=boox\ndescription=White app drawer and notification shade backgrounds for e-ink\n\" > \$M/module.prop
chcon -R u:object_r:system_file:s0 \$M/system; rm -f \$M/disable \$M/remove'"
done
echo "installed; reboot to apply"
