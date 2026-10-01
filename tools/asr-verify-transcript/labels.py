"""The labelling logic of the recordings (path B of the recognizer benchmark).

Each clip of datasets/asr/manifest.jsonl gets a confirmed sentence and an expected
result. This module proposes both from the nearest case of datasets/recognizer/, turns an
expected result into plain words, reads the owner's corrections, and keeps the recordings
file (the format: bench/recognizer/README.md). server.py puts a web page on top of it.
It replaced bench/recognizer/confirm.py (owner UI1, 2026-09-29).
"""
import difflib
import json
import os
import re
import sys
import threading

ROOT = "/root/groundstation"
sys.path.insert(0, os.path.join(ROOT, "bench/recognizer"))
sys.path.insert(0, os.path.join(ROOT, "projects/integration_harden2"))

from scorer import KIND_WORDS as VISION_WORDS    # the scorer's words per vision kind
from scorer import read_notation                  # the benchmark's one notation reader
from util.guarded import atomic_write, parse_json
from util.mission import step_text

MANIFEST = os.path.join(ROOT, "datasets/asr/manifest.jsonl")
CASES_DIR = os.path.join(ROOT, "datasets/recognizer")
OUT = os.path.join(ROOT, "datasets/asr/recordings.json")
ALTERNATIVES = 5
# Below this similarity the nearest case may be another sentence: propose whisper's
# text as the sentence. 0.9, because one changed direction word ("right" vs "forward")
# still scores 0.88.
SENTENCE_MATCH = 0.9
MARKS = re.compile(r"[֑-ׇ]")       # Hebrew vowel and cantillation marks
NON_WORD = re.compile(r"[^\w]+")

# fly_by axis -> (the word for +, the word for -)
AXIS_WORDS = {
    "dx": ("forward", "backwards"),
    "dy": ("right", "left"),
    "dz": ("up", "down"),
}
KIND_WORDS = {
    "none": "Nothing flies (a reject, an empty plan, a vision request or a halt)",
    "emergency": "Emergency stop",
    "open": "Any mission that flies",
    "review": "Not graded (review)",
}


def normalize(text):
    """Hebrew text without marks and punctuation, for the similarity only."""
    bare = MARKS.sub("", text)
    return NON_WORD.sub(" ", bare).strip().lower()


def number(value):
    """10.0 -> "10", 1.5 -> "1.5"."""
    return f"{value:g}"


# ---------------------------------------------------------------- plain words
def fly_words(key, value):
    plus, minus = AXIS_WORDS.get(key, ("+" + str(key), "-" + str(key)))
    if value is None:
        return f"fly {plus} or {minus}, any distance"
    if value == "+":
        return f"fly {plus}, any distance"
    if value == "-":
        return f"fly {minus}, any distance"
    if isinstance(value, list):
        return f"fly {number(value[1])} m, {plus} or {minus}"
    if value < 0:
        return f"fly {minus} {number(-value)} m"
    return f"fly {plus} {number(value)} m"


def turn_words(value):
    if value is None:
        return "turn, any angle"
    if value == "+":
        return "turn right (clockwise), any angle"
    if value == "-":
        return "turn left (counter-clockwise), any angle"
    if isinstance(value, list):
        return f"turn {number(value[1])}°, either way"
    if value < 0:
        return f"turn left {number(-value)}° (counter-clockwise)"
    return f"turn right {number(value)}° (clockwise)"


def step_words(step):
    """One expected step [type, key, value] -> plain words ("fly backwards 8 m")."""
    kind, key, value = step
    if kind == "fly_by":
        return fly_words(key, value)
    if kind == "spin_by":
        return turn_words(value)
    if kind == "delay":
        if isinstance(value, (int, float)):
            return f"wait {number(value)} s"
        return "wait, any time"
    if kind == "takeoff":
        return "take off"
    if kind == "land":
        return "land"
    # a step type with no words yet: the chat's own text for it
    return step_text({"type": kind, key: value} if key else {"type": kind})


