#!/usr/bin/env python3
"""Lane 3c: SAM3 alone as the presence gate (no VLM). Runs SAM3 once per (image, phrase) with a low score floor,
keeps every score, then sweeps a presence threshold and scores SAM3 alone, the Qwen3-VL gate and the Gemma 4 gate
(from a vlm-compare.json) against presence labels (labels/presence-<date>.json). Only SAM3 runs; no drone.
    python3 sam3_alone.py --detect          # SAM3 over all asks -> <out>-raw.json
    python3 sam3_alone.py --score           # raw + labels + vlm-compare.json -> <out>.md / <out>.json
"""
import argparse, datetime, glob, json, os, sys, time, cv2
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "projects", "integration_harden"))
BENCH = os.path.join(ROOT, "tools", "bench", "sam3-mask-bench")
CAND_PHRASES = ["person", "car", "window", "boiler"]
DESK_PHRASES = ["person", "chair", "monitor", "boiler"]
THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

def images():
    cands = sorted(glob.glob(os.path.join(BENCH, "candidates", "*")))
    desk = sorted(glob.glob("/root/models/vision/sam3-desk-frames/*.jpg"))[::15][:8]
    return [(p, CAND_PHRASES, "bench") for p in cands] + [(p, DESK_PHRASES, "desk") for p in desk]

def load(p):
    f = cv2.imread(p)
    if f is not None and f.shape[1] > 1280:
        s = 1280 / f.shape[1]; f = cv2.resize(f, (1280, int(f.shape[0] * s)))
    return f

def pct(xs, q):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0

def detect(out, floor):
    from perception2.sam3_backend import Sam3Backend
    sam3 = Sam3Backend(); rows = []; t_all = time.time()
    for p, phrases, group in images():
        fr = load(p)
        if fr is None: continue
        for ph in phrases:
            t0 = time.time(); dets = sam3.detect(fr, ph, conf=floor, topk=50); ms = (time.time() - t0) * 1000
            scores = sorted([float(d.get("score", d.get("conf", 0.0))) for d in dets], reverse=True)
            rows.append({"image": os.path.basename(p), "set": group, "phrase": ph, "scores": scores,
                         "max": scores[0] if scores else 0.0, "ms": round(ms), "top_box": [int(v) for v in dets[0]["box"]] if dets else None})
            print(f"{os.path.basename(p)[:28]:28s} {ph:8s} max={rows[-1]['max']:.2f} n={len(scores)} {ms:.0f} ms", flush=True)
    json.dump({"floor": floor, "wall_s": round(time.time() - t_all), "rows": rows}, open(out + "-raw.json", "w"), indent=1)
    print("wrote", out + "-raw.json")

def build_consensus(vlm_path, out_labels):
    """Labels = the two VLM gates agree (NOT human truth). Disputed asks are left out. Also writes a blank template."""
    d = json.load(open(vlm_path)); by = {}
    for r in d["rows"]:
        if r["job"] == "gate": by.setdefault((r["image"], r["phrase"]), {})[r["model"]] = bool(r["vlm_present"])
    labels = {}; template = {}; disputed = []
    for (im, ph), v in by.items():
        template.setdefault(im, {})[ph] = None
        if len(v) >= 2 and len(set(v.values())) == 1: labels.setdefault(im, {})[ph] = list(v.values())[0]
        else: disputed.append({"image": im, "phrase": ph, **v})
    json.dump({"labeled_by": "CONSENSUS of the qwen3vl and gemma4 gates from vlm-compare.json (NOT human truth; disputed asks omitted)",
               "labels": labels, "disputed": disputed}, open(out_labels, "w"), indent=1)
    tpl = out_labels.replace(".json", "").replace("-vlm-consensus", "") + ".template.json"
    json.dump({"labeled_by": "FILL IN: who looked at the images, and when", "labels": template,
               "how": "true = at least one such object clearly visible; false = not; then: python3 sam3_alone.py --score --labels <this file renamed presence-<date>.json>"},
              open(tpl, "w"), indent=1)
    print(f"consensus labels: {sum(len(v) for v in labels.values())} asks, disputed {len(disputed)} -> {out_labels}; template -> {tpl}")

