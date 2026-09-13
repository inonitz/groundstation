#!/usr/bin/env python3
"""Run SAM3 (bf16) over the demo test manifest: matched + variant prompts, notify phrases.
Renders an overlay per (test, prompt) into overlays/ and writes results/2026-09-03-suite.json.
Reference = current-pipeline output from the logs (in the manifest), for side-by-side judging.
"""
import json, os, time
import numpy as np, torch, cv2
from PIL import Image
from transformers import Sam3Model, Sam3Processor

BENCH = os.path.dirname(os.path.abspath(__file__))
MAN = json.load(open(f"{BENCH}/tests/manifest.json"))
FRAME_DIR = MAN["frame_dir"]
MODEL = "/root/models/vision/sam3-official"
OVL = f"{BENCH}/overlays"; os.makedirs(OVL, exist_ok=True)
RES = f"{BENCH}/results/2026-09-03-suite.json"
GREEN, CYAN, RED = (0, 200, 0), (255, 220, 0), (0, 0, 255)  # BGR

def detect(model, proc, img, text):
    inp = proc(images=img, text=text, return_tensors="pt").to("cuda")
    inp["pixel_values"] = inp["pixel_values"].to(torch.bfloat16)
    with torch.no_grad():
        out = model(**inp)
    r = proc.post_process_instance_segmentation(
        out, threshold=0.5, mask_threshold=0.5,
        target_sizes=inp.get("original_sizes").tolist())[0]
    m = r["masks"].float().cpu().numpy() if len(r["scores"]) else np.zeros((0,))
    b = r["boxes"].float().cpu().numpy() if len(r["scores"]) else np.zeros((0, 4))
    s = r["scores"].float().cpu().numpy() if len(r["scores"]) else np.zeros((0,))
    return m, b, s

def draw(cv_img, masks, boxes, scores, color, label):
    out = cv_img.copy()
    for i in range(len(scores)):
        mk = masks[i]
        if mk.ndim == 3:
            mk = mk[0]
        mk = mk.astype(bool)
        if mk.shape[:2] == out.shape[:2]:
            out[mk] = (0.5 * out[mk] + 0.5 * np.array(color)).astype(np.uint8)
        x1, y1, x2, y2 = [int(v) for v in boxes[i]]
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(out, f"{label} {scores[i]:.2f}", (x1, max(12, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    return out

def main():
    model = Sam3Model.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda").eval()
    proc = Sam3Processor.from_pretrained(MODEL)
    results = []
    for t in MAN["tests"]:
        path = f"{FRAME_DIR}/{t['image']}"
        if not os.path.exists(path):
            print("MISSING", path); continue
        img = Image.open(path).convert("RGB")
        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        base_color = CYAN if t["id"] == "t9_street_scene_ocr" else GREEN
        prompts = [("matched", t["matched_prompt"], base_color)]
        for i, v in enumerate(t.get("variants", [])):
            prompts.append((f"var{i}", v, base_color))
        if t.get("notify"):
            prompts.append(("notify", t["notify"], RED))
        rec = {"id": t["id"], "image": t["image"], "prompts": []}
        for tag, prompt, color in prompts:
            t0 = time.time(); m, b, s = detect(model, proc, img, prompt)
            dt = round((time.time() - t0) * 1000, 1)
            ov = draw(cv_img, m, b, s, color, prompt[:18])
            fn = f"{OVL}/{t['id']}__{tag}.jpg"
            cv2.imwrite(fn, ov)
            rec["prompts"].append({"tag": tag, "prompt": prompt, "n_det": int(len(s)),
                                   "top_score": round(float(s.max()), 3) if len(s) else 0.0,
                                   "latency_ms": dt, "overlay": os.path.basename(fn)})
            print(f"{t['id']:26s} {tag:7s} n={len(s):2d} top={rec['prompts'][-1]['top_score']:.2f} {prompt[:40]}")
        rec["reference"] = t.get("reference")
        results.append(rec)
    json.dump({"date": "2026-09-03", "model": "facebook/sam3 bf16", "tests": results},
              open(RES, "w"), indent=2)
    print("wrote", RES)

if __name__ == "__main__":
    main()
