#!/usr/bin/env python3
"""Flight planning per case, three stacks side by side, from the bench's newest raw JSON per stack:
Gemma 4 direct Hebrew (gemma4-direct), Hy-MT2 -> Qwen (hymt2-*), DictaLM -> Qwen (dicta-*). Lists every
command case where any stack is not a pass.    python3 planning_table.py <out.md>"""
import glob, json, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CMD = os.path.join(ROOT, "tools", "bench", "hebrew-command-bench")
sys.path.insert(0, CMD)
from cases_commands import CASES, VERBOSE_CASES


def newest(pattern):
    """Newest raw JSON for the pattern whose translator prompt is v1 (the deployed prompt); v2 runs are skipped."""
    for f in sorted(glob.glob(os.path.join(CMD, "results", pattern)), key=os.path.getmtime, reverse=True):
        d = json.load(open(f))
        if d.get("prompt", "v1") == "v1":
            return d, os.path.basename(f)
    raise SystemExit(f"no v1-prompt run matches {pattern}")


def main(out):
    he = {c[0]: (c[1], c[3]) for c in CASES + VERBOSE_CASES}
    stacks = [("Gemma 4 direct", "*-recognizer-gemma4-direct.json"), ("Hy-MT2 -> Qwen", "*-recognizer-hymt2-*.json"), ("DictaLM -> Qwen", "*-recognizer-dicta-*.json")]
    data = [(name, *newest(pat)) for name, pat in stacks]
    v = lambda x: "pass" if str(x).startswith(("CORRECT", "valid")) else str(x)
    exp = lambda e: "open" if e is None else ("EMPTY" if e == [] else "; ".join(f"{t}" + (f" {k}={val}" if k else "") for t, k, val in e))
    lines = ["# Flight planning per case, three stacks side by side", "",
             "Sources: " + ", ".join(f"{n} = {f}" for n, _, f in data), "", "| set | case | Hebrew | expected | " + " | ".join(n for n, _, _ in data) + " |", "|---|---|---|---|" + "---|" * len(data)]
    tot = {n: [0, 0] for n, _, _ in data}; n_rows = 0
    for s in ("std190", "verbose"):
        for c in data[0][1]["verdicts"][s]:
            vs = [v(d["verdicts"][s].get(c, "?")) for _, d, _ in data]
            for (n, _, _), x in zip(data, vs):
                tot[n][1] += 1; tot[n][0] += (x == "pass")
            if all(x == "pass" for x in vs): continue
            n_rows += 1; lines.append(f"| {s} | {c} | {he[c][0][:60]} | {exp(he[c][1])[:50]} | " + " | ".join(vs) + " |")
    lines += ["", "Totals (commands): " + ", ".join(f"{n} {t[0]}/{t[1]}" for n, t in tot.items()) + f". {n_rows} cases where at least one stack is not a pass."]
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n"); print(lines[-1])


if __name__ == "__main__":
    main(sys.argv[1])
