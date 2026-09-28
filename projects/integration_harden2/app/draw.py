"""The drawing basics the chat pane, the status pane and the camera view share: the cv2
font, the pane ground colour, the TrueType fonts, ASCII cleanup, pixel wrapping and a
labelled box. Font composition (owner-inspected 2026-09-12, mockup
tools/ui-mockups/live-pane.html): DejaVu Sans for Hebrew, DejaVu Sans Mono for the tag
column, Ubuntu Regular for English values + header."""
import os

import cv2
from PIL import ImageFont
from PIL import features as pil_features

import config
from system.fatal import die

FONT = cv2.FONT_HERSHEY_SIMPLEX
PANE_GROUND = (31, 25, 22)  # the dark ground of the status + chat panes (#16191f)


# ======================================= fonts =======================================
# Hebrew/RTL for the chat overlay. OpenCV's Hershey font is ASCII-only, so Hebrew is
# drawn with a TrueType font (DejaVuSans has Hebrew glyphs). PIL and bidi are required
# (system/deps.py checks them at start-up); a MISSING FONT is fatal.
_SZ = config.HE_FONT_SIZE
# The Hebrew font is REQUIRED (a missing one is fatal, per the owner). Ubuntu (English)
# and the mono font (tags) are optional niceties: fall back to the Hebrew font if
# absent. os.path.exists, no try.
_HE_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
if not os.path.exists(_HE_PATH):
    die(f"overlay Hebrew font missing: {_HE_PATH} (apt-get install fonts-dejavu)")
FONT_HE = ImageFont.truetype(_HE_PATH, _SZ)

_VAL_PATH = "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"
FONT_VAL = FONT_HE
if os.path.exists(_VAL_PATH):
    FONT_VAL = ImageFont.truetype(_VAL_PATH, _SZ)

_TAG_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_TAG = FONT_HE
if os.path.exists(_TAG_PATH):
    FONT_TAG = ImageFont.truetype(_TAG_PATH, _SZ - 2)

# Raqm does bidi natively -> do NOT pre-reverse
RAQM = bool(pil_features.check("raqm"))


# ==================================== text helpers ====================================
def ascii_only(s):
    """Drop non-ASCII characters; cv2.putText cannot draw them."""
    return (s or "").encode("ascii", "ignore").decode("ascii")


def wrap_px(text, maxpx, font=None):
    """Wrap to fit maxpx using the real font metrics (per-element font). PIL path
    only. A line break in the text starts a new line: PIL cannot measure multi-line
    text (a transcript with a line break crashed the app, 2026-09-25)."""
    lines = []
    font = font or FONT_HE
    if not text:
        return [""]

    for paragraph in text.split("\n"):
        lines.extend(_wrap_line(paragraph, maxpx, font))
    return lines or [""]


def _wrap_line(text, maxpx, font):
    """Wrap one line (no line break inside) at spaces to fit maxpx."""
    trial = ""
    cur = ""
    lines = []

    for wd in text.split(" "):
        trial = (cur + " " + wd).strip()
        if not cur or font.getlength(trial) <= maxpx:
            cur = trial
            continue
        lines.append(cur)
        cur = wd
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_box(img, box, color, label=None, thick=2):
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)
    if label:
        cv2.putText(img, label, (x1, max(y1 - 6, 12)), FONT, 0.5, color, 1, cv2.LINE_AA)
    return
