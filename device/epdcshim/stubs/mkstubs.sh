#!/bin/sh
# Build stub link libraries (libc, libdl, liblog, libdrm) from stubs/symbols.txt, so the shim links
# without the device's proprietary libraries (CI, public repo). Stubs only carry symbol NAMES and
# VERSIONS: the composer process loads the real libraries at runtime. Usage: stubs/mkstubs.sh <outdir>
set -eu
cd "$(dirname "$0")"
OUT=${1:?outdir}
CLANG=${CLANG:-clang}
LLD=${LLD:-ld.lld}
mkdir -p "$OUT"
for lib in $(grep -v '^#' symbols.txt | awk '{print $1}' | sort -u); do
  c="$OUT/$lib.c"; v="$OUT/$lib.map"
  : > "$c"
  grep "^$lib " symbols.txt | awk '{print "void " $2 "(void) {}"}' >> "$c"
  ver=$(grep "^$lib " symbols.txt | awk '{print $3}' | sort -u)
  vflag=
  if [ "$ver" != "-" ]; then
    { echo "$ver {"; echo "  global:"; grep "^$lib " symbols.txt | awk '{print "    " $2 ";"}'; echo "  local: *;"; echo "};"; } > "$v"
    vflag="-Wl,--version-script=$v"
  fi
  "$CLANG" --target=aarch64-linux-android30 -fPIC -fno-builtin -w -nostdlib -shared -fuse-ld="$LLD" \
    -Wl,-soname,"$lib.so" $vflag -o "$OUT/$lib.so" "$c"
done
echo "stubs in $OUT"
