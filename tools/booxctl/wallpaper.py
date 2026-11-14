"""E-ink wallpapers. Default: Hokusai's The Great Wave (public domain) as a light print. Keeping
only 45% of the ink makes Android treat the wallpaper as light, so launcher labels and status-bar
icons turn dark (full-contrast version: white labels, unreadable on the panel; 2026-11-14 camera)."""
import hashlib
import subprocess
from pathlib import Path

PANEL = (1872, 1404)
WAVE_URL = "https://upload.wikimedia.org/wikipedia/commons/a/a5/Tsunami_by_hokusai_19th_century.jpg"
WAVE_SHA256 = "30c170260de393f51bd592adacc6f0714b60f157c09744e9c5b6d46e6a613718"
INK = 0.45


def light_print(src: Path, out: Path, ink: float = INK) -> Path:
    """Greyscale, cover-crop to the panel, stretch to the full range, then keep `ink` of the darkness."""
    import cv2
    import numpy as np
    g = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
    h, w = g.shape
    W, H = PANEL
    s = max(W / w, H / h)
    g = cv2.resize(g, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    y, x = (g.shape[0] - H) // 2, (g.shape[1] - W) // 2
    g = g[y:y + H, x:x + W].astype(float)
    lo, hi = np.percentile(g, [1, 99])
    g = np.clip((g - lo) * 255 / max(hi - lo, 1), 0, 255)
    g = 255 - (255 - g) * ink
    cv2.imwrite(str(out), cv2.cvtColor(g.astype(np.uint8), cv2.COLOR_GRAY2BGR))
    return Path(out)


def fetch_wave(dest: Path) -> Path:
    subprocess.run(["curl", "-fsSL", "-A", "booxctl-wallpaper", "-o", str(dest), WAVE_URL], check=True)
    if hashlib.sha256(Path(dest).read_bytes()).hexdigest() != WAVE_SHA256:
        raise RuntimeError("downloaded Great Wave does not match the pinned sha256")
    return Path(dest)


def install(dev, png: Path) -> None:
    """Replace the home and lock wallpaper files as root and drop the stale colour hints.
    Takes effect after a reboot (no adb API for setting a wallpaper image)."""
    h = hashlib.sha256(Path(png).read_bytes()).hexdigest()
    dev.push(png, "/data/local/tmp/boox-wallpaper.png")
    dev.su(f'[ "$(sha256sum /data/local/tmp/boox-wallpaper.png | cut -d" " -f1)" = {h} ] && '
           "for f in wallpaper wallpaper_orig wallpaper_lock wallpaper_lock_orig; do "
           "cp /data/local/tmp/boox-wallpaper.png /data/system/users/0/$f; "
           "chown system:system /data/system/users/0/$f; chmod 600 /data/system/users/0/$f; done; "
           "restorecon /data/system/users/0/wallpaper* 2>/dev/null; "
           "rm -f /data/system/users/0/wallpaper_info.xml /data/local/tmp/boox-wallpaper.png")
