#!/system/bin/sh
# noatsecure: without it the init -> hal_graphics_composer_default transition sets AT_SECURE and the
# linker drops LD_PRELOAD (docs/runbooks/eink-interface.md).
/data/adb/magisk/magiskpolicy --live "allow init hal_graphics_composer_default process noatsecure"
# One hardware blend stage: any frame with more than one layer is GPU-composited into one full-size
# target. The EPDC panics the kernel when it converts while narrow overlay planes are on screen
# (pstore: rgb32_to_4bit_32 <- __onyx_epdc_buf_put_queue). Must be set before the composer starts.
/data/adb/magisk/magisk resetprop vendor.display.primary_mixer_stages 1

# Boot guard: a faulty shim can panic the kernel on every boot, and the Note5 has no volume key for
# Magisk safe mode. Count boots that never reach 60 s after boot_completed (service.sh resets the
# counter); at the 3rd, restore the previous shim. Runs before Magisk mounts the module, so the
# composer never loads the bad .so.
M=${0%/*}
C=/data/adb/boox_boot_count
L=$M/system/vendor/lib64/libbooxepdc.so
n=$(cat $C 2>/dev/null || echo 0)
n=$((n + 1))
echo $n > $C
if [ $n -ge 3 ] && [ -f $L.prev ]; then
  cp $L $L.bad
  mv -f $L.prev $L
  chcon u:object_r:vendor_file:s0 $L
  echo 0 > $C
  echo "$(date) boot guard: $n unhealthy boots, restored previous shim" >> /data/adb/boox_guard.log
fi
