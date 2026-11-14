from booxctl import root
from booxctl.device import Device


def test_temp_root_never_flashes(fake, tmp_path, monkeypatch):
    img = tmp_path / "patched.img"
    img.write_bytes(b"x")
    monkeypatch.setattr(Device, "wait_for", lambda self, state, timeout=180: None)
    monkeypatch.setattr(root, "grant_shell_su", lambda dev: None)
    fake.on("su -c 'id'", stdout=b"uid=0(root) gid=0(root)\n")
    root.temp_root(Device(fake), img)
    fb = [c for c in fake.calls if c[0] == "fastboot"]
    assert any("boot" in c for c in fb)
    assert not any("flash" in c for c in fake.calls)


def test_magisk_apk_pinned_with_sha():
    assert root.MAGISK_VERSION == "v31.1"
    assert root.MAGISK_SHA256 == "89cefac0a318afa39fb3880c45c87b036c05bc1ebf02a7a715b7f8d7c26ac6e7"
