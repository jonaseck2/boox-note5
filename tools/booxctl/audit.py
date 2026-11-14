"""Visual-style audit: predict what the e-ink panel shows for a screen, then score every text and icon
element for contrast. The prediction replicates device/epdcshim's tone pass exactly (luma, 32 px
photo/text tiles, two curves, 1 px bold), so it is exact for the pixels the shim writes and free of
camera noise. Camera shots are only used to spot-check the worst findings."""
import json
import re
import time
from pathlib import Path

import numpy as np

B = 32  # shim band/tile size


def _lut(black: int, white: int) -> np.ndarray:
    i = np.arange(256)
    if white <= black:
        white = black + 1
    return np.clip((i - black) * 255 // (white - black), 0, 255).astype(np.uint8)


def simulate(img_bgr: np.ndarray, p: dict) -> np.ndarray:
    """Predicted panel grey (uint8 HxW) for a BGR screencap, using the shim's lut.* props `p`."""
    r, g, b = (img_bgr[..., 2].astype(np.int32), img_bgr[..., 1].astype(np.int32), img_bgr[..., 0].astype(np.int32))
    luma = ((54 * r + 183 * g + 19 * b) >> 8).astype(np.uint8)
    h, w = luma.shape
    photo = np.zeros((h, w), bool)
    if p.get("adaptive", 1):
        for y0 in range(0, h, B):
            band = luma[y0:y0 + B:2]
            for x0 in range(0, w, B):
                t = band[:, x0:x0 + B:2]
                if t.size and (np.count_nonzero((t >= 48) & (t <= 208)) * 100 > p.get("pct", 35) * t.size):
                    photo[y0:y0 + B, x0:x0 + B] = True
    text = _lut(p.get("black", 40), p.get("white", 235))[luma]
    out = np.where(photo, _lut(p.get("pblack", 16), p.get("pwhite", 245))[luma], text)
    if p.get("bold", 1):
        prev = np.full_like(text, 255)
        prev[:, 1:] = np.where(photo[:, :-1], 255, text[:, :-1])
        out = np.where(photo, out, np.minimum(text, prev))
    return out.astype(np.uint8)


def score(pred: np.ndarray, bounds) -> dict:
    """Paper = the box's dominant grey; ink = 10th percentile of the pixels that differ from it by
    more than 12 levels (text and glyph strokes cover only a few % of wide label boxes)."""
    x0, y0, x1, y1 = bounds
    c = pred[max(y0, 0):y1, max(x0, 0):x1].ravel()
    if c.size == 0:
        return {"contrast": 0, "ink": 0, "paper": 0, "verdict": "empty"}
    paper = int(np.bincount(c, minlength=256).argmax())
    fg = c[np.abs(c.astype(int) - paper) > 12]
    if fg.size < max(12, c.size // 2000):
        return {"contrast": 0, "ink": paper, "paper": paper, "verdict": "vanishes"}
    ink = int(np.percentile(fg, 10)) if paper > 127 else int(np.percentile(fg, 90))
    con = abs(paper - ink)
    if con < 40:
        v = "vanishes"
    elif con < 100 or min(paper, ink) > 120 or max(paper, ink) < 170:
        v = "low"
    else:
        v = "ok"
    return {"contrast": con, "ink": ink, "paper": paper, "verdict": v}


def nodes(xml: str) -> list:
    """Visible elements worth reading: text, or an icon with a content description."""
    out = []
    for m in re.finditer(r"<node [^>]*>", xml):
        n = m.group(0)
        t = re.search(r'text="([^"]*)"', n).group(1)
        d = re.search(r'content-desc="([^"]*)"', n).group(1)
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n)
        pkg = re.search(r'package="([^"]*)"', n).group(1)
        if not b or not (t or d):
            continue
        x0, y0, x1, y1 = map(int, b.groups())
        if x1 - x0 < 8 or y1 - y0 < 8 or (x1 - x0) * (y1 - y0) > 1872 * 1404 * 0.25:
            continue
        out.append({"label": t or d, "kind": "text" if t else "icon", "pkg": pkg, "bounds": [x0, y0, x1, y1]})
    return out


# name -> adb shell command that brings the screen up (run from Home)
SCREENS = [
    ("home", "input keyevent HOME"),
    ("app-drawer", "input keyevent HOME; sleep 1; input swipe 936 1300 936 300 300"),
    ("notifications", "cmd statusbar expand-notifications"),
    ("quick-settings", "cmd statusbar expand-settings"),
    ("volume-panel", "input keyevent VOLUME_DOWN"),
    ("recents", "input keyevent APP_SWITCH"),
    ("settings", "am start -n com.android.settings/.Settings"),
    ("settings-display", "am start -a android.settings.DISPLAY_SETTINGS"),
    ("settings-eink", "am start -n org.boox.einksettings/.EinkSettingsActivity"),
    ("settings-wifi", "am start -a android.settings.WIFI_SETTINGS"),
    ("settings-apps", "am start -a android.settings.APPLICATION_SETTINGS"),
    ("settings-battery", "am start -a android.intent.action.POWER_USAGE_SUMMARY"),
    ("settings-about", "am start -a android.settings.DEVICE_INFO_SETTINGS"),
    ("chrome-hn", "am start -a android.intent.action.VIEW -d https://news.ycombinator.com -n com.android.chrome/com.google.android.apps.chrome.Main"),
    ("chrome-omni", "am start -a android.intent.action.VIEW -d https://omni.se -n com.android.chrome/com.google.android.apps.chrome.Main"),
    ("chrome-menu", "am start -n com.android.chrome/com.google.android.apps.chrome.Main; sleep 3; input keyevent MENU"),
    ("play-books", "am start -n com.google.android.apps.books/.app.BooksActivity"),
    ("keep", "am start -n com.google.android.keep/.activities.BrowseActivity"),
    ("play-store", "am start -n com.android.vending/.AssetBrowserActivity"),
    ("calendar", "am start -n org.lineageos.etar/com.android.calendar.AllInOneActivity"),
    ("files", "am start -n com.android.documentsui/.LauncherActivity"),
    ("contacts", "am start -n com.android.contacts/.activities.PeopleActivity"),
    ("keyboard", "am start -a android.intent.action.VIEW -d https://www.google.com -n com.android.chrome/com.google.android.apps.chrome.Main; sleep 4; input tap 936 140"),
    ("storytel", "am start -n grit.storytel.app/.MainActivity"),
]


def props(dev) -> dict:
    keys = {"black": 40, "white": 235, "pblack": 16, "pwhite": 245, "photo_pct": 35, "adaptive": 1, "bold": 1}
    out = {}
    for k, d in keys.items():
        v = dev.getprop(f"persist.boox.lut.{k}")
        out["pct" if k == "photo_pct" else k] = int(v) if v.isdigit() else d
    return out


def run(dev, out_dir: Path, screens=SCREENS, log=print) -> dict:
    import cv2
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = props(dev)
    report = {"props": p, "screens": []}
    for name, cmd in screens:
        dev.shell("cmd statusbar collapse; input keyevent BACK; input keyevent HOME")
        time.sleep(1.5)
        dev.shell(cmd)
        time.sleep(4)
        xml = dev.shell("uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; cat /sdcard/ui.xml")
        (out_dir / f"{name}.xml").write_text(xml)
        dev.screencap(out_dir / f"{name}.png")
        img = cv2.imread(str(out_dir / f"{name}.png"))
        pred = simulate(img, p)
        cv2.imwrite(str(out_dir / f"{name}.pred.png"), pred)
        items = []
        for n in nodes(xml):
            n.update(score(pred, n["bounds"]))
            items.append(n)
        bad = [n for n in items if n["verdict"] != "ok"]
        report["screens"].append({"name": name, "elements": len(items), "flagged": bad})
        log(f"{name}: {len(items)} elements, {len(bad)} flagged")
    (out_dir / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return report
