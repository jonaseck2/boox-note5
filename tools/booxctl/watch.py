"""Continuous monitoring of the tablet over adb-over-Wi-Fi.

Loop: keep `adb connect host:5555` alive; log every up/down transition; stream crash-relevant
logcat lines; after each (re)connect, pull panic logs the module saved from pstore
(/data/adb/boox_crash/<stamp>/, see device/epdcshim/module/post-fs-data.sh) and the guard log.
Everything lands in <out>/events.log, <out>/logcat.log and <out>/crash/<stamp>/.
"""
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Lines worth keeping from a full logcat: fatal signals, ANRs, the shim, SF/composer, input, power.
INTERESTING = re.compile(
    r"( F |FATAL|boox-touch|Fatal signal|ANR in|tombstone|libbooxepdc|epdc|SurfaceFlinger|composer|"
    r"DisplayPowerController|PowerManagerService.*(sleep|wake)|am_crash|am_anr|lowmemorykiller|"
    r"WindowManager.*(Display|Dozing))", re.I)


def new_dirs(remote_listing: str, have: set[str]) -> list[str]:
    """Crash dirs on the device (one name per line) not yet pulled."""
    names = [n.strip() for n in remote_listing.splitlines()]
    return sorted(n for n in names if re.fullmatch(r"\d{8}-\d{6}", n) and n not in have)


class Watch:
    def __init__(self, host: str, out: Path, adb: str = "adb"):
        self.target = host if ":" in host else f"{host}:5555"
        self.out = Path(out)
        self.adb_bin = adb
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "crash").mkdir(exist_ok=True)
        self.logcat = None

    def event(self, msg: str):
        line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
        print(line, flush=True)
        with open(self.out / "events.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def adb(self, *args, timeout=30):
        try:
            return subprocess.run([self.adb_bin, "-s", self.target, *args], capture_output=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def up(self) -> bool:
        r = self.adb("shell", "echo ok", timeout=10)
        if r is not None and r.returncode == 0 and b"ok" in r.stdout:
            return True
        subprocess.run([self.adb_bin, "connect", self.target], capture_output=True, timeout=15)
        r = self.adb("shell", "echo ok", timeout=10)
        return r is not None and r.returncode == 0 and b"ok" in r.stdout

    def su(self, cmd: str) -> str:
        r = self.adb("shell", f"/debug_ramdisk/su -c '{cmd}'")
        return r.stdout.decode(errors="replace") if r else ""

    def harvest(self):
        have = {p.name for p in (self.out / "crash").iterdir()}
        for d in new_dirs(self.su("ls -1 /data/adb/boox_crash"), have):
            dst = self.out / "crash" / d
            dst.mkdir()
            self.su(f"mkdir -p /data/local/tmp/bc && cp -r /data/adb/boox_crash/{d}/. /data/local/tmp/bc/ "
                    f"&& chmod -R 644 /data/local/tmp/bc/*")
            self.adb("pull", "/data/local/tmp/bc/.", str(dst), timeout=60)
            self.su("rm -rf /data/local/tmp/bc")
            text = "".join(p.read_text(errors="replace") for p in dst.iterdir() if p.is_file())
            cause = next((l.strip() for l in text.splitlines()
                          if re.search(r"Kernel panic|Unable to handle|BUG:|Internal error", l)), "?")
            self.event(f"PANIC LOG {d}: {cause}")
        (self.out / "guard.log").write_text(self.su("cat /data/adb/boox_guard.log"), encoding="utf-8")
        boot = self.adb("shell", "cat /proc/uptime")
        if boot and boot.returncode == 0:
            self.event(f"uptime {boot.stdout.decode().split()[0]}s")

    def start_logcat(self):
        if self.logcat and self.logcat.poll() is None:
            return
        self.logcat = subprocess.Popen([self.adb_bin, "-s", self.target, "logcat", "-v", "time",
                                        "-b", "main,system,crash,events", "-T", "1"],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def drain_logcat(self, budget_s: float):
        # Blocking readline on a pipe; good enough: logcat emits steadily while the device is up.
        end = time.time() + budget_s
        with open(self.out / "logcat.log", "a", encoding="utf-8") as f:
            while time.time() < end and self.logcat and self.logcat.poll() is None:
                line = self.logcat.stdout.readline().decode(errors="replace")
                if not line:
                    break
                if INTERESTING.search(line):
                    f.write(line)
                    f.flush()
                    if re.search(r"Fatal signal|FATAL EXCEPTION|ANR in", line):
                        self.event("APP/NATIVE CRASH: " + line.strip()[:200])
                    elif "boox-touch" in line:
                        self.event("TOUCH RECOVERED: " + line.strip()[:200])

    def run(self, poll_s: float = 5):
        was_up = None
        down_since = None
        while True:
            ok = self.up()
            if ok and was_up is not True:
                gap = f" after {int(time.time() - down_since)}s down" if down_since else ""
                self.event(f"UP {self.target}{gap}")
                self.harvest()
                self.start_logcat()
            elif not ok and was_up is not False:
                down_since = time.time()
                self.event(f"DOWN {self.target}")
                if self.logcat:
                    self.logcat.kill()
            was_up = ok
            if ok:
                self.drain_logcat(poll_s)
            else:
                time.sleep(poll_s)
