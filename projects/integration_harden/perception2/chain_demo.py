#!/usr/bin/env python3
"""End-to-end chain demo for perception2: instruction -> concept (VLM) -> presence gate (VLM) ->
SAM3 grounding -> masks. Prints each stage and writes an overlay image. Run from integration_harden:

    python3 perception2/chain_demo.py [image] [instruction]
"""
import os, sys, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import perception2
from perception2 import parse_highlight, extract_concepts, make_vlm_asker, build_engine
from perception2 import vlm_client as vlm

BENCH = "/root/groundstation/tools/bench/sam3-mask-bench"


def run(image, instruction, precision="nf4"):
    frame = cv2.imread(image)
    assert frame is not None, image
    print(f"\n=== CHAIN: {os.path.basename(image)} {frame.shape[1]}x{frame.shape[0]} ===")
    print(f"[1] instruction : {instruction!r}")

    up = vlm.ensure_server(wait=180)
    print(f"[2] VLM server  : {'up' if up else 'DOWN (offline concept fallback)'}")
    ask = make_vlm_asker() if up else None

    phrase = parse_highlight(instruction)
    print(f"[3] parsed phrase: {phrase!r}")

    t = time.time()
    concepts = extract_concepts(phrase, ask=ask)
    print(f"[4] concepts     : {concepts!r}   ({(time.time()-t)*1000:.0f} ms)")

    engine = build_engine(vlm_ask=vlm.ask, precision=precision)

    t = time.time()
    present, box = engine.presence_gate(frame, phrase)
    print(f"[5] presence gate: present={present} vlm_box_px={box}   ({(time.time()-t)*1000:.0f} ms)")

    t = time.time()
    dets, masks, dbg = engine.highlight_step(frame, concepts, vlm_box_px=box, use_sam=True)
    print(f"[6] SAM3 highlight: {len(dets)} dets, {len(masks)} masks   ({(time.time()-t)*1000:.0f} ms)")
    for d in dets:
        print(f"      - {d['label']:10s} {d['conf']:.2f} {d['box']}")

    disp = frame.copy()
    ov = disp.copy()
    for m in masks:
        if m.shape[:2] == disp.shape[:2]:
            ov[m] = (220, 60, 220)
    cv2.addWeighted(ov, 0.45, disp, 0.55, 0, disp)
    for d in dets:
        x1, y1, x2, y2 = d["box"]
        cv2.rectangle(disp, (x1, y1), (x2, y2), (60, 220, 60), 2)
        cv2.putText(disp, f"{d['label']} {d['conf']:.2f}", (x1, max(y1-6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 220, 60), 2)
    out = os.path.join(BENCH, "results", f"chain-{os.path.splitext(os.path.basename(image))[0]}.jpg")
    cv2.imwrite(out, disp)
    print(f"[7] overlay      : {out}")
    return out


if __name__ == "__main__":
    img = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BENCH, "candidates", "street-scene-1.jpg")
    ins = sys.argv[2] if len(sys.argv) > 2 else "highlight all the vehicles"
    run(img, ins)
