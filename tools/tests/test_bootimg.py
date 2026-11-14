import gzip
import struct

from booxctl import bootimg


def _cpio(entries):
    out = b""
    for i, (name, data, mode) in enumerate(entries + [("TRAILER!!!", b"", 0)]):
        nb = name.encode() + b"\0"
        hdr = b"070701" + b"".join(b"%08X" % v for v in (i + 1, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(nb), 0))
        rec = hdr + nb
        rec += b"\0" * (-len(rec) % 4) + data
        rec += b"\0" * (-len(rec) % 4)
        out += rec
    return out


def _boot(tmp_path, ramdisk):
    page = 4096
    kernel = b"K" * 5000
    rd = gzip.compress(ramdisk)
    dtb = b"D" * 300
    h = bytearray(1660)
    h[:8] = b"ANDROID!"
    struct.pack_into("<8I", h, 8, len(kernel), 0, len(rd), 0, 0, 0, 0, page)
    struct.pack_into("<I", h, 40, 2)
    struct.pack_into("<I", h, 1648, len(dtb))
    pad = lambda b: b + b"\0" * (-len(b) % page)
    img = pad(bytes(h)) + pad(kernel) + pad(rd) + pad(dtb)
    p = tmp_path / "boot.img"; p.write_bytes(img)
    return p, kernel, dtb


def test_add_file_to_ramdisk_keeps_kernel_and_dtb(tmp_path):
    src, kernel, dtb = _boot(tmp_path, _cpio([("init", b"ELF", 0o100750)]))
    out = tmp_path / "new.img"
    bootimg.add_ramdisk_file(src, out, "overlay.d/boox.rc", b"on boot\n", mode=0o100644)
    parts = bootimg.unpack(out)
    assert parts["kernel"] == kernel and parts["dtb"] == dtb
    files = dict((n, d) for n, d, _ in bootimg.cpio_entries(gzip.decompress(parts["ramdisk"])))
    assert files["init"] == b"ELF"
    assert files["overlay.d/boox.rc"] == b"on boot\n"
    assert "overlay.d" in files  # directory entry created
