import subprocess
from pathlib import Path


def capture(path: Path, device_index: int = 0, settle_s: float = 2.0) -> Path:
    path = Path(path)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "avfoundation",
         "-framerate", "30", "-video_size", "1920x1080", "-pixel_format", "nv12",
         "-i", f"{device_index}:none", "-ss", str(settle_s), "-frames:v", "1", str(path)],
        check=True, capture_output=True, timeout=30)
    return path
