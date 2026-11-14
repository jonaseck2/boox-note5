import time
from pathlib import Path

SERIAL_FILE = Path.home() / ".config" / "boox" / "serial"


def resolve_serial(config: Path = SERIAL_FILE) -> str:
    """The tablet's adb serial: $BOOX_SERIAL, else the first line of ~/.config/boox/serial.
    Always pinned, because other adb devices (a TV, an emulator) may be connected."""
    import os
    if os.environ.get("BOOX_SERIAL"):
        return os.environ["BOOX_SERIAL"].strip()
    try:
        s = Path(config).read_text().strip().splitlines()[0].strip()
        if s:
            return s
    except (OSError, IndexError):
        pass
    raise DeviceError(f"no device serial: set BOOX_SERIAL or write it to {config} (see `adb devices`)")


class DeviceError(RuntimeError):
    pass


class RootRequired(DeviceError):
    pass


class Device:
    def __init__(self, runner, serial: str | None = None):
        self.r = runner
        self.serial = serial or resolve_serial()

    def adb(self, *args, check=True, timeout=120, input=None):
        res = self.r.run(["adb", "-s", self.serial, *args], timeout=timeout, input=input)
        if check and res.returncode != 0:
            raise DeviceError(f"adb {' '.join(args)}: rc={res.returncode} "
                              f"{res.stderr.decode(errors='replace')}{res.stdout.decode(errors='replace')}")
        return res

    def shell(self, cmd: str, timeout=120) -> str:
        return self.adb("shell", cmd, timeout=timeout).stdout.decode(errors="replace")

    SU_PATHS = ("su", "/debug_ramdisk/su")  # Magisk without its app (fresh GSI): su only at /debug_ramdisk

    def su(self, cmd: str, timeout=120) -> str:
        quoted = "'" + cmd.replace("'", "'\\''") + "'"
        for su_bin in self.SU_PATHS:
            res = self.adb("shell", f"{su_bin} -c {quoted}", check=False, timeout=timeout)
            if b"inaccessible or not found" not in res.stdout + res.stderr:
                break
        out = res.stdout.decode(errors="replace")
        both = out + res.stderr.decode(errors="replace")
        if res.returncode != 0 and ("su: inaccessible or not found" in both or "su: not found" in both
                                    or "request rejected" in both):
            raise RootRequired("root shell not available (temporary root lost after reboot?)")
        if res.returncode != 0:
            raise DeviceError(f"su {cmd}: rc={res.returncode} {out}{res.stderr.decode(errors='replace')}")
        return out

    def pull(self, remote: str, local: Path, timeout=3600):
        self.adb("pull", remote, str(local), timeout=timeout)

    def push(self, local: Path, remote: str, timeout=600):
        self.adb("push", str(local), remote, timeout=timeout)

    def getprop(self, name: str) -> str:
        return self.shell(f"getprop {name}").strip()

    def screencap(self, local: Path):
        # Stock Onyx screencap prints a debug line to stdout, so exec-out is corrupt.
        remote = "/sdcard/booxctl.png"
        self.shell(f"screencap -p {remote}")
        self.pull(remote, local)
        self.shell(f"rm {remote}")

    def fastboot(self, *args, timeout=300) -> str:
        res = self.r.run(["fastboot", "-s", self.serial, *args], timeout=timeout)
        out = (res.stdout + res.stderr).decode(errors="replace")
        if res.returncode != 0:
            raise DeviceError(f"fastboot {' '.join(args)}: {out}")
        return out

    def reboot(self, target=None):
        self.adb("reboot", *([target] if target else []), check=False)

    def state(self) -> str:
        res = self.r.run(["adb", "devices"])
        for line in res.stdout.decode().splitlines():
            if line.startswith(self.serial):
                return line.split()[1]
        res = self.r.run(["fastboot", "devices"])
        for line in res.stdout.decode().splitlines():
            if line.startswith(self.serial):
                return "fastbootd" if "fastbootd" in line else "bootloader"
        return "absent"

    def wait_for(self, state: str, timeout: float = 180):
        end = time.time() + timeout
        while time.time() < end:
            s = self.state()
            if s == state:
                return
            time.sleep(2)
        raise DeviceError(f"timeout waiting for {state} (last: {self.state()})")
