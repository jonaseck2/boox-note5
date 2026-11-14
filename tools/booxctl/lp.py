"""Minimal liblp (Android dynamic partition metadata, v10.x) reader/writer for the Note5 super.

Format: geometry at byte 4096 (backup at 8192); metadata slots start at 12288, each
metadata_max_size bytes, primaries first, then backups. Header 256 bytes (v10.2) followed by
tables: partitions (52 B), extents (24 B), groups (48 B), block devices (64 B). SHA-256 checksums
over the header (checksum zeroed) and over the tables.
"""
import hashlib
import struct

GEOMETRY_OFFSET = 4096
METADATA_OFFSET = 4096 * 3
HEADER_MAGIC = 0x414C5030
TARGET_LINEAR = 0
ATTR_READONLY = 1


class LpError(RuntimeError):
    pass


def _geometry(path):
    with open(path, "rb") as f:
        f.seek(GEOMETRY_OFFSET)
        g = f.read(52)
    magic, _sz = struct.unpack_from("<II", g, 0)
    if magic != 0x616C4467:
        raise LpError("bad geometry magic")
    max_size, slots, lbs = struct.unpack_from("<III", g, 40)
    return max_size, slots, lbs


def super_sectors(path) -> int:
    import os
    return os.path.getsize(path) // 512


def slot_offsets(path, slot):
    max_size, slots, _ = _geometry(path)
    primary = METADATA_OFFSET + slot * max_size
    backup = METADATA_OFFSET + slots * max_size + slot * max_size
    return primary, backup, max_size


def read_slot(path, slot) -> bytes:
    primary, _, max_size = slot_offsets(path, slot)
    with open(path, "rb") as f:
        f.seek(primary)
        return f.read(max_size)


def parse(raw: bytes) -> dict:
    magic, major, minor, hsz = struct.unpack_from("<IHHI", raw, 0)
    if magic != HEADER_MAGIC:
        raise LpError("bad metadata header magic")
    tables_size, = struct.unpack_from("<I", raw, 44)
    tables = raw[hsz:hsz + tables_size]
    if hashlib.sha256(tables).digest() != raw[48:80]:
        raise LpError("tables checksum mismatch")
    d = [struct.unpack_from("<III", raw, 80 + 12 * i) for i in range(4)]
    rows = lambda i: [tables[d[i][0] + k * d[i][2]: d[i][0] + (k + 1) * d[i][2]] for k in range(d[i][1])]
    extents = []
    for e in rows(1):
        n, ttype, tdata, tsrc = struct.unpack_from("<QIQI", e, 0)
        if ttype != TARGET_LINEAR or tsrc != 0:
            raise LpError("only linear extents on block device 0 are supported")
        extents.append((n, tdata))
    parts = []
    for p in rows(0):
        attrs, first, num, group = struct.unpack_from("<IIII", p, 36)
        parts.append({"name": p[:36].rstrip(b"\0").decode(), "attributes": attrs, "group_index": group,
                      "extents": extents[first:first + num]})
    groups = [{"name": g[:36].rstrip(b"\0").decode(), "flags": struct.unpack_from("<I", g, 36)[0],
               "maximum_size": struct.unpack_from("<Q", g, 40)[0]} for g in rows(2)]
    bdevs = []
    for b in rows(3):
        fls, al, alo, size = struct.unpack_from("<QIIQ", b, 0)
        bdevs.append({"first_logical_sector": fls, "alignment": al, "alignment_offset": alo, "size": size,
                      "name": b[24:60].rstrip(b"\0").decode(), "flags": struct.unpack_from("<I", b, 60)[0]})
    flags = struct.unpack_from("<I", raw, 128)[0] if hsz >= 132 else 0
    return {"major": major, "minor": minor, "header_size": hsz, "flags": flags,
            "partitions": parts, "groups": groups, "block_devices": bdevs}


