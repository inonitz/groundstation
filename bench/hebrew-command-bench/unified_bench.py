#!/usr/bin/env python3
"""The harden2 lane (2026-09-08): Gemma 4 E4B ALONE through harden2's unified call on EVERY set of the dataset.
Commands are scored by the wire scorer (score), perception and military by the keyword groups applied to
"<kind words> the <target_en>" (kind words: highlight -> "highlight find mark follow track focus", count -> "count how
many", describe -> "describe tell what"), emergency by stage 0. Number guard and shot-echo guard as in the pipeline.
Run: MVD_HOME=integration_harden2 python3 unified_bench.py [--tag T]. One llama-server (Gemma 4, thinking off)."""
import os, sys, json, time, argparse, datetime
os.environ.setdefault("MVD_HOME", "integration_harden2"); os.environ.setdefault("MVD_TRANSLATOR", "none")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from bench import to_scorer_schema, LlamaServer, MODELS, GEMMA4_EXTRA, PORT
import cases_commands as C, cases_perception as P
from recognizer import recognize_direct, numbers_vs_mission
from pipeline import Pipeline, is_shot_echo
score = C.score
KIND_WORDS = {"highlight": "highlight find mark follow track focus", "count": "count how many", "describe": "describe tell what see look scene area frame image", "reject": ""}

class W:
    def halt(self): return 200
    def fly_mission(self, m): return 200

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", default="unified-gemma4"); ap.add_argument("--smoke", action="store_true"); a = ap.parse_args()
    cut = 5 if a.smoke else None
    sets = {"emergency": C.EMERGENCY_CASES[:cut], "std190": C.CASES[:cut], "verbose": C.VERBOSE_CASES[:cut], "perception": P.PERC100[:cut], "military": P.SLANG20[:cut]}
    out = {}; verdicts = {}; rows_all = {}; t_all = time.time()
    with LlamaServer(MODELS["gemma4"], extra=GEMMA4_EXTRA):
        pipe = Pipeline(W(), qwen_port=PORT)
        for set_name, cases in sets.items():
            rows = []
            for c in cases:
                name, he = c[0], c[1]; t0 = time.time()
                kind, payload, flags = recognize_direct(he); obj = None
                if set_name == "emergency":
                    v = "CORRECT" if kind == "emergency" else f"missed({kind})"
                elif kind == "emergency":
                    v = "routed:emergency"
                elif kind == "reject":
                    v = "CORRECT-reject" if c[3] == [] else "REJECT-neg-guard"
                elif set_name in ("std190", "verbose"):
                    expected = c[3]
                    if kind == "mission":
                        v = score(to_scorer_schema(payload), expected)
                    else:
                        obj = pipe._plan2(payload) or {}; k2 = obj.get("kind"); mission = obj.get("mission") or []
                        if k2 == "mission":
                            missing = numbers_vs_mission(payload, mission)
                            if not mission: v = score([], expected)
                            elif missing: v = "CORRECT-reject" if expected == [] else f"REJECT-numbers{missing}"
                            elif is_shot_echo(payload, mission): v = "CORRECT-reject" if expected == [] else "REJECT-echo"
                            else: v = score(to_scorer_schema(mission), expected)
                        elif k2 == "reject": v = "CORRECT-reject" if expected == [] else "REJECT"
                        else: v = "CORRECT-perception" if expected == [] else f"wrong-route({k2})"
                else:
                    groups = c[3]
                    if kind == "mission": v = "wrong-route(bypass)"
                    else:
                        obj = pipe._plan2(payload) or {}; k2 = obj.get("kind"); tgt = (obj.get("target_en") or "")
                        text = f"{KIND_WORDS.get(k2, '')} the {tgt}"
                        v = "CORRECT" if (k2 in ("highlight", "count", "describe") and not P.score_perception(text, groups)) else (f"wrong-route({k2})" if k2 not in ("highlight", "count", "describe") else f"keywords-missed({tgt[:30]})")
                rows.append({"case": name, "score": v, "obj": obj, "t_ms": round((time.time() - t0) * 1000)})
                if not v.startswith(("CORRECT", "valid", "routed:")): print(f"    FAIL {set_name:10s} {name:22s} {v[:40]} | {str(obj)[:80]}", flush=True)
            ok = sum(1 for r in rows if r["score"].startswith(("CORRECT", "valid"))); n = len([r for r in rows if not r["score"].startswith("routed:")])
            out[set_name] = {"ok": ok, "n": n}; verdicts[set_name] = {r["case"]: r["score"] for r in rows}; rows_all[set_name] = rows
            print(f"== {set_name}: {ok}/{n}", flush=True)
    tot = sum(v["ok"] for v in out.values()); n = sum(v["n"] for v in out.values())
    lines = ["| set | Gemma 4 alone (harden2 unified call) |", "|---|---|"] + [f"| {k} | {v['ok']}/{v['n']} |" for k, v in out.items()] + [f"| ALL | {tot}/{n} |"]
    ms = sorted(r["t_ms"] for rs in rows_all.values() for r in rs); lines.append(f"\nlatency per case: p50 {ms[len(ms)//2]} ms, p95 {ms[int(len(ms)*.95)]} ms; wall {time.time()-t_all:.0f} s")
    print("\n".join(lines))
    day = datetime.date.today().isoformat()
    json.dump({"home": os.environ["MVD_HOME"], "planner": "gemma4", "results": out, "verdicts": verdicts, "rows": rows_all}, open(os.path.join(HERE, "results", f"{day}-{a.tag}.json"), "w"), indent=1)
    open(os.path.join(HERE, "results", f"{day}-{a.tag}.md"), "w").write("# Gemma 4 alone through harden2's unified call, every set\n\n" + "\n".join(lines) + "\n")
    open(os.path.join(HERE, "results", f"{day}-{a.tag}.done"), "w").write("done")

if __name__ == "__main__":
    main()
