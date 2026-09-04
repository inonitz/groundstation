#!/usr/bin/env python3
"""Engine-level A/B: drive the real PerceptionEngine with each backend and compare.

This is NOT the raw-backend comparison (that lives in RESULTS.md). It proves the perception2 swap:
the SAME engine logic (relative gate + mask hygiene, single-homed in perception/engine.py) runs on
two backends -- OmDet+SAM2.1 (perception) vs SAM3-nf4 (perception2) -- and we compare detections,
mask coverage and per-highlight latency.

One model set resident at a time: each backend runs in its own subprocess (VRAM isolation). The
presence gate is bypassed (no VLM server needed); bare concepts are fed so the backends are compared
directly, not the concept front-end.

    python3 compare_engines.py            # run both subprocesses, then print + write the comparison
    python3 compare_engines.py omdet OUT  # worker: run OmDet+SAM2.1 path, write OUT.json
    python3 compare_engines.py sam3  OUT  # worker: run SAM3-nf4 path, write OUT.json
"""
import os, sys, json, time, subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
IH = "/root/groundstation/projects/integration_harden"
CAND = os.path.join(HERE, "candidates")
sys.path.insert(0, IH)

IMAGES = ["img0.png", "img1.png", "img2.png", "img3.png", "img4.png", "img5.jpeg", "img6.jpeg",
          "img7.jpeg", "img10_highlight_windows_from_event_perform_ocr.jpeg",
          "market-0.jpg", "market-1.jpg", "market-2.jpg", "street-crowd-0.jpg", "street-crowd-1.jpg",
          "street-scene-0.jpg", "street-scene-1.jpg", "street-scene-2.jpg"]
CONCEPTS = ["person", "window", "car"]     # a fixed panel: covers crowds, buildings, streets


def _build_engine(backend):
    from perception import PerceptionEngine
    if backend == "omdet":
        from perception.detectors import OmDet, Eyes
        import config
        eyes = Eyes()
        det = OmDet(config.resolve_torch_device())
        return PerceptionEngine(detect=lambda f, p, c: det.detect(f, p, conf=c),
                                mask_for_box=eyes.mask_for_box, vlm_ask=None)
    import perception2
    return perception2.build_engine(vlm_ask=None)


def worker(backend, out):
    import cv2
    eng = _build_engine(backend)
    rows = []
    for name in IMAGES:
        path = os.path.join(CAND, name)
        frame = cv2.imread(path)
        if frame is None:
            continue
        for concept in CONCEPTS:
            t = time.time()
            dets, masks, _ = eng.highlight_step(frame, concept, use_sam=True)
            dt = (time.time() - t) * 1000.0
            rows.append({"image": name, "concept": concept, "n": len(dets), "ms": round(dt, 1),
                         "boxes": [d["box"] for d in dets],
                         "mask_px": int(sum(int(m.sum()) for m in masks))})
    json.dump({"backend": backend, "rows": rows}, open(out, "w"))
    print(f"[{backend}] {len(rows)} rows -> {out}", flush=True)


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def _pct(xs, p):
    return round(float(np.percentile(xs, p)), 1) if xs else 0.0


def compare(a, b):
    ra = {(r["image"], r["concept"]): r for r in a["rows"]}
    rb = {(r["image"], r["concept"]): r for r in b["rows"]}
    keys = sorted(set(ra) | set(rb))
    lines = ["# Engine-level A/B: OmDet+SAM2.1 vs SAM3-nf4", "",
             "Both run through the same PerceptionEngine (relative gate + mask hygiene). Presence "
             "gate bypassed; bare concepts fed. Latency = full highlight_step (detect + mask).", "",
             "| image | concept | OmDet n | SAM3 n | best box IoU |",
             "|-------|---------|--------:|-------:|-------------:|"]
    tot_a = tot_b = 0
    for k in keys:
        da, db = ra.get(k), rb.get(k)
        na = da["n"] if da else 0
        nb = db["n"] if db else 0
        tot_a += na; tot_b += nb
        iou = 0.0
        if da and db and da["boxes"] and db["boxes"]:
            iou = max(_iou(x, y) for x in da["boxes"] for y in db["boxes"])
        if na or nb:
            lines.append(f"| {k[0]} | {k[1]} | {na} | {nb} | {iou:.2f} |")
    la = [r["ms"] for r in a["rows"]]
    lb = [r["ms"] for r in b["rows"]]
    lines += ["", "## Totals", "",
              "| backend | total dets | latency p50 ms | p90 ms |",
              "|---------|-----------:|---------------:|-------:|",
              f"| OmDet+SAM2.1 | {tot_a} | {_pct(la,50)} | {_pct(la,90)} |",
              f"| SAM3-nf4 | {tot_b} | {_pct(lb,50)} | {_pct(lb,90)} |", ""]
    return "\n".join(lines)


def main():
    if len(sys.argv) == 3 and sys.argv[1] in ("omdet", "sam3"):
        worker(sys.argv[1], sys.argv[2]); return
    ao = os.path.join(HERE, "results", "2026-09-03-engine-ab-omdet.json")
    bo = os.path.join(HERE, "results", "2026-09-03-engine-ab-sam3.json")
    env = dict(os.environ)
    for backend, out in (("omdet", ao), ("sam3", bo)):
        print(f"=== running {backend} subprocess ===", flush=True)
        subprocess.run([sys.executable, __file__, backend, out], check=True, env=env)
    a = json.load(open(ao)); b = json.load(open(bo))
    report = compare(a, b)
    rp = os.path.join(HERE, "results", "2026-09-03-engine-ab.md")
    open(rp, "w").write(report)
    print("\n" + report + f"\n\n(written to {rp})")


if __name__ == "__main__":
    main()
