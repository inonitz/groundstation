#!/usr/bin/env python3
"""Chat-pane overlay renderer for the live scene window. PURE rendering: no app state, no threads.
`render_chat` takes a snapshot of the chat and returns a BGR panel; the caller holds the lock and
passes the snapshot in. Font composition (owner-inspected 2026-09-12, mockup tools/ui-mockups/
live-pane.html): DejaVu Sans for Hebrew, DejaVu Sans Mono for the tag column, Ubuntu Regular for
English values + header. Degrades to ASCII-only cv2 Hershey text if PIL/bidi/font are missing."""
import os, textwrap
import cv2, numpy as np
import config
from perception import ascii_only

FONT = cv2.FONT_HERSHEY_SIMPLEX

# Hebrew/RTL for the chat overlay. OpenCV's Hershey font is ASCII-only, so Hebrew is drawn with a
# TrueType font (DejaVuSans has Hebrew glyphs) and python-bidi for correct right-to-left order.
try:
    from PIL import Image, ImageDraw, ImageFont
    from bidi.algorithm import get_display
    _SZ = config.HE_FONT_SIZE
    def _ttf(path, sz, fb):
        try: return ImageFont.truetype(path, sz) if os.path.exists(path) else fb
        except Exception: return fb
    _FONT_HE  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", _SZ)               # Hebrew
    _FONT_VAL = _ttf("/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf", _SZ, _FONT_HE)                     # English values/header
    _FONT_TAG = _ttf("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", _SZ - 2, _FONT_HE)           # tags + HUD (mono)
    _HE_FONT = _FONT_HE
    try:
        from PIL import features as _pil_features
        _RAQM = bool(_pil_features.check("raqm"))   # Raqm does bidi natively -> do NOT pre-reverse
    except Exception:
        _RAQM = False
    _HAVE_HE = True
except Exception as _he_err:
    print("[overlay] Hebrew overlay off (PIL/bidi/font missing):", _he_err, flush=True)
    _HAVE_HE = False


def _is_rtl(s):
    """A line renders RTL only if it is PREDOMINANTLY Hebrew. A mixed line (Hebrew + English words +
    numbers) lays out badly under PIL bidi, so we keep it LTR -- and system messages are single-script."""
    heb = sum(1 for c in s if "֐" <= c <= "׿")
    lat = sum(1 for c in s if c.isascii() and c.isalpha())
    return heb > lat


def _wrap_px(text, maxpx, font=None):
    """Wrap to fit maxpx using the real font metrics (per-element font)."""
    font = font or _HE_FONT
    if not text:
        return [""]
    if not _HAVE_HE:
        return textwrap.wrap(text, max(int(maxpx / 9), 12)) or [""]
    lines, cur = [], ""
    for wd in text.split(" "):
        trial = (cur + " " + wd).strip()
        if not cur or font.getlength(trial) <= maxpx:
            cur = trial
        else:
            lines.append(cur); cur = wd
    if cur:
        lines.append(cur)
    return lines or [""]


_TAG_COL = (163, 149, 139)   # dim tag column (BGR = mockup #8b95a3)


