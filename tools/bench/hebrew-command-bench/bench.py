"""Benchmark for the Recognizer. Run `python3 bench.py` for the full measurement.

Lanes (see main() at the bottom):
    (default)   every sentence set through the complete Recognizer, then the planner
    --smoke     the same lane on a 6-case slice per set, ~40 s
    --audit     offline scorer audit, no GPU
    --cases     regenerate CASES.md
    --translator dicta|hymt2|gemma4   which stage-3 model is resident (default dicta; gemma4 = Gemma 4 E4B as the translator, owner ask 2026-09-08)
    --perfect-en  control: the reference English goes straight to the planner (planner ceiling)
    --tag NAME  suffix for the raw JSON file name

Method invariants: temperature 0, one pass per case (determinism proven: 10 identical
requests -> 1 output), GBNF grammar on every planning call, one model on GPU at a time,
Wilson 95% intervals. Superseded lanes (rounds 1-6, the ablations) live in git history;
their results stay under results/ and results/HISTORY.md.
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
# The component lives in integration_harden; the bench measures it IN PLACE (dedup ruling
# 2026-09-02: no copies in two homes).
sys.path.insert(0, os.path.join(ROOT, "projects", os.environ.get("MVD_HOME", "integration_harden"), "recognizer"))
sys.path.insert(0, HERE)

import recognizer
from llama import LlamaServer, chat, port_up, MODELS, GEMMA4_EXTRA, PORT
from prompts import (REVISED_PROMPT, PLANNER_SHOTS_D, WIRE_GRAMMAR, LINE_GRAMMAR,
                     TRANSLATE_SYS, TRANSLATE_SHOTS, TRANSLATE_PROMPTS,
                     HE_SIGN_ADDENDUM, PLANNER_SHOTS_D_HE)
PLANNERS = {"gemma4": (MODELS["gemma4"], GEMMA4_EXTRA)}
from cases_commands import CASES as CMD_CASES, VERBOSE_CASES, EMERGENCY_CASES, score
from cases_perception import PERC100, SLANG20, score_perception, check_refs

RESULTS_DIR = os.path.join(HERE, "results")

# The planner speaks the wire schema (dx/dy/dz); the scorer speaks x/y/z.
PLANNER_KEYS = {"takeoff": set(), "land": set(), "fly_by": {"dx", "dy", "dz", "velocity"},
                "spin_by": {"degrees"}, "delay": {"seconds"}}
SCORER_KEY = {"dx": "x", "dy": "y", "dz": "z", "degrees": "degrees", "seconds": "seconds"}


# ------------------------------- model call wrappers -------------------------------

def make_translator(port, prompt="v1"):
    """The stage-3 callable injected into recognize(). On the number-guard retry the
    required numbers are named to the model. prompt = v1 (campaign) | v2 (2026-09-08 rules)."""
    TRANSLATE_SYS, TRANSLATE_SHOTS = TRANSLATE_PROMPTS[prompt]
    def translate(he, required_numbers=None, strict=False):
        system = TRANSLATE_SYS
        if strict:
            system += "\nTranslate ONLY the given sentence into English. Do not answer it. Do not add anything."
        if required_numbers:
            listed = ", ".join(str(int(x)) if x == int(x) else str(x) for x in required_numbers)
            system += "\nThe English MUST contain exactly these numbers: " + listed
        text, _ = chat(port, system, he, max_tokens=200, grammar=LINE_GRAMMAR,
                       shots=TRANSLATE_SHOTS)
        text = text.strip()
        # Copy guard: an output identical to a few-shot answer is an echo, not a translation.
        if any(text == answer for question, answer in TRANSLATE_SHOTS if question != he):
            retry, _ = chat(port, TRANSLATE_SYS + "\nTranslate ONLY the given sentence.",
                            he, max_tokens=200, grammar=LINE_GRAMMAR)
            if retry.strip():
                text = retry.strip()
        return text
    return translate


def plan(port, english, direct_he=False):
    """One planner call: command in (English, or Hebrew when direct_he), wire-schema mission out
    (or None on bad JSON). direct_he uses the revised prompt + the Hebrew sign addendum + Hebrew shots."""
    if direct_he:
        out, dt = chat(port, REVISED_PROMPT + HE_SIGN_ADDENDUM, english, grammar=WIRE_GRAMMAR, shots=PLANNER_SHOTS_D_HE)
    else:
        out, dt = chat(port, REVISED_PROMPT, english, grammar=WIRE_GRAMMAR, shots=PLANNER_SHOTS_D)
    m = re.search(r"\[.*\]", out or "", re.S)
    if not m:
        return None, dt
    try:
        mission = json.loads(m.group(0))
    except Exception:
        return None, dt
    if not isinstance(mission, list):
        return None, dt
    for step in mission:
        if not isinstance(step, dict) or step.get("type") not in PLANNER_KEYS:
            return None, dt
        if any(k != "type" and k not in PLANNER_KEYS[step["type"]] for k in step):
            return None, dt
    return mission, dt


def to_scorer_schema(mission):
    """dx/dy/dz -> x/y/z; velocity is dropped (the scorer judges geometry, the app clamps it)."""
    out = []
    for step in mission:
        converted = {"type": step["type"]}
        for k, v in step.items():
            if k in SCORER_KEY:
                converted[SCORER_KEY[k]] = v
        out.append(converted)
    return out


# ------------------------------------ statistics ------------------------------------

def pct(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100.0
    f = math.floor(k)
    c = min(f + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f))


def wilson(ok, n, z=1.96):
    p = ok / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half


def latency_row(label, xs):
    cells = " | ".join(str(pct(xs, p)) for p in (25, 50, 75, 95, 99))
    return f"| {label} | {cells} | {max(xs)} |"


# ------------------------------- the measurement lane -------------------------------

def run_recognizer(smoke=False, translator="dicta", tag="", prompt="v1", planner="qwen3vl", direct_he=False):
    """Every sentence set through the complete Recognizer; command sets continue to the
    planner. Prints the scorecard, writes the raw JSON."""
    assert not port_up(PORT), "a llama-server is already running; this bench is sequential"
    cut = 6 if smoke else None
    sets = {"emergency": EMERGENCY_CASES[:cut], "std190": CMD_CASES[:cut],
            "verbose": VERBOSE_CASES[:cut], "perception": PERC100[:cut],
            "military": SLANG20[:cut]}
    t0 = time.time()

    # Pass 1, DictaLM resident: stages 0-6 on everything. Stage-0 fires on non-emergency
    # sentences are false positives and are reported, not hidden.
    recognized = {}
    stage0_false = []
    if direct_he:
        # No translator: stages 0-2 only (emergency, bypass, Hebrew rewrites); the Hebrew goes to the planner.
        # Perception sets are not scorable here (the keyword scorer needs English) and are skipped.
        print("== Recognizer pass, DIRECT HEBREW (no translator; stages 0-2) ==", flush=True)
        for set_name, cases in sets.items():
            rows = []
            for case in cases:
                name, hebrew = case[0], case[1]
                if recognizer.emergency(hebrew):
                    kind, payload, flags = "emergency", None, []
                else:
                    mission = recognizer.bypass(recognizer.hebnum_to_digits(hebrew))
                    if mission is not None:
                        kind, payload, flags = "mission", mission, []
                    else:
                        he2, flags = recognizer.apply_he(hebrew)
                        kind, payload = "command", he2
                if kind == "emergency" and set_name != "emergency":
                    stage0_false.append((set_name, name, hebrew))
                rows.append({"case": name, "kind": kind, "payload": payload, "flags": flags, "t_ms": 0})
            recognized[set_name] = rows
        sets = {k: v for k, v in sets.items() if k in ("emergency", "std190", "verbose")}
    else:
      print(f"== Recognizer pass ({translator} resident) ==", flush=True)
      with LlamaServer(MODELS[translator], extra=(GEMMA4_EXTRA if translator == "gemma4" else ())):
        translate = make_translator(PORT, prompt)
        for set_name, cases in sets.items():
            rows = []
            for case in cases:
                name, hebrew = case[0], case[1]
                t_start = time.time()
                kind, payload, flags = recognizer.recognize(hebrew, translate)
                if kind == "emergency" and set_name != "emergency":
                    stage0_false.append((set_name, name, hebrew))
                rows.append({"case": name, "kind": kind, "payload": payload,
                             "flags": flags, "t_ms": round((time.time() - t_start) * 1000)})
            recognized[set_name] = rows
            print(f"  {set_name}: {len(rows)} sentences", flush=True)

    results = {"emergency": {
        "ok": sum(1 for r in recognized["emergency"] if r["kind"] == "emergency"),
        "n": len(recognized["emergency"])}}

    # Perception sets are scored on the Recognizer's English; the VLM is not simulated.
    for set_name, cases in (("perception", sets.get("perception", [])), ("military", sets.get("military", []))):
        if not cases:
            results[set_name] = {"ok": 0, "n": 0}; continue
        groups = {c[0]: c[3] for c in cases}
        ok = sum(1 for r in recognized[set_name]
                 if r["kind"] in ("command", "perception") and not score_perception(r["payload"], groups[r["case"]]))
        results[set_name] = {"ok": ok, "n": len(recognized[set_name])}

    # Pass 2, the planner resident: command sets continue to the planner and mission scoring.
    print(f"== planner pass ({planner} resident{', direct Hebrew' if direct_he else ''}) ==", flush=True)
    with LlamaServer(PLANNERS[planner][0], extra=PLANNERS[planner][1]):
        for set_name, cases in (("std190", sets["std190"]), ("verbose", sets["verbose"])):
            expected = {c[0]: c[3] for c in cases}
            rows = []
            for r in recognized[set_name]:
                if r["kind"] == "mission":
                    verdict = score(to_scorer_schema(r["payload"]), expected[r["case"]])
                    rows.append({"case": r["case"], "score": verdict, "t_total_ms": 0})
                elif r["kind"] in ("command", "perception"):
                    mission, t_plan = plan(PORT, r["payload"], direct_he=direct_he)
                    verdict = score(to_scorer_schema(mission) if mission is not None else None,
                                    expected[r["case"]])
                    rows.append({"case": r["case"], "score": verdict,
                                 "t_total_ms": r["t_ms"] + round(t_plan * 1000)})
                elif r["kind"] == "reject":      # read back, nothing flies: a PASS on a must-not-fly
                    verdict = "CORRECT-reject" if expected[r["case"]] == [] else "REJECT"
                    rows.append({"case": r["case"], "score": verdict, "t_total_ms": r["t_ms"]})
                else:                            # false-positive emergency: reported separately
                    rows.append({"case": r["case"], "score": f"routed:{r['kind']}",
                                 "t_total_ms": r["t_ms"]})
            ok = sum(1 for r in rows if r["score"].startswith(("CORRECT", "valid")))
            n = len([r for r in rows if not r["score"].startswith("routed:")])
            results[set_name] = {"ok": ok, "n": n, "rows": rows}
            fails = [r for r in rows if not r["score"].startswith(("CORRECT", "valid", "routed:"))]
            for r in fails[:8]:
                print(f"    FAIL {r['case']:16s} {r['score']}", flush=True)

    _print_scorecard(results, recognized, stage0_false)
    stamp = datetime.date.today().isoformat()
    out = os.path.join(RESULTS_DIR, f"{stamp}-recognizer{'-smoke' if smoke else ''}"
                                    f"{'-' + tag if tag else ''}.json")
    json.dump({"translator": translator, "prompt": prompt, "planner": planner, "direct_he": direct_he,
               "results": {k: {kk: vv for kk, vv in v.items() if kk != "rows"}
                           for k, v in results.items()},
               # per-case planner verdicts, so a change is gated by the cases that FLIPPED
               "verdicts": {k: {r["case"]: r["score"] for r in v["rows"]}
                            for k, v in results.items() if "rows" in v},
               "stage0_false_positives": stage0_false, "recognized": recognized,
               "wall_s": round(time.time() - t0)},
              open(out, "w"), ensure_ascii=False, indent=1)
    print(f"raw -> {out}\nwall {round(time.time() - t0)}s", flush=True)


def run_perfect_en(planner="qwen3vl"):
    """Control: the hand-written English reference of every command case goes straight to the
    planner (no Hebrew, no translator). This is the planner-only ceiling: a case that fails here
    fails regardless of the translator. Qwen3-VL resident only."""
    assert not port_up(PORT), "a llama-server is already running; this bench is sequential"
    t0 = time.time()
    out = {}
    with LlamaServer(PLANNERS[planner][0], extra=PLANNERS[planner][1]):
        for set_name, cases in (("std190", CMD_CASES), ("verbose", VERBOSE_CASES)):
            rows = []
            for name, hebrew, english, expected in cases:
                mission, t_plan = plan(PORT, english)
                verdict = score(to_scorer_schema(mission) if mission is not None else None, expected)
                rows.append({"case": name, "english": english, "score": verdict,
                             "mission": mission, "t_ms": round(t_plan * 1000)})
            ok = sum(1 for r in rows if r["score"].startswith(("CORRECT", "valid")))
            out[set_name] = {"ok": ok, "n": len(rows), "rows": rows}
            print(f"| perfect-EN {set_name} | {ok}/{len(rows)} ({ok/len(rows):.0%}) |", flush=True)
            for r in [r for r in rows if not r["score"].startswith(("CORRECT", "valid"))]:
                print(f"    FAIL {r['case']:16s} {r['score']:26s} | {r['english'][:70]}", flush=True)
    stamp = datetime.date.today().isoformat()
    path = os.path.join(RESULTS_DIR, f"{stamp}-perfect-en{'-' + planner if planner != 'qwen3vl' else ''}.json")
    json.dump({"results": {k: {"ok": v["ok"], "n": v["n"]} for k, v in out.items()},
               "verdicts": {k: {r["case"]: r["score"] for r in v["rows"]} for k, v in out.items()},
               "rows": {k: v["rows"] for k, v in out.items()}, "wall_s": round(time.time() - t0)},
              open(path, "w"), ensure_ascii=False, indent=1)
    print(f"raw -> {path}\nwall {round(time.time() - t0)}s", flush=True)


def _print_scorecard(results, recognized, stage0_false):
    print("\n| set | result |")
    print("|---|---|")
    total_ok = total_n = 0
    for name in ("emergency", "std190", "verbose", "perception", "military"):
        r = results[name]
        total_ok += r["ok"]
        total_n += r["n"]
        print(f"| {name} | {r['ok']}/{r['n']} ({r['ok']/r['n']:.0%}) |" if r["n"] else f"| {name} | skipped |")
    print(f"| ALL | {total_ok}/{total_n} ({total_ok/total_n:.0%}) |")
    print("\n| set / stage | p25 | p50 | p75 | p95 | p99 | max (ms) |")
    print("|---|---|---|---|---|---|---|")
    for name in ("std190", "verbose"):
        if "rows" in results[name]:
            print(latency_row(f"{name}: Recognizer + planner",
                              [r["t_total_ms"] for r in results[name]["rows"]]))
    for name in ("perception", "military"):
        if recognized.get(name):
            print(latency_row(f"{name}: Recognizer only",
                              [r["t_ms"] for r in recognized[name]]))
    print(f"\nstage-0 false positives: {len(stage0_false)} {stage0_false or ''}")


# --------------------------------- secondary lanes ---------------------------------

def audit():
    """No GPU: every hand-written English reference must satisfy its own keyword groups,
    and the component self-test must be clean."""
    bad = check_refs() + recognizer.selftest()
    if bad:
        print("\n".join(str(b) for b in bad))
        raise SystemExit(1)
    print("audit CLEAN: scorer references and recognizer self-test all pass")


def write_cases_md():
    """Regenerate CASES.md, the human-readable inventory of every tested sentence."""
    def expected_text(e):
        if e is None:
            return "open-ended (validity only)"
        if e == []:
            return "[] (no action)"
        return "; ".join(f"{t}" + (f" {k}={v}" if k else "") for t, k, v in e)

    with open(os.path.join(HERE, "CASES.md"), "w") as f:
        f.write("# Every sentence the bench tests\n\nGenerated by `python3 bench.py --cases`"
                " -- edit the cases_*.py files, not this.\n")
        f.write(f"\n## Commands ({len(CMD_CASES)}) -- scored as mission JSON\n\n"
                "| # | id | Hebrew | English reference | expected |\n|---|---|---|---|---|\n")
        for i, (name, he, en, exp) in enumerate(CMD_CASES, 1):
            f.write(f"| {i} | {name} | {he} | {en} | {expected_text(exp)} |\n")
        f.write(f"\n## Verbose commands ({len(VERBOSE_CASES)})\n\n"
                "| # | id | Hebrew | English reference | expected |\n|---|---|---|---|---|\n")
        for i, (name, he, en, exp) in enumerate(VERBOSE_CASES, 1):
            f.write(f"| {i} | {name} | {he} | {en} | {expected_text(exp)} |\n")
        f.write(f"\n## Emergency ({len(EMERGENCY_CASES)}) -- must be caught by stage 0\n\n"
                "| # | id | Hebrew |\n|---|---|---|\n")
        for i, (name, he) in enumerate(EMERGENCY_CASES, 1):
            f.write(f"| {i} | {name} | {he} |\n")
        f.write(f"\n## Perception ({len(PERC100)}) -- scored by keyword preservation\n\n"
                "| # | id | depth | Hebrew | English reference |\n|---|---|---|---|---|\n")
        for i, (name, he, en, g, depth) in enumerate(PERC100, 1):
            f.write(f"| {i} | {name} | {depth} | {he} | {en} |\n")
        f.write(f"\n## Military phraseology ({len(SLANG20)})\n\n"
                "| # | id | class | Hebrew | English reference |\n|---|---|---|---|---|\n")
        for i, (name, he, en, g, klass) in enumerate(SLANG20, 1):
            f.write(f"| {i} | {name} | {klass} | {he} | {en} |\n")
    print(f"CASES.md written: {len(CMD_CASES)}+{len(VERBOSE_CASES)} commands, "
          f"{len(EMERGENCY_CASES)} emergency, {len(PERC100)} perception, {len(SLANG20)} military")


# --------------------------------------- main ---------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--smoke", action="store_true", help="6-case slice per set, ~40 s")
    parser.add_argument("--audit", action="store_true", help="offline checks only, no GPU")
    parser.add_argument("--cases", action="store_true", help="regenerate CASES.md and exit")
    parser.add_argument("--translator", choices=("dicta", "hymt2", "gemma4"), default="dicta",
                        help="stage-3 model resident for the Recognizer pass (default dicta)")
    parser.add_argument("--tag", default="", help="suffix for the raw JSON name, e.g. hymt2")
    parser.add_argument("--prompt", choices=("v1", "v2", "tgemma"), default="v1",
                        help="translator prompt: v1 (campaign) | v2 (2026-09-08 six rules + new shots)")
    parser.add_argument("--planner", choices=("qwen3vl", "gemma4"), default="qwen3vl",
                        help="planner model resident in pass 2 (default qwen3vl)")
    parser.add_argument("--direct-he", action="store_true",
                        help="no translator: Hebrew (after stages 0-2) goes straight to the planner; perception sets skipped")
    parser.add_argument("--perfect-en", action="store_true",
                        help="control: reference English straight to the planner (planner-only ceiling)")
    args = parser.parse_args()

    if args.audit:
        audit()
    elif args.perfect_en:
        audit()
        run_perfect_en(planner=args.planner)
    elif args.cases:
        write_cases_md()
    else:
        audit()                                  # never measure with a broken scorer
        run_recognizer(smoke=args.smoke, translator=args.translator, tag=args.tag, prompt=args.prompt,
                       planner=args.planner, direct_he=args.direct_he)


if __name__ == "__main__":
    main()
