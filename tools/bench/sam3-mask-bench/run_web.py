#!/usr/bin/env python3
"""Run SAM3 bf16 over the 8 owner-approved web candidates with concept + attribute prompts.
Renders overlays to overlays/web_*, writes results/2026-09-03-web.json."""
import json, os, time, colorsys
import numpy as np, torch, cv2
from PIL import Image
from transformers import Sam3Model, Sam3Processor
BENCH=os.path.dirname(os.path.abspath(__file__)); D=f"{BENCH}/candidates"; OVL=f"{BENCH}/overlays"
MODEL="/root/models/vision/sam3-official"
JOBS=[
 ("market-0.jpg",   ["person","person carrying a bag","person wearing a hat"]),
 ("market-1.jpg",   ["person","person carrying a bag","person wearing a hat"]),
 ("market-2.jpg",   ["person","person carrying a bag","person wearing a hat"]),
 ("street-crowd-0.jpg",["person","person wearing a backpack","bicycle"]),
 ("street-crowd-1.jpg",["person","person wearing a backpack","bicycle"]),
 ("street-scene-0.jpg",["car","van","window"]),
 ("street-scene-1.jpg",["car","van","window"]),
 ("street-scene-2.jpg",["car","van","window"]),
]
def main():
    M=Sam3Model.from_pretrained(MODEL,dtype=torch.bfloat16).to("cuda").eval()
    P=Sam3Processor.from_pretrained(MODEL)
    def det(im,txt):
        inp=P(images=im,text=txt,return_tensors="pt").to("cuda");inp["pixel_values"]=inp["pixel_values"].to(torch.bfloat16)
        with torch.no_grad(): o=M(**inp)
        r=P.post_process_instance_segmentation(o,threshold=0.5,mask_threshold=0.5,target_sizes=inp.get("original_sizes").tolist())[0]
        n=len(r["scores"])
        m=r["masks"].float().cpu().numpy() if n else np.zeros((0,)); b=r["boxes"].float().cpu().numpy() if n else np.zeros((0,4)); s=r["scores"].float().cpu().numpy() if n else np.zeros((0,))
        return n,m,b,s
    def draw(cv,m,b,s,label):
        out=cv.copy()
        for i in range(len(s)):
            hue=(i*0.13)%1.0; col=tuple(int(x*255) for x in colorsys.hsv_to_rgb(hue,0.9,1.0))[::-1]
            mk=m[i]; mk=mk[0] if mk.ndim==3 else mk; mk=mk.astype(bool)
            if mk.shape[:2]==out.shape[:2]: out[mk]=(0.5*out[mk]+0.5*np.array(col)).astype(np.uint8)
            x1,y1,x2,y2=[int(v) for v in b[i]]; cv2.rectangle(out,(x1,y1),(x2,y2),col,2)
        cv2.putText(out,f"'{label}': {len(s)}",(10,28),cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,255,0),2)
        return out
    res=[]
    for fn,prompts in JOBS:
        im=Image.open(f"{D}/{fn}").convert("RGB"); cv=cv2.cvtColor(np.array(im),cv2.COLOR_RGB2BGR)
        entry={"image":fn,"prompts":[]}
        for pr in prompts:
            n,m,b,s=det(im,pr); slug=pr.replace(" ","_")
            cv2.imwrite(f"{OVL}/web_{fn[:-4]}__{slug}.jpg",draw(cv,m,b,s,pr))
            top=round(float(s.max()),3) if n else 0.0
            entry["prompts"].append({"prompt":pr,"n":int(n),"top":top})
            print(f"{fn:20s} '{pr:24s}' n={n:2d} top={top}")
        res.append(entry)
    json.dump({"date":"2026-09-03","model":"facebook/sam3 bf16","images":res},open(f"{BENCH}/results/2026-09-03-web.json","w"),indent=2)
    print("done")
if __name__=="__main__": main()
