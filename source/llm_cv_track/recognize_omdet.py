#!/usr/bin/env python3
"""Single-shot OPEN-VOCAB recognition on a still image (the STAR engine, no camera/voice):
image + prompt -> OmDet-Turbo detects the prompted object(s) -> SAM2.1 masks them -> annotated jpg +
<out>_log.txt.  Feed it imagery + specific prompts.

  python3 recognize_omdet.py <image> "<prompt>" [--mask] [--show] [--conf 0.25] [-o out.jpg]
  e.g.  python3 recognize_omdet.py room.jpg "guitar case, headphones" --mask
Comma-separate multiple things in one prompt.
"""
import os, sys, time
os.environ.setdefault("SCENE_HL_BACKEND", "vlm")
import cv2, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = "/root/groundstation/source/llm_cv_scene"
sys.path.insert(0, HERE); sys.path.insert(0, SCENE)
import config
from eyes import Eyes
import highlight_seg as HS

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__); return
    path = args[0]; rest = args[1:]
    want_mask = "--mask" in rest; show = "--show" in rest
    conf = 0.25; out = None; parts = []; i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("--mask", "--show"): i += 1; continue
        if a == "-o": out = rest[i+1]; i += 2; continue
        if a == "--conf": conf = float(rest[i+1]); i += 2; continue
        if a.startswith("-"): i += 1; continue
        parts.append(a); i += 1
    prompt = " ".join(parts) or "object"

    img = cv2.imread(path)
    if img is None: print("cannot read image:", path); return
    out = out or (os.path.splitext(path)[0] + "_omdet.jpg")
    log_path = os.path.splitext(out)[0] + "_log.txt"
    buf = []
    def log(s=""): print(s); buf.append(str(s))
    hh, ww = img.shape[:2]; fa = float(hh*ww)
    log(f"[recognize_omdet] {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"[recognize_omdet] argv   : {' '.join(sys.argv)}")
    log(f"[recognize_omdet] image  : {path} ({ww}x{hh})")
    log(f"[recognize_omdet] prompt : {prompt}   conf={conf}  mask={want_mask}")
    log("[recognize_omdet] loading OmDet-Turbo + SAM2 (first run ~slow)...")
    eyes = Eyes(); det = HS.OmDet(eyes.tdevice)
    t0 = time.time()
    raw = det.detect(img, prompt, conf=conf, topk=20)
    log(f"\n=== OmDet found {len(raw)} detection(s) in {(time.time()-t0)*1000:.0f} ms ===")
    disp = img.copy(); masks = []
    if want_mask:
        for d in raw:
            m = eyes.mask_for_box(img, d["box"])
            if m is not None and 0 < m.sum() <= 0.6*fa:
                if m.shape[:2] != disp.shape[:2]:
                    m = cv2.resize(m.astype("uint8"), (disp.shape[1], disp.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
                masks.append(m)
        if masks:
            ov = disp.copy()
            for m in masks: ov[m] = config.COL_SAM2_HL
            cv2.addWeighted(ov, 0.45, disp, 0.55, 0, disp)
    for d in raw:
        x1, y1, x2, y2 = d["box"]
        log(f"  {d['label']:24s} {d['conf']:.2f}  {d['box']}")
        cv2.rectangle(disp, (x1, y1), (x2, y2), config.COL_YOLOE_HL, 2)
        cv2.putText(disp, f"{d['label']} {d['conf']:.2f}", (x1, max(y1-6, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, config.COL_YOLOE_HL, 2, cv2.LINE_AA)
    cv2.imwrite(out, disp)
    log(f"\n[recognize_omdet] saved image -> {out}")
    open(log_path, "w").write("\n".join(buf) + "\n")
    print(f"[recognize_omdet] saved log   -> {log_path}")
    if show:
        cv2.imshow("recognize_omdet", disp)
        while True:
            k = cv2.waitKey(50) & 0xFF
            if k in (27, ord('q')): break
            if cv2.getWindowProperty("recognize_omdet", cv2.WND_PROP_VISIBLE) < 1: break
        cv2.destroyAllWindows()
    os._exit(0)

if __name__ == "__main__":
    main()
