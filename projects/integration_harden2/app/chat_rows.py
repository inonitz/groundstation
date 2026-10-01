"""The chat model: which kind each chat line is, its tag, colour and direction, the pane
header, and the chat grouped into turns and rows. PURE: no app state, no threads, no
drawing."""
import os

import config
from app.draw import ascii_only
from util.hebrew import is_hebrew


CHAT_COLOURS = config.CHAT_COLOURS       # the palette lives in config (owner D8 a)

# Rows switch on the KIND tagged at the write site -- no startswith, no partition.
_KIND_TAG = {
    "user": "You",
    "scene": "Scene",
    "spoken": "Spoken",
    "answer": "Answer",
    "action": "Action",
    "reject": "reject",
    "miss": "miss",
    "en": "En",
    "kind_hl": "Kind",
    "kind_meta": "Kind",
    "action_meta": "Action",
    "sam3": "SAM3",
    "cmd_head": "Cmds",
    "cmd": "",
}
# The colour of each kind. kind_hl is coloured by the turn's highlight outcome; a kind
# not listed here (scene, answer) is a model line.
_KIND_COLOUR = {
    "action": "green",
    "sam3": "green",
    "reject": "red",
    "miss": "amber",
    "user": "you",
    "spoken": "spoken",
    "cmd_head": "cmd",
    "cmd": "cmd",
    "en": "light",
    "kind_meta": "light",
    "action_meta": "light",
}
# Kinds with a fixed direction; every other kind is RTL when its text is mostly Hebrew.
_RTL_FIXED = {
    "answer": True,
    "action": False,
    "kind_hl": False,
    "cmd_head": False,
    "cmd": False,
}

PLANNER_NAMES = {"gemma4": "Gemma-4-E4B"}


def _is_rtl(s):
    """A line renders RTL only if it is PREDOMINANTLY Hebrew. A mixed line (Hebrew +
    English words + numbers) lays out badly under PIL bidi, so we keep it LTR -- and
    system messages are single-script."""
    heb = sum(1 for c in s if is_hebrew(c))
    lat = sum(1 for c in s if c.isascii() and c.isalpha())
    return heb > lat


def _model_lines():
    """The live model stack, one (label, value) per subsystem, read from the env/config
    so it reflects what is actually wired -- not a hardcoded string. harden2 is
    single-stack (Gemma 4 / SAM3 / whisper); the env knobs still drive these, so a
    future swap shows here automatically."""
    planner = PLANNER_NAMES.get(config.PLANNER, config.PLANNER)
    eyes = os.path.basename(config.SAM3_MODEL_DIR)

    asr = config.ASR_MODEL_PATH
    if "ivrit" in asr:
        ears = "whisper-ivrit-v3"
    elif asr:
        ears = os.path.basename(os.path.dirname(asr)) or "whisper"
    else:
        ears = "whisper-ivrit-v3"
    return [("brain", planner), ("eyes", eyes), ("ears", ears)]


def _is_miss(t):
    """A model line reporting the target is not present (tags miss +
    the red status light)."""
    return (
        t.startswith('no "')
        or t.startswith("I don't see")
        or t.startswith("\u05dc\u05d0 \u05e8\u05d5\u05d0\u05d4")
        or t.startswith("\u05dc\u05d0 \u05de\u05e6\u05d0\u05ea\u05d9")
    )


def chat_kind(text):
    """Classify a GENERIC model say() line to its kind. Used ONLY at the say() write
    site, where the kind is not known structurally; every other write site tags
    directly. Overlay never re-parses."""
    if text.startswith("rejected -- "):
        return "reject"
    if _is_miss(text):
        return "miss"
    if text.startswith("Highlighting:"):
        return "action"
    if text.startswith("\u05e1\u05e4\u05e8\u05ea\u05d9"):
        return "answer"
    return "scene"


def chat_header(session_dir, killed):
    """The header: title (Ubuntu), then ONE line per subsystem derived from the live
    env/config (mono), then the dump path + key hints. Each line follows the real
    config, so it never lies -- if the env names a different backend, the line changes
    with it. "·" is the mid-line dot (not ".")."""
    dump = ""
    C = CHAT_COLOURS

    header = [("MVD harden2 — Hebrew voice drone", C["light"], "val")]
    for label, value in _model_lines():
        header.append((f"{label:<6}{value}", C["dim"], "tag"))

    if session_dir:
        dump = "/".join(session_dir.rstrip("/").split("/")[-2:])
        header.append(("dump: " + ascii_only(dump)[:54], C["dim"], "tag"))

    header.append((
        f"{config.PUSH_TO_TALK_KEY_NAME} talk  ·  {config.KILL_KEY_NAME} kill  ·  "
        f"{config.CLEAR_KEY_NAME} clear  ·  [ ] or wheel scroll  ·  "
        f"{config.QUIT_KEY_NAME} quit",
        C["dim"],
        "tag"
    ))
    if killed:
        header.append((
            f"MANUAL OVERRIDE — press {config.KILL_KEY_NAME} to re-arm",
            C["red"],
            "val"
        ))
    return header


def group_turns(chat, thinking):
    """Group the flat chat into turns. A turn STARTS at a user line and runs to the next
    user line. Highlight + describe results land SECONDS later from a worker thread, so
    they must stay in the turn that produced them. The old ("meta","") separator was
    emitted synchronously BEFORE those async lines -- it split a turn from its own
    result, so a miss bled into the next turn's Kind colour. Grouping on the user line
    fixes that; the legacy separator row is ignored."""
    turns = []
    cur = []

    for role, text, kind in chat:
        if role == "user":
            if cur:
                turns.append(cur)
            cur = [(role, text, kind)]
            continue
        cur.append((role, text, kind))
    if cur:
        turns.append(cur)

    # "thinking..." belongs to the live (last) turn
    if not thinking:
        return turns
    if turns:
        turns[-1].append(("model", "thinking...", "scene"))
    else:
        turns.append([("model", "thinking...", "scene")])
    return turns


def _highlight_colour(lines):
    """The colour of a turn's highlight outcome: red on a miss, green on a hit, amber
    while it is still open."""
    fail = any(k == "miss" for _r, _t, k in lines)
    ok = any(k in ("action", "sam3") for _r, _t, k in lines)
    if fail:
        return CHAT_COLOURS["red"]
    if ok:
        return CHAT_COLOURS["green"]
    return CHAT_COLOURS["amber"]


def turn_rows(turns):
    """The pane rows: (tag, value, bgr_color, rtl) per line; None between turns."""
    hl_col = None
    col = None
    rtl = False
    rows = []

    for ti, lines in enumerate(turns):
        if ti:
            rows.append(None)                                 # divider between turns

        hl_col = _highlight_colour(lines)
        for _role, text, kind in lines:
            if kind == "kind_hl":
                col = hl_col
            else:
                col = CHAT_COLOURS[_KIND_COLOUR.get(kind, "model")]
            rtl = _RTL_FIXED.get(kind, _is_rtl(text))
            rows.append((_KIND_TAG.get(kind, "Scene"), text, col, rtl))
    return rows
