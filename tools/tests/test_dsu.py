import struct

from booxctl import dsu
from booxctl.device import Device


def test_install_intent_has_sizes(fake):
    dsu.install(Device(fake), "/sdcard/Download/system_raw.gz", 3387408384, userdata_bytes=8 << 30)
    joined = [" ".join(c) for c in fake.calls]
    cmd = next(j for j in joined if "android.os.image.action.START_INSTALL" in j)
    assert "--el KEY_SYSTEM_SIZE 3387408384" in cmd
    assert "--el KEY_USERDATA_SIZE 8589934592" in cmd
    assert "file:///sdcard/Download/system_raw.gz" in cmd


def _sparse(blk=4096):
    hdr = struct.pack("<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, blk, 3, 2, 0)
    raw = struct.pack("<HHII", 0xCAC1, 0, 1, 12 + blk) + b"A" * blk
    fill = struct.pack("<HHII", 0xCAC2, 0, 2, 16) + b"\x01\x02\x03\x04"
    return hdr + raw + fill


def test_sparse_image_converted_to_raw(tmp_path):
    src = tmp_path / "s.img"; src.write_bytes(_sparse())
    out = tmp_path / "r.img"
    dsu.unsparse(src, out)
    data = out.read_bytes()
    assert len(data) == 3 * 4096
    assert data[:4096] == b"A" * 4096
    assert data[4096:] == b"\x01\x02\x03\x04" * 2048


def test_raw_image_passes_through(tmp_path):
    src = tmp_path / "r.img"; src.write_bytes(b"\x00" * 8192)
    assert dsu.is_sparse(src) is False


def test_boot_reboots_without_gsi_tool_enable(fake):
    fake.on("gsi_tool status", stdout=b"normal\n[0] dsu\ninstalled: system_gsi\n")
    dsu.boot(Device(fake))
    joined = [" ".join(c) for c in fake.calls]
    assert not any("gsi_tool enable" in j for j in joined)
    assert any("ACTION_REBOOT_TO_DYN_SYSTEM" in j for j in joined)
