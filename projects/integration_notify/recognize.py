#!/usr/bin/env python3
"""Single-shot recognition for integration_notify: an image file -> an annotated image + a
matching <out>_log.txt (args, prompt, VLM output, detections). Mirrors llm_cv_scene/recognize.py,
and adds the person-notify feature (--notify "<attributes>": mark people who match).

Usage:
  python3 recognize.py <image> "<prompt>" [--detect "person,car"] [--notify "<attributes>"] [--mask] [--show] [-o out.jpg]
Examples:
  python3 recognize.py people.jpg "what do you see"
  python3 recognize.py people.jpg --notify "a man in a red shirt" -o out.jpg
"""
import sys, os, time, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SCENE_HL_BACKEND", "vlm")
os.environ.setdefault("SCENE_BG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "yolo26n-seg.pt"))
import config, vlm


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); return
    path = sys.argv[1]
    rest = sys.argv[2:]
    want_mask = "--mask" in rest
    show = "--show" in rest
    out = rest[rest.index("-o") + 1] if "-o" in rest else None
    notify_attrs = rest[rest.index("--notify") + 1] if "--notify" in rest else None
    detect_arg  = rest[rest.index("--detect") + 1] if "--detect" in rest else None
    consumed = {out, notify_attrs, detect_arg}
    prompt = " ".join(a for a in rest if not a.startswith("-") and a not in consumed) \
             or "Describe the scene in one sentence."

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
    log(f"[recognize] backend : Qwen3-VL @ {config.LLAMA_URL}   mask={want_mask}  notify={notify_attrs!r}")

    # ---- VLM scene analysis (description + grounded objects) ----
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
                    import numpy as np
                    m = r[0].masks.data[0].cpu().numpy().astype(bool)
                    if m.shape[:2] != disp.shape[:2]:
                        m = cv2.resize(m.astype("uint8"), (disp.shape[1], disp.shape[0]),
                                       interpolation=cv2.INTER_NEAREST).astype(bool)
                    ov = disp.copy(); ov[m] = config.COL_SAM2_HL
                    cv2.addWeighted(ov, 0.45, disp, 0.55, 0, disp)
            except Exception as e:
                log(f"   sam2: {e}")
        cv2.rectangle(disp, (x1, y1), (x2, y2), config.COL_YOLOE_HL, 2)
        cv2.putText(disp, d["label"], (x1, max(y1 - 6, 14)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, config.COL_YOLOE_HL, 2, cv2.LINE_AA)

    _eyes = None
    if detect_arg or notify_attrs:
        from eyes import Eyes
        _eyes = Eyes()

    # ---- optional: reliable YOLO detection of named classes + SAM2 (e.g. --detect person) ----
    if detect_arg:
        classes = [c.strip().lower() for c in detect_arg.split(",") if c.strip()]
        log(f"\n=== DETECT (YOLO): {classes} ===")
        ydets = [d for d in _eyes.background(img) if str(d.get("label","")).lower() in classes]
        log(f"[recognize] YOLO found {len(ydets)} instance(s) of {classes}")
        for d in ydets:
            x1, y1, x2, y2 = [int(v) for v in d["box"]]
            try:
                m = _eyes.mask_for_box(img, d["box"])
            except Exception as e:
                m = None; log(f"   sam2: {e}")
            if m is not None and m.sum() > 0:
                if m.shape[:2] != disp.shape[:2]:
                    import numpy as np
                    m = cv2.resize(m.astype("uint8"), (disp.shape[1], disp.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
                ov = disp.copy(); ov[m] = config.COL_SAM2_HL
                cv2.addWeighted(ov, 0.45, disp, 0.55, 0, disp)
            cv2.rectangle(disp, (x1, y1), (x2, y2), config.COL_YOLOE_HL, 2)
            cv2.putText(disp, f"{d.get('label')} {float(d.get('conf',0)):.2f}", (x1, max(y1-6,14)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, config.COL_YOLOE_HL, 2, cv2.LINE_AA)

    # ---- optional: person-notify (YOLO persons -> strict VLM attribute match) ----
    if notify_attrs:
        log(f"\n=== NOTIFY: people matching '{notify_attrs}' ===")
        persons = [p for p in _eyes.background(img) if str(p.get("label", "")).lower() == "person"]
        matches = 0
        for p in persons:
            x1, y1, x2, y2 = [int(v) for v in p["box"]]
            crop = img[max(0, y1):y2, max(0, x1):x2]
            if crop.size == 0:
                continue
            yes, raw = vlm.confirm(crop, notify_attrs)
            log(f"  person {p['box']} -> {raw!r} match={yes}")
            col = (60, 60, 255) if yes else (130, 130, 130)
            cv2.rectangle(disp, (x1, y1), (x2, y2), col, 4 if yes else 2)
            if yes:
                matches += 1
                cv2.putText(disp, "MATCH", (x1, max(y1 - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8, (60, 60, 255), 2, cv2.LINE_AA)
        log(f"[recognize] notify: {matches}/{len(persons)} people matched '{notify_attrs}'")

    cv2.imwrite(out, disp)
    log(f"\n[recognize] saved image -> {out}")
    with open(log_path, "w") as f:
        f.write("\n".join(buf) + "\n")
    print(f"[recognize] saved log   -> {log_path}")

    if show:
        cv2.imshow("recognize", disp)
        while True:
            k = cv2.waitKey(50) & 0xFF
            if k in (27, ord('q')) or cv2.getWindowProperty("recognize", cv2.WND_PROP_VISIBLE) < 1:
                break
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
