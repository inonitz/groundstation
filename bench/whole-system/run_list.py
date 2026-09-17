def _clips_dir(root):  # clips dir: asr_clips/ (2026-09-12), then legacy asr/clips and clips
    import os as _o
    for c in ("asr_clips", "asr/clips", "clips"):
        p = _o.path.join(root, *c.split("/"))
        if _o.path.isdir(p):
            return p
    return _o.path.join(root, "asr_clips")

#!/usr/bin/env python3
"""Text-mode run of a live-test list through the REAL Recognizer, translator and planner (no mic).
Every "N. <hebrew> -> <expected> | ..." line of the list is fed as text: stage 0-6 with the resident
translator, then Qwen3-VL plans the command lines, exactly as bench.py does. Each line is judged
against the expected notation (dz+10 / -90 deg / takeoff / land / delay 5 / EMPTY / halt / VLM...);
lines whose expectation says "record", "or", "open" are marked REVIEW and shown, not judged.

    python3 run_list.py ../../desk-test/live-test-75.md --translator hymt2 [--out report.md]   (lives in bench/whole-system)
    python3 run_list.py <list.md> --from-clips <session_dir>     # AUDIO REPLAY: the session's recorded
        push-to-talk clips go through whisper-cli (the node's model + flags) instead of the list's text;
        clip N is aligned with list line N (speak lists in order). Isolates the language stack.
One model on the GPU at a time (translator pass, then planner pass). ~2 min for 75 lines.
"""
import argparse, json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CMD_BENCH = os.path.join(ROOT, "tools", "bench", "hebrew-command-bench")   # bench.py, llama.py, cases_*
sys.path.insert(0, os.path.join(ROOT, "projects", os.environ.get("MVD_HOME", "integration_harden2"), "recognizer"))
sys.path.insert(0, os.path.join(ROOT, "projects", os.environ.get("MVD_HOME", "integration_harden2")))
sys.path.insert(0, CMD_BENCH)
import recognizer
from bench import make_translator, plan
from llama import LlamaServer, MODELS, QWEN3VL_EXTRA, PORT, port_up
from perception.engine import parse_highlight

LINE_RE = re.compile(r"^\s*(\d+)\.\s*(?:NEW\s+)?(.+?)\s*->\s*(.+?)\s*(?:\|.*)?$")
BIN = os.path.join(ROOT, "build", "release", "shared", "dji", "bin")
ASR_MODEL = "/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q5_k.bin"


def transcribe(clip):
    """whisper-cli with the ASR node's model and decode settings (Hebrew forced, beam 4, GPU)."""
    import subprocess
    p = subprocess.run([f"{BIN}/whisper-cli", "-m", ASR_MODEL, "-l", "he", "-bs", "4", "-nt", "-fa", "-f", clip],
                       capture_output=True, text=True, env=dict(os.environ, LD_LIBRARY_PATH=BIN))
    return " ".join(p.stdout.split())


def parse_expected(text):
    """-> ("steps", [ (type, key, value|None) ]) | ("empty",) | ("halt",) | ("perception",) | ("review", text)"""
    t = text.strip()
    low = t.lower()
    if re.search(r"\b(record|open|or a clean|or clean| or |should reach|reject/empty|, or )", low) and "never 0.5" not in low:
        return ("review", t)
    if low.startswith("empty") or " empty" in low and "mission" in low and "vlm" not in low:
        return ("empty",)
    if low.startswith("halt") or low.startswith("stop"):
        return ("halt",)
    if low.startswith("vlm") or "perception" in low or "highlight" in low:
        return ("perception",)
    steps = []
    for m in re.finditer(r"d([xyz])\s*([+-]\s*\d+(?:\.\d+)?)|fly_by ([xyz])=([-\d.]+)|([+-]?\d+(?:\.\d+)?)\s*deg\b|spin_by degrees=\(?'?(?:abs'?,\s*)?([-\d.]+)\)?|\b(takeoff|land)\b|delay(?: seconds=|\s+)(\d+(?:\.\d+)?)", t):
        if m.group(1):
            steps.append(("fly_by", "d" + m.group(1), float(m.group(2).replace(" ", ""))))
        elif m.group(3):
            steps.append(("fly_by", "d" + m.group(3), float(m.group(4))))
        elif m.group(5):
            steps.append(("spin_by", "degrees", float(m.group(5))))
        elif m.group(6):
            steps.append(("spin_by", "degrees", ("abs", abs(float(m.group(6))))) if "abs" in t else ("spin_by", "degrees", float(m.group(6))))
        elif m.group(7):
            steps.append((m.group(7), None, None))
        elif m.group(8):
            steps.append(("delay", "seconds", float(m.group(8))))
    if not steps:
        return ("review", t)
    if "only" in low or "no delay" in low or "no wait" in low:
        return ("steps", steps)
    return ("steps", steps)


