#!/usr/bin/env python3
"""Agent3 YOLO image-quality test.

Measures seg detection/classification quality across:
  - resolution   : 384 vs 480
  - precision    : fp32 vs INT4 (matched resolution)
  - input quality: original / JPEG q75,q50,q25,q10 / 320x240 downscale-roundtrip

Metric per (image, variant, degradation): does the primary object survive, at
what confidence, and how many total detections. Depth section reports median
depth stability of the same variants on the target region.

End-to-end (NMS-free) seg head: output0 row = [x1,y1,x2,y2,score,class,32 mask].
"""
import io, os, glob
import onnxruntime as ort
import numpy as np
from PIL import Image, ImageFilter

ort.set_default_logger_severity(3)
MDIR = '/root/models/vision'
COCO = {0: 'person', 1: 'bicycle', 2: 'car', 7: 'truck', 16: 'dog'}
CONF = 0.25

IMAGES = [
    ('person_std', '/root/groundstation/dependencies/gz_models/person_standing/thumbnails/1.png', 0),
    ('person_wlk', '/root/groundstation/dependencies/gz_models/person_walking/thumbnails/1.png', 0),
    ('dog_coco',   '/root/groundstation/build/release/shared/_deps/yolos-cpp-src/data/dog.jpg', 16),
]
# (label, model file, run-size). Baked models ignore run-size (fixed export).
SEG_VARIANTS = [
    ('fp32-384', 'yolo26n-seg-384.onnx', 384),
    ('fp32-480', 'yolo26n-seg-480.onnx', 480),
    ('int4@384', 'yolo26n-seg.int4.onnx', 384),
    ('int4@480', 'yolo26n-seg.int4.onnx', 480),
    ('int8@384', 'yolo26n-seg.int8.onnx', 384),
]
DEGRADE = ['orig', 'jpg75', 'jpg50', 'jpg25', 'jpg10', 'ds320']


def degrade(img, mode):
    if mode == 'orig':
        return img
    if mode == 'ds320':                       # dashboard-path 320x240 roundtrip
        return img.resize((320, 240)).resize(img.size)
    q = int(mode[3:])
    b = io.BytesIO(); img.save(b, 'JPEG', quality=q)
    return Image.open(io.BytesIO(b.getvalue())).convert('RGB')


def letterbox(img, S):
    w, h = img.size
    r = min(S / w, S / h); nw, nh = round(w * r), round(h * r)
    c = Image.new('RGB', (S, S), (114, 114, 114))
    c.paste(img.resize((nw, nh)), ((S - nw) // 2, (S - nh) // 2))
    return (np.asarray(c).astype(np.float32) / 255).transpose(2, 0, 1)[None]


def load(mfile):
    return ort.InferenceSession(os.path.join(MDIR, mfile), providers=['CPUExecutionProvider'])


def seg_run(sess, img, S):
    o = sess.run(None, {'images': letterbox(img, S)})[0][0]
    return o[o[:, 4] > CONF]


print("=" * 78)
print("SEG: primary-object confidence  (n=total dets>%.2f; '-'=primary lost)" % CONF)
print("=" * 78)

# preload sessions (skip int8 if it fails)
sessions = {}
for lbl, mf, S in SEG_VARIANTS:
    try:
        sessions[lbl] = (load(mf), S)
    except Exception as e:
        sessions[lbl] = ('FAIL', str(e)[:60])

for iname, ipath, pcls in IMAGES:
    src = Image.open(ipath).convert('RGB')
    print("\n[%s]  primary=%s  (%dx%d)" % (iname, COCO.get(pcls, pcls), *src.size))
    hdr = "  %-6s" % 'deg' + "".join("%-14s" % v[0] for v in SEG_VARIANTS)
    print(hdr)
    for dg in DEGRADE:
        di = degrade(src, dg)
        row = "  %-6s" % dg
        for lbl, mf, S in SEG_VARIANTS:
            sess = sessions[lbl]
            if sess[0] == 'FAIL':
                row += "%-14s" % 'LOADFAIL'; continue
            try:
                m = seg_run(sess[0], di, sess[1])
            except Exception as e:
                row += "%-14s" % 'RUNFAIL'; continue
            prim = m[m[:, 5].astype(int) == pcls]
            conf = float(prim[:, 4].max()) if len(prim) else None
            cell = ("%.3f(%d)" % (conf, len(m))) if conf is not None else "-(%d)" % len(m)
            row += "%-14s" % cell
        print(row)

# ---- depth: median-depth stability on center crop of target ----
print("\n" + "=" * 78)
print("DEPTH: raw output stats on person_std (orig), by variant")
print("=" * 78)
DEPTH_VARIANTS = [
    ('fp32-384', 'yolo26n-depth-384.onnx', 384),
    ('fp32-480', 'yolo26n-depth-480.onnx', 480),
    ('int4@384', 'yolo26n-depth.int4.onnx', 384),
    ('int8@384', 'yolo26n-depth.int8.onnx', 384),
]
dsrc = Image.open(IMAGES[0][1]).convert('RGB')
for lbl, mf, S in DEPTH_VARIANTS:
    try:
        sess = load(mf)
        out = sess.run(None, {'images': letterbox(dsrc, S)})[0]
        a = np.asarray(out, dtype=np.float32).ravel()
        print("  %-10s out%s  min %.3f  med %.3f  max %.3f  mean %.3f"
              % (lbl, list(np.asarray(out).shape), a.min(), np.median(a), a.max(), a.mean()))
    except Exception as e:
        print("  %-10s LOAD/RUN FAIL: %s" % (lbl, str(e)[:60]))
