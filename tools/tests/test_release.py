import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from booxctl import release

REPO = Path(__file__).resolve().parents[2]


def _fake_repo(root: Path) -> Path:
    shim = root / "device/epdcshim"
    (shim / "module").mkdir(parents=True)
    (shim / "libbooxepdc.so").write_bytes(b"\x7fELF fake shim")
    (shim / "module/post-fs-data.sh").write_text("#!/system/bin/sh\necho pfd\n")
    (shim / "module/service.sh").write_text("#!/system/bin/sh\necho svc\n")
    (root / "device/eink-settings.sh").write_text("#!/bin/sh\necho settings\n")
    # files next to the glue that must NOT ship
    (shim / "epdcshim.c").write_text("int x;\n")
    (shim / "install.sh").write_text("#!/bin/sh\n")
    return root


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_bundle_holds_exactly_the_glue_files(tmp_path):
    repo = _fake_repo(tmp_path / "repo")
    z = release.build_glue_bundle(repo, tmp_path / "out", "2026.11.14.1")
    assert z == tmp_path / "out/boox-glue-2026.11.14.1.zip"
    with zipfile.ZipFile(z) as zf:
        assert sorted(zf.namelist()) == [
            "eink-settings.sh", "libbooxepdc.so", "manifest.json",
            "module/post-fs-data.sh", "module/service.sh"]


def test_manifest_carries_version_and_correct_hashes(tmp_path):
    repo = _fake_repo(tmp_path / "repo")
    z = release.build_glue_bundle(repo, tmp_path / "out", "2026.11.14.1")
    with zipfile.ZipFile(z) as zf:
        m = json.loads(zf.read("manifest.json"))
        assert m["kind"] == "glue"
        assert m["version"] == "2026.11.14.1"
        assert m["format"] == 1
        assert set(m["files"]) == {"eink-settings.sh", "libbooxepdc.so",
                                   "module/post-fs-data.sh", "module/service.sh"}
        for name, entry in m["files"].items():
            body = zf.read(name)
            assert entry["sha256"] == _sha(body)
            assert entry["size"] == len(body)
    src = repo / "device/epdcshim/libbooxepdc.so"
    assert m["files"]["libbooxepdc.so"]["sha256"] == _sha(src.read_bytes())


def test_sidecar_checksum_matches_zip(tmp_path):
    repo = _fake_repo(tmp_path / "repo")
    z = release.build_glue_bundle(repo, tmp_path / "out", "1")
    side = z.with_name(z.name + ".sha256").read_text()
    assert side == f"{_sha(z.read_bytes())}  {z.name}\n"  # `shasum -a 256 -c` format


def test_build_is_byte_reproducible(tmp_path):
    repo = _fake_repo(tmp_path / "repo")
    a = release.build_glue_bundle(repo, tmp_path / "a", "1").read_bytes()
    os.utime(repo / "device/eink-settings.sh", (946684800, 946684800))  # mtime change must not matter
    b = release.build_glue_bundle(repo, tmp_path / "b", "1").read_bytes()
    assert a == b


def test_scripts_are_executable_in_the_zip(tmp_path):
    repo = _fake_repo(tmp_path / "repo")
    z = release.build_glue_bundle(repo, tmp_path / "out", "1")
    with zipfile.ZipFile(z) as zf:
        modes = {i.filename: (i.external_attr >> 16) for i in zf.infolist()}
    for name in ("eink-settings.sh", "module/post-fs-data.sh", "module/service.sh"):
        assert modes[name] & stat.S_IXUSR, name
    assert not modes["libbooxepdc.so"] & stat.S_IXUSR
    assert not modes["manifest.json"] & stat.S_IXUSR


@pytest.mark.parametrize("bad", ["", "v1/../x", "1 2", "a\nb", "-1"])
def test_rejects_unsafe_version(tmp_path, bad):
    repo = _fake_repo(tmp_path / "repo")
    with pytest.raises(ValueError):
        release.build_glue_bundle(repo, tmp_path / "out", bad)


def test_missing_source_fails_and_writes_nothing(tmp_path):
    repo = _fake_repo(tmp_path / "repo")
    (repo / "device/epdcshim/libbooxepdc.so").unlink()
    with pytest.raises(FileNotFoundError):
        release.build_glue_bundle(repo, tmp_path / "out", "1")
    out = tmp_path / "out"
    assert not out.exists() or not any(out.iterdir())


def test_builds_from_the_real_repo(tmp_path):
    # libbooxepdc.so is a build product (gitignored, cross-compiled against device libs): absent in CI
    if not (Path(__file__).resolve().parents[2] / "device/epdcshim/libbooxepdc.so").is_file():
        pytest.skip("libbooxepdc.so not built (device/epdcshim/build.sh needs the device sysroot)")
    z = release.build_glue_bundle(REPO, tmp_path, "0.0.0-test")
    with zipfile.ZipFile(z) as zf:
        m = json.loads(zf.read("manifest.json"))
    so = (REPO / "device/epdcshim/libbooxepdc.so").read_bytes()
    assert m["files"]["libbooxepdc.so"]["sha256"] == _sha(so)
