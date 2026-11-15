import numpy as np
from booxctl import audit

P = dict(black=40, white=235, pblack=16, pwhite=245, pct=35, adaptive=1, bold=1)


def test_text_tile_curve_maps_near_white_to_white_and_dark_to_black():
    img = np.full((64, 64, 3), 240, np.uint8)
    img[10:12, :, :] = 60
    pred = audit.simulate(img, P)
    assert pred[0, 0] == 255 and pred[10, 5] == int((60 - 40) * 255 / 195)


def test_bold_extends_dark_stroke_one_pixel_right():
    img = np.full((32, 32, 3), 255, np.uint8)
    img[:, 10] = 0
    pred = audit.simulate(img, P)
    assert pred[5, 10] == 0 and pred[5, 11] == 0 and pred[5, 12] == 255


def test_photo_tile_gets_gentle_curve():
    img = np.tile(np.linspace(60, 200, 32, dtype=np.uint8), (32, 1))[:, :, None].repeat(3, 2)
    pred = audit.simulate(img, P)
    # a mid-grey photo tile keeps mid tones (gentle 16/245) instead of the strong curve
    assert abs(int(pred[0, 16]) - int((int(img[0, 16, 0]) - 16) * 255 / 229)) <= 1


def test_score_flags_light_grey_text_on_white():
    pred = np.full((40, 200), 255, np.uint8)
    pred[15:25, 20:180] = 235                            # faint text
    s = audit.score(pred, (0, 0, 200, 40))
    assert s["contrast"] < 40 and s["verdict"] == "vanishes"


def test_score_passes_black_text_on_white():
    pred = np.full((40, 200), 255, np.uint8)
    pred[15:25, 20:180:3] = 0
    assert audit.score(pred, (0, 0, 200, 40))["verdict"] == "ok"


def test_short_text_in_wide_box_is_found():
    pred = np.full((31, 1132), 255, np.uint8)
    pred[8:22, 0:115:3] = 0                              # "Brightness": ~1.6% of the box
    s = audit.score(pred, (0, 0, 1132, 31))
    assert s["verdict"] == "ok" and s["contrast"] > 200


DARK = dict(P, auto_dark=1, dark_black=20, dark_white=180, dark_frac=60, dark_photo_lo=72)


def _dark_page():
    img = np.full((64, 64, 3), 30, np.uint8)            # Material dark surface
    img[:, 10] = 180                                     # a 1 px light text stroke
    return img


def test_mostly_dark_frame_uses_dark_curve():
    pred = audit.simulate(_dark_page(), DARK)
    assert pred[5, 0] == (30 - 20) * 255 // 160 and pred[5, 10] == 255


def test_dark_frame_bold_extends_light_stroke():
    pred = audit.simulate(_dark_page(), DARK)
    assert pred[5, 11] == 255 and pred[5, 12] == (30 - 20) * 255 // 160


def test_dark_frame_dark_grey_card_is_not_a_photo():
    img = np.full((64, 64, 3), 30, np.uint8)
    img[32:, 32:] = 60                                   # surfaceContainer card: mid-grey under the light rule
    pred = audit.simulate(img, DARK)
    assert pred[40, 40] == (60 - 20) * 255 // 160        # text curve, not the photo curve


def test_auto_dark_off_keeps_light_curve():
    pred = audit.simulate(_dark_page(), dict(DARK, auto_dark=0))
    assert pred[5, 0] == 0 and pred[5, 10] == 0          # dark-dilating bold erases the 1 px light stroke


def test_light_frame_ignores_dark_profile():
    img = np.full((64, 64, 3), 240, np.uint8)
    img[10:12, :, :] = 60
    pred = audit.simulate(img, DARK)
    assert pred[0, 0] == 255 and pred[10, 5] == int((60 - 40) * 255 / 195)
