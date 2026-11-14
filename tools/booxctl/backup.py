"""Full partition backup of the Boox, verified by SHA-256 on both ends."""
import hashlib
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from .device import resolve_serial, DeviceError


def _serial() -> str:
    try:
        return resolve_serial()
    except DeviceError:
        return "unknown"

BYNAME = "/dev/block/bootdevice/by-name"
# Bootloader chain and secure-world partitions. Restoring them wrongly can hard-brick.
CRITICAL = re.compile(r"^(xbl|xbl_config|abl|tz|hyp|rpm|devcfg|keymaster|cmnlib|cmnlib64|"
                      r"qupfw|uefisecapp|imagefv|featenabler|storsec|multiimgoem|"
                      r"sbl1|aop|bluetooth|dsp|modem|fsc|fsg|modemst1|modemst2|"
                      r"persist|ddr|cdt|limits|limits-cdsp|devinfo|apdp|msadp|dip|"
                      r"splash|logfs|frp|keystore|secdata|toolsfv|uefivarstore)(_[ab])?$")


class BackupError(RuntimeError):
    pass


SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_FILE = re.compile(r"^[A-Za-z0-9_./-]+$")


@dataclass
class Partition:
    name: str
    size: int


@dataclass
class VerifyReport:
    ok: bool
    checked: int
    bad: list = field(default_factory=list)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class DeviceBackup:
    """Adapter giving backup.dump the three device operations it needs (root required)."""

    def __init__(self, dev):
        self.dev = dev

    def list_partitions(self):
        out = self.dev.su(f"for p in $(ls {BYNAME}); do echo $p $(blockdev --getsize64 {BYNAME}/$p); done")
        parts = []
        for line in out.splitlines():
            bits = line.split()
            if not bits:
                continue
            if len(bits) != 2 or not bits[1].isdigit():
                raise BackupError(f"cannot size partition: {line!r}")
            parts.append(Partition(bits[0], int(bits[1])))
        if not parts:
            raise BackupError(f"no partitions found under {BYNAME}")
        return parts

    def device_sha256(self, name):
        return self.dev.su(f"sha256sum {BYNAME}/{name}", timeout=3600).split()[0]

    def read_partition(self, name, local: Path):
        # Stream through exec-out so large partitions (super) never land on /data.
        res = self.dev.r.run(["adb", "-s", self.dev.serial, "exec-out",
                              f"su -c 'cat {BYNAME}/{name}'"], timeout=7200)
        if res.returncode != 0:
            raise BackupError(f"read {name}: rc={res.returncode} {res.stderr[:200]!r}")
        local.write_bytes(res.stdout)


def _load(dest: Path) -> dict:
    mf = dest / "manifest.json"
    return json.loads(mf.read_text()) if mf.exists() else {"serial": _serial(), "partitions": []}


def dump(dev, dest: Path, skip=("userdata",)) -> dict:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = _load(dest)
    known = {e["name"]: e for e in manifest["partitions"]}
    for part in dev.list_partitions():
        if part.name in skip:
            continue
        img = dest / f"{part.name}.img"
        prev = known.get(part.name)
        if prev and img.exists() and img.stat().st_size == part.size and sha256_file(img) == prev["sha256"]:
            continue
        dev.read_partition(part.name, img)
        local = sha256_file(img)
        remote = dev.device_sha256(part.name)
        if img.stat().st_size != part.size or local != remote:
            raise BackupError(f"{part.name}: size {img.stat().st_size}/{part.size}, "
                              f"sha local {local[:12]} device {remote[:12]}")
        known[part.name] = {"name": part.name, "size": part.size, "sha256": local}
        manifest["partitions"] = list(known.values())
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=1))
    manifest["partitions"] = list(known.values())
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def _file(dest: Path, e: dict) -> Path:
    return dest / e.get("file", f"{e['name']}.img")


