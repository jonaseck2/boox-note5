"""E-ink refresh control and camera-verified probing. Kernel interface: docs/runbooks/eink-interface.md."""

# Kernel force_waveform values, traced from SurfaceFlinger's ioctl(/dev/ebc, 0x700b, &v) (2026-11-09).
MODES = {"normal": -1, "speed": 2305, "a2": 2308, "x": 16777220}
EBCCTL_REMOTE = "/data/local/tmp/ebcctl"
PANEL_CLEAN = "/sys/class/sepdc/debug/panel_clean"


def set_mode(dev, mode: str) -> None:
    """Force a waveform for subsequent updates. 'normal' (-1) returns control to the system."""
    dev.su(f"{EBCCTL_REMOTE} {MODES[mode]}")


def full_refresh(dev) -> None:
    """Reading panel_clean makes the kernel EPDC run a full-panel clean refresh."""
    dev.su(f"cat {PANEL_CLEAN} >/dev/null; sleep 1; setprop sys.boox.epdc.force $(date +%s)")


def flash_visible(trace) -> bool:
    """A full refresh has a fixed shape in mean panel brightness: a dip well below the settled
    level, then an overshoot above it. The camera's auto-exposure ramp at recording start only
    rises towards the settled level and never overshoots, so it cannot read as a flash."""
    import statistics
    if len(trace) < 6:
        return False
    settled = statistics.median(trace[-10:])
    dips = [i for i, v in enumerate(trace) if v < settled - 40]
    return bool(dips) and any(v > settled + 15 for v in trace[dips[0]:])


def mode_switch_visible(diff_normal: float, diff_fast: float, ratio: float = 1.4) -> bool:
    """A fast waveform (A2) leaves a scrolled page visibly further from the screencap than Normal."""
    return diff_fast >= diff_normal * ratio


def probe(dev, workdir, corners, ebcctl_local) -> dict:
    """Camera-verified probe: full refresh flash + A2-vs-Normal scroll difference. Device must be rooted."""
    import json, subprocess, time
    from pathlib import Path
    import cv2, numpy as np
    from . import camera, vision
    wd = Path(workdir); wd.mkdir(parents=True, exist_ok=True)
    dev.push(Path(ebcctl_local), EBCCTL_REMOTE)
    dev.su(f"chmod 755 {EBCCTL_REMOTE}")
    # 1. full refresh, recorded as video
    vid = wd / "flash.mp4"
    rec = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "avfoundation",
                            "-framerate", "30", "-video_size", "1920x1080", "-pixel_format", "nv12",
                            "-i", "0:none", "-t", "3", str(vid)])
    time.sleep(1.2); full_refresh(dev); rec.wait()
    if rec.returncode != 0:
        raise RuntimeError("camera recording failed (camera busy?)")
    cap, trace = cv2.VideoCapture(str(vid)), []
    while True:
        ok, f = cap.read()
        if not ok: break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY); trace.append(float(g[150:1000, 300:1800].mean()))
    # 2. scroll the Settings list in Normal and A2
    diffs = {}
    try:
      for mode in ("normal", "a2"):
        set_mode(dev, mode)
        dev.shell("am force-stop com.android.settings; am start -n com.android.settings/.Settings >/dev/null 2>&1; sleep 3")
        full_refresh(dev); time.sleep(2.5)
        dev.shell("input swipe 1000 1200 1000 400 300"); time.sleep(0.6)
        cam = camera.capture(wd / f"scroll_{mode}.jpg", settle_s=0.0)
        dev.screencap(wd / f"scroll_{mode}.png")
        w = vision.warp_to_screen(cam, corners=corners).astype(float)
        s = cv2.imread(str(wd / f"scroll_{mode}.png"), 0).astype(float)
        lo, hi = np.percentile(w, 2), np.percentile(w, 98)
        wn = np.clip((w - lo) / (hi - lo + 1e-6) * 255, 0, 255)
        diffs[mode] = float(np.abs(wn - s)[60:1300, 300:].mean())
        dev.shell("input keyevent HOME")
    finally:
        set_mode(dev, "normal")
    return {"full_refresh": flash_visible(trace), "flash_swing": max(trace) - min(trace),
            "mode_switch": mode_switch_visible(diffs["normal"], diffs["a2"]), "scroll_diff": diffs}
