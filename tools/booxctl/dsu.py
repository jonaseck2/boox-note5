"""Dynamic System Updates: boot a GSI from /data without touching super. Stock is one reboot away."""
import gzip
import shutil
import struct
import zipfile
from pathlib import Path

SPARSE_MAGIC = 0xED26FF3A
DSU_ACTIVITY = "com.android.dynsystem/com.android.dynsystem.VerificationActivity"


def is_sparse(path) -> bool:
    with open(path, "rb") as f:
        head = f.read(4)
    return len(head) == 4 and struct.unpack("<I", head)[0] == SPARSE_MAGIC


def unsparse(src, out) -> int:
    """Android sparse image -> raw image. Handles RAW, FILL, DONT_CARE and CRC32 chunks."""
    with open(src, "rb") as f, open(out, "wb") as o:
        magic, _maj, _min, hdr_sz, chunk_hdr_sz, blk, total_blks, total_chunks, _crc = struct.unpack("<IHHHHIIII", f.read(28))
        if magic != SPARSE_MAGIC:
            raise ValueError("not a sparse image")
        f.seek(hdr_sz)
        for _ in range(total_chunks):
            ctype, _r, nblk, tot = struct.unpack("<HHII", f.read(12))
            f.seek(chunk_hdr_sz - 12, 1)
            body = tot - chunk_hdr_sz
            if ctype == 0xCAC1:            # RAW
                remaining = body
                while remaining:
                    buf = f.read(min(remaining, 1 << 22)); o.write(buf); remaining -= len(buf)
            elif ctype == 0xCAC2:          # FILL
                pattern = f.read(4) * (blk // 4)
                for _ in range(nblk):
                    o.write(pattern)
            elif ctype == 0xCAC3:          # DONT_CARE
                o.seek(nblk * blk, 1)
            elif ctype == 0xCAC4:          # CRC32
                f.seek(body, 1)
            else:
                raise ValueError(f"unknown chunk type {ctype:#x}")
        o.truncate(total_blks * blk)
    return total_blks * blk


def prepare(zip_path, workdir) -> tuple:
    """Unzip system.img from a GSI zip, unsparse if needed, gzip. Returns (gz_path, raw_size)."""
    wd = Path(workdir); wd.mkdir(parents=True, exist_ok=True)
    img = wd / "system.img"
    if not img.exists():
        with zipfile.ZipFile(zip_path) as z, z.open("system.img") as s, open(img, "wb") as d:
            shutil.copyfileobj(s, d, 1 << 22)
    raw = wd / "system_raw.img"
    if is_sparse(img):
        unsparse(img, raw)
    else:
        raw = img
    gz = wd / "system_raw.gz"
    if not gz.exists():
        with open(raw, "rb") as s, gzip.open(gz, "wb", compresslevel=1) as d:
            shutil.copyfileobj(s, d, 1 << 22)
    return gz, raw.stat().st_size


def install(dev, gz_remote: str, raw_size: int, userdata_bytes: int = 8 << 30) -> None:
    dev.shell(f"am start-activity -n {DSU_ACTIVITY} -a android.os.image.action.START_INSTALL "
              f"-d file://{gz_remote} --el KEY_SYSTEM_SIZE {raw_size} --el KEY_USERDATA_SIZE {userdata_bytes}")


def status(dev) -> str:
    return dev.su("gsi_tool status 2>&1").strip()


def boot(dev) -> None:
    """Commit the finished DSU install and boot it once, via the same service action as the
    notification's Restart button. A plain reboot discards an uncommitted install, and
    `gsi_tool enable` only re-arms a disabled one. The next reboot returns to stock."""
    if "installed: system_gsi" not in status(dev):
        raise RuntimeError("no installed DSU image (run dsu install and wait for 'ready')")
    dev.su("am startservice -n com.android.dynsystem/.DynamicSystemInstallationService "
           "-a com.android.dynsystem.ACTION_REBOOT_TO_DYN_SYSTEM")


def discard(dev) -> str:
    return dev.su("gsi_tool wipe 2>&1").strip()
