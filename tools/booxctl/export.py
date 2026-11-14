import os
from dataclasses import dataclass
from pathlib import Path


class ExportIncomplete(RuntimeError):
    pass


@dataclass
class ExportReport:
    files: int
    bytes: int


def local_count(path: Path) -> int:
    return sum(len(f) for _, _, f in os.walk(path))


def local_bytes(path: Path) -> int:
    return sum((Path(d) / n).stat().st_size for d, _, fs in os.walk(path) for n in fs
               if not (Path(d) / n).is_symlink())


def export_sdcard(dev, dest: Path) -> ExportReport:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    remote = int(dev.shell("find /sdcard/ -type f 2>/dev/null | wc -l").strip() or 0)
    dev.pull("/sdcard/.", dest, timeout=4 * 3600)
    have = local_count(dest)
    if have < remote:
        raise ExportIncomplete(f"device has {remote} files, local copy has {have}")
    return ExportReport(files=have, bytes=local_bytes(dest))
