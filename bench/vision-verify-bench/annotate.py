#!/usr/bin/env python3
"""Human truth, fast. Shows each row's image with the proposed box (green = estimate/SAM3, orange = yours).

Keys:
    y     the box is right (present)
    n     absent / nothing to draw
    d     the head exists but the relation does not hold (misplaced)
    drag  draw the correct box
    r     clear all boxes
    x     remove the last box
    s     skip
    q     save and quit

Writes back into dataset/queries.jsonl: gt_box, gt_boxes, present, head_present,
box_source='human', labeled_by.
Run: python3 annotate.py [--only-unlabeled] [--rows A-B] [--reset-row N] [--reset]   (needs a display)
"""
import datetime
import getpass
import json
import os
import sys

import cv2

sys.path.insert(0, "/root/groundstation/projects/integration_harden2")
os.environ.setdefault("MVD_HOME", "integration_harden2")

import config
import app.render as overlay   # the demo's own screen code (was overlay.py)
from app.render import draw_box, FONT   # the demo's own box and label style

COL_GUESS = config.COL_YOLOE_HL       # green: the SAM3 / estimate guess
COL_HUMAN = (255, 140, 0)             # orange: a box you added yourself

SOURCE = {"bed": "bedroom", "sess": "your live session", "old": "old bench image"}
CLASS = {1: "simple, present", 2: "simple, absent", 3: "relation, holds",
         4: "related noun absent", 5: "both present, relation wrong", 6: "look-alike trap"}
RELW = {"next_to": "next to", "on_top_of": "on", "held_by": "held by",
        "talking_to": "talking to", "inside": "inside"}
KEYS = ["drag = add a box", "right-click = remove that box", "x = remove the last box",
        "r = clear all", "s = skip", "q = save and quit"]

HERE = os.path.dirname(os.path.abspath(__file__))
QUERIES = os.path.join(HERE, "dataset/queries.jsonl")

# Mouse state shared with the OpenCV callback, and the SAM3 proposals for the color rule.
state = {"boxes": [], "drag": None}
PROPOSALS = {}


# ---------------------------------------------------------------- text drawing
def wrap_cv(text, scale, max_px):
    """Greedy word wrap for a cv2 Hershey line, measured with getTextSize."""
    lines = []
    current = ""
    for word in text.split(" "):
        candidate = (current + " " + word).strip()
        if cv2.getTextSize(candidate, FONT, scale, 1)[0][0] <= max_px or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def outlined(img, y, text, scale=0.62, up=False):
    """White text with a thin dark outline, wrapped to the frame. Returns the y after the block.
    up=True stacks the lines upward from y (for text anchored at the bottom)."""
    lines = wrap_cv(text, scale, img.shape[1] - 16)
    step = int(30 * scale / 0.62)
    if up:
        lines = list(reversed(lines))
    for i, line in enumerate(lines):
        yy = y - i * step if up else y + i * step
        cv2.putText(img, line, (8, yy), FONT, scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, line, (8, yy), FONT, scale, (255, 255, 255), 1, cv2.LINE_AA)
    return (y - len(lines) * step) if up else (y + len(lines) * step)