# The plan editor's rows (owner UI1 (3)): action -> (step type, key, sign). The signs are
# the benchmark's (datasets/recognizer/commands.json): forward dx+ (g_fwd1), right dy+
# (g_right4), up dz+ (up10), turn right = clockwise = +degrees (spin90cw).
ROW_ACTIONS = {
    "fly forward": ("fly_by", "dx", 1),
    "fly back": ("fly_by", "dx", -1),
    "fly right": ("fly_by", "dy", 1),
    "fly left": ("fly_by", "dy", -1),
    "go up": ("fly_by", "dz", 1),
    "go down": ("fly_by", "dz", -1),
    "turn right": ("spin_by", "degrees", 1),
    "turn left": ("spin_by", "degrees", -1),
    "turn either way": ("spin_by", "degrees", 0),
    "take off": ("takeoff", None, 0),
    "land": ("land", None, 0),
    "wait": ("delay", "seconds", 1),
}


def row_step(row):
    """One editor row {"action", "amount"} -> (step, error). An empty amount means any
    amount in that direction ("+" or "-"); a turn either way needs its angle."""
    action = row.get("action")
    amount = str(row.get("amount", "")).strip()
    value = None
    if action not in ROW_ACTIONS:
        return None, f"unknown action {action!r}"
    kind, key, sign = ROW_ACTIONS[action]
    if key is None:
        return [kind, None, None], None
    if not amount:
        if sign == 0:
            return None, f"{action}: type the angle"
        return [kind, key, "+" if sign > 0 else "-"], None
    if not re.fullmatch(r"\d+(\.\d+)?", amount):
        return None, f"{action}: {amount!r} is not a positive number"
    value = float(amount)
    if sign == 0:
        return [kind, key, ["abs", value]], None
    return [kind, key, sign * value], None


def expect_from_rows(rows):
    """The editor's rows -> (a mission expect, error)."""
    steps = []
    if not rows:
        return None, "add a step, or choose nothing flies, halt or vision request"
    for row in rows:
        step, error = row_step(row)
        if error is not None:
            return None, error
        steps.append(step)
    return {"kind": "mission", "steps": steps}, None


def step_row(step):
    """One expected step -> an editor row (the reverse of row_step)."""
    kind, key, value = step
    sign = 1
    amount = ""
    if kind in ("takeoff", "land"):
        return {"action": "take off" if kind == "takeoff" else "land", "amount": ""}
    if isinstance(value, list):
        return {"action": "turn either way", "amount": number(value[1])}
    if value == "-" or (isinstance(value, (int, float)) and value < 0):
        sign = -1
    if isinstance(value, (int, float)):
        amount = number(abs(value))
    for action, (a_kind, a_key, a_sign) in ROW_ACTIONS.items():
        if (a_kind, a_key, a_sign) == (kind, key, sign):
            return {"action": action, "amount": amount}
    return {"action": "wait", "amount": amount}


def rows_of(expect):
    """A mission's editor rows; [] for any other kind."""
    if expect.get("kind") != "mission":
        return []
    return [step_row(step) for step in expect.get("steps", [])]


# A vision request's kind is saved in its own field, "vision" (owner SC1, 2026-09-30):
# the scorer fails a request of another kind. "any" saves no field: every kind passes.
VISION_KINDS = tuple(VISION_WORDS)
WORD_RE = re.compile(r"[a-z][a-z' -]*")


def vision_expect(kind, text):
    """The vision editor -> (a perception expect, error). kind: highlight, count,
    describe or "any"; text: the target words, "," between words, "/" between
    synonyms ("red, chair / seat")."""
    groups = []
    if kind != "any" and kind not in VISION_KINDS:
        return None, f"unknown vision kind {kind!r}"
    for part in (text or "").split(","):
        words = [w.strip().lower() for w in part.split("/") if w.strip()]
        if not words:
            continue
        bad = [w for w in words if not WORD_RE.fullmatch(w)]
        if bad:
            return None, f"English words only: {', '.join(bad)}"
        groups.append(words)
    if kind == "any" and not groups:
        return None, "choose a kind or type a target word"
    if kind == "any":
        return {"kind": "perception", "groups": groups}, None
    return {"kind": "perception", "vision": kind, "groups": groups}, None