def _draw_pane(panel, header, rows, conv_top, height):
    """Draw the pane: a header (top-down) then the conversation (bottom-up) as a tag column + value.
    header: list of (text, bgr_color, fontkey). rows: (tag, value, bgr_color, rtl) or None (turn split).
    Fonts per element: Hebrew values = DejaVuSans, English values = Ubuntu, tags = DejaVuSansMono.
    Hebrew values are right-aligned (RTL); English values start after the tag. Falls back to cv2 Hershey."""
    W = panel.shape[1]; TAG_R = 66; VALX = 76        # tags RIGHT-aligned ending at TAG_R; values start at VALX
    if not _HAVE_HE:
        y = 22
        for text, col, _fk in header:
            cv2.putText(panel, ascii_only(text), (12, y), FONT, 0.5, tuple(int(x) for x in col), 1, cv2.LINE_AA); y += 19
        yy = height - 14
        for r in reversed(rows):
            if yy < conv_top + 14:
                break
            if r is None:
                yy -= 11; continue
            tag, value, col, _ = r; col = tuple(int(x) for x in col)
            if tag:
                (tw, _), _ = cv2.getTextSize(ascii_only(tag), FONT, 0.42, 1)
                cv2.putText(panel, ascii_only(tag), (max(6, TAG_R - tw), yy), FONT, 0.42, _TAG_COL, 1, cv2.LINE_AA)
            cv2.putText(panel, ascii_only(value), (VALX, yy), FONT, 0.46, col, 1, cv2.LINE_AA); yy -= 21
        return panel
    _F = {"tag": _FONT_TAG, "val": _FONT_VAL, "he": _FONT_HE}
    img = Image.fromarray(panel); d = ImageDraw.Draw(img)
    y = 12
    for text, col, fk in header:                               # header top-down
        f = _F.get(fk, _FONT_VAL); d.text((12, y), text, font=f, fill=tuple(int(x) for x in col)); y += 19
    d.line((10, conv_top - 8, W - 10, conv_top - 8), fill=(59, 49, 43))
    yy = height - 14 - _FONT_HE.size
    for r in reversed(rows):
        if yy < conv_top:
            break
        if r is None:                                          # turn separator
            d.line((10, yy + 13, W - 10, yy + 13), fill=(59, 49, 43)); yy -= 14; continue
        tag, value, col, rtl = r; col = tuple(int(x) for x in col)
        vfont = _FONT_HE if rtl else _FONT_VAL
        wrapped = _wrap_px(value, W - VALX - 12, vfont)
        for j, wl in enumerate(reversed(wrapped)):             # bottom wrapped line first
            ly = yy - j * 21
            if rtl:
                vis = wl if _RAQM else get_display(wl); tw = d.textlength(vis, font=vfont)
                d.text((max(VALX, W - tw - 12), ly), vis, font=vfont, fill=col)
            else:
                d.text((VALX, ly), wl, font=vfont, fill=col)
        if tag:                                                # tag on the row's TOP line, right-aligned, mono
            tw = d.textlength(tag, font=_FONT_TAG)
            d.text((max(6, TAG_R - tw), yy - (len(wrapped) - 1) * 21), tag, font=_FONT_TAG, fill=_TAG_COL)
        yy -= 21 * len(wrapped)
    return np.array(img)


def draw_box(img, box, color, label=None, thick=2):
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)
    if label:
        cv2.putText(img, label, (x1, max(y1 - 6, 12)), FONT, 0.5, color, 1, cv2.LINE_AA)


def _model_lines():
    """The live model stack, one (label, value) per subsystem, read from the env/config so it reflects
    what is actually wired -- not a hardcoded string. harden2 is single-stack (Gemma 4 / SAM3 / whisper);
    the env knobs still drive these, so a future swap shows here automatically."""
    planner = config.PLANNER
    planner = {"gemma4": "Gemma-4-E4B", "qwen3vl": "Qwen3-VL-4B"}.get(planner, planner)
    eyes = os.path.basename(config.SAM3_MODEL_DIR)
    asr = config.ASR_MODEL_PATH
    if "ivrit" in asr:   ears = "whisper-ivrit-v3"
    elif asr:            ears = os.path.basename(os.path.dirname(asr)) or "whisper"
    else:                ears = "whisper-ivrit-v3"
    return [("brain", planner), ("eyes", eyes), ("ears", ears)]


def _is_miss(t):
    """A model line reporting the target is not present (tags miss + the red status light)."""
    return (t.startswith('no "') or t.startswith("I don't see")
            or t.startswith("\u05dc\u05d0 \u05e8\u05d5\u05d0\u05d4") or t.startswith("\u05dc\u05d0 \u05de\u05e6\u05d0\u05ea\u05d9"))


def chat_kind(text):
    """Classify a GENERIC model say() line to its kind. Used ONLY at the say() write site, where the
    kind is not known structurally; every other write site tags directly. Overlay never re-parses."""
    if text.startswith("rejected -- "):  return "reject"
    if _is_miss(text):                    return "miss"
    if text.startswith("Highlighting:"):  return "action"
    if text.startswith("\u05e1\u05e4\u05e8\u05ea\u05d9"):          return "answer"
    return "scene"