def serialize(meta: dict) -> bytes:
    name36 = lambda s: s.encode().ljust(36, b"\0")
    pt, et = b"", b""
    for p in meta["partitions"]:
        first = len(et) // 24
        for n, start in p["extents"]:
            et += struct.pack("<QIQI", n, TARGET_LINEAR, start, 0)
        pt += name36(p["name"]) + struct.pack("<IIII", p["attributes"], first, len(p["extents"]), p["group_index"])
    gt = b"".join(name36(g["name"]) + struct.pack("<IQ", g["flags"], g["maximum_size"]) for g in meta["groups"])
    bt = b"".join(struct.pack("<QIIQ", b["first_logical_sector"], b["alignment"], b["alignment_offset"], b["size"])
                  + name36(b["name"]) + struct.pack("<I", b["flags"]) for b in meta["block_devices"])
    tables = pt + et + gt + bt
    hsz = meta["header_size"]
    h = bytearray(hsz)
    struct.pack_into("<IHHI", h, 0, HEADER_MAGIC, meta["major"], meta["minor"], hsz)
    struct.pack_into("<I", h, 44, len(tables))
    h[48:80] = hashlib.sha256(tables).digest()
    descs = [(0, len(meta["partitions"]), 52), (len(pt), len(et) // 24, 24),
             (len(pt) + len(et), len(meta["groups"]), 48), (len(pt) + len(et) + len(gt), len(meta["block_devices"]), 64)]
    for i, (o, n, s) in enumerate(descs):
        struct.pack_into("<III", h, 80 + 12 * i, o, n, s)
    if hsz >= 132:
        struct.pack_into("<I", h, 128, meta["flags"])
    h[12:44] = hashlib.sha256(bytes(h)).digest()
    return bytes(h) + tables


def extents_of(meta, name):
    return next(p["extents"] for p in meta["partitions"] if p["name"] == name)


def rebuild_for_gsi(meta: dict, system_bytes: int, super_sectors: int, first_usable: int = 2048) -> dict:
    """New slot metadata: vendor_b keeps its exact extents; system_b gets every other free sector
    it needs; system_ext_b, product_b and the stale system_b-cow snapshot are dropped."""
    vendor = next(p for p in meta["partitions"] if p["name"] == "vendor_b")
    need = -(-system_bytes // 512)
    need = -(-need // 8) * 8  # whole 4 KiB blocks
    taken = sorted((s, s + n) for n, s in vendor["extents"])
    free, cur = [], first_usable
    for a, b in taken:
        if a > cur:
            free.append((cur, a))
        cur = max(cur, b)
    if cur < super_sectors:
        free.append((cur, super_sectors))
    ext = []
    for a, b in free:
        a8 = -(-a // 8) * 8
        if need <= 0 or b - a8 < 8:
            continue
        take = min(need, (b - a8) // 8 * 8)
        ext.append((take, a8))
        need -= take
    if need > 0:
        raise LpError(f"system image does not fit in super: short by {need * 512} bytes")
    group = vendor["group_index"]
    total = sum(n for n, _ in ext) + sum(n for n, _ in vendor["extents"])
    groups = [dict(g) for g in meta["groups"]]
    if groups[group]["maximum_size"] and groups[group]["maximum_size"] < total * 512:
        raise LpError("group maximum_size too small for the new layout")
    return {**meta, "partitions": [
        {"name": "system_b", "attributes": ATTR_READONLY, "group_index": group, "extents": ext},
        {"name": "vendor_b", "attributes": vendor["attributes"], "group_index": group, "extents": list(vendor["extents"])}],
        "groups": groups}


def read_partition(path, meta, name) -> bytes:
    out = b""
    with open(path, "rb") as f:
        for n, start in extents_of(meta, name):
            f.seek(start * 512); out += f.read(n * 512)
    return out


def build_super(src_super, system_img, out_path, slot: int = 1) -> dict:
    """Copy src_super, rewrite metadata `slot` (primary + backup) for the GSI layout, and write
    system_img into system_b's new extents. Other slots and vendor_b's sectors stay byte-identical."""
    import os
    import shutil
    shutil.copyfile(src_super, out_path)
    meta = rebuild_for_gsi(parse(read_slot(src_super, slot)), os.path.getsize(system_img), super_sectors(src_super))
    blob = serialize(meta)
    primary, backup, max_size = slot_offsets(src_super, slot)
    if len(blob) > max_size:
        raise LpError("metadata larger than metadata_max_size")
    padded = blob.ljust(max_size, b"\0")
    with open(out_path, "r+b") as o, open(system_img, "rb") as s:
        for off in (primary, backup):
            o.seek(off); o.write(padded)
        for n, start in extents_of(meta, "system_b"):
            o.seek(start * 512)
            chunk = s.read(n * 512)
            o.write(chunk.ljust(n * 512, b"\0"))
    check = parse(read_slot(out_path, slot))
    if check != parse(blob):
        raise LpError("metadata read-back mismatch")
    return meta
