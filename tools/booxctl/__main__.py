import argparse
import sys
from pathlib import Path

from . import camera
from .device import Device
from .runner import Runner


def backup_root() -> Path:
    import datetime
    import os
    base = Path(os.environ.get("BOOX_BACKUP_DIR", Path.home() / "boox-backups"))
    return base / datetime.date.today().isoformat()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="booxctl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shot", help="screencap + camera frame")
    s.add_argument("dir", type=Path)
    e = sub.add_parser("export-sdcard", help="copy /sdcard to the Mac")
    e.add_argument("dest", type=Path, nargs="?")
    b = sub.add_parser("backup", help="partition backup")
    b.add_argument("action", choices=["dump", "verify", "restore-script", "import-edl"])
    b.add_argument("dest", type=Path, nargs="?")
    b.add_argument("--include-critical", action="store_true")
    pc = sub.add_parser("calibrate", help="store camera panel corners from a white Settings screen")
    pc.add_argument("out", type=Path, nargs="?")
    pd = sub.add_parser("dsu", help="boot a GSI via Dynamic System Updates (stock stays untouched)")
    pd.add_argument("action", choices=["prepare", "install", "status", "boot", "discard"])
    pd.add_argument("zip", type=Path, nargs="?")
    pe = sub.add_parser("epd", help="e-ink control")
    pe.add_argument("action", choices=["probe", "mode", "clean"])
    pe.add_argument("value", nargs="?")
    pe.add_argument("--corners", type=Path, help="JSON 4 panel corners from a white-screen calibration")
    pf = sub.add_parser("flicker", help="record the panel during an adb action and score flicker")
    pf.add_argument("dir", type=Path)
    pf.add_argument("--action", default="", help="adb shell command run 3.5 s into the recording (ffmpeg needs ~2 s to start)")
    pf.add_argument("--seconds", type=float, default=7.0)
    pt = sub.add_parser("tap", help="tap the on-screen element with this text or content-desc")
    pt.add_argument("text")
    pr = sub.add_parser("release", help="build (and publish) a glue release bundle")
    pr.add_argument("kind", choices=["glue"])
    pr.add_argument("--version", required=True, help="YYYY.MM.DD.N")
    pr.add_argument("--publish", action="store_true", help="create GitHub Release glue-v<version>")
    pr.add_argument("--repo", default="jonaseck2/boox-note5")
    pu = sub.add_parser("update", help="install a glue release on the tablet (verify, precheck, install, reboot, post-check)")
    pu.add_argument("kind", choices=["glue"])
    g = pu.add_mutually_exclusive_group(required=True)
    g.add_argument("--tag", help="GitHub release tag, e.g. glue-v2026.11.14.1")
    g.add_argument("--bundle", type=Path, help="local boox-glue-<version>.zip (with its .sha256 next to it)")
    pu.add_argument("--repo", default="jonaseck2/boox-note5")
    pw = sub.add_parser("wallpaper", help="install an e-ink wallpaper (default: The Great Wave, light print); reboots")
    pw.add_argument("which", nargs="?", default="wave", choices=["wave", "white"])
    pa = sub.add_parser("audit", help="visual-style audit: predicted panel contrast of every element on ~24 screens")
    pa.add_argument("dir", type=Path)
    a = ap.parse_args(argv)
    dev = None if a.cmd == "release" else Device(Runner())   # release needs no tablet (CI)
    if a.cmd == "audit":
        from . import audit
        audit.run(dev, a.dir)
        return 0
    if a.cmd == "wallpaper":
        import tempfile
        from . import wallpaper
        d = Path(tempfile.mkdtemp(prefix="boox-wp-"))
        if a.which == "wave":
            png = wallpaper.light_print(wallpaper.fetch_wave(d / "wave.jpg"), d / "wave.png")
        else:
            import numpy as np, cv2
            png = d / "white.png"
            cv2.imwrite(str(png), np.full((1404, 1872, 3), 255, np.uint8))
        wallpaper.install(dev, png)
        dev.reboot()
        print(f"{a.which} wallpaper installed; rebooting to apply")
        return 0
    if a.cmd == "update":
        import tempfile
        from . import update
        bundle = a.bundle or update.fetch(a.tag, a.repo, Path(tempfile.mkdtemp(prefix="boox-dl-")))
        return 0 if update.update_glue(dev, bundle, Path(__file__).resolve().parents[2]) else 1
    if a.cmd == "release":
        import subprocess
        from . import release
        release.version_code(a.version)
        root = Path(__file__).resolve().parents[2]
        z = release.build_glue_bundle(root, root / "dist", a.version)
        print(z)
        if a.publish:
            tag = f"glue-v{a.version}"
            subprocess.run(["gh", "release", "create", tag, "-R", a.repo, "--title", f"Glue {a.version}",
                            "--notes", "E-ink glue bundle (display shim, Magisk module scripts, e-ink settings). "
                            "Install from the Mac: `booxctl update glue --tag " + tag + "`.",
                            str(z), str(z) + ".sha256"], check=True)
        return 0
    if a.cmd == "tap":
        from . import ui
        ok = ui.tap_text(dev, a.text)
        print("tapped" if ok else f"not found: {a.text}")
        return 0 if ok else 1
    if a.cmd == "flicker":
        from . import flicker
        import json
        cf = Path.home() / "boox-backups" / "camera-corners.json"
        corners = json.loads(cf.read_text()) if cf.exists() else None
        print(flicker.run(dev, a.dir, a.action, a.seconds, corners=corners))
        return 0
    if a.cmd == "shot":
        a.dir.mkdir(parents=True, exist_ok=True)
        dev.screencap(a.dir / "screen.png")
        camera.capture(a.dir / "camera.jpg")
        print(a.dir / "screen.png", a.dir / "camera.jpg")
    elif a.cmd == "export-sdcard":
        from .export import export_sdcard
        dest = a.dest or backup_root() / "sdcard"
        rep = export_sdcard(dev, dest)
        print(f"OK {rep.files} files, {rep.bytes} bytes -> {dest}")
    elif a.cmd == "backup":
        import json
        from . import backup
        dest = a.dest or backup_root() / "partitions"
        if a.action == "dump":
            m = backup.dump(backup.DeviceBackup(dev), dest)
            print(f"dumped {len(m['partitions'])} partitions -> {dest}")
        elif a.action == "import-edl":
            m = backup.import_edl(dest)
            print(f"imported {len(m['partitions'])} partitions -> {dest / 'manifest.json'}")
        elif a.action == "verify":
            rep = backup.verify(dest)
            print(f"OK {rep.checked} partitions" if rep.ok else f"FAIL bad={rep.bad} checked={rep.checked}")
            return 0 if rep.ok else 1
        else:
            m = json.loads((dest / "manifest.json").read_text())
            sys.stdout.write(backup.restore_script(m, a.include_critical))
    elif a.cmd == "calibrate":
        from . import vision, epd
        out = a.out or Path.home() / "boox-backups" / "camera-corners.json"
        dev.shell("am force-stop com.android.settings; am start -n com.android.settings/.Settings >/dev/null 2>&1; sleep 3")
        epd.full_refresh(dev)
        import time; time.sleep(2.5)
        frame = camera.capture(out.with_suffix(".jpg"))
        print("corners", vision.save_calibration(frame, out), "->", out)
    elif a.cmd == "dsu":
        from . import dsu
        if a.action in ("prepare", "install"):
            gz, size = dsu.prepare(a.zip, a.zip.parent / "dsu")
            print(f"prepared {gz} raw_size={size}")
            if a.action == "install":
                remote = "/sdcard/Download/system_raw.gz"
                dev.push(gz, remote, timeout=3600)
                dsu.install(dev, remote, size)
                print("install started; poll: booxctl dsu status")
        elif a.action == "status":
            print(dsu.status(dev))
        elif a.action == "boot":
            dsu.boot(dev); print("rebooting into GSI")
        else:
            print(dsu.discard(dev))
    elif a.cmd == "epd":
        from . import epd
        if a.action == "mode":
            epd.set_mode(dev, a.value); print(f"mode {a.value} = {epd.MODES[a.value]}")
        elif a.action == "clean":
            epd.full_refresh(dev); print("full refresh")
        else:
            import json
            default = Path.home() / "boox-backups" / "camera-corners.json"
            corners = json.loads((a.corners or default).read_text()) if (a.corners or default.exists()) else None
            ebc = Path(__file__).resolve().parents[2] / "device" / "ebcctl" / "ebcctl"
            r = epd.probe(dev, backup_root() / "epd-probe", corners, ebc)
            print(f"full_refresh: {'VISIBLE' if r['full_refresh'] else 'NOT_VISIBLE'} (swing {r['flash_swing']:.0f})")
            print(f"mode_switch: {'VISIBLE' if r['mode_switch'] else 'NOT_VISIBLE'} (scroll diff {r['scroll_diff']})")
            return 0 if r["full_refresh"] and r["mode_switch"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
