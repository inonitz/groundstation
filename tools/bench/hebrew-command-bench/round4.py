#!/usr/bin/env python3
"""Round 4 -- app prompt vs revised prompt, on the REAL wire schema (dx/dy/dz + velocity).

Arm naming: prompt / planner model / input.
  app prompt      = what the phone app ships today (SpeechResolving.kt:599-635), 5-action subset.
  revised prompt  = candidate replacement: + sign rule, + question/negation->[] rule, + 6 shots.
  perfect-EN      = hand-written English reference input; simulates a flawless translator.
  dicta-HE / tgemma-HE = real Hebrew through that translator first.

Arms (strictly sequential, one model on GPU at a time, GBNF on every planning call):
  app-prompt/qwen2.5c/perfect-EN      CONTROL on the app engine (what ships today)
  revised-prompt/qwen2.5c/perfect-EN  treatment on the app engine
  app-prompt/qwen3vl/perfect-EN       CONTROL on the groundstation engine (reference scenario)
  revised-prompt/qwen3vl/perfect-EN   treatment on the groundstation engine
  revised-prompt/qwen3vl/dicta-HE     pipeline: backlog-B candidate
  revised-prompt/qwen3vl/tgemma-HE    pipeline: dedicated-translator challenger
Plus: 40 perception commands through both translators (keyword-group preservation, full dump)
and per-call char/latency capture for the length-vs-latency curve.

Fidelity disclosures:
 - The app prompt is reconstructed from SpeechResolving.kt (scaffold verbatim); its schema block
   is re-rendered in the app's short-JSON format but LIMITED to the bench's 5-action whitelist so
   every arm shares one scorer. The app also ships fly_circle/follow_me/etc.
 - The app itself uses findJson + lenient decode, not GBNF. Here ALL planning calls carry the
   grammar (standing round-1..3 ruling, keeps arms comparable).
Determinism at temp 0 was proven round 1 (10 identical requests -> 1 output): each case runs once."""
import json, math, os, sys, time, datetime, random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_bench as rb
from cases import CASES, score
from cases_perception import PERCEPTION_CASES, score_perception

SMOKE = os.environ.get("ROUND4_SMOKE") == "1"
STD = CASES[:8] if SMOKE else CASES
PERC = PERCEPTION_CASES[:4] if SMOKE else PERCEPTION_CASES

MODELS = {
 "qwen25c": "/root/models/translate/qwen2.5-coder-1.5b-gguf/qwen2.5-coder-1.5b-instruct-q4_0.gguf",
 "qwen3vl": "/root/models/vlm/Qwen3-VL-4B-Instruct/Qwen3-VL-4B-Instruct-Q4_K_M.gguf",
 "dicta":   "/root/models/asr/dictalm-3-1.7b/dictalm-3.0-1.7b-instruct-q4_k_m.gguf",
 "tgemma":  "/root/models/translate/translategemma-4b-it-gguf/translategemma-4b-it.Q4_K_M.gguf",
}
QWEN3VL_EXTRA = ("--mmproj", "/root/models/vlm/Qwen3-VL-4B-Instruct/mmproj-BF16.gguf",
                 "--flash-attn", "on", "--cache-type-k", "q4_0", "--cache-type-v", "q4_0")
PORT = 18091

# ---- app prompt, reconstructed. Scaffold: SpeechResolving.kt:599-635. Schema block:
# ---- app's appendPropertyShortJson format (desc comment line, "name":  type, (optional) mark),
# ---- restricted to the 5 whitelisted actions.
SCHEMA_5 = '''"takeoff":  object {
\t"type": "takeoff",
},

"land":  object {
\t"type": "land",
},

// Moves aircraft relative to it's current position (m). At least one direction must be non zero.
"fly_by":  object {
\t"type": "fly_by",
\t// x+ is forward
\t"dx":  number (optional),
\t// y+ is right
\t"dy":  number (optional),
\t// z+ is up
\t"dz":  number (optional),
\t// -6..6 (m/s)
\t"velocity":  number (optional),
},

// Spins aircraft relative to it's current heading.
"spin_by":  object {
\t"type": "spin_by",
\t"degrees":  number (optional),
},

"delay":  object {
\t"type": "delay",
\t"seconds":  number,
},'''

