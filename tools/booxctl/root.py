"""Temporary root: Magisk-patched boot image booted with `fastboot boot` (nothing is flashed)."""
import hashlib
import os
import re
import time
import zipfile
from pathlib import Path

MAGISK_VERSION = "v31.1"
MAGISK_SHA256 = "89cefac0a318afa39fb3880c45c87b036c05bc1ebf02a7a715b7f8d7c26ac6e7"
MAGISK_URL = f"https://github.com/topjohnwu/Magisk/releases/download/{MAGISK_VERSION}/Magisk-{MAGISK_VERSION}.apk"
REMOTE = "/data/local/tmp/mg"
APK_FILES = {
    "lib/arm64-v8a/libmagiskboot.so": "magiskboot",
    "lib/arm64-v8a/libmagiskinit.so": "magiskinit",
    "lib/arm64-v8a/libmagisk.so": "magisk",
    "lib/arm64-v8a/libinit-ld.so": "init-ld",
    "lib/arm64-v8a/libbusybox.so": "busybox",
    "assets/boot_patch.sh": "boot_patch.sh",
    "assets/util_functions.sh": "util_functions.sh",
}


class RootError(RuntimeError):
    pass


def magisk_apk(cache: Path) -> Path:
    apk = Path(cache) / f"Magisk-{MAGISK_VERSION}.apk"
    if not apk.exists():
        import urllib.request
        apk.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MAGISK_URL, apk)
    if hashlib.sha256(apk.read_bytes()).hexdigest() != MAGISK_SHA256:
        raise RootError(f"{apk}: sha256 mismatch")
    return apk


def patch_boot(dev, stock: Path, out: Path, cache: Path) -> Path:
    """Patch `stock` on the device as the shell user with Magisk's boot_patch.sh."""
    apk = magisk_apk(cache)
    staging = Path(out).parent / "mg-staging"
    staging.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as z:
        for src, dst in APK_FILES.items():
            (staging / dst).write_bytes(z.read(src))
    dev.shell(f"rm -rf {REMOTE} && mkdir -p {REMOTE}")
    for f in staging.iterdir():
        dev.push(f, f"{REMOTE}/{f.name}")
    dev.push(Path(stock), f"{REMOTE}/boot.img")
    log = dev.shell(f"cd {REMOTE} && chmod 755 * && ./busybox sh boot_patch.sh boot.img 2>&1; echo rc=$?", timeout=600)
    if "rc=0" not in log or "new-boot.img" not in dev.shell(f"ls {REMOTE}"):
        raise RootError(f"boot_patch.sh failed:\n{log[-2000:]}")
    dev.pull(f"{REMOTE}/new-boot.img", Path(out))
    return Path(out)


def grant_shell_su(dev, timeout: float = 60):
    """First `su` from the shell makes Magisk show a grant prompt. Tap Grant via uiautomator."""
    dev.adb("shell", "su -c true", check=False, timeout=5)
    end = time.time() + timeout
    while time.time() < end:
        xml = dev.shell("uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; cat /sdcard/ui.xml")
        m = re.search(r'text="(?:Grant|GRANT|Allow|ALLOW)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            dev.shell(f"input tap {(x1 + x2) // 2} {(y1 + y2) // 2}")
            return
        dev.adb("shell", "su -c true", check=False, timeout=5)
        time.sleep(2)
    raise RootError("Magisk grant prompt not found")


def temp_root(dev, patched: Path) -> None:
    dev.reboot("bootloader")
    dev.wait_for("bootloader", timeout=120)
    dev.fastboot("boot", str(patched))
    dev.wait_for("device", timeout=300)
    grant_shell_su(dev)
    if "uid=0" not in dev.su("id"):
        raise RootError("su did not return uid=0")
