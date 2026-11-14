"""Find on-screen elements by visible text via uiautomator, and tap them."""
import re


def find_center(xml: str, text: str):
    """Centre (x, y) of the first node whose text or content-desc equals `text`, else None."""
    for m in re.finditer(r"<node [^>]*>", xml):
        n = m.group(0)
        if re.search(r'(text|content-desc)="' + re.escape(text) + '"', n):
            b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n)
            if b:
                x0, y0, x1, y1 = map(int, b.groups())
                return (x0 + x1) // 2, (y0 + y1) // 2
    return None


def tap_text(dev, text: str) -> bool:
    xml = dev.shell("uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; cat /sdcard/ui.xml")
    c = find_center(xml, text)
    if c:
        dev.shell(f"input tap {c[0]} {c[1]}")
    return c is not None
