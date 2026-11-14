import hashlib
import json

from booxctl import backup
from booxctl.backup import Partition, restore_script, verify


def _sha(b):
    return hashlib.sha256(b).hexdigest()


class FakeDev:
    """Device double for backup: partitions with byte contents."""

    def __init__(self, parts):
        self.parts = parts
        self.dumped = []

    def list_partitions(self):
        return [Partition(n, len(b)) for n, b in self.parts.items()]

    def device_sha256(self, name):
        return _sha(self.parts[name])

    def read_partition(self, name, local):
        self.dumped.append(name)
        local.write_bytes(self.parts[name])


def test_dump_skips_userdata(tmp_path):
    dev = FakeDev({"boot_a": b"A" * 10, "userdata": b"U" * 10})
    m = backup.dump(dev, tmp_path)
    assert [e["name"] for e in m["partitions"]] == ["boot_a"]
    assert "userdata" not in dev.dumped


def test_backup_skips_verified_and_redoes_partial(tmp_path):
    dev = FakeDev({"boot_a": b"A" * 10, "dtbo_a": b"D" * 10})
    backup.dump(dev, tmp_path)
    (tmp_path / "dtbo_a.img").write_bytes(b"D" * 4)  # partial
    dev.dumped.clear()
    backup.dump(dev, tmp_path)
    assert dev.dumped == ["dtbo_a"]


def test_verify_flags_hash_mismatch(tmp_path):
    dev = FakeDev({"boot_a": b"A" * 10, "dtbo_a": b"D" * 10})
    backup.dump(dev, tmp_path)
    (tmp_path / "boot_a.img").write_bytes(b"X" * 10)
    rep = verify(tmp_path)
    assert not rep.ok
    assert rep.bad == ["boot_a"]


def test_dump_raises_when_device_and_local_hash_differ(tmp_path):
    dev = FakeDev({"boot_a": b"A" * 10})
    dev.device_sha256 = lambda n: "0" * 64
    import pytest
    with pytest.raises(backup.BackupError):
        backup.dump(dev, tmp_path)


def test_restore_excludes_critical_by_default(tmp_path):
    m = {"partitions": [{"name": n, "size": 1, "sha256": "0" * 64} for n in
                        ["boot_a", "xbl_a", "abl_b", "tz_a", "super", "vbmeta_b"]]}
    s = restore_script(m)
    assert "\"$EDL\" w boot_a " in s and "\"$EDL\" w vbmeta_b " in s
    for c in ["xbl_a", "abl_b", "tz_a"]:
        assert f"\"$EDL\" w {c} " not in s
    s2 = restore_script(m, include_critical=True)
    assert "\"$EDL\" w xbl_a " in s2
    assert "fastboot" not in s


def test_backup_redoes_same_size_corrupt_image(tmp_path):
    dev = FakeDev({"boot_a": b"A" * 10})
    backup.dump(dev, tmp_path)
    (tmp_path / "boot_a.img").write_bytes(b"Z" * 10)
    dev.dumped.clear()
    backup.dump(dev, tmp_path)
    assert dev.dumped == ["boot_a"]


def _rawprogram(d, lun, entries):
    xml = "<data>" + "".join(
        f'<program SECTOR_SIZE_IN_BYTES="4" filename="{f}" label="{l}" num_partition_sectors="{n}"/>'
        for f, l, n in entries) + "</data>"
    (d / f"lun{lun}" / f"rawprogram{lun}.xml").write_text(xml)


def test_import_edl_builds_manifest_and_verifies(tmp_path):
    (tmp_path / "lun4").mkdir()
    (tmp_path / "lun4" / "boot_b.bin").write_bytes(b"B" * 8)
    (tmp_path / "lun0").mkdir()
    (tmp_path / "lun0" / "super.bin").write_bytes(b"S" * 4)
    _rawprogram(tmp_path, 4, [("boot_b.bin", "boot_b", 2)])
    _rawprogram(tmp_path, 0, [("super.bin", "super", 1)])
    m = backup.import_edl(tmp_path)
    names = sorted(e["name"] for e in m["partitions"])
    assert names == ["boot_b", "super"]
    assert verify(tmp_path).ok
    (tmp_path / "lun4" / "boot_b.bin").write_bytes(b"X" * 8)
    assert verify(tmp_path).bad == ["boot_b"]


def test_restore_script_rejects_unsafe_partition_names():
    import pytest
    m = {"partitions": [{"name": "boot_a; rm -rf ~", "size": 1, "sha256": "0" * 64}]}
    with pytest.raises(backup.BackupError):
        restore_script(m)



def test_import_edl_rejects_truncated_image(tmp_path):
    import pytest
    (tmp_path / "lun0").mkdir()
    (tmp_path / "lun0" / "super.bin").write_bytes(b"S" * 4)
    _rawprogram(tmp_path, 0, [("super.bin", "super", 4)])  # expects 16 bytes
    with pytest.raises(backup.BackupError):
        backup.import_edl(tmp_path)


def test_import_edl_rejects_image_missing_from_rawprogram(tmp_path):
    import pytest
    (tmp_path / "lun0").mkdir()
    (tmp_path / "lun0" / "super.bin").write_bytes(b"S" * 4)
    with pytest.raises(backup.BackupError):
        backup.import_edl(tmp_path)


def test_restore_script_checks_hashes_before_writing():
    m = {"partitions": [{"name": "boot_a", "size": 1, "sha256": "ab" * 32, "file": "lun4/boot_a.bin"}]}
    s = restore_script(m)
    assert "ab" * 32 + "  lun4/boot_a.bin" in s
    assert s.index("shasum -a 256 -c") < s.index('"$EDL" w boot_a')


def test_list_partitions_fails_on_unparsable_or_empty(fake):
    import pytest
    from booxctl.device import Device
    fake.on("su -c", stdout=b"boot_a 100\nsuper blockdev: permission denied\n")
    with pytest.raises(backup.BackupError):
        backup.DeviceBackup(Device(fake)).list_partitions()
    fake.script.clear(); fake.on("su -c", stdout=b"")
    with pytest.raises(backup.BackupError):
        backup.DeviceBackup(Device(fake)).list_partitions()
