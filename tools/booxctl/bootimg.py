"""Android boot image v2 (header_version 2) with gzip ramdisk: unpack, add a ramdisk file, repack.
Used to drop a Magisk overlay.d init script into boot_b without on-device tools."""
import gzip
import struct

PAGE_FIELDS = "<8I"


def _align(n, page):
    return (n + page - 1) // page * page


def unpack(path) -> dict:
    b = open(path, "rb").read()
    if b[:8] != b"ANDROID!":
        raise ValueError("not an Android boot image")
    ks, _, rs, _, ss, _, _, page = struct.unpack_from(PAGE_FIELDS, b, 8)
    hv, = struct.unpack_from("<I", b, 40)
    if hv != 2:
        raise ValueError(f"unsupported header_version {hv}")
    rdo_size, = struct.unpack_from("<I", b, 1632)
    dtb_size, = struct.unpack_from("<I", b, 1648)
    off = page
    parts = {"header": b[:page], "page": page}
    for name, size in (("kernel", ks), ("ramdisk", rs), ("second", ss), ("recovery_dtbo", rdo_size), ("dtb", dtb_size)):
        parts[name] = b[off:off + size]
        off += _align(size, page)
    return parts


def cpio_entries(data: bytes):
    """Yield (name, data, mode) from a newc cpio archive, stopping at TRAILER!!!."""
    i = 0
    while i < len(data):
        h = data[i:i + 110]
        if h[:6] not in (b"070701", b"070702"):
            raise ValueError("bad cpio magic")
        f = [int(h[6 + 8 * k:14 + 8 * k], 16) for k in range(13)]
        mode, fsize, nsize = f[1], f[6], f[11]
        name = data[i + 110:i + 110 + nsize - 1].decode()
        j = i + 110 + nsize
        j += -j % 4
        body = data[j:j + fsize]
        j += fsize
        j += -j % 4
        if name == "TRAILER!!!":
            return
        yield name, body, mode
        i = j


def cpio_build(entries) -> bytes:
    out = b""
    for ino, (name, body, mode) in enumerate(list(entries) + [("TRAILER!!!", b"", 0)], start=1):
        nb = name.encode() + b"\0"
        nlink = 2 if mode & 0o040000 else 1
        hdr = b"070701" + b"".join(b"%08X" % v for v in (ino, mode, 0, 0, nlink, 0, len(body), 0, 0, 0, 0, len(nb), 0))
        rec = hdr + nb
        rec += b"\0" * (-len(rec) % 4) + body
        rec += b"\0" * (-len(rec) % 4)
        out += rec
    return out


def add_ramdisk_file(src, out, name: str, body: bytes, mode: int = 0o100644) -> None:
    p = unpack(src)
    entries = [e for e in cpio_entries(gzip.decompress(p["ramdisk"])) if e[0] != name]
    names = {e[0] for e in entries}
    parent = name.rsplit("/", 1)[0] if "/" in name else None
    if parent and parent not in names:
        entries.append((parent, b"", 0o040755))
    entries.append((name, body, mode))
    rd = gzip.compress(cpio_build(entries), compresslevel=9)
    page = p["page"]
    h = bytearray(p["header"])
    struct.pack_into("<I", h, 16, len(rd))         # ramdisk_size
    h[576:608] = b"\0" * 32                         # id (SHA1) — not checked with verification disabled
    pad = lambda x: x + b"\0" * (-len(x) % page)
    img = pad(bytes(h)) + pad(p["kernel"]) + pad(rd) + pad(p["second"]) + pad(p["recovery_dtbo"]) + pad(p["dtb"])
    open(out, "wb").write(img)
