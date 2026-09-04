#!/usr/bin/env python3
"""In-depth: SAM3 vs OmDet (detection) and SAM3 vs SAM2.1 (mask IoU, same boxes), all 17 images.
Writes results/2026-09-03-indepth.json + prints tables. Base SAM3 = the correct image model."""
import sys, os, json, time
import numpy as np, torch, cv2
from PIL import Image
sys.path.insert(0, "/root/groundstation/projects/integration_harden")
os.environ.setdefault("SCENE_SAM2", "/root/models/vision/sam2.1_b.pt")
CAND="/root/groundstation/tools/bench/sam3-mask-bench/candidates"
SAM3_DIR="/root/models/vision/sam3-official"
# image -> primary concept
JOBS=[("img0.png","window"),("img1.png","window"),("img2.png","person"),("img3.png","person"),
("img4.png","person"),("img5.jpeg","person"),("img6.jpeg","person"),("img7.jpeg","person"),
("img10_highlight_windows_from_event_perform_ocr.jpeg","car"),
("market-0.jpg","person"),("market-1.jpg","person"),("market-2.jpg","person"),
("street-crowd-0.jpg","person"),("street-crowd-1.jpg","person"),
("street-scene-0.jpg","car"),("street-scene-1.jpg","car"),("street-scene-2.jpg","car")]

def iou(a,b):
    if a is None or b is None: return 0.0
    a=a.astype(bool); b=b.astype(bool)
    if a.shape!=b.shape: b=cv2.resize(b.astype(np.uint8),(a.shape[1],a.shape[0]),interpolation=cv2.INTER_NEAREST).astype(bool)
    u=(a|b).sum(); return float((a&b).sum()/u) if u else 0.0

def main():
    from transformers import Sam3Model, Sam3Processor
    from perception.detectors import OmDet
    from ultralytics import SAM
    dev="cuda"
    s3=Sam3Model.from_pretrained(SAM3_DIR, dtype=torch.bfloat16).to(dev).eval()
    s3p=Sam3Processor.from_pretrained(SAM3_DIR)
    omdet=OmDet(device=dev)
    sam2=SAM("/root/models/vision/sam2.1_b.pt")
    def s3_detect(img):
        inp=s3p(images=img, text=concept, return_tensors="pt").to(dev); inp["pixel_values"]=inp["pixel_values"].to(torch.bfloat16)
        with torch.no_grad(): out=s3(**inp)
        r=s3p.post_process_instance_segmentation(out, threshold=0.5, mask_threshold=0.5, target_sizes=inp.get("original_sizes").tolist())[0]
        n=len(r["scores"])
        m=r["masks"].float().cpu().numpy() if n else np.zeros((0,)); b=r["boxes"].float().cpu().numpy() if n else np.zeros((0,4)); s=r["scores"].float().cpu().numpy() if n else np.zeros((0,))
        return m,b,s
    rows=[]
    for fn,concept in JOBS:
        globals()['concept']=concept
        img=Image.open(f"{CAND}/{fn}").convert("RGB"); bgr=cv2.cvtColor(np.array(img),cv2.COLOR_RGB2BGR)
        m3,b3,s3s=s3_detect(img)
        od=omdet.detect(bgr, concept, conf=0.30, topk=50)
        ious=[]
        for i in range(min(len(s3s),12)):  # cap masks compared for speed
            x1,y1,x2,y2=[int(v) for v in b3[i]]
            try:
                r=sam2(bgr, bboxes=[x1,y1,x2,y2], verbose=False, device="0")
                m2=r[0].masks.data[0].cpu().numpy().astype(bool) if (r and r[0].masks is not None and len(r[0].masks.data)) else None
            except Exception: m2=None
            mm=m3[i]; mm=mm[0] if mm.ndim==3 else mm
            ious.append(iou(mm.astype(bool), m2))
        row={"image":fn,"concept":concept,
             "sam3_n":int(len(s3s)),"sam3_top":round(float(s3s.max()),3) if len(s3s) else 0.0,
             "omdet_n":int(len(od)),"omdet_top":round(od[0]["conf"],3) if od else 0.0,
             "mask_iou_mean":round(float(np.mean(ious)),3) if ious else 0.0}
        rows.append(row)
        print("%-52s %-7s SAM3 n=%2d(%.2f)  OmDet n=%2d(%.2f)  mask-IoU=%.3f"%(fn,concept,row["sam3_n"],row["sam3_top"],row["omdet_n"],row["omdet_top"],row["mask_iou_mean"]))
    json.dump({"date":"2026-09-03","rows":rows}, open("/root/groundstation/tools/bench/sam3-mask-bench/results/2026-09-03-indepth.json","w"), indent=2)
    import statistics as st
    print("=== SAM3 total dets: %d | OmDet total dets: %d | mean mask-IoU: %.3f ==="%(
        sum(r["sam3_n"] for r in rows), sum(r["omdet_n"] for r in rows),
        st.mean([r["mask_iou_mean"] for r in rows if r["mask_iou_mean"]>0] or [0])))
if __name__=="__main__": main()
