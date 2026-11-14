"""Release bundles for the GitHub Releases of github.com/jonaseck2/boox.

Class A (glue) bundle: the e-ink glue that `device/epdcshim/install.sh` and `device/eink-settings.sh`
put on the device, plus `manifest.json` (format 1: kind, version, sha256 + size per file).
The zip is byte-reproducible: fixed order, fixed timestamps, fixed modes.
Design: docs/plans/2026-11-14-ota-design.md.
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path

MANIFEST_FORMAT = 1
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$")
_EPOCH = (1980, 1, 1, 0, 0, 0)  # earliest zip timestamp; keeps builds reproducible


def _glue_sources(repo_root: Path) -> dict:
    """Map arcname -> source path. module/* is globbed so a new module script ships without a code change."""
    shim = repo_root / "device/epdcshim"
    files = {"libbooxepdc.so": shim / "libbooxepdc.so",
             "eink-settings.sh": repo_root / "device/eink-settings.sh"}
    module = shim / "module"
    if not module.is_dir():
        raise FileNotFoundError(module)
    for p in sorted(module.iterdir()):
        if p.is_file():
            files[f"module/{p.name}"] = p
    for p in files.values():
        if not p.is_file():
            raise FileNotFoundError(p)
    apk = repo_root / "device/einksettings/build/EinkSettings.apk"   # optional: needs the Android SDK
    if apk.is_file():
        files["EinkSettings.apk"] = apk
    return dict(sorted(files.items()))


def _add(zf: zipfile.ZipFile, name: str, body: bytes, mode: int) -> None:
    info = zipfile.ZipInfo(name, _EPOCH)
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3  # unix, so unzip honours the mode bits
    zf.writestr(info, body)


def build_glue_bundle(repo_root: Path, out_dir: Path, version: str) -> Path:
    """Write out_dir/boox-glue-<version>.zip and its `shasum -a 256 -c` sidecar; return the zip path."""
    if not isinstance(version, str) or not _VERSION.match(version):
        raise ValueError(f"unsafe version string: {version!r}")
    repo_root, out_dir = Path(repo_root), Path(out_dir)
    sources = _glue_sources(repo_root)
    bodies = {name: p.read_bytes() for name, p in sources.items()}
    manifest = {"format": MANIFEST_FORMAT, "kind": "glue", "version": version,
                "files": {n: {"sha256": hashlib.sha256(b).hexdigest(), "size": len(b)} for n, b in bodies.items()}}

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"boox-glue-{version}.zip"
    tmp = out.with_name(out.name + ".part")
    with zipfile.ZipFile(tmp, "w") as zf:
        for name, body in bodies.items():
            _add(zf, name, body, 0o755 if name.endswith(".sh") else 0o644)
        _add(zf, "manifest.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(), 0o644)
    tmp.replace(out)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    out.with_name(out.name + ".sha256").write_text(f"{digest}  {out.name}\n")
    return out


_GLUE_VERSION = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})\.(\d{1,2})$")


def version_code(version: str) -> int:
    """`YYYY.MM.DD.N` -> YYYYMMDD*100 + N (Magisk versionCode; owner decision 2026-11-14)."""
    m = _GLUE_VERSION.match(version or "")
    if not m:
        raise ValueError(f"version must be YYYY.MM.DD.N (N <= 99): {version!r}")
    y, mo, d, n = map(int, m.groups())
    if not (2020 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31):
        raise ValueError(f"not a date: {version!r}")
    return (y * 10000 + mo * 100 + d) * 100 + n


def verify_bundle(zip_path: Path, out_dir: Path) -> dict:
    """Check the .sha256 sidecar and every manifest hash, extract into out_dir, return the manifest.
    Raises ValueError naming the first bad file; nothing usable is left in out_dir on failure."""
    zip_path, out_dir = Path(zip_path), Path(out_dir)
    side = zip_path.with_name(zip_path.name + ".sha256")
    if side.exists():
        want = side.read_text().split()[0]
        if hashlib.sha256(zip_path.read_bytes()).hexdigest() != want:
            raise ValueError(f"sha256 of {zip_path.name} does not match its sidecar")
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        if manifest.get("format") != MANIFEST_FORMAT or manifest.get("kind") != "glue":
            raise ValueError("not a format-1 glue bundle")
        names = set(zf.namelist()) - {"manifest.json"}
        if names != set(manifest["files"]):
            raise ValueError(f"bundle files differ from manifest: {sorted(names ^ set(manifest['files']))}")
        bodies = {}
        for name, meta in manifest["files"].items():
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"unsafe path in bundle: {name}")
            body = zf.read(name)
            if hashlib.sha256(body).hexdigest() != meta["sha256"] or len(body) != meta["size"]:
                raise ValueError(f"hash mismatch: {name}")
            bodies[name] = body
    for name, body in bodies.items():
        dst = out_dir / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(body)
        dst.chmod(0o755 if name.endswith(".sh") else 0o644)
    return manifest
