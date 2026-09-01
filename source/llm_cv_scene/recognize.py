#!/usr/bin/env python3
"""Single-shot recognition: an image file + a prompt -> a highlighted image + a description,
plus a matching <out>_log.txt containing the args, prompt, VLM output and everything printed.

Usage:
  python3 recognize.py <image> "<prompt>" [--mask] [--show] [-o out.jpg]
"""
import sys, os, time, cv2
import config, vlm


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); return
    path = sys.argv[1]
    rest = sys.argv[2:]
    want_mask = "--mask" in rest
    show = "--show" in rest
    out = rest[rest.index("-o") + 1] if "-o" in rest else None
    prompt = " ".join(a for a in rest if not a.startswith("-") and a != (out or "")) \
             or "Describe the scene and highlight the notable objects."

    buf = []
    def log(s=""):
        print(s); buf.append(str(s))

    img = cv2.imread(path)
    if img is None:
        print("cannot read image:", path); return
    if not vlm.ensure_server():
        print("[recognize] llama-server unavailable; aborting."); return
    h, w = img.shape[:2]
    out = out or (os.path.splitext(path)[0] + "_annotated.jpg")
    log_path = os.path.splitext(out)[0] + "_log.txt"

    log(f"[recognize] {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"[recognize] argv    : {' '.join(sys.argv)}")
    log(f"[recognize] image   : {path}  ({w}x{h})")
    log(f"[recognize] prompt  : {prompt}")
    log(f"[recognize] backend : Qwen3-VL @ {config.LLAMA_URL}   mask={want_mask}")
    log("[recognize] querying VLM...")

    t0 = time.time()
    desc, dets = vlm.analyze(img, prompt)
    log(f"\n=== VLM ANSWER  ({time.time()-t0:.1f}s) ===\n{desc}")
    log(f"\n=== OBJECTS ({len(dets)}) ===")

    disp = img.copy()
    sam = None
    if want_mask and dets:
        try:
            from ultralytics import SAM
            sam = SAM(config.SAM2_WEIGHTS)
        except Exception as e:
            log(f"SAM2 load failed: {e}")
    for d in dets:
        x1, y1, x2, y2 = d["box"]
        log(f"  {d['label']:24s} {d['box']}")
        if sam is not None:
            try:
                r = sam(img, bboxes=[x1, y1, x2, y2], verbose=False, device=config.resolve_device())
                if r and r[0].masks is not None and len(r[0].masks.data) > 0:
                    m = r[0].masks.data[0].cpu().numpy().astype(bool)
                    if m.shape[:2] != disp.shape[:2]:
                        import numpy as np
                        m = cv2.resize(m.astype("uint8"), (disp.shape[1], disp.shape[0]),
                                       interpolation=cv2.INTER_NEAREST).astype(bool)
                    ov = disp.copy(); ov[m] = config.COL_SAM2_HL
                    cv2.addWeighted(ov, 0.45, disp, 0.55, 0, disp)
            except Exception as e:
                log(f"   sam2: {e}")
        cv2.rectangle(disp, (x1, y1), (x2, y2), config.COL_YOLOE_HL, 2)
        cv2.putText(disp, d["label"], (x1, max(y1 - 6, 14)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, config.COL_YOLOE_HL, 2, cv2.LINE_AA)

    cv2.imwrite(out, disp)
    log(f"\n[recognize] saved image -> {out}")
    with open(log_path, "w") as f:
        f.write("\n".join(buf) + "\n")
    print(f"[recognize] saved log   -> {log_path}")

    if show:
        cv2.imshow("recognize", disp)
        print("[recognize] press Esc or q to close the window")
        while True:
            k = cv2.waitKey(50) & 0xFF
            if k in (27, ord('q')): break
            if cv2.getWindowProperty("recognize", cv2.WND_PROP_VISIBLE) < 1: break
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