def hebrew_line(img, text, y):
    """The spoken Hebrew, right-aligned, the demo's font and bidi rules, dark stroke instead of a bar."""
    if not text or not getattr(overlay, "_HAVE_HE", False):
        return img
    import numpy as np
    from PIL import Image, ImageDraw
    pil = Image.fromarray(img[:, :, ::-1])
    draw = ImageDraw.Draw(pil)
    for i, wrapped in enumerate(overlay._wrap_px(text, pil.width - 20, overlay._FONT_HE)):
        visual = wrapped if overlay._RAQM else overlay.get_display(wrapped)
        text_width = draw.textlength(visual, font=overlay._FONT_HE)
        y_line = y + i * (overlay._FONT_HE.size + 6)
        draw.text((pil.width - text_width - 10, y_line), visual, font=overlay._FONT_HE,
                  fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    return np.array(pil)[:, :, ::-1].copy()


def stack_up(img, y, lines, scale):
    """Draw lines bottom-up from y, keeping their order top-to-bottom. Returns the y above the block."""
    step = int(30 * scale / 0.62)
    for i, line in enumerate(reversed(lines)):
        outlined(img, y - i * step, line, scale)
    return y - len(lines) * step


# ---------------------------------------------------------------- row text
def question(row):
    """The one question this row asks, then one key per line."""
    head = row["head"]
    if not row.get("related"):
        return [f"This row asks for: the {head}. Put a box on EVERY {head} in the picture.",
                f"y = the boxes are right, one per {head}",
                f"n = there is no {head} here"]
    other = row["related"][0]["noun"]
    rel = f"{RELW.get(row['relation'], row['relation'])} the {other}"
    return [f"This row asks for: the {head} {rel}.",
            f"y = yes, I see a {head} {rel}   (a box on each one that fits)",
            f"d = there is a {head} and a {other}, but no {head} is {rel}",
            f"n = there is no {head}, or no {other}, in the picture"]


def describe(row):
    """One header line: source, class, and what to find."""
    source = SOURCE.get(row["id"].split("_")[0], "image")
    want = row["head"]
    if row.get("related"):
        want += f" {RELW.get(row['relation'], row['relation'])} {row['related'][0]['noun']}"
    return f'{source}  |  {CLASS.get(row["cls"], row["cls"])}  |  find: {want}'


# ---------------------------------------------------------------- file + reset
def load_rows():
    return [json.loads(line) for line in open(QUERIES)]


def save_rows(rows):
    with open(QUERIES, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def handle_reset_row(rows, number):
    """--reset-row N: forget ONE verdict by 1-based row number, then save."""
    row = rows[number - 1]
    row["box_source"] = "sam3-propose" if row.get("sam3_box") else "estimate"
    row["gt_box"] = row.get("sam3_box")
    row["gt_boxes"] = []
    row.pop("labeled_by", None)
    row.pop("many", None)
    row["present"] = row.get("expected_present", row.get("present"))
    row["head_present"] = row.get("expected_head_present", row.get("head_present"))
    save_rows(rows)
    print(f"row {number} ({row['id']}) reset; run again with --only-unlabeled")


def handle_reset_all(rows):
    """--reset: forget every human verdict; the guesses come back, then save."""
    count = 0
    for row in rows:
        if row.get("box_source") != "human":
            continue
        row["box_source"] = "sam3-propose" if row.get("sam3_box") else "estimate"
        row["gt_box"] = row.get("sam3_box")
        row.pop("labeled_by", None)
        # The original expectation, not the human key.
        row["present"] = row.get("expected_present", row.get("present"))
        row["head_present"] = row.get("expected_head_present", row.get("head_present"))
        count += 1
    save_rows(rows)
    print(f"reset {count} human verdicts; run again without --reset")


# ---------------------------------------------------------------- interaction
def on_mouse(event, x, y, flags, _):
    """Left-drag adds a box; right-click removes the smallest box under the cursor."""
    if event == cv2.EVENT_LBUTTONDOWN:
        state["drag"] = (x, y)
        return
    if event == cv2.EVENT_LBUTTONUP and state["drag"]:
        x0, y0 = state["drag"]
        box = [min(x0, x), min(y0, y), max(x0, x), max(y0, y)]
        state["drag"] = None
        if box[2] - box[0] > 6 and box[3] - box[1] > 6:
            state["boxes"].append(box)
        return
    if event == cv2.EVENT_RBUTTONDOWN:
        under = [b for b in state["boxes"] if b[0] <= x <= b[2] and b[1] <= y <= b[3]]
        if under:
            state["boxes"].remove(min(under, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])))