APP_HEAD = '''# Role

You are a speech-to-intent engine.

The user wants to perform a sequence of one or more actions.

Translate & Convert the user's natural language request into a JSON array of system actions.

Each action must exactly match one of the JSON Schemas below.

# Rules

- The JSON Schemas below are the ONLY valid actions.
- Never invent actions or fields. Never rephrase their names.
- Use ONLY the available system actions and fields below.
- Use the EXACT "type" value, field names & enum constants from the schemas.
- Output valid JSON Array only.

# Semantics

- Infer the user's intent and populate schema fields accordingly.
- If field is optional and the user did not explicitly or implicitly specify a value, you must omit the field.
- Comments in the input Schema provide each field's semantics. Don't output comments.
- Grammar in request like "x and y", "x then y", "do x, y" hints at multiple actions.
     -- for ex.: "takeoff, fly forward ... then fly upwards ... and then ..." is multiple actions.'''

APP_TAIL = '''# Output

Return ONLY the JSON array.'''

APP_PROMPT = APP_HEAD + "\n\n# Available Actions\n" + SCHEMA_5 + "\n\n" + APP_TAIL

# ---- revised prompt = app-prompt scaffold + the three measured deficits fixed:
# ---- (a) verbal->sign map (round-3: 7/14 top-arm fails were "turn right N" -> -N),
# ---- (b) negation/question -> [] rule, (c) few-shot (added separately as chat turns).
REVISED_PROMPT = APP_HEAD + '''

# Signs & Directions (follow EXACTLY)

- fly_by is in the aircraft body frame: dx+ forward, dx- backward; dy+ right, dy- left; dz+ up, dz- down.
- spin_by degrees: turning RIGHT = clockwise = POSITIVE degrees. Turning LEFT = counterclockwise = NEGATIVE degrees.
  "turn right 20 degrees" -> {"type":"spin_by","degrees":20}. "turn left 30 degrees" -> {"type":"spin_by","degrees":-30}.
- A full turn is 360 degrees. Half a turn is 180 degrees.
- Number words ("five", "half a meter") become digits (5, 0.5).

# Refusals

- A negated clause ("don't fly up", "do not land") produces NO action for that clause.
- Questions, status requests, and anything that is not a movement command -> output [] (empty array).
- Keep the actions in the exact order the user gave them.

# Available Actions
''' + SCHEMA_5 + "\n\n" + APP_TAIL

PLANNER_SHOTS_D = [
 ("fly left 12 meters", '[{"type":"fly_by","dy":-12}]'),
 ("go down 2 meters then fly forward 6 meters", '[{"type":"fly_by","dz":-2},{"type":"fly_by","dx":6}]'),
 ("do not fly up", "[]"),
 ("what's your altitude", "[]"),
 ("turn right 20 degrees", '[{"type":"spin_by","degrees":20}]'),
 ("take off, rise 4 meters, turn 90 degrees clockwise, fly forward 6 meters, and land",
  '[{"type":"takeoff"},{"type":"fly_by","dz":4},{"type":"spin_by","degrees":90},{"type":"fly_by","dx":6},{"type":"land"}]'),
]

WIRE_GRAMMAR = r'''
root ::= "[" ws (action (ws "," ws action)*)? ws "]"
action ::= takeoff | land | flyby | spinby | delay
takeoff ::= "{" ws "\"type\"" ws ":" ws "\"takeoff\"" ws "}"
land ::= "{" ws "\"type\"" ws ":" ws "\"land\"" ws "}"
flyby ::= "{" ws "\"type\"" ws ":" ws "\"fly_by\"" (ws "," ws axis)+ ws "}"
axis ::= ("\"dx\"" | "\"dy\"" | "\"dz\"" | "\"velocity\"") ws ":" ws num
spinby ::= "{" ws "\"type\"" ws ":" ws "\"spin_by\"" ws "," ws "\"degrees\"" ws ":" ws num ws "}"
delay ::= "{" ws "\"type\"" ws ":" ws "\"delay\"" ws "," ws "\"seconds\"" ws ":" ws num ws "}"
num ::= "-"? [0-9]+ ("." [0-9]+)?
ws ::= [ \t\n]*
'''

