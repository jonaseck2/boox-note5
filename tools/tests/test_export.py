import pytest

from booxctl.device import Device
from booxctl.export import ExportIncomplete, export_sdcard


def test_export_compares_counts(fake, tmp_path, monkeypatch):
    fake.on("find /sdcard", stdout=b"120\n")
    monkeypatch.setattr("booxctl.export.local_count", lambda p: 119)
    with pytest.raises(ExportIncomplete):
        export_sdcard(Device(fake), tmp_path / "sdcard")


def test_export_ok_when_counts_match(fake, tmp_path, monkeypatch):
    fake.on("find /sdcard", stdout=b"120\n")
    monkeypatch.setattr("booxctl.export.local_count", lambda p: 120)
    rep = export_sdcard(Device(fake), tmp_path / "sdcard")
    assert rep.files == 120