def judge(exp, kind, payload, mission, flags):
    if exp[0] == "review":
        return "REVIEW"
    if exp[0] == "halt":
        return "PASS" if kind == "emergency" else f"FAIL(no halt: {kind})"
    if exp[0] == "perception":
        return "PASS" if kind == "perception" else f"FAIL(routed {kind}{': ' + flags[-1] if kind == 'reject' and flags else ''})"
    if exp[0] == "empty":
        if kind in ("reject", "perception"):
            return "PASS(safe: " + kind + ")"
        return "PASS" if not mission else f"FAIL(flew {len(mission)} steps)"
    want = exp[1]
    if kind == "reject":
        return f"FAIL(reject: {flags[-1] if flags else ''})"
    if kind == "perception":
        return "FAIL(routed perception)"
    if not mission:
        return "FAIL(EMPTY)"
    if len(mission) != len(want):
        return f"FAIL(len {len(mission)} vs {len(want)})"
    for got, (typ, key, val) in zip(mission, want):
        if got.get("type") != typ:
            return f"FAIL(type {got.get('type')} vs {typ})"
        if key is None:
            continue
        g = got.get(key)
        if g is None:
            return f"FAIL(missing {key})"
        if isinstance(val, tuple):            # ('abs', 180)
            if abs(float(g)) != val[1]:
                return f"FAIL({key} {g} vs |{val[1]}|)"
        elif float(g) != val:
            return f"FAIL({key} {g} vs {val})"
    extra = [k for step in mission for k in step if k not in ("type", "dx", "dy", "dz", "degrees", "seconds", "velocity")]
    return "PASS" + (" (+velocity)" if any("velocity" in s for s in mission) else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("list")
    ap.add_argument("--translator", choices=("dicta", "hymt2"), default="hymt2")
    ap.add_argument("--out", default="")
    ap.add_argument("--prompt", choices=("v1", "v2"), default="v1")
    ap.add_argument("--from-clips", default="", help="session dir: replay its clips/*.wav through whisper instead of the list text")
    a = ap.parse_args()
    lines = [(int(m.group(1)), m.group(2), m.group(3)) for m in
             (LINE_RE.match(l) for l in open(a.list, encoding="utf-8")) if m]
    heard = {}
    if a.from_clips:
        import glob as _g
        clips = sorted(_g.glob(os.path.join(_clips_dir(a.from_clips), "*.wav")))
        print(f"[replay] {len(clips)} clips from {a.from_clips}; transcribing with whisper-cli ...", flush=True)
        for i, c in enumerate(clips):
            heard[i + 1] = transcribe(c)
        # Each clip is matched to the list line whose Hebrew it overlaps most (token Jaccard), so
        # repeats, skips and ad-hoc sentences do not shift the alignment; clips below 0.34 overlap
        # are reported unmatched. The spoken (heard) Hebrew is what the pipeline gets.
        def toks(s): return set(re.sub(r"[\s,.?!:;\-]+", " ", s).split())
        matched, unmatched = [], []
        for i in sorted(heard):
            h = heard[i]
            best = max(((len(toks(h) & toks(he)) / max(1, len(toks(h) | toks(he))), n, he, exp) for n, he, exp in lines), key=lambda x: x[0])
            if best[0] >= 0.34:
                matched.append((best[1], h, best[3]))
            else:
                unmatched.append((i, h))
        print(f"[replay] matched {len(matched)} clips to list lines, {len(unmatched)} unmatched", flush=True)
        for i, h in unmatched[:20]:
            print(f"[replay]   unmatched clip {i}: {h[:70]}", flush=True)
        lines = matched
    assert not port_up(PORT), "a llama-server is already on the bench port; stop it first"
    t0 = time.time()
    rows = []
    with LlamaServer(MODELS[a.translator]):
        translate = make_translator(PORT, a.prompt)
        for n, he, exp in lines:
            t1 = time.time()
            kind, payload, flags = recognizer.recognize(he, translate)
            rows.append({"n": n, "he": he, "exp": exp, "kind": kind, "payload": payload, "flags": flags,
                         "ms": round((time.time() - t1) * 1000), "mission": None})
    with LlamaServer(MODELS["qwen3vl"], extra=QWEN3VL_EXTRA):
        for r in rows:
            if r["kind"] == "command":
                r["mission"], _ = plan(PORT, r["payload"])
            elif r["kind"] == "mission":
                r["mission"] = r["payload"]
    out = [f"# {'AUDIO REPLAY' if a.from_clips else 'Text-mode'} run of {os.path.basename(a.list)} — translator {a.translator}, prompt {a.prompt}, {time.strftime('%Y-%m-%d %H:%M')}"
           + (f" — clips from {os.path.basename(a.from_clips.rstrip('/'))}, whisper q5_k beam 4 (clip N = line N)" if a.from_clips else ""),
           "Fed as text (no mic) through the real Recognizer, translator and Qwen3-VL planner. HL = the highlight phrase the",
           "engine would extract (None = plain VLM question). REVIEW = the list has no single expected result.", "",
           "| # | Hebrew | English / bypass | kind | flags | mission | HL | expected | verdict |", "|---|---|---|---|---|---|---|---|---|"]
    tally = {"PASS": 0, "FAIL": 0, "REVIEW": 0}
    for r in rows:
        exp = parse_expected(r["exp"])
        v = judge(exp, r["kind"], r["payload"], r["mission"], r["flags"])
        tally[v.split("(")[0]] += 1
        en = r["payload"] if isinstance(r["payload"], str) else ("(bypass)" if r["kind"] == "mission" else "")
        hl = parse_highlight(r["payload"]) if r["kind"] == "perception" else ""
        mis = "" if r["mission"] is None else json.dumps(r["mission"], ensure_ascii=False).replace('"type": ', "").replace('"', "")
        out.append(f"| {r['n']} | {r['he']} | {en} | {r['kind']} | {','.join(r['flags'])} | {mis} | {hl} | {r['exp'][:60]} | {v} |")
    out += ["", f"PASS {tally['PASS']}  FAIL {tally['FAIL']}  REVIEW {tally['REVIEW']}  (wall {round(time.time() - t0)} s)"]
    text = "\n".join(out)
    print(text)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text + "\n")
        print("->", a.out)


if __name__ == "__main__":
    main()
