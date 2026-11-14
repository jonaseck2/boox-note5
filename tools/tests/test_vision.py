import numpy as np

from booxctl import vision


def _quad_scene():
    """Dark 1920x1080 frame with a bright, skewed panel and one black bar on it."""
    import cv2
    img = np.full((1080, 1920), 30, np.uint8)
    quad = np.array([[60, 120], [1850, 140], [1820, 1050], [90, 1020]], np.int32)
    cv2.fillPoly(img, [quad], 220)
    return img, quad


def test_warp_to_screen_finds_panel_and_fills_output():
    img, _ = _quad_scene()
    out = vision.warp_to_screen(img, size=(1872, 1404))
    assert out.shape == (1404, 1872)
    # interior is panel, not bezel
    assert out[50:-50, 50:-50].mean() > 200


def test_diff_score_masks_glare_strip():
    a = np.full((1404, 1872), 200, np.uint8)
    b = a.copy()
    b[:, :300] = 0
    assert vision.diff_score(a, b, mask_left_px=300) == 0.0
    b[:, 400:500] = 0
    assert vision.diff_score(a, b, mask_left_px=300) > 0.0


def test_calibration_roundtrip(tmp_path):
    img, quad = _quad_scene()
    path = tmp_path / "corners.json"
    corners = vision.save_calibration(img, path)
    assert vision.load_calibration(path) == corners
    assert abs(corners[0][0] - 60) < 15 and abs(corners[2][1] - 1050) < 15
