#!/bin/sh
# Run AFTER the tablet is in EDL (deep-flash cable: tablet off, hold button/short D+ to GND, plug in, release ~3 s).
# Outside the Claude Code sandbox (libusb). Default: flash the adb-enabled boot so Android 15 can be inspected.
#   ./recover-edl.sh adb     -> boot_b with overlay.d adb rc (keeps Android 15 in super)
#   ./recover-edl.sh stock   -> full Onyx restore: super, vbmeta_b, boot_b (Magisk) from the verified backup
set -e
E="$HOME/boox-backups/tools/edlvenv/bin/edl"; L="$HOME/boox-backups/tools/loaders/poke6.bin"
B="$HOME/boox-backups/2026-11-08/edl/rl"; W="$HOME/boox-backups/$(date +%F)/recover"; mkdir -p "$W/logs"; cd "$W"
case "${1:-adb}" in
  adb)   "$E" w boot_b "$HOME/boox-backups/gsi/boot_b.magisk.adbkey.img" --memory=ufs --loader="$L" ;;
  stock) (cd "$B" && sed -n '/^shasum/,/^SHA256$/p' restore.sh | tail -n +2 | sed '$d' | grep -E ' lun0/super.bin| lun4/vbmeta_b.bin' | shasum -a 256 -c -)
         "$E" w super "$B/lun0/super.bin" --memory=ufs --loader="$L"
         "$E" w vbmeta_b "$B/lun4/vbmeta_b.bin" --memory=ufs
         "$E" w boot_b "$HOME/boox-backups/2026-11-08/root/boot_b.magisk.img" --memory=ufs ;;
  *) echo "usage: $0 adb|stock"; exit 2 ;;
esac
"$E" reset
