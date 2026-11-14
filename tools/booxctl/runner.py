import os
import subprocess
from dataclasses import dataclass


@dataclass
class Result:
    returncode: int
    stdout: bytes
    stderr: bytes


class Runner:
    """Runs host commands. Tests replace it with a fake."""

    def env(self) -> dict:
        e = dict(os.environ)
        e["ADB_LIBUSB"] = "1"
        return e

    def run(self, argv, *, input=None, timeout=120, env=None) -> Result:
        p = subprocess.run(argv, input=input, capture_output=True, timeout=timeout,
                           env=env or self.env())
        return Result(p.returncode, p.stdout, p.stderr)
