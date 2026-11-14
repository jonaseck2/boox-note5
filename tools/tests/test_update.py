from booxctl.device import Device
from booxctl import update


def _ok(fake):
    fake.on("su -c 'id'", stdout=b"uid=0(root) gid=0(root)\n")
    fake.on("getprop init.svc.boox_composer", stdout=b"running\n")
    fake.on("boox_boot_count", stdout=b"3\n")
    return fake


def test_precheck_ok(fake):
    assert update.precheck(Device(_ok(fake))) == []


def test_precheck_reports_missing_guard(fake):
    fake.on("boox_boot_count", stdout=b"0\n")
    probs = update.precheck(Device(_ok(fake)))
    assert any("boot guard" in p for p in probs)


def test_precheck_reports_composer_not_running(fake):
    fake.on("getprop init.svc.boox_composer", stdout=b"\n")
    probs = update.precheck(Device(_ok(fake)))
    assert any("boox_composer" in p for p in probs)


def test_precheck_reports_no_root(fake):
    fake.on("su -c 'id'", stdout=b"uid=2000(shell)\n")
    probs = update.precheck(Device(_ok(fake)))
    assert any("root" in p for p in probs)
