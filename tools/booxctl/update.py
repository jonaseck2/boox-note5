"""`booxctl update glue`: install an e-ink glue release from the Mac (design: docs/plans/2026-11-14-ota-design.md).

Order: verify the bundle -> precheck the way back -> install through device/epdcshim/install.sh ->
e-ink settings -> reboot -> post-check. A new shim takes effect only after the reboot (the composer maps it).
The way back if the new shim is bad: the boot guard restores libbooxepdc.so.prev after 3 unhealthy boots.
"""
import os
import subprocess
import tempfile
import time
from pathlib import Path

from . import release

MODULE = "/data/adb/modules/boox_epdc"


def precheck(dev) -> list:
    """Problems that make an update unsafe; empty list = OK."""
    probs = []
    try:
        if "uid=0" not in dev.su("id"):
            probs.append("no root shell (/debug_ramdisk/su)")
    except Exception as e:  # RootRequired, DeviceError
        probs.append(f"no root shell: {e}")
    if dev.getprop("init.svc.boox_composer") != "running":
        probs.append("boox_composer is not running: the boot image lacks the shimmed composer service")
    try:
        n = dev.su(f"grep -c boox_boot_count {MODULE}/post-fs-data.sh || true").strip()
        if not n.isdigit() or int(n) == 0:
            probs.append("boot guard missing in the installed module: install the current glue over USB first")
    except Exception as e:
        probs.append(f"cannot read the installed module: {e}")
    return probs


def _pstore(dev) -> str:
    return dev.su("ls -l /sys/fs/pstore/ 2>/dev/null || true")


def new_panics(before: str, after: str) -> list:
    """Kernel panic records (pstore dmesg-ramoops-*) present after but not before. console-/pmsg-ramoops
    hold the previous boot's logs and change on every boot, so they are not panic evidence."""
    def recs(listing):
        return {" ".join(l.split()[-3:]) for l in listing.splitlines() if "dmesg-ramoops" in l}
    return sorted(r.split()[-1] for r in recs(after) - recs(before))


def wait_booted(dev, timeout: float = 180) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if dev.state() == "device" and dev.getprop("sys.boot_completed") == "1":
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def postcheck(dev, version: str, pstore_before: str) -> list:
    probs = []
    if dev.getprop("init.svc.boox_composer") != "running":
        probs.append("boox_composer not running after reboot")
    prop = dev.su(f"cat {MODULE}/module.prop")
    if f"version={version}" not in prop:
        probs.append(f"module.prop does not show version={version}")
    maps = dev.su("grep -c libbooxepdc /proc/$(pidof vendor.qti.hardware.display.composer-service)/maps || true").strip()
    if not maps.isdigit() or int(maps) == 0:
        probs.append("composer does not map libbooxepdc.so")
    panics = new_panics(pstore_before, _pstore(dev))
    if panics:
        probs.append(f"new kernel panic record(s) {panics} during the update boot (see /sys/fs/pstore)")
    return probs


def fetch(tag: str, repo: str, out_dir: Path) -> Path:
    subprocess.run(["gh", "release", "download", tag, "-R", repo, "-D", str(out_dir), "--clobber"], check=True)
    zips = sorted(out_dir.glob("boox-glue-*.zip"))
    if len(zips) != 1:
        raise RuntimeError(f"expected one boox-glue zip in release {tag}, found {[z.name for z in zips]}")
    return zips[0]


def update_glue(dev, bundle: Path, repo_root: Path, log=print) -> bool:
    work = Path(tempfile.mkdtemp(prefix="boox-glue-"))
    manifest = release.verify_bundle(bundle, work)          # raises before any device write
    version = manifest["version"]
    release.version_code(version)
    log(f"bundle {bundle.name}: version {version}, {len(manifest['files'])} files verified")
    probs = precheck(dev)
    if probs:
        for p in probs:
            log(f"precheck FAILED: {p}")
        return False
    log("precheck OK")
    before = _pstore(dev)
    env = {**os.environ, "SRC": str(work), "VERSION": version, "BOOX_SERIAL": dev.serial}
    subprocess.run([str(repo_root / "device/epdcshim/install.sh")], env=env, check=True, capture_output=True)
    subprocess.run(["sh", str(work / "eink-settings.sh"), dev.serial], env=env, check=True, capture_output=True)
    log("installed; rebooting")
    dev.reboot()
    time.sleep(5)
    if not wait_booted(dev):
        log("post-check FAILED: no boot within 180 s. The boot guard restores the previous shim after 3 "
            "unhealthy boots; the last resort is the EDL cable (device/recover-edl.sh adb).")
        return False
    time.sleep(10)
    probs = postcheck(dev, version, before)
    for p in probs:
        log(f"post-check FAILED: {p}")
    if not probs:
        log(f"post-check OK: glue {version} running")
    return not probs
