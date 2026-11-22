"""`booxctl soak <target>`: sleep/wake cycles with a touch-controller check after every wake.

The release gate for anything that touches power or input: the owner's use is screen off for hours,
then pick up and touch. A test that only ever runs with the screen on and USB attached never reaches
that path. Run it over Wi-Fi adb with the cable out (USB holds the device awake).
"""
import subprocess
import time

TP = "/sys/bus/i2c/devices/2-0024"


def touch_ok(out: str) -> bool:
    """`head -n1 drv_irq; cat sleep_status` output -> controller powered and its IRQ enabled."""
    lines = out.split()
    return "ENABLED" in out and bool(lines) and lines[-1] == "on"


def run(target: str, cycles: int = 20, off_s: float = 30, log=print) -> int:
    def sh(cmd: str, timeout: float = 20) -> str:
        try:
            r = subprocess.run(["adb", "-s", target, "shell", cmd], capture_output=True, text=True, timeout=timeout)
            return r.stdout
        except subprocess.TimeoutExpired:
            return ""
    su = lambda c: sh(f"/debug_ramdisk/su -c '{c}'")
    before = su("wc -c < /data/adb/boox_touch.log 2>/dev/null; cat /sys/power/suspend_stats/fail").split()
    ok = 0
    for i in range(1, cycles + 1):
        sh("input keyevent SLEEP")
        time.sleep(off_s)
        sh("input keyevent WAKEUP")
        time.sleep(4)
        state = su(f"head -n1 {TP}/drv_irq; cat {TP}/sleep_status")
        good = touch_ok(state)
        ok += good
        log(f"cycle {i}/{cycles}: {'ok' if good else 'TOUCH DEAD'} ({' '.join(state.split()) or 'no answer'})")
    after = su("wc -c < /data/adb/boox_touch.log 2>/dev/null; cat /sys/power/suspend_stats/fail").split()
    log(f"touch ok after {ok}/{cycles} wakes; boox_touch.log bytes {before[:1]} -> {after[:1]} "
        f"(growth = auto-recoveries); suspend failures {before[1:]} -> {after[1:]}")
    return 0 if ok == cycles else 1
