#!/bin/sh
# Build libbooxepdc.so. Needs Homebrew llvm + lld, and sysroot/ with the device's
# libdrm, liblog, libdl, libc (adb pull from /vendor/lib64 and /system/lib64).
set -eu
cd "$(dirname "$0")"
"$(brew --prefix llvm)/bin/clang" --target=aarch64-linux-android30 -O2 -fPIC \
  -fno-stack-protector -ffreestanding -nostdlib -mno-outline-atomics \
  -fuse-ld="$(brew --prefix lld)/bin/ld.lld" -shared -Wl,-soname,libbooxepdc.so \
  -o libbooxepdc.so epdcshim.c sysroot/libdrm.so sysroot/liblog.so sysroot/libdl.so sysroot/libc.so
echo built libbooxepdc.so