def start_boxes(row):
    """The boxes to show first: your saved ones if human, else the SAM3 proposals."""
    if row.get("box_source") == "human":
        saved = row.get("gt_boxes") or ([row["gt_box"]] if row.get("gt_box") else [])
        return [list(b) for b in saved]
    guesses = PROPOSALS.get(row["id"]) or ([row["sam3_box"]] if row.get("sam3_box") else [])
    return [list(b) for b in guesses]


def box_color(row, index, boxes):
    """Orange only for a box you just added on top of the SAM3 proposals; green otherwise."""
    is_last = index == len(boxes) - 1
    added_by_you = row.get("box_source") != "human" and len(boxes) > len(PROPOSALS.get(row["id"], []))
    return COL_HUMAN if is_last and added_by_you else COL_GUESS


def render(img, row, index, total):
    """Draw the frame with its boxes, header, Hebrew line, keys and question."""
    view = img.copy()
    for j, box in enumerate(state["boxes"]):
        label = row["head"] if j == 0 else None
        draw_box(view, [int(c) for c in box], box_color(row, j, state["boxes"]), label, 2)
    y = outlined(view, 26, f"row {index + 1} of {total}   {describe(row)}")
    view = hebrew_line(view, row["he"], y - 16)
    y = stack_up(view, view.shape[0] - 12, KEYS, 0.5)
    stack_up(view, y - 10, question(row), 0.6)
    return view


def label_one(img, row, index, total, who):
    """Show one row and block until a verdict/skip/quit key. Returns 'next' or 'quit'."""
    state["boxes"] = start_boxes(row)
    while True:
        cv2.imshow("annotate", render(img, row, index, total))
        key = cv2.waitKey(30) & 0xFF
        if key == ord("y"):
            if not state["boxes"]:
                print("y needs at least one box; draw one, or press n")
                continue
            row.update(present=True, head_present=True, gt_boxes=state["boxes"],
                       gt_box=state["boxes"][0], box_source="human", labeled_by=who)
            row.pop("many", None)
            return "next"
        if key == ord("n"):
            row.update(present=False, head_present=False, gt_boxes=[], gt_box=None,
                       box_source="human", labeled_by=who)
            return "next"
        if key == ord("d"):
            first = state["boxes"][0] if state["boxes"] else None
            row.update(present=False, head_present=True, gt_boxes=state["boxes"],
                       gt_box=first, box_source="human", labeled_by=who)
            return "next"
        if key == ord("r"):
            state["boxes"] = []
        if key == ord("x") and state["boxes"]:
            state["boxes"].pop()
        if key == ord("s"):
            return "next"
        if key == ord("q"):
            return "quit"


def parse_range(argv, total):
    """--rows A-B gives a 1-based inclusive range; default is every row."""
    if "--rows" not in argv:
        return 1, total
    a, b = argv[argv.index("--rows") + 1].split("-")
    return int(a), int(b)


def main():
    global PROPOSALS
    rows = load_rows()

    if "--reset-row" in sys.argv:
        handle_reset_row(rows, int(sys.argv[sys.argv.index("--reset-row") + 1]))
        return
    if "--reset" in sys.argv:
        handle_reset_all(rows)
        return

    only_unlabeled = "--only-unlabeled" in sys.argv
    who = f"{getpass.getuser()} {datetime.date.today()}"
    try:
        PROPOSALS = json.load(open(os.path.join(HERE, "dataset/proposals.json")))
    except Exception:
        PROPOSALS = {}

    cv2.namedWindow("annotate", cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback("annotate", on_mouse)
    low, high = parse_range(sys.argv, len(rows))

    for index, row in enumerate(rows):
        if not (low <= index + 1 <= high):
            continue
        if only_unlabeled and row.get("box_source") == "human":
            continue
        img = cv2.imread(os.path.join(HERE, "dataset/images", row["image"]))
        if img is None:
            continue
        if label_one(img, row, index, len(rows), who) == "quit":
            save_rows(rows)
            cv2.destroyAllWindows()
            return

    save_rows(rows)
    cv2.destroyAllWindows()
    print("saved", QUERIES)


if __name__ == "__main__":
    main()