def render_chat(height, chat, thinking, killed, session_dir):
    """Build the chat panel from a SNAPSHOT. The caller holds S.lock and passes chat/thinking/killed;
    this function touches no shared state. chat: list of (role, text, kind). A turn runs from one user line
    to the next; async results (highlight/describe land from a worker thread) stay in their turn."""
    w = config.CHAT_W
    panel = np.empty((height, w, 3), np.uint8); panel[:] = (31, 25, 22)   # mockup dark ground (#16191f)

    C = {"you": (120, 210, 255), "light": (240, 235, 231), "dim": (163, 149, 139),
         "green": (100, 220, 60), "amber": (41, 180, 240), "model": (176, 235, 160),
         "red": (107, 107, 255), "spoken": (74, 210, 255), "cmd": (245, 235, 150)}

    # header: title (Ubuntu), then ONE line per subsystem derived from the live env/config (mono), then
    # the dump path + key hints. Each line follows the real config, so it never lies -- if the env names
    # a different backend, the line changes with it. "·" is the mid-line dot (not ".").
    header = [("MVD harden2 — Hebrew voice drone", C["light"], "val")]
    for _lbl, _val in _model_lines():
        header.append((f"{_lbl:<6}{_val}", C["dim"], "tag"))
    if session_dir:
        _dump = "/".join(session_dir.rstrip("/").split("/")[-2:])
        header.append(("dump: " + ascii_only(_dump)[:54], C["dim"], "tag"))
    header.append(("F5 talk  ·  c clear  ·  q quit", C["dim"], "tag"))
    if killed:
        header.append(("MANUAL OVERRIDE — press M to re-arm", C["red"], "val"))
    conv_top = 12 + 19 * len(header) + 8

    # Group the flat chat into turns. A turn STARTS at a user line and runs to the next user line.
    # Highlight + describe results land SECONDS later from a worker thread, so they must stay in the
    # turn that produced them. The old ("meta","") separator was emitted synchronously BEFORE those
    # async lines -- it split a turn from its own result, so a miss bled into the next turn's Kind
    # colour. Grouping on the user line fixes that; the legacy separator row is ignored.
    turns, cur = [], []
    for role, text, kind in chat:
        if role == "user":
            if cur: turns.append(cur)
            cur = [(role, text, kind)]
        else:
            if not cur: cur = []
            cur.append((role, text, kind))
    if cur: turns.append(cur)
    if thinking:                                                 # belongs to the live (last) turn
        if turns: turns[-1].append(("model", "thinking...", "scene"))
        else: turns.append([("model", "thinking...", "scene")])

    # Row rendering switches on the KIND tagged at the write site -- no startswith, no partition.
    _KIND_TAG = {"user": "You", "scene": "Scene", "spoken": "Spoken", "answer": "Answer",
                 "action": "Action", "reject": "reject", "miss": "miss", "en": "En",
                 "kind_hl": "Kind", "kind_meta": "Kind", "action_meta": "Action", "sam3": "SAM3",
                 "cmd_head": "Cmds", "cmd": ""}
    _RTL_FIXED = {"answer": True, "action": False, "kind_hl": False, "cmd_head": False, "cmd": False}
    rows = []
    for ti, lines in enumerate(turns):
        if ti: rows.append(None)                                 # divider between turns
        fail = any(k == "miss" for _r, _t, k in lines)
        ok   = any(k in ("action", "sam3") for _r, _t, k in lines)
        hl_col = C["red"] if fail else (C["green"] if ok else C["amber"])   # highlight outcome colour
        for role, text, kind in lines:
            tag = _KIND_TAG.get(kind, "Scene")
            if kind == "kind_hl":                             col = hl_col
            elif kind in ("action", "sam3"):                  col = C["green"]
            elif kind == "reject":                            col = C["red"]
            elif kind == "miss":                              col = C["amber"]
            elif kind == "user":                              col = C["you"]
            elif kind == "spoken":                            col = C["spoken"]
            elif kind in ("cmd_head", "cmd"):                 col = C["cmd"]
            elif kind in ("en", "kind_meta", "action_meta"):  col = C["light"]
            else:                                             col = C["model"]     # scene, answer
            rtl = _RTL_FIXED.get(kind, _is_rtl(text))
            rows.append((tag, text, col, rtl))
    if not rows:
        rows = [("", "press F5, speak, press F5.", (150, 150, 150), False),
                ("", 'e.g. "highlight the red car"', (150, 150, 150), False)]
    return _draw_pane(panel, header, rows, conv_top, height)
