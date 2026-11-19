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

# 3) Front light follows Android's display brightness. Android drives panel0-backlight (0..255,
#    through the composer), which has no light behind it on this panel. Mirror it to onyx_bl_br:
#    slider, screen off (0), dim, doze and adaptive brightness all arrive there. `read` is a shell
#    builtin, so the 0.25 s poll forks nothing. Measured: on 100, asleep 0, slider 30 -> 30.
#    Night Light -> warm front light: onyx_bl_ct 0 = cold .. 24 = warm (camera: R/B 1.037 -> 1.174).
#    Night Light's temperature (2596..4082 K, lower = warmer) maps linearly onto 24..0; off = 0.
PANEL=/sys/class/backlight/panel0-backlight/brightness
CT=/sys/class/backlight/onyx_bl_ct/brightness
max=$(cat /sys/class/backlight/onyx_bl_br/max_brightness 2>/dev/null || echo 28)
pmax=$(cat /sys/class/backlight/panel0-backlight/max_brightness 2>/dev/null || echo 255)
ctmax=$(cat /sys/class/backlight/onyx_bl_ct/max_brightness 2>/dev/null || echo 24)
last=; lastct=; n=0
while true; do
  read p < "$PANEL" 2>/dev/null || p=0
  case "$p" in ''|*[!0-9]*) p=0 ;; esac
  if [ "$p" != "$last" ]; then
    echo $(( p * max / pmax )) > "$BR"
    last=$p
  fi
  n=$(( (n + 1) % 8 ))
  if [ $n = 0 ]; then                      # Night Light every 2 s (settings is a binder call)
    ct=0
    if [ "$(settings get secure night_display_activated 2>/dev/null)" = 1 ]; then
      k=$(settings get secure night_display_color_temperature 2>/dev/null)
      case "$k" in ''|*[!0-9]*) k=2850 ;; esac
      ct=$(( (4082 - k) * ctmax / (4082 - 2596) ))
      [ "$ct" -lt 0 ] && ct=0
      [ "$ct" -gt "$ctmax" ] && ct=$ctmax
    fi
    if [ "$ct" != "$lastct" ]; then echo "$ct" > "$CT"; lastct=$ct; fi
  fi
  sleep 0.25
done
