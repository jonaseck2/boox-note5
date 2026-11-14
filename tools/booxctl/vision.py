"""Camera-frame geometry and comparison: map the panel onto the screencap pixel grid."""
import cv2
import numpy as np

PANEL = (1872, 1404)  # landscape width, height


def to_gray(img) -> np.ndarray:
    if isinstance(img, (str, bytes)) or hasattr(img, "__fspath__"):
        img = cv2.imread(str(img), cv2.IMREAD_GRAYSCALE)
    elif img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def find_panel(gray: np.ndarray) -> np.ndarray:
    """Return the panel's 4 corners (tl, tr, br, bl) as float32. The panel is the largest bright quad."""
    blur = cv2.GaussianBlur(gray, (9, 9), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(contours, key=cv2.contourArea)
    hull = cv2.convexHull(c)
    eps = 0.02 * cv2.arcLength(hull, True)
    approx = cv2.approxPolyDP(hull, eps, True).reshape(-1, 2)
    if len(approx) != 4:
        rect = cv2.minAreaRect(hull)
        approx = cv2.boxPoints(rect)
    pts = approx.astype(np.float32)
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], np.float32)


def warp_to_screen(img, size=PANEL, corners=None) -> np.ndarray:
    gray = to_gray(img)
    src = find_panel(gray) if corners is None else np.asarray(corners, np.float32)
    w, h = size
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(gray, m, (w, h))


def diff_score(a: np.ndarray, b: np.ndarray, mask_left_px: int = 300) -> float:
    """Mean absolute grey difference, ignoring the glare strip on the left edge."""
    a = to_gray(a).astype(np.int16)[:, mask_left_px:]
    b = to_gray(b).astype(np.int16)[:, mask_left_px:]
    return float(np.abs(a - b).mean())


def save_calibration(white_frame, path) -> list:
    """Find panel corners on a mostly-white screen and store them; reuse for frames with dark content."""
    import json
    corners = find_panel(to_gray(white_frame)).round(1).tolist()
    open(path, "w").write(json.dumps(corners))
    return corners


def load_calibration(path) -> list:
    import json
    return json.loads(open(path).read())
