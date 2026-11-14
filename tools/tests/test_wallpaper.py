import numpy as np
import cv2
from booxctl import wallpaper


def test_light_print_fills_panel_and_stays_light(tmp_path):
    src = tmp_path / "src.png"
    img = np.zeros((900, 1600, 3), np.uint8)
    img[:, 800:] = 255                                  # half black, half white
    cv2.imwrite(str(src), img)
    out = wallpaper.light_print(src, tmp_path / "out.png")
    g = cv2.imread(str(out), 0)
    assert g.shape == (1404, 1872)
    assert g.min() >= 255 - 0.45 * 255 - 1              # darkest ink is 45% grey: Android picks dark text
    assert g.max() == 255
