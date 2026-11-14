"""Flicker meter: record the panel with the Mac camera while adb drives an action, then score
how much of the panel went through a state outside its start..end range (flash, ghost, reversal)."""
import subprocess
import threading
import time
from pathlib import Path

import numpy as np


def flicker_metrics(frames, thresh: int = 30, window: int = 21) -> dict:
    """frames: grey uint8 arrays of the warped panel, oldest first.
    changed_area: fraction that differs between first and last frame (the intended change).
    transient_area: fraction that at some frame left [min(start,end)-thresh, max(start,end)+thresh].
    A monotonic transition stays inside that interval. Flashes, ghosts and reversals leave it.
    flash_area: the same test, but per frame against the frames `window` before and after (0.7 s at
    30 fps). Content that persists longer than the window (a popup) is not counted, a flash is."""
    st = np.stack([np.asarray(f, np.int16) for f in frames])
    first, last = st[0], st[-1]
    lo = np.minimum(first, last) - thresh
    hi = np.maximum(first, last) + thresh
    transient = ((st < lo) | (st > hi)).any(axis=0)
    changed = np.abs(last - first) > thresh
    n = first.size
    flash = np.zeros(first.shape, bool)
    for t in range(window, len(st) - window):
        a, b = st[t - window], st[t + window]
        flash |= (st[t] < np.minimum(a, b) - thresh) | (st[t] > np.maximum(a, b) + thresh)
    ta, ca = transient.sum() / n, changed.sum() / n
    return {"changed_area": float(ca), "transient_area": float(ta),
            "flicker_ratio": float(ta / max(ca, ta, 1e-6)), "flash_area": float(flash.sum() / n),
            "frames": len(frames)}


def record(path: Path, seconds: float, device_index: int = 0) -> Path:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "avfoundation",
                    "-framerate", "30", "-video_size", "1920x1080", "-pixel_format", "nv12",
                    "-i", f"{device_index}:none", "-t", str(seconds), "-c:v", "libx264", "-preset",
                    "ultrafast", "-crf", "12", str(path)], check=True, capture_output=True,
                   timeout=seconds + 30)
    return path


def load_warped(path: Path, corners=None, size=(468, 351), skip_s: float = 1.0):
    import cv2
    from . import vision
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frames, i = [], 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        i += 1
        if i < skip_s * fps:                      # camera auto-exposure settles in the first second
            continue
        if corners is None:
            corners = vision.find_panel(vision.to_gray(img))
        w = vision.warp_to_screen(img, corners=corners)
        g = cv2.blur(vision.to_gray(cv2.resize(w, size, interpolation=cv2.INTER_AREA)), (3, 3))
        frames.append(g)
    return frames


def run(dev, out_dir: Path, action: str, seconds: float = 7.0, delay_s: float = 3.5, corners=None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    video = out_dir / "flicker.mp4"
    t = threading.Thread(target=record, args=(video, seconds))
    t.start()
    time.sleep(delay_s)
    if action:
        dev.shell(action)
    t.join()
    frames = load_warped(video, corners=corners)
    m = flicker_metrics(frames)
    import cv2
    cv2.imwrite(str(out_dir / "first.png"), frames[0])
    cv2.imwrite(str(out_dir / "last.png"), frames[-1])
    return m
