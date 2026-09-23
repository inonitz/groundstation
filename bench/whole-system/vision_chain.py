#!/usr/bin/env python3
"""Lane 3b: does SAM3 highlight the asked object from each VLM's HIGHLIGHT phrase?
Input: a vlm-compare.json (vlm_compare.py). Reference = SAM3 on the asked concept. For every gate ask where the
object is present, the VLM must say present and its phrase must make SAM3 return a box overlapping the reference
top box (IoU >= 0.5). Also reports the VLM's own box as a fallback. Only SAM3 runs.
    python3 vision_chain.py <vlm-compare.json> <out.md>"""
import json, os, sys, glob, cv2
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "projects", "integration_harden2"))
from perception2.sam3_backend import Sam3Backend
BENCH = os.path.join(ROOT, "tools", "bench", "sam3-mask-bench")


def iou(a, b):
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    iw = max(0, min(ax2, bx2) - max(ax1, bx1)); ih = max(0, min(ay2, by2) - max(ay1, by1)); i = iw * ih
    u = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - i
    return i / u if u > 0 else 0


def main(src, out):
    d = json.load(open(src)); rows = [r for r in d["rows"] if r["job"] == "gate"]
    paths = {os.path.basename(p): p for p in glob.glob(f"{BENCH}/candidates/*") + glob.glob("/root/models/vision/sam3-desk-frames/*.jpg")}
    frames = {}
    def frame(name):
        if name not in frames:
            f = cv2.imread(paths[name])
            if f.shape[1] > 1280:
                s = 1280 / f.shape[1]; f = cv2.resize(f, (1280, int(f.shape[0] * s)))
            frames[name] = f
        return frames[name]
    sam3 = Sam3Backend(); ref = {}; per = {}
    head = ["# Does SAM3 highlight what was asked, from each VLM's HIGHLIGHT phrase?", "",
            "Chain: VLM gate says present + returns a phrase -> the phrase goes to SAM3 (as in scene_omdet). Reference = SAM3 on the asked concept.",
            "hit = SAM3 on the VLM phrase returns a box with IoU >= 0.5 against the reference top box. gate ok = present/absent matches the reference.", "",
            "| model/mode | gate ok | VLM said present when ref present | SAM3 hit from the VLM phrase | VLM phrase gave SAM3 nothing | VLM-box fallback IoU>=0.5 |", "|---|---|---|---|---|---|"]
    sheet = ["", "## Per image and phrase", "", "| image | phrase | ref | model/mode | VLM said | VLM phrase | SAM3 on VLM phrase | box fallback IoU |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        key = (r["image"], r["phrase"])
        if key not in ref:
            ref[key] = sam3.detect(frame(r["image"]), r["phrase"], conf=0.5, topk=50)[1]
        dets = ref[key]; present = len(dets) > 0
        k = f"{r['model']}/{r['mode']}"; p = per.setdefault(k, {"gate": 0, "n": 0, "pres_n": 0, "said": 0, "hit": 0, "empty": 0, "fb": 0, "fbn": 0})
        p["n"] += 1; p["gate"] += (r["vlm_present"] == present); s3 = "-"; fb = "-"
        if present:
            p["pres_n"] += 1
            if r["vlm_present"]:
                p["said"] += 1
                vd = sam3.detect(frame(r["image"]), r["vlm_target"], conf=0.3, topk=20)[1] if r["vlm_target"] else []
                if not vd:
                    p["empty"] += 1; s3 = "NOTHING"
                else:
                    best = max(iou(v["box"], dets[0]["box"]) for v in vd); s3 = f"{len(vd)} dets, best IoU {best:.2f}"
                    if best >= 0.5: p["hit"] += 1
                if r.get("iou") is not None:
                    p["fbn"] += 1; p["fb"] += (r["iou"] >= 0.5); fb = f"{r['iou']:.2f}"
        sheet.append(f"| {r['image'][:26]} | {r['phrase']} | {'present (' + str(len(dets)) + ')' if present else 'absent'} | {k} | {'present' if r['vlm_present'] else 'absent'} | {r['vlm_target'] or '-'} | {s3} | {fb} |")
    for k, p in per.items():
        head.append(f"| {k} | {p['gate']}/{p['n']} | {p['said']}/{p['pres_n']} | {p['hit']}/{p['said']} | {p['empty']}/{p['said']} | {p['fb']}/{p['fbn']} |")
    open(out, "w", encoding="utf-8").write("\n".join(head + sheet) + "\n"); print("\n".join(head))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
