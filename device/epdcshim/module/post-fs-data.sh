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

# Crash lifecycle. A kernel panic parks the SoC in Qualcomm crash-dump mode (USB 05c6:900E): blank
# panel, no adb, only a long power hold gets out. download_mode 0 makes the panic reboot instead,
# kernel.panic 10 s later. The full RAM dump over EDL is lost, the kernel log in pstore is kept.
echo 0 > /sys/module/msm_poweroff/parameters/download_mode 2>/dev/null
echo 10 > /proc/sys/kernel/panic
echo 1 > /proc/sys/kernel/panic_on_oops
# Save a new kernel panic record (dmesg-ramoops-*) to /data/adb/boox_crash/<stamp>/, keep 20.
# console-/pmsg-ramoops change on every boot and are not panic evidence (tools/booxctl/update.py).
if ls /sys/fs/pstore/dmesg-ramoops-* >/dev/null 2>&1; then
  h=$(cat /sys/fs/pstore/dmesg-ramoops-* | sha256sum | cut -d' ' -f1)
  if [ "$h" != "$(cat /data/adb/boox_crash/.last 2>/dev/null)" ]; then
    D=/data/adb/boox_crash/$(date +%Y%m%d-%H%M%S)
    mkdir -p $D && cp /sys/fs/pstore/* $D/ 2>/dev/null
    echo $h > /data/adb/boox_crash/.last
    echo "$(date) pstore panic record saved to $D" >> /data/adb/boox_guard.log
  fi
fi
ls -1d /data/adb/boox_crash/2* 2>/dev/null | sort -r | tail -n +21 | xargs rm -rf 2>/dev/null

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
