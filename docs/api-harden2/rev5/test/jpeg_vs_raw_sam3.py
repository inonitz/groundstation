"""Does JPEG q95 change SAM3's output against the raw frame? 2026-10-16.
For each image: detect on the decoded array (the "raw" frame SAM3 would see live), then
on the same array after a JPEG q95 encode+decode; compare boxes by IoU and scores."""
import glob, json, os, sys, time
import cv2, numpy as np
sys.path.insert(0, "/root/groundstation/projects/integration_harden2")
from sam3.model import Sam3Backend

def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1]); x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / ua if ua else 0.0

files = sorted(glob.glob("/root/groundstation/bench/perception/dataset/images/*.jpg"))
m = Sam3Backend()
rows = []; t0 = time.time()
for f in files:
    name = os.path.basename(f)
    concept = name.split("-")[-1].rsplit(".", 1)[0].replace("_", " ") if "-" in name else "person"
    if concept in ("all chairs",): concept = "chair"
    img = cv2.imread(f)
    if img is None: continue
    if img.shape[1] > 1280:
        img = cv2.resize(img, (1280, int(img.shape[0] * 1280 / img.shape[1])))
    ok, j = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95]); jimg = cv2.imdecode(j, cv2.IMREAD_COLOR)
    _, raw = m.detect(img, concept, conf=0.30, topk=8)
    _, jpg = m.detect(jimg, concept, conf=0.30, topk=8)
    matched = []; unmatched_raw = 0
    for r in raw:
        best = max(((iou(r["box"], q["box"]), q) for q in jpg), key=lambda x: x[0], default=(0, None))
        if best[0] >= 0.5: matched.append((best[0], abs(r["conf"] - best[1]["conf"])))
        else: unmatched_raw += 1
    rows.append({"file": name, "concept": concept, "n_raw": len(raw), "n_jpg": len(jpg),
                 "matched": len(matched), "unmatched_raw": unmatched_raw,
                 "min_iou": round(min([x[0] for x in matched], default=1.0), 3),
                 "max_dconf": round(max([x[1] for x in matched], default=0.0), 4),
                 "psnr": round(float(cv2.PSNR(img, jimg)), 1)})
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
print("TOTAL", len(rows), "images in", round(time.time() - t0, 1), "s")
n = sum(r["n_raw"] for r in rows); same = sum(r["matched"] for r in rows)
print("boxes raw:", n, "matched in jpg at IoU>=0.5:", same, "count differs on", sum(r["n_raw"] != r["n_jpg"] for r in rows), "images")
print("min IoU over matched:", min(r["min_iou"] for r in rows), "max score delta:", max(r["max_dconf"] for r in rows))
