#!/system/bin/sh
# Boox e-ink glue, run by Magisk at late_start. See docs/runbooks/eink-interface.md.
BR=/sys/class/backlight/onyx_bl_br/brightness     # front light, 0..28

# 1) Force GPU composition. The EPDC reads only one plane, and a narrow plane panics the kernel.
#    SF resets the flag on restart and during display init, so re-apply it every 10 s (idempotent).
( while true; do service call SurfaceFlinger 1008 i32 1 >/dev/null 2>&1; sleep 10; done ) &

until [ "$(getprop sys.boot_completed)" = 1 ]; do sleep 2; done

# Boot guard: this boot is healthy after 60 s of uptime past boot_completed (see post-fs-data.sh).
( sleep 60; echo 0 > /data/adb/boox_boot_count ) &

# 2) Animations off: animation frames leave ghost traces under partial waveforms.
settings put global window_animation_scale 0
settings put global transition_animation_scale 0
settings put global animator_duration_scale 0

# Wi-Fi adb on port 5555, so the tablet can be used and monitored without a cable (booxctl watch).
# adb keeps its RSA key check. persist.boox.adb.tcp=0 turns it off. Restarting adbd drops USB adb briefly.
if [ "$(getprop persist.boox.adb.tcp)" != 0 ] && [ "$(getprop service.adb.tcp.port)" != 5555 ]; then
  setprop service.adb.tcp.port 5555; stop adbd; start adbd
fi

# 3) Front light follows Android's display brightness. Android drives panel0-backlight (0..255,
#    through the composer), which has no light behind it on this panel. Mirror it to onyx_bl_br:
#    slider, screen off (0), dim, doze and adaptive brightness all arrive there. `read` is a shell
#    builtin, so the 0.25 s poll forks nothing. Measured: on 100, asleep 0, slider 30 -> 30.
#    Warmth: onyx_bl_ct 0 = cold .. 24 = warm (camera: R/B 1.037 -> 1.174), from
#    persist.boox.light.warmth (E-ink settings slider, Quick Settings tile). While Night Light is on,
#    its temperature (2596..4082 K, lower = warmer, mapped onto 24..0) raises it, never lowers it.
PANEL=/sys/class/backlight/panel0-backlight/brightness
CT=/sys/class/backlight/onyx_bl_ct/brightness
max=$(cat /sys/class/backlight/onyx_bl_br/max_brightness 2>/dev/null || echo 28)
pmax=$(cat /sys/class/backlight/panel0-backlight/max_brightness 2>/dev/null || echo 255)
ctmax=$(cat /sys/class/backlight/onyx_bl_ct/max_brightness 2>/dev/null || echo 24)
last=; lastct=; n=0
# 4) Touch: prevent, detect, recover. See docs/runbooks/device-facts.md "Touchscreen lost".
#    Cause (2026-11-22, live): the kernel tries to suspend every 60 s and never succeeds
#    (suspend_stats success 0, failed_suspend_late, pending wakeup source wacom_irq_wakelock). On one
#    of those attempts the cyttsp5 PM notifier powers the controller off ("onyx_tp_power:power off
#    success") and nothing powers it on again: drv_irq DISABLED, sleep_status off, touch dead.
#    a) Prevent: hold a kernel wakelock, so the futile suspend attempts stop. They never succeeded,
#       so this costs no sleep. persist.boox.nosuspend=0 turns it off.
#    b) Recover: while the screen is on, check the driver every 2 s. Two bad checks in a row ->
#       unbind and bind the driver (re-probe powers the controller on; verified on the dead state,
#       2026-11-22). At most once per 20 s. Every recovery is logged to /data/adb/boox_touch.log.
[ "$(getprop persist.boox.nosuspend)" = 0 ] || echo boox_nosuspend > /sys/power/wake_lock
TP=/sys/bus/i2c/devices/2-0024
TPD=/sys/bus/i2c/drivers/cyttsp5_i2c_adapter
bad=0; t=0; tfix=-100
touch_recover() {
  { echo "== $(date) touch dead (drv_irq: $1, sleep_status: $2): rebinding driver"
    for f in /sys/power/suspend_stats/*; do echo "${f##*/}: $(cat $f)"; done
    dmesg | grep -E "ONYX_TP|PM: (suspend|late)" | tail -20
    echo 2-0024 > $TPD/unbind; sleep 1; echo 2-0024 > $TPD/bind; sleep 3
    echo "after: $(head -n1 $TP/drv_irq) / $(cat $TP/sleep_status)"; } >> /data/adb/boox_touch.log 2>&1
  log -t boox-touch "touch dead ($1 / $2), driver rebound: $(head -n1 $TP/drv_irq) / $(cat $TP/sleep_status)"
}
while true; do
  read p < "$PANEL" 2>/dev/null || p=0
  case "$p" in ''|*[!0-9]*) p=0 ;; esac
  if [ "$p" != "$last" ]; then
    echo $(( p * max / pmax )) > "$BR"
    last=$p
  fi
  n=$(( (n + 1) % 8 ))
  if [ $n = 0 ]; then                      # Night Light every 2 s (settings is a binder call)
    ct=$(getprop persist.boox.light.warmth)
    case "$ct" in ''|*[!0-9]*) ct=0 ;; esac
    if [ "$(settings get secure night_display_activated 2>/dev/null)" = 1 ]; then
      k=$(settings get secure night_display_color_temperature 2>/dev/null)
      case "$k" in ''|*[!0-9]*) k=2850 ;; esac
      nl=$(( (4082 - k) * ctmax / (4082 - 2596) ))
      [ "$nl" -gt "$ct" ] && ct=$nl
    fi
    [ "$ct" -lt 0 ] && ct=0
    [ "$ct" -gt "$ctmax" ] && ct=$ctmax
    if [ "$ct" != "$lastct" ]; then echo "$ct" > "$CT"; lastct=$ct; fi
    t=$((t + 1))                           # touch check (builtins only)
    if [ "$p" != 0 ]; then
      irq=; ss=; read irq < $TP/drv_irq 2>/dev/null; read ss < $TP/sleep_status 2>/dev/null
      case "$irq/$ss" in *DISABLED*|*/off) bad=$((bad + 1)) ;; *) bad=0 ;; esac
      if [ $bad -ge 2 ] && [ $((t - tfix)) -ge 10 ]; then touch_recover "$irq" "$ss"; tfix=$t; bad=0; fi
    else bad=0; fi
  fi
  sleep 0.25
done
