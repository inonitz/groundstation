#!/usr/bin/env python3
"""Draw, per image and phrase, a three-panel overlay: [Qwen3-VL] its HIGHLIGHT phrase + its own VLM_BOX (yellow) +
SAM3's boxes from that phrase (green) | [Gemma 4] the same | [reference] SAM3 on the asked concept (magenta).
Input: a vlm-compare.json with full replies and boxes. Output: <out_dir>/<image>__<phrase>.jpg + index.md.
    python3 overlays.py <vlm-compare.json> <out_dir>"""
import json, os, sys, glob, cv2, numpy as np
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "projects", "integration_harden"))
from perception2.sam3_backend import Sam3Backend
from perception.engine import scale_vlm_box
BENCH = os.path.join(ROOT, "tools", "bench", "sam3-mask-bench")


def main(src, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    d = json.load(open(src)); rows = [r for r in d["rows"] if r["job"] == "gate"]
    paths = {os.path.basename(p): p for p in glob.glob(f"{BENCH}/candidates/*") + glob.glob("/root/models/vision/sam3-desk-frames/*.jpg")}
    sam3 = Sam3Backend(); index = ["# Overlays: what each VLM asked SAM3 to highlight, next to the reference", "",
                                   "Yellow = the VLM's own VLM_BOX. Green = SAM3 boxes from the VLM's HIGHLIGHT phrase. Magenta = SAM3 on the asked concept (reference; no human ground truth exists).", "",
                                   "| image | phrase | Qwen3-VL said | Gemma 4 said | file |", "|---|---|---|---|---|"]
    keys = sorted({(r["image"], r["phrase"]) for r in rows})
    for img, ph in keys:
        f = cv2.imread(paths[img])
        if f.shape[1] > 1280:
            s = 1280 / f.shape[1]; f = cv2.resize(f, (1280, int(f.shape[0] * s)))
        ref = sam3.detect(f, ph, conf=0.5, topk=50)
        panels, said = [], {}
        for model in ("qwen3vl", "gemma4"):
            rr = [r for r in rows if r["model"] == model and r["image"] == img and r["phrase"] == ph]
            pan = f.copy(); label = f"{model}: absent"
            if rr:
                r = rr[0]
                if r["vlm_present"]:
                    label = f"{model}: '{r['vlm_target']}'"
                    for dd in sam3.detect(f, r["vlm_target"], conf=0.3, topk=20):
                        x1, y1, x2, y2 = dd["box"]; cv2.rectangle(pan, (x1, y1), (x2, y2), (60, 220, 60), 2)
                    if r.get("vlm_box"):
                        x1, y1, x2, y2 = scale_vlm_box(tuple(r["vlm_box"]), f.shape); cv2.rectangle(pan, (x1, y1), (x2, y2), (0, 230, 255), 3)
            said[model] = label.split(": ", 1)[1]
            cv2.putText(pan, label[:60], (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2); panels.append(pan)
        pan = f.copy()
        for dd in ref:
            x1, y1, x2, y2 = dd["box"]; cv2.rectangle(pan, (x1, y1), (x2, y2), (220, 60, 220), 2)
        cv2.putText(pan, f"reference: SAM3 '{ph}' ({len(ref)})", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2); panels.append(pan)
        w = 640; panels = [cv2.resize(p, (w, int(p.shape[0] * w / p.shape[1]))) for p in panels]
        name = f"{os.path.splitext(img)[0]}__{ph.replace(' ', '_')}.jpg"
        cv2.imwrite(os.path.join(out_dir, name), cv2.hconcat(panels), [cv2.IMWRITE_JPEG_QUALITY, 85])
        index.append(f"| {img} | {ph} | {said.get('qwen3vl', '')} | {said.get('gemma4', '')} | [{name}]({name}) |")
    open(os.path.join(out_dir, "index.md"), "w", encoding="utf-8").write("\n".join(index) + "\n")
    print(f"{len(keys)} overlays -> {out_dir}/index.md")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
