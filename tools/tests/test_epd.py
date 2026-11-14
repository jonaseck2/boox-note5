import numpy as np

from booxctl import epd


def test_flash_ignores_exposure_ramp_before_trigger():
    ramp = [90, 120, 150, 160, 158] + [158] * 30   # camera auto-exposure settling, no refresh
    assert epd.flash_visible(ramp) is False


def test_mode_values_match_kernel_trace():
    assert epd.MODES == {"normal": -1, "speed": 2305, "a2": 2308, "x": 16777220}


def test_set_mode_runs_ebcctl_as_root(fake):
    from booxctl.device import Device
    fake.on("su -c", stdout=b"")
    epd.set_mode(Device(fake), "a2")
    assert any("ebcctl 2308" in " ".join(c) for c in fake.calls)


def test_full_refresh_reads_panel_clean(fake):
    from booxctl.device import Device
    epd.full_refresh(Device(fake))
    assert any("cat /sys/class/sepdc/debug/panel_clean" in " ".join(c) for c in fake.calls)


def test_flash_detected_from_brightness_trace():
    assert epd.flash_visible([150, 149, 150, 151, 77, 166, 183, 160, 158, 157, 157, 157]) is True
    assert epd.flash_visible([150, 151, 149, 150, 152, 150]) is False


def test_full_refresh_then_forces_shim_full_update(fake):
    # v2 shim sends nothing for an unchanged frame; after panel_clean the panel is blank, so the
    # refresh must bump sys.boox.epdc.force to make the shim redraw the whole frame.
    from booxctl.device import Device
    epd.full_refresh(Device(fake))
    cmds = [" ".join(c) for c in fake.calls]
    i_clean = next(i for i, c in enumerate(cmds) if "panel_clean" in c)
    assert any("setprop sys.boox.epdc.force" in c for c in cmds[i_clean:])
