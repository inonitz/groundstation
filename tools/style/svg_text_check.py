#!/usr/bin/env python3
"""Check an inline-SVG drawing: every <text> must stay inside the <rect> it sits in, and no
<path> segment may cross a text. Widths come from the DejaVu fonts (the pages load IBM Plex,
whose advance widths are within a few percent). Usage: svg_text_check.py FILE.html ..."""
import re
import sys

from PIL import ImageFont

SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
PAD = 8          # the margin a text must keep from its box's right edge
SLACK = 1.04     # Plex against DejaVu: a few percent, taken as a margin


def font_for(cls, sizes):
    if "mono" in cls:
        return ImageFont.truetype(MONO, sizes["mono"])
    if cls.startswith("t") or " t" in f" {cls}":
        return ImageFont.truetype(BOLD, sizes["t"])
    if "s" in cls.split():
        return ImageFont.truetype(SANS, sizes["s"])
    if "delta" in cls:
        return ImageFont.truetype(BOLD, 13)
    return ImageFont.truetype(SANS, sizes["text"])


def sizes_of(html):
    def px(pattern, default):
        m = re.search(pattern, html)
        return int(m.group(1)) if m else default
    return {
        "text": px(r"svg text \{[^}]*font-size: (\d+)px", 13),
        "t": px(r"svg \.t \{[^}]*font-size: (\d+)px", 14),
        "s": px(r"svg \.s \{[^}]*font-size: (\d+)px", 12),
        "mono": px(r"svg \.mono \{[^}]*font-size: (\d+)px", 12),
    }


def segments(d):
    """The straight segments of a path made of M, H and V commands."""
    segs = []
    x = y = None
    for cmd, arg in re.findall(r"([MHV])\s*([-\d.,\s]+)", d):
        if cmd == "M":
            x, y = (float(v) for v in arg.replace(",", " ").split()[:2])
        elif cmd == "H":
            nx = float(arg.split()[0])
            segs.append((min(x, nx), y, max(x, nx), y))
            x = nx
        elif cmd == "V":
            ny = float(arg.split()[0])
            segs.append((x, min(y, ny), x, max(y, ny)))
            y = ny
    return segs


def check(path):
    html = open(path, encoding="utf-8").read()
    sizes = sizes_of(html)
    rects = [(c, float(x), float(y), float(w), float(h)) for c, x, y, w, h in re.findall(
        r'<rect class="([^"]*)" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', html)]
    texts = re.findall(r'<text class="([^"]*)" x="([\d.]+)" y="([\d.]+)">([^<]*)</text>', html)
    texts += [("", x, y, t) for x, y, t in re.findall(r'<text x="([\d.]+)" y="([\d.]+)">([^<]*)</text>', html)]
    paths = [segments(d) for d in re.findall(r'<path class="l-[^"]*" d="([^"]+)"', html)]
    faults = 0

    for cls, x, y, text in texts:
        x, y = float(x), float(y)
        font = font_for(cls, sizes)
        width = font.getlength(text) * SLACK
        size = font.size
        box = (x, y - size, x + width, y + 3)
        holders = [r for r in rects if r[0] != "proc" and r[1] <= x <= r[1] + r[3] and r[2] <= y <= r[2] + r[4]]
        for c, rx, ry, rw, rh in holders:
            if x + width > rx + rw - PAD:
                faults += 1
                print(f"  OVERFLOW by {x + width - (rx + rw - PAD):5.0f}px  {text[:60]!r}  in box '{c}' at ({rx:.0f},{ry:.0f}) w={rw:.0f}")
        if x + width > 1600 * 1.0 and "viewBox" in html:
            vb = float(re.search(r'viewBox="0 0 (\d+)', html).group(1))
            if x + width > vb - 4:
                faults += 1
                print(f"  OFF CANVAS by {x + width - vb:5.0f}px  {text[:60]!r}")
        for segs in paths:
            for sx1, sy1, sx2, sy2 in segs:
                if sx1 == sx2 and box[0] < sx1 < box[2] and sy1 < box[3] and sy2 > box[1]:
                    faults += 1
                    print(f"  CROSSED by a vertical line at x={sx1:.0f}: {text[:60]!r} (y={y:.0f})")
                if sy1 == sy2 and box[1] < sy1 < box[3] and sx1 < box[2] and sx2 > box[0]:
                    faults += 1
                    print(f"  CROSSED by a horizontal line at y={sy1:.0f}: {text[:60]!r} (x={x:.0f})")
    print(f"{path}: {faults} faults")
    return faults


if __name__ == "__main__":
    total = sum(check(p) for p in sys.argv[1:])
    sys.exit(1 if total else 0)
