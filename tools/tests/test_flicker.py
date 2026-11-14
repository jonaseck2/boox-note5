import numpy as np
from booxctl.flicker import flicker_metrics


def frames_with(region_values, size=(60, 80), base=200):
    out = []
    for v in region_values:
        f = np.full(size, base, np.uint8)
        f[10:30, 10:50] = v          # region = 800 px of 4800 → 1/6 of the frame
        out.append(f)
    return out


def test_static_frames_have_no_flicker():
    m = flicker_metrics(frames_with([200] * 10))
    assert m["changed_area"] == 0 and m["transient_area"] == 0


def test_clean_step_change_is_not_flicker():
    m = flicker_metrics(frames_with([200] * 4 + [50] * 6))
    assert abs(m["changed_area"] - 1 / 6) < 0.01
    assert m["transient_area"] == 0


def test_blink_back_to_start_is_flicker():
    m = flicker_metrics(frames_with([200, 200, 20, 20, 200, 200]))
    assert m["changed_area"] == 0
    assert abs(m["transient_area"] - 1 / 6) < 0.01


def test_flash_through_white_before_settling_is_flicker():
    m = flicker_metrics(frames_with([120, 120, 255, 30, 30, 30], base=120))
    assert abs(m["transient_area"] - 1 / 6) < 0.01
    assert m["flicker_ratio"] > 0.9


def test_content_that_persists_longer_than_window_is_not_a_flash():
    # a popup shown for 30 frames (1 s at 30 fps) then dismissed: real content, not flicker
    m = flicker_metrics(frames_with([200] * 30 + [20] * 30 + [200] * 30), window=10)
    assert m["flash_area"] == 0


def test_short_blink_inside_window_is_a_flash():
    m = flicker_metrics(frames_with([200] * 30 + [20] * 3 + [200] * 30), window=10)
    assert abs(m["flash_area"] - 1 / 6) < 0.01


def test_flash_through_white_during_transition_is_a_flash():
    m = flicker_metrics(frames_with([120] * 30 + [255] * 3 + [30] * 30, base=120), window=10)
    assert abs(m["flash_area"] - 1 / 6) < 0.01