ALLOWED_D = {"takeoff": set(), "land": set(), "fly_by": {"dx","dy","dz","velocity"},
             "spin_by": {"degrees"}, "delay": {"seconds"}}
import re
def parse_d(out):
    m = re.search(r"\[.*\]", out or "", re.S)
    if not m: return None
    try: arr = json.loads(m.group(0))
    except Exception: return None
    if not isinstance(arr, list): return None
    norm = []
    for a in arr:
        if not isinstance(a, dict) or a.get("type") not in ALLOWED_D: return None
        if any(k != "type" and k not in ALLOWED_D[a["type"]] for k in a): return None
        b = {"type": a["type"]}
        for src, dst in (("dx","x"), ("dy","y"), ("dz","z"), ("degrees","degrees"), ("seconds","seconds")):
            if src in a: b[dst] = a[src]
        norm.append(b)          # velocity dropped: scorer judges geometry, app clamps velocity
    return norm

def plan_all_d(port, texts, system, shots=()):
    rows, by_name = [], {c[0]: c for c in STD}
    for name, text, t_tr in texts:
        out, t_plan = rb.chat(port, system, text, grammar=WIRE_GRAMMAR, shots=shots)
        rows.append({"case": name, "score": score(parse_d(out), by_name[name][3]), "input": text,
                     "t_translate_ms": round(t_tr * 1000), "t_plan_ms": round(t_plan * 1000),
                     "in_chars": len(text), "out_chars": len(out or ""), "out": (out or "")[:200]})
    return rows

TGEMMA_PROMPT = ("<start_of_turn>user\n"
 "You are a professional Hebrew (he) to English (en) translator. Your goal is to accurately convey "
 "the meaning and nuances of the original Hebrew text while adhering to English grammar, "
 "vocabulary, and cultural sensitivities.\n"
 "Produce only the English translation, without any additional explanations or commentary. "
 "Please translate the following Hebrew text into English:\n\n\n"
 "{he}<end_of_turn>\n<start_of_turn>model\n")

def tgemma_translate_all(port, cases3):
    # native single-turn template (reproduced from the GGUF chat_template); llama-server cannot
    # parse the custom jinja, so the server boots with --chat-template gemma and we hit /completion
    tr = []
    for item in cases3:
        name, he = item[0], item[1]
        t, dt = rb.completion(port, TGEMMA_PROMPT.format(he=he), max_tokens=80, grammar=rb.LINE_GRAMMAR)
        tr.append((name, t.strip(), dt))
    return tr

def translate_all(port, cases3):
    tr = []
    for item in cases3:
        name, he = item[0], item[1]
        t, dt = rb.chat(port, rb.TRANSLATE_SYS, he, max_tokens=80,
                        grammar=rb.LINE_GRAMMAR, shots=rb.TRANSLATE_SHOTS)
        tr.append((name, t.strip(), dt))
    return tr

def mcnemar(rows_a, rows_b):
    ok = lambda r: r["score"].startswith(("CORRECT", "valid"))
    a = {r["case"]: ok(r) for r in rows_a}; b = {r["case"]: ok(r) for r in rows_b}
    n01 = sum(1 for c in a if a[c] and not b[c]); n10 = sum(1 for c in a if not a[c] and b[c])
    n = n01 + n10
    if n == 0: return n01, n10, 1.0
    p = sum(math.comb(n, k) for k in range(min(n01, n10) + 1)) / 2**n * 2
    return n01, n10, min(1.0, p)

def corr(xs, ys):
    n = len(xs); mx, my = sum(xs)/n, sum(ys)/n
    sx = math.sqrt(sum((x-mx)**2 for x in xs)); sy = math.sqrt(sum((y-my)**2 for y in ys))
    if sx == 0 or sy == 0: return 0.0
    return sum((x-mx)*(y-my) for x, y in zip(xs, ys)) / (sx * sy)

