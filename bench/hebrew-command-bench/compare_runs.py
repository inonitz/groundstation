#!/usr/bin/env python3
"""Per-case diff of two bench raw JSONs (results/<date>-recognizer[-tag].json).
Prints per-set pass counts for both runs and every case whose verdict changed, so a Recognizer
change is judged by cases that flipped, not by a summary that can hide a fail/pass swap.

    python3 compare_runs.py results/A.json results/B.json
"""
import json
import sys


def verdicts(path):
    d = json.load(open(path, encoding="utf-8"))
    out = {}
    for set_name, rows in d["recognized"].items():
        for r in rows:
            out[(set_name, r["case"])] = (r["kind"], r["payload"])
    scored = {}
    for set_name, res in d["results"].items():
        scored[set_name] = (res["ok"], res["n"])
    return d.get("translator", "?"), out, scored


def main(a, b):
    ta, va, sa = verdicts(a)
    tb, vb, sb = verdicts(b)
    print(f"A = {a}  (translator {ta})\nB = {b}  (translator {tb})\n")
    print("| set | A ok/n | B ok/n | delta |\n|---|---|---|---|")
    for s in ("emergency", "std190", "verbose", "perception", "military"):
        oa, na = sa.get(s, (0, 0)); ob, nb = sb.get(s, (0, 0))
        print(f"| {s} | {oa}/{na} | {ob}/{nb} | {ob - oa:+d} |")
    ta_ok = sum(v[0] for v in sa.values()); tb_ok = sum(v[0] for v in sb.values())
    print(f"| ALL | {ta_ok} | {tb_ok} | {tb_ok - ta_ok:+d} |\n")
    changed = [(k, va[k], vb[k]) for k in va if k in vb and va[k] != vb[k]]
    print(f"Recognizer outputs that differ: {len(changed)} of {len(va)}")
    for (s, c), (ka, pa), (kb, pb) in changed:
        print(f"  {s:10s} {c:18s} A: [{ka}] {json.dumps(pa, ensure_ascii=False)[:90]}")
        print(f"  {'':10s} {'':18s} B: [{kb}] {json.dumps(pb, ensure_ascii=False)[:90]}")
    da, db = json.load(open(a)).get("verdicts"), json.load(open(b)).get("verdicts")
    if da and db:
        flips = [(s, c, da[s][c], db[s][c]) for s in da for c in da[s]
                 if c in db.get(s, {}) and (da[s][c].startswith(("CORRECT", "valid"))
                                            != db[s][c].startswith(("CORRECT", "valid")))]
        print(f"\nplanner verdicts that FLIPPED pass/fail: {len(flips)}")
        for s, c, x, y in flips:
            print(f"  {s:10s} {c:18s} {x}  ->  {y}" + ("   (Recognizer output unchanged -> planner noise)"
                                                       if va[(s, c)] == vb[(s, c)] else ""))
    else:
        print("\n(no per-case verdicts in one of the files: older bench.py)")
    only = set(va) ^ set(vb)
    if only:
        print(f"cases present in only one run: {sorted(only)[:10]}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
