"""Checks every expected result the benchmark grades: datasets/recognizer and the
recordings (owner, 2026-10-02: "check for anything that you might've missed"). A label
the scorer cannot match, or a field it does not read, fails here, not in a benchmark."""
import glob
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RECORDINGS = os.path.join(ROOT, "datasets", "asr", "recordings.json")
KINDS = ("mission", "none", "open", "emergency", "perception", "review")
VISION = ("highlight", "count", "describe")
STEP_TYPES = (
    "takeoff", "land", "delay", "fly_by", "spin_by", "gimbal_pitch", "home",
    "fly_circle", "fly_square", "look_at", "fly_gps", "wave",
)


def files():
    """(path, data) of every set file and the recordings (a live list holds only
    names)."""
    out = []
    pattern = os.path.join(ROOT, "datasets", "recognizer", "*.json")
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if "set" in data:
            out.append((path, data))
    with open(RECORDINGS, encoding="utf-8") as f:
        out.append((RECORDINGS, json.load(f)))
    return out


def step_problems(steps):
    problems = []
    for step in steps:
        if step == "halt":
            continue
        if not (isinstance(step, list) and len(step) == 3):
            problems.append(f"step {step!r} is not [type, key, value]")
            continue
        if step[0] not in STEP_TYPES:
            problems.append(f"unknown step type {step[0]!r}")
    return problems


def expect_problems(expect):
    """Every reason the scorer cannot grade this expect as meant. [] = fine."""
    problems = []
    kind = expect.get("kind")
    if kind not in KINDS:
        return [f"unknown kind {kind!r}"]

    if kind == "mission":
        if "steps" in expect:
            problems += step_problems(expect["steps"])
        elif "alternatives" in expect:
            for alternative in expect["alternatives"]:
                if alternative != "halt":
                    problems += step_problems(alternative)
        else:
            problems.append("a mission with no steps and no alternatives")

    if kind == "perception":
        if expect.get("vision", "highlight") not in VISION:
            problems.append(f"unknown vision kind {expect.get('vision')!r}")
        for group in expect.get("groups", []):
            words_ok = all(isinstance(w, str) and w.strip() for w in group)
            if not group or not words_ok:
                problems.append(f"an empty group or word in {group!r}")
            for word in group:
                if "-" in word:
                    problems.append(f"hyphenated word {word!r}: Gemma writes spaces")
                if word in ("all", "many"):
                    problems.append(f"{word!r} is a quantity, not part of the target")
    return problems


def test_every_expect_is_gradable_as_meant():
    problems = []
    for path, data in files():
        for case in data["cases"]:
            if case.get("removed"):
                continue
            for problem in expect_problems(case["expect"]):
                problems.append(f"{os.path.basename(path)} {case['name']}: {problem}")
    assert problems == [], "\n".join(problems)


def test_no_draft_is_left_and_every_name_is_unique():
    names = {}
    problems = []
    for path, data in files():
        for case in data["cases"]:
            if "draft" in case:
                problems.append(f"{case['name']}: an unconfirmed draft")
            if path != RECORDINGS and case["name"] in names:
                problems.append(f"{case['name']}: in {names[case['name']]} and {path}")
            names[case["name"]] = path
    assert problems == [], "\n".join(problems)


def test_every_recording_has_its_clip_and_a_reason_when_removed():
    problems = []
    # the clips are private audio, never in git (ruling V1): only this machine has them
    if not os.path.isdir(os.path.join(ROOT, "datasets", "asr", "clips")):
        pytest.skip("no clips folder here (audio stays local)")
    with open(RECORDINGS, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    for i, case in enumerate(cases, 1):
        if not os.path.exists(os.path.join(ROOT, case["wav"])):
            problems.append(f"clip {i}: no file {case['wav']}")
        if case.get("removed") and not case.get("removed_reason"):
            problems.append(f"clip {i}: removed with no reason")
        silent = not case["he"]
        if not case.get("removed") and silent and case["expect"]["kind"] != "none":
            problems.append(f"clip {i}: no sentence, but something is expected")
    assert problems == [], "\n".join(problems)