def main():
    assert not rb.port_up(PORT) and not rb.port_up(rb.QWEN_PORT), "llama-server already running; bench is strictly sequential"
    for m in MODELS.values(): assert os.path.exists(m), f"missing model {m}"
    t_start = time.time()
    results, cache, perc = [], {}, {}

    print(f"== [1/4] DictaLM: translate {len(STD)} std + {len(PERC)} perception ==", flush=True)
    with rb.LlamaServer(MODELS["dicta"], PORT):
        cache["dicta"] = translate_all(PORT, STD)
        perc["dicta"] = translate_all(PORT, PERC)

    print(f"== [2/4] TranslateGemma: translate {len(STD)} std + {len(PERC)} perception ==", flush=True)
    with rb.LlamaServer(MODELS["tgemma"], PORT, extra=("--chat-template", "gemma")):
        cache["tgemma"] = tgemma_translate_all(PORT, STD)
        perc["tgemma"] = tgemma_translate_all(PORT, PERC)

    en_texts = [(c[0], c[2], 0.0) for c in STD]
    print("== [3/4] qwen2.5-coder-1.5b: prod + improved prompts, EN ==", flush=True)
    with rb.LlamaServer(MODELS["qwen25c"], PORT):
        results.append(rb.summarize("app-prompt/qwen2.5c/perfect-EN", plan_all_d(PORT, en_texts, APP_PROMPT)))
        results.append(rb.summarize("revised-prompt/qwen2.5c/perfect-EN", plan_all_d(PORT, en_texts, REVISED_PROMPT, shots=PLANNER_SHOTS_D)))

    print("== [4/4] Qwen3-VL-4B: prod-en, improved-en, dicta->, tgemma-> ==", flush=True)
    with rb.LlamaServer(MODELS["qwen3vl"], PORT, extra=QWEN3VL_EXTRA):
        results.append(rb.summarize("app-prompt/qwen3vl/perfect-EN", plan_all_d(PORT, en_texts, APP_PROMPT)))
        results.append(rb.summarize("revised-prompt/qwen3vl/perfect-EN", plan_all_d(PORT, en_texts, REVISED_PROMPT, shots=PLANNER_SHOTS_D)))
        results.append(rb.summarize("revised-prompt/qwen3vl/dicta-HE", plan_all_d(PORT, cache["dicta"], REVISED_PROMPT, shots=PLANNER_SHOTS_D)))
        results.append(rb.summarize("revised-prompt/qwen3vl/tgemma-HE", plan_all_d(PORT, cache["tgemma"], REVISED_PROMPT, shots=PLANNER_SHOTS_D)))

    stamp = datetime.date.today().isoformat()
    R = {r["pipeline"]: r for r in results}

    # perception: keyword preservation
    perc_rows = {}
    for kind in ("dicta", "tgemma"):
        rows = []
        gmap = {p[0]: p[2] for p in PERC}; hmap = {p[0]: p[1] for p in PERC}
        for name, en, dt in perc[kind]:
            missed = score_perception(en, gmap[name])
            rows.append({"case": name, "he": hmap[name], "en": en, "t_ms": round(dt*1000),
                         "missed": ["|".join(g) for g in missed], "ok": not missed})
        perc_rows[kind] = rows
        ok = sum(1 for r in rows if r["ok"]); n = len(rows)
        lo, hi = rb.wilson(ok, n)
        groups_total = sum(len(gmap[r["case"]]) for r in rows)
        groups_kept = groups_total - sum(len(r["missed"]) for r in rows)
        print(f"perception {kind}: {ok}/{n} all-keywords ({ok/n:.0%}) wilson95 [{lo:.0%},{hi:.0%}]  "
              f"groups kept {groups_kept}/{groups_total} ({groups_kept/groups_total:.0%})", flush=True)

    # McNemar on the questions that matter
    pairs = [("app-prompt/qwen3vl/perfect-EN", "revised-prompt/qwen3vl/perfect-EN"), ("app-prompt/qwen2.5c/perfect-EN", "revised-prompt/qwen2.5c/perfect-EN"),
             ("revised-prompt/qwen3vl/dicta-HE", "revised-prompt/qwen3vl/tgemma-HE"), ("revised-prompt/qwen3vl/perfect-EN", "revised-prompt/qwen3vl/dicta-HE")]
    mn = {}
    for a, b in pairs:
        n01, n10, p = mcnemar(R[a]["cases"], R[b]["cases"])
        mn[f"{a} vs {b}"] = {"only_a": n01, "only_b": n10, "p": round(p, 5)}
        print(f"McNemar {a} vs {b}: a-only {n01}, b-only {n10}, p={p:.4g}", flush=True)

    # length-vs-latency, translate stage (input-side) + plan stage (output-side)
    ll = {}
    for kind in ("dicta", "tgemma"):
        xs = [len(dict((c[0], c[1]) for c in STD)[n]) for n, _, _ in cache[kind]] + [len(dict((p[0], p[1]) for p in PERC)[n]) for n, _, _ in perc[kind]]
        ys = [dt*1000 for _, _, dt in cache[kind]] + [dt*1000 for _, _, dt in perc[kind]]
        os_ = [len(t) for _, t, _ in cache[kind]] + [len(t) for _, t, _ in perc[kind]]
        buckets = {}
        for x, y in zip(xs, ys):
            k = "<=25" if x <= 25 else "26-60" if x <= 60 else "61-120" if x <= 120 else ">120"
            buckets.setdefault(k, []).append(y)
        ll[kind] = {"r_input_chars": round(corr(xs, ys), 3), "r_output_chars": round(corr(os_, ys), 3),
                    "bucket_p50_ms": {k: round(rb.pct(v, 50)) for k, v in sorted(buckets.items())}}
        print(f"latency-vs-length {kind}: r(in)={ll[kind]['r_input_chars']} r(out)={ll[kind]['r_output_chars']} "
              f"p50 by input-len {ll[kind]['bucket_p50_ms']}", flush=True)
    plan_rows = R["revised-prompt/qwen3vl/perfect-EN"]["cases"]
    ll["plan_qwen3vl"] = {"r_input_chars": round(corr([r["in_chars"] for r in plan_rows], [r["t_plan_ms"] for r in plan_rows]), 3),
                          "r_output_chars": round(corr([r["out_chars"] for r in plan_rows], [r["t_plan_ms"] for r in plan_rows]), 3)}
    print(f"latency-vs-length plan(qwen3vl improved): {ll['plan_qwen3vl']}", flush=True)

    out = os.path.join(HERE, "results", f"{stamp}-round4-results.json")
    json.dump({"arms": results, "perception": perc_rows, "mcnemar": mn, "latency_length": ll,
               "smoke": SMOKE, "wall_s": round(time.time() - t_start)},
              open(out, "w"), ensure_ascii=False, indent=1)

    dump = os.path.join(HERE, "results", f"{stamp}-perception-dump.md")
    with open(dump, "w") as f:
        f.write("# Perception-command translations (round 4) -- full dump for owner review\n\n")
        f.write("| case | Hebrew | DictaLM | TranslateGemma | missed (dicta) | missed (tgemma) |\n|---|---|---|---|---|---|\n")
        d2 = {r["case"]: r for r in perc_rows["tgemma"]}
        for r in perc_rows["dicta"]:
            g = d2[r["case"]]
            f.write(f"| {r['case']} | {r['he']} | {r['en']} | {g['en']} | {', '.join(r['missed']) or '-'} | {', '.join(g['missed']) or '-'} |\n")

    print("\n| arm | acc | wilson95 | p25 | p50 | p75 | p95 | p99 | max |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(results, key=lambda r: -r["acc"]):
        L = r["latency_e2e_ms"]
        print(f"| {r['pipeline']} | {r['ok']}/{r['n']} ({r['acc']:.0%}) | [{r['wilson95'][0]:.0%}, {r['wilson95'][1]:.0%}] "
              f"| {L['p25']} | {L['p50']} | {L['p75']} | {L['p95']} | {L['p99']} | {L['max']} |")
    print(f"\nresults -> {out}\nperception dump -> {dump}\nwall {round(time.time()-t_start)}s", flush=True)

if __name__ == "__main__":
    main()