def vision_of(expect):
    """A perception expect -> the vision editor's {"kind", "words"}."""
    groups = expect.get("groups", [])
    return {
        "kind": expect.get("vision", "any"),
        "words": ", ".join(" / ".join(g) for g in groups),
    }


def plan_words(expect):
    """An expected result -> a list of plain-word lines."""
    kind = expect.get("kind")
    if kind == "mission":
        return [step_words(step) for step in expect.get("steps", [])]
    if kind == "perception":
        vision = vision_of(expect)
        what = "A vision request (any kind)"
        if vision["kind"] != "any":
            what = f"A {vision['kind']} request"
        if not vision["words"]:
            return [what]
        return [f"{what} that names: " + vision["words"].replace(", ", "; ")]
    return [KIND_WORDS.get(kind, f"kind {kind}")]


def read_expect(text):
    """What the owner typed -> (expect, error). A JSON object, or the live-list
    notation ("dx-8", "dz+10, +90, takeoff", "EMPTY", "halt", "VLM")."""
    value = None
    text = (text or "").strip()
    if not text:
        return None, "empty: type a plan, for example dx-8"
    if not text.startswith("{"):
        value = read_notation(text)
        if value["kind"] == "review":
            return None, "not understood: try dx-8, dz+10, +90, takeoff, EMPTY, halt"
        return value, None
    ok, value = parse_json(text)
    if not ok:
        return None, f"not JSON: {value}"
    if not isinstance(value, dict) or "kind" not in value:
        return None, 'a JSON plan needs a "kind"'
    return value, None


# ---------------------------------------------------------------- the data
def load_manifest():
    with open(MANIFEST, encoding="utf-8") as src:
        return [json.loads(line) for line in src if line.strip()]


