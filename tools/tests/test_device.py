from pathlib import Path

import pytest

from booxctl.device import Device, RootRequired
from booxctl.runner import Result, Runner


def test_runner_always_passes_serial(fake, tmp_path):
    dev = Device(fake, serial="TESTSERIAL1")
    dev.shell("true")
    dev.pull("/sdcard/x", tmp_path / "x")
    dev.fastboot("getvar", "all")
    assert len(fake.calls) == 3
    for argv in fake.calls:
        i = argv.index("-s")
        assert argv[i + 1] == "TESTSERIAL1"


def test_su_missing_raises_root_required(fake):
    fake.on("su -c", stderr=b"/system/bin/sh: su: inaccessible or not found\n", returncode=127)
    with pytest.raises(RootRequired):
        Device(fake).su("id")


def test_su_rejected_by_magisk_raises_root_required(fake):
    fake.on("su -c", stderr=b"su: request rejected (2000)\n", returncode=1)
    with pytest.raises(RootRequired):
        Device(fake).su("id")


def test_screencap_writes_to_sdcard_then_pulls(fake, tmp_path):
    Device(fake).screencap(tmp_path / "s.png")
    tails = [" ".join(c[3:]) for c in fake.calls]
    assert tails[0] == "shell screencap -p /sdcard/booxctl.png"
    assert tails[1].startswith("pull /sdcard/booxctl.png")
    assert tails[2] == "shell rm /sdcard/booxctl.png"


def test_adb_env_sets_libusb():
    assert Runner().env()["ADB_LIBUSB"] == "1"


def test_su_falls_back_to_magisk_debug_ramdisk(fake):
    # GSI without Magisk app: no `su` in PATH, but /debug_ramdisk/su works.
    fake.script.append(("shell su -c", Result(127, b"", b"/system/bin/sh: su: inaccessible or not found\n")))
    fake.on("/debug_ramdisk/su -c", stdout=b"uid=0(root)\n")
    assert "uid=0" in Device(fake).su("id")


def test_serial_from_env_wins(monkeypatch, tmp_path):
    from booxctl.device import resolve_serial
    cfg = tmp_path / "serial"; cfg.write_text("FILESERIAL\n")
    monkeypatch.setenv("BOOX_SERIAL", "ENVSERIAL")
    assert resolve_serial(cfg) == "ENVSERIAL"


def test_serial_from_config_file(monkeypatch, tmp_path):
    from booxctl.device import resolve_serial
    cfg = tmp_path / "serial"; cfg.write_text("FILESERIAL\n")
    monkeypatch.delenv("BOOX_SERIAL", raising=False)
    assert resolve_serial(cfg) == "FILESERIAL"


def test_missing_serial_is_an_error(monkeypatch, tmp_path):
    from booxctl.device import resolve_serial, DeviceError
    monkeypatch.delenv("BOOX_SERIAL", raising=False)
    with pytest.raises(DeviceError):
        resolve_serial(tmp_path / "absent")
