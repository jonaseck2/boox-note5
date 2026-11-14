import os
from pathlib import Path

import pytest

from booxctl import lp

SUPER = Path.home() / "boox-backups/2026-11-08/edl/rl/lun0/super.bin"
real = pytest.mark.skipif(not SUPER.exists(), reason="needs the EDL super backup")


@real
def test_roundtrip_real_metadata_slot1():
    raw = lp.read_slot(SUPER, 1)
    meta = lp.parse(raw)
    assert [p["name"] for p in meta["partitions"]] == ["system_b", "system_ext_b", "product_b", "vendor_b", "system_b-cow"]
    assert lp.serialize(meta) == raw[:len(lp.serialize(meta))]


@real
def test_rebuild_for_gsi_keeps_vendor_and_fits():
    meta = lp.parse(lp.read_slot(SUPER, 1))
    vendor_before = lp.extents_of(meta, "vendor_b")
    new = lp.rebuild_for_gsi(meta, system_bytes=3272933376, super_sectors=lp.super_sectors(SUPER))
    names = [p["name"] for p in new["partitions"]]
    assert names == ["system_b", "vendor_b"]
    assert lp.extents_of(new, "vendor_b") == vendor_before
    sysx = lp.extents_of(new, "system_b")
    assert sum(n for n, _ in sysx) * 512 >= 3272933376
    used = sorted([(s, s + n) for n, s in sysx + vendor_before])
    assert all(a[1] <= b[0] for a, b in zip(used, used[1:])), "extents overlap"
    assert used[0][0] >= 2048 and used[-1][1] <= lp.super_sectors(SUPER)
    assert lp.parse(lp.serialize(new))["partitions"][0]["name"] == "system_b"


def test_rebuild_refuses_when_too_big():
    meta = {"major": 10, "minor": 2, "header_size": 256, "flags": 1, "partitions": [
        {"name": "vendor_b", "attributes": 1, "group_index": 1, "extents": [(100, 2048)]}],
        "groups": [{"name": "default", "flags": 0, "maximum_size": 0}, {"name": "qti_dynamic_partitions_b", "flags": 0, "maximum_size": 1 << 40}],
        "block_devices": [{"first_logical_sector": 2048, "alignment": 0, "alignment_offset": 0, "size": 4096 * 512, "name": "super", "flags": 0}]}
    with pytest.raises(lp.LpError):
        lp.rebuild_for_gsi(meta, system_bytes=10 << 30, super_sectors=4096)


def _synthetic_super(path, sectors=4096):
    import hashlib, struct
    g = bytearray(52)
    struct.pack_into("<II", g, 0, 0x616C4467, 52)
    struct.pack_into("<III", g, 40, 4096, 3, 4096)
    z = bytearray(g); z[8:40] = b"\0" * 32; g[8:40] = hashlib.sha256(z).digest()
    meta = {"major": 10, "minor": 2, "header_size": 256, "flags": 1,
            "partitions": [{"name": "system_b", "attributes": 1, "group_index": 1, "extents": [(64, 2048)]},
                           {"name": "vendor_b", "attributes": 1, "group_index": 1, "extents": [(64, 3000)]}],
            "groups": [{"name": "default", "flags": 0, "maximum_size": 0}, {"name": "qti_dynamic_partitions_b", "flags": 0, "maximum_size": 0}],
            "block_devices": [{"first_logical_sector": 2048, "alignment": 0, "alignment_offset": 0, "size": sectors * 512, "name": "super", "flags": 0}]}
    buf = bytearray(sectors * 512)
    buf[4096:4096 + 52] = g; buf[8192:8192 + 52] = g
    m = lp.serialize(meta)
    for slot in range(3):
        for off in (12288 + slot * 4096, 12288 + 3 * 4096 + slot * 4096):
            buf[off:off + len(m)] = m
    buf[3000 * 512:3064 * 512] = b"V" * (64 * 512)
    path.write_bytes(bytes(buf))


def test_build_super_writes_image_and_keeps_vendor(tmp_path):
    src, img, out = tmp_path / "super.bin", tmp_path / "sys.img", tmp_path / "new.bin"
    _synthetic_super(src)
    img.write_bytes(bytes(range(256)) * (200 * 512 // 256))  # 200 sectors
    lp.build_super(src, img, out)
    meta = lp.parse(lp.read_slot(out, 1))
    assert [p["name"] for p in meta["partitions"]] == ["system_b", "vendor_b"]
    assert lp.read_partition(out, meta, "system_b")[:img.stat().st_size] == img.read_bytes()
    assert lp.read_partition(out, meta, "vendor_b") == b"V" * (64 * 512)
    # backup copy of slot 1 matches primary
    p, b, m = lp.slot_offsets(out, 1)
    data = out.read_bytes()
    assert data[p:p + m] == data[b:b + m]