def load_cases():
    """Every case of the topical files in datasets/recognizer/ as (file name, case,
    normalized he). A live list holds case names only: skipped."""
    pool = []
    for name in sorted(os.listdir(CASES_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(CASES_DIR, name), encoding="utf-8") as src:
            data = json.load(src)
        if "list" in data:
            continue
        for case in data["cases"]:
            pool.append((name, case, normalize(case["he"])))
    return pool


def nearest(pool, heard):
    """The ALTERNATIVES cases most similar to whisper's text, one per distinct sentence:
    [(ratio, file name, case)], best first."""
    ranked = []
    seen = set()
    best = []
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(normalize(heard))

    for name, case, text in pool:
        matcher.set_seq1(text)
        ranked.append((matcher.ratio(), name, case, text))
    ranked.sort(key=lambda item: -item[0])

    for ratio, name, case, text in ranked:
        if text in seen:
            continue
        seen.add(text)
        best.append((ratio, name, case))
        if len(best) == ALTERNATIVES:
            break
    return best


def heard_of(row):
    """Whisper's exact text; "" for a clip whisper wrote nothing for (the manifest
    holds null there)."""
    return row["transcript_he"] or ""


def wav_of(row):
    return os.path.join("datasets/asr", row["clip"])


def propose(row, choice):
    """This clip's case, built from one nearest case (ratio, file name, case)."""
    ratio, name, case = choice
    sentence = case["he"]
    if ratio < SENTENCE_MATCH:
        sentence = heard_of(row)
    return {
        "name": os.path.splitext(os.path.basename(row["clip"]))[0],
        "he": sentence,
        "expect": case["expect"],
        "wav": wav_of(row),
        "file": name,
        "case": case["name"],
        "note": f"nearest {name}/{case['name']} ({ratio:.2f}); live: {row['action']}",
    }


class Recordings:
    """The recordings file: one saved case per clip, written in clip order after every
    save, atomically. Thread-safe (the web server answers on several threads)."""

    def __init__(self, path=OUT, rows=None, pool=None):
        self.path = path
        self.rows = rows if rows is not None else load_manifest()
        self.pool = pool if pool is not None else load_cases()
        self._lock = threading.Lock()
        self._near = {}                       # clip index -> nearest()
        self._saved = {}                      # wav -> case
        if os.path.exists(path):
            with open(path, encoding="utf-8") as src:
                for case in json.load(src)["cases"]:
                    self._saved[case["wav"]] = case
        return

    def total(self):
        return len(self.rows)

    def saved_count(self):
        with self._lock:
            return len(self._saved)

    def first_unsaved(self):
        """The first clip with no saved case (where the owner stopped); total when
        every clip is saved."""
        with self._lock:
            for index, row in enumerate(self.rows):
                if wav_of(row) not in self._saved:
                    return index
        return len(self.rows)

    def options(self, index):
        row = self.rows[index]
        with self._lock:
            if index not in self._near:
                self._near[index] = nearest(self.pool, heard_of(row))
            return self._near[index]

    def rerank(self, index, text):
        """The nearest cases to the sentence the owner typed (whisper may have written
        nothing, clips 63-100). They become this clip's options, so a save's option
        number names the same case. -> the options as the page shows them."""
        found = nearest(self.pool, text)
        with self._lock:
            self._near[index] = found
        return self.shown(found)

    @staticmethod
    def shown(options):
        return [
            {
                "similarity": round(ratio, 2),
                "file": name,
                "name": alt["name"],
                "he": alt["he"],
                "expect": alt["expect"],
                "plan": plan_words(alt["expect"]),
                "rows": rows_of(alt["expect"]),
                "vision": vision_of(alt["expect"]),
            }
            for ratio, name, alt in options
        ]

    def clip(self, index):
        """Everything the page shows for one clip: the saved case if there is one,
        else the proposal from the nearest case."""
        row = self.rows[index]
        options = self.options(index)
        with self._lock:
            saved = self._saved.get(wav_of(row))
        case = saved
        if case is None:
            case = propose(row, options[0])
            # the box starts with whisper's EXACT text (owner UI1 (3)); a nearest
            # case's sentence is only an offer
            case["he"] = heard_of(row)
        return {
            "index": index,
            "total": len(self.rows),
            "saved": saved is not None,
            "heard": heard_of(row),
            "live_action": row["action"],
            "case": case,
            "plan": plan_words(case["expect"]),
            "rows": rows_of(case["expect"]),
            "vision": vision_of(case["expect"]),
            "actions": list(ROW_ACTIONS),
            "options": self.shown(options),
        }

    def save(self, index, he, expect, option=0, removed=None):
        """Save one clip: the sentence and plan the owner confirmed; option names the
        nearest case it came from (for the note). removed: the owner's reason to take
        the clip out of the set (owner B4 (8)): the record keeps "removed": true and
        the reason, its plan becomes review (never graded), and path B skips it.
        -> the number saved."""
        row = self.rows[index]
        options = self.options(index)
        case = propose(row, options[min(max(option, 0), len(options) - 1)])
        case["he"] = he                       # exactly what the sentence box holds
        case["expect"] = expect
        if expect.get("kind") == "review":
            case["note"] += "; the owner: not gradable"
        if removed:
            case["expect"] = {"kind": "review"}
            case["removed"] = True
            case["removed_reason"] = removed
        with self._lock:
            self._saved[case["wav"]] = case
            ordered = [
                self._saved[wav_of(r)] for r in self.rows if wav_of(r) in self._saved
            ]
            count = len(ordered)
        self._write(ordered)
        return count

    def _write(self, cases):
        data = {
            "set": "recordings",
            "source": (
                "datasets/asr/manifest.jsonl, confirmed with "
                "tools/asr-verify-transcript"
            ),
            "cases": cases,
        }
        text = json.dumps(data, ensure_ascii=False, indent=1)
        if not atomic_write(self.path, text.encode("utf-8")):
            print(f"NOT SAVED: {self.path} (the reason is printed above)", flush=True)
        return
