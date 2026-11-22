#!/bin/sh
# Install the boox_epdc Magisk module on the device (root via /debug_ramdisk/su).
# The boot image must carry the boox_composer service from ../boox-adb.rc.template.
# Takes effect on the next boot.
set -eu
cd "$(dirname "$0")"
SRC=${SRC:-.}                 # source dir: this dir, or an extracted glue bundle (booxctl update glue)
VERSION=${VERSION:-dev}
VCODE=$(echo "$VERSION" | awk -F. 'NF==4 && $1 ~ /^[0-9]+$/ {printf "%d", ($1*10000+$2*100+$3)*100+$4; ok=1} END {if (!ok) print 0}')
S=${BOOX_SERIAL:-$(head -n1 ~/.config/boox/serial 2>/dev/null)}; [ -n "$S" ] || { echo "set BOOX_SERIAL or write the serial to ~/.config/boox/serial" >&2; exit 1; }
export ADB_LIBUSB=1
A="adb -s $S"
sha() { if command -v shasum >/dev/null; then shasum -a 256 "$1"; else sha256sum "$1"; fi | cut -d' ' -f1; }   # sha256sum: Linux/Windows hosts
H_SO=$(sha "$SRC/libbooxepdc.so")
H_PF=$(sha "$SRC/module/post-fs-data.sh")
H_SV=$(sha "$SRC/module/service.sh")
$A push "$SRC/libbooxepdc.so" /data/local/tmp/libbooxepdc.so >/dev/null
$A push "$SRC/module/post-fs-data.sh" /data/local/tmp/boox-post-fs-data.sh >/dev/null
$A push "$SRC/module/service.sh" /data/local/tmp/boox-service.sh >/dev/null
$A shell '/debug_ramdisk/su -c "
set -e
# staged files sit in shell-writable /data/local/tmp: verify hashes before copying into the root-owned module
# (toybox sha256sum -c -s returned 0 for a tampered file, so compare explicitly)
v() { [ \"\$(sha256sum \$2 | cut -d\" \" -f1)\" = \"\$1\" ] || { echo HASH MISMATCH \$2; exit 1; }; }
v '"$H_SO"' /data/local/tmp/libbooxepdc.so
v '"$H_PF"' /data/local/tmp/boox-post-fs-data.sh
v '"$H_SV"' /data/local/tmp/boox-service.sh
M=/data/adb/modules/boox_epdc
mkdir -p \$M/system/vendor/lib64
# never cp over the live file: the composer maps it, in-place writes crash it (SIGSEGV in epdc_thread)
L=\$M/system/vendor/lib64/libbooxepdc.so
[ -f \$L ] && ! cmp -s \$L /data/local/tmp/libbooxepdc.so && cp \$L \$L.prev   # boot guard fallback
cp /data/local/tmp/libbooxepdc.so \$L.new
chmod 644 \$L.new
chcon u:object_r:vendor_file:s0 \$L.new
mv -f \$L.new \$L
printf \"id=boox_epdc\nname=Boox EPDC shim\nversion='"$VERSION"'\nversionCode='"$VCODE"'\nauthor=boox\ndescription=E-ink glue: composer EPDC shim, GPU composition, front light\n\" > \$M/module.prop
cp /data/local/tmp/boox-post-fs-data.sh \$M/post-fs-data.sh
cp /data/local/tmp/boox-service.sh \$M/service.sh
chmod 755 \$M/post-fs-data.sh \$M/service.sh
test -x /data/adb/magisk/magiskpolicy || echo WARNING: /data/adb/magisk/magiskpolicy missing, repopulate /data/adb/magisk
for p in enable=1 list_mode=2308 a=0 b=0 c=1872 d=1404 disp=0 period_us=100000 always=0 raw=0; do
  k=\${p%%=*}; [ -n \"\$(getprop persist.boox.epdc.\$k)\" ] || setprop persist.boox.epdc.\$k \${p#*=}
done
ls -lZ \$M/system/vendor/lib64; cat \$M/post-fs-data.sh \$M/service.sh
"'
