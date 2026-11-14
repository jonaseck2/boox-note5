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


BEFORE = """-r--r----- 1 system log  131060 1970-01-01 03:19 console-ramoops-0
-r--r--r-- 1 root   root 131036 2026-11-14 16:08 dmesg-ramoops-1
-r--r----- 1 system log  131060 1970-01-01 03:19 pmsg-ramoops-0
"""


def test_normal_reboot_is_not_a_panic():
    after = BEFORE.replace("03:19", "03:25")          # console/pmsg rotate on every boot
    assert update.new_panics(BEFORE, after) == []


def test_new_dmesg_record_is_a_panic():
    after = BEFORE + "-r--r--r-- 1 root   root 131036 2026-11-14 18:30 dmesg-ramoops-0\n"
    assert update.new_panics(BEFORE, after) == ["dmesg-ramoops-0"]