def _expected_sizes(lun_dir: Path) -> dict:
    """filename -> expected bytes, from the rawprogram*.xml that `edl rl --genxml` writes per LUN."""
    import xml.etree.ElementTree as ET
    sizes = {}
    for x in lun_dir.glob("rawprogram*.xml"):
        for el in ET.parse(x).getroot().iter("program"):
            sizes[el.get("filename")] = int(el.get("num_partition_sectors")) * int(el.get("SECTOR_SIZE_IN_BYTES"))
    return sizes


def import_edl(rl_dir: Path) -> dict:
    """Write manifest.json for an `edl rl --genxml` dump (lun*/<name>.bin) so verify() can check it.
    Every image must match the partition size recorded in that LUN's rawprogram XML, so a dump
    interrupted mid-file is rejected instead of being recorded as a verified backup."""
    rl_dir = Path(rl_dir)
    parts = []
    for f in sorted(rl_dir.glob("lun*/*.bin")):
        if f.name.startswith("gpt_"):
            continue
        if not SAFE_NAME.match(f.stem):
            raise BackupError(f"unsafe partition file name: {f.name!r}")
        expected = _expected_sizes(f.parent).get(f.name)
        if expected is None:
            raise BackupError(f"{f}: not listed in {f.parent}/rawprogram*.xml (dump with --genxml)")
        if f.stat().st_size != expected:
            raise BackupError(f"{f}: {f.stat().st_size} bytes, partition is {expected} (truncated dump?)")
        parts.append({"name": f.stem, "size": expected, "sha256": sha256_file(f),
                      "file": str(f.relative_to(rl_dir))})
    m = {"serial": _serial(), "source": "edl", "partitions": parts}
    (rl_dir / "manifest.json").write_text(json.dumps(m, indent=1))
    return m


def verify(dest: Path) -> VerifyReport:
    dest = Path(dest)
    m = _load(dest)
    bad = [e["name"] for e in m["partitions"]
           if not _file(dest, e).exists() or sha256_file(_file(dest, e)) != e["sha256"]]
    return VerifyReport(ok=not bad and bool(m["partitions"]), checked=len(m["partitions"]), bad=bad)


def restore_script(manifest: dict, include_critical: bool = False) -> str:
    # Onyx removed fastboot flash/boot/erase on this device: restore goes through EDL.
    lines = ["#!/bin/sh",
             "# Restore via Qualcomm EDL. Start this, then `adb reboot edl` (or vol up+down while plugging USB).",
             "# Run outside any sandbox that hides USB from libusb. Generated by booxctl.",
             "set -e", 'cd "$(dirname "$0")"',
             'EDL="${EDL:-$HOME/boox-backups/tools/edlvenv/bin/edl}"',
             'LOADER="${LOADER:-$HOME/boox-backups/tools/loaders/poke6.bin}"']
    chosen = [e for e in manifest["partitions"] if include_critical or not CRITICAL.match(e["name"])]
    for e in chosen:
        n, f = e["name"], e.get("file", f"{e['name']}.img")
        if not SAFE_NAME.match(n) or not SAFE_FILE.match(f) or ".." in f or not re.fullmatch(r"[0-9a-f]{64}", e["sha256"]):
            raise BackupError(f"unsafe partition name, path or hash in manifest: {n!r} {f!r}")
    lines.append("# Verify every image before the first write; set -e aborts on a mismatch.")
    lines.append("shasum -a 256 -c - <<'SHA256'")
    lines += [f"{e['sha256']}  {e.get('file', e['name'] + '.img')}" for e in chosen]
    lines.append("SHA256")
    for e in manifest["partitions"]:
        n = e["name"]
        if CRITICAL.match(n) and not include_critical:
            lines.append(f"# skipped critical: {n}")
            continue
        f = e.get("file", f"{n}.img")
        if not SAFE_NAME.match(n) or not SAFE_FILE.match(f) or ".." in f:
            raise BackupError(f"unsafe partition name or path in manifest: {n!r} {f!r}")
        lines.append(f'"$EDL" w {shlex.quote(n)} {shlex.quote(f)} --memory=ufs --loader="$LOADER"')
    lines.append('"$EDL" reset')
    return "\n".join(lines) + "\n"
