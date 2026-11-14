#!/bin/sh
# Build libbooxepdc.so. Links against sysroot/ (the device's libdrm, liblog, libdl, libc, pulled with
# adb from /vendor/lib64 and /system/lib64; gitignored) when present, else against stub libraries
# generated from stubs/symbols.txt (CI, fresh clones). Both give the same imports: see the runbook.
set -eu
cd "$(dirname "$0")"
if command -v brew >/dev/null 2>&1 && [ -x "$(brew --prefix llvm 2>/dev/null)/bin/clang" ]; then
  CLANG=${CLANG:-$(brew --prefix llvm)/bin/clang}
  LLD=${LLD:-$(brew --prefix lld)/bin/ld.lld}
fi
CLANG=${CLANG:-clang}
LLD=${LLD:-ld.lld}
export CLANG LLD
SYSROOT=${SYSROOT:-sysroot}
if [ ! -f "$SYSROOT/libc.so" ]; then
  SYSROOT=build/stubs
  stubs/mkstubs.sh "$PWD/$SYSROOT" >/dev/null
fi
"$CLANG" --target=aarch64-linux-android30 -O2 -fPIC \
  -fno-stack-protector -ffreestanding -nostdlib -mno-outline-atomics \
  -fuse-ld="$LLD" -shared -Wl,--no-undefined -Wl,-soname,libbooxepdc.so \
  -o libbooxepdc.so epdcshim.c "$SYSROOT/libdrm.so" "$SYSROOT/liblog.so" "$SYSROOT/libdl.so" "$SYSROOT/libc.so"
echo "built libbooxepdc.so (sysroot: $SYSROOT)"