def score(out, labels_path, vlm_path):
    raw = json.load(open(out + "-raw.json")); rows = raw["rows"]
    L = json.load(open(labels_path)) if os.path.exists(labels_path) else None
    labels = L["labels"] if L else None; who = L.get("labeled_by", "?") if L else None
    vlm = {}; vlm_lat = {}
    if os.path.exists(vlm_path):
        d = json.load(open(vlm_path))
        for r in d["rows"]:
            if r["job"] == "gate": vlm.setdefault((r["image"], r["phrase"]), {})[r["model"]] = bool(r["vlm_present"])
        vlm_lat = {k: v.get("latency_p50_ms") for k, v in d["summary"].items()}
    models = sorted({m for v in vlm.values() for m in v})
    cands = [(f"SAM3 alone, present if max score >= {t:.1f}", {(r["image"], r["phrase"]): r["max"] >= t for r in rows}) for t in THRESHOLDS]
    cands += [(f"{m} gate (production prompt)", {k: v[m] for k, v in vlm.items() if m in v}) for m in models]
    ms = [r["ms"] for r in rows][1:]
    lines = ["# SAM3 alone as the presence gate — threshold sweep, next to the two VLM gates", "",
             f"{len(rows)} asks ({sum(r['set']=='bench' for r in rows)} bench-image asks + {sum(r['set']=='desk' for r in rows)} desk-frame asks). "
             f"SAM3 ran once per ask with score floor {raw['floor']}; presence at threshold t = max score >= t. SAM3 is deterministic.",
             f"Labels: {('`' + os.path.relpath(labels_path, HERE) + '` — labeled by: ' + who) if labels else 'NONE — only agreement with the VLM gates is reported'}.",
             f"SAM3 detect latency per ask (first call excluded): p50 {pct(ms, .5)} ms, p95 {pct(ms, .95)} ms. VLM gate p50 from vlm-compare: "
             + ", ".join(f"{k} {v} ms" for k, v in vlm_lat.items()), ""]
    result = {"n": len(rows), "labels": who, "sam3_ms_p50": pct(ms, .5), "sam3_ms_p95": pct(ms, .95), "candidates": {}}
    if labels:
        lab = {}
        for r in rows:
            v = labels.get(r["image"], {}).get(r["phrase"])
            if v is not None: lab[(r["image"], r["phrase"])] = bool(v)
        n_abs = sum(not v for v in lab.values()); n_pres = sum(lab.values())
        lines += [f"Labeled asks: {len(lab)}/{len(rows)} ({n_pres} present, {n_abs} absent; boiler is absent by construction). Unlabeled asks are skipped.", "",
                  "| candidate gate | correct / labeled | false present / absent asks | missed / present asks | bench correct | desk correct |", "|---|---|---|---|---|---|"]
        for name, dec in cands:
            ok = fp = miss = bok = dok = bn = dn = 0
            for r in rows:
                k = (r["image"], r["phrase"])
                if k not in dec or k not in lab: continue
                c = dec[k] == lab[k]; ok += c
                if r["set"] == "bench": bn += 1; bok += c
                else: dn += 1; dok += c
                fp += dec[k] and not lab[k]; miss += lab[k] and not dec[k]
            lines.append(f"| {name} | {ok}/{bn + dn} | {fp}/{n_abs} | {miss}/{n_pres} | {bok}/{bn} | {dok}/{dn} |")
            result["candidates"][name] = {"correct": ok, "n": bn + dn, "false_present": fp, "absent": n_abs, "missed": miss, "present": n_pres}
        unl = [(r["image"], r["phrase"]) for r in rows if (r["image"], r["phrase"]) not in lab]
        dis = [(r["image"], r["phrase"], r["max"]) for r in rows if (r["image"], r["phrase"]) in lab and (r["max"] >= 0.5) != lab[(r["image"], r["phrase"])]]
        lines += ["", "## Asks the owner must settle by eye (strips: results/<date>/side-by-side.md, grouped by image, one per prompt)", "",
                  f"Unlabeled (the label source did not decide): {len(unl)}", ""] + [f"- {im} / {ph}" for im, ph in unl] + \
                 ["", f"SAM3 @0.5 disagrees with the label: {len(dis)}", ""] + [f"- {im} / {ph}: SAM3 max {mx:.2f}, label {'present' if lab[(im, ph)] else 'absent'}" for im, ph, mx in dis]
        lines += ["", "## Per ask (* = disagrees with the label; ? = no label)", "",
                  "| image | phrase | label | SAM3 max | SAM3 @0.5 | " + " | ".join(models) + " |", "|---|---|---|---|---|" + "---|" * len(models)]
        for r in rows:
            k = (r["image"], r["phrase"]); s3 = r["max"] >= 0.5
            cell = lambda v: "-" if v is None else ("present" if v else "absent") + ("" if k not in lab or v == lab[k] else " *")
            lines.append(f"| {r['image'][:26]} | {r['phrase']} | {('present' if lab[k] else 'absent') if k in lab else '?'} | {r['max']:.2f} | {cell(s3)} | "
                         + " | ".join(cell(vlm.get(k, {}).get(m)) for m in models) + " |")
    else:
        lines += ["| candidate | agrees with qwen3vl gate | agrees with gemma4 gate | says present on boiler |", "|---|---|---|---|"]
        for name, dec in cands:
            aq = sum(dec[k] == v.get("qwen3vl") for k, v in vlm.items() if k in dec and "qwen3vl" in v)
            ag = sum(dec[k] == v.get("gemma4") for k, v in vlm.items() if k in dec and "gemma4" in v)
            lines.append(f"| {name} | {aq}/{len(vlm)} | {ag}/{len(vlm)} | {sum(dec[k] for k in dec if k[1] == 'boiler')}/{sum(k[1]=='boiler' for k in dec)} |")
    open(out + ".md", "w", encoding="utf-8").write("\n".join(lines) + "\n"); json.dump(result, open(out + ".json", "w"), indent=1)
    print("\n".join(lines[:8 + len(cands) + (2 if labels else 0)]))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--detect", action="store_true"); ap.add_argument("--score", action="store_true")
    ap.add_argument("--consensus", action="store_true", help="build labels from the two VLM gates agreeing (not truth)")
    ap.add_argument("--floor", type=float, default=0.05)
    day = datetime.date.today().isoformat()
    ap.add_argument("--out", default=os.path.join(HERE, "results", day, "sam3-alone"))
    ap.add_argument("--labels", default=os.path.join(HERE, "labels", f"presence-{day}.json"))
    ap.add_argument("--vlm", default=os.path.join(HERE, "results", day, "vlm-compare.json"))
    a = ap.parse_args(); os.makedirs(os.path.dirname(a.out), exist_ok=True)
    if a.consensus:
        a.labels = a.labels.replace(".json", "-vlm-consensus.json"); build_consensus(a.vlm, a.labels)
    if a.detect: detect(a.out, a.floor)
    if a.score: score(a.out, a.labels, a.vlm)
