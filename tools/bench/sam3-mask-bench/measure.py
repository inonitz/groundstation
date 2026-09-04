#!/usr/bin/env python3
"""Precise SAM3 latency+VRAM benchmark for one config. Usage: measure_bench.py {bf16|nf4}."""
import sys, os, time, json, glob, subprocess
import numpy as np, torch
from PIL import Image
MD="/root/models/vision/sam3-official"
FRAMES=sorted(glob.glob("/root/models/vision/sam3-desk-frames/*.jpg"))
N_WARM=5; N=50
def pid_mib():
    try:
        out=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid,used_memory","--format=csv,noheader,nounits"],text=True)
        for ln in out.strip().splitlines():
            p,m=[x.strip() for x in ln.split(",")]
            if int(p)==os.getpid(): return int(m)
    except Exception: pass
    return None
def load(cfg):
    from transformers import Sam3Model, Sam3Processor, BitsAndBytesConfig
    if cfg=="bf16":
        m=Sam3Model.from_pretrained(MD,dtype=torch.bfloat16).to("cuda")
    else:
        q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,bnb_4bit_use_double_quant=True)
        m=Sam3Model.from_pretrained(MD,quantization_config=q,dtype=torch.bfloat16)
    return m.eval(), Sam3Processor.from_pretrained(MD)
def one(m,p,img,text):
    inp=p(images=img,text=text,return_tensors="pt").to("cuda")
    inp["pixel_values"]=inp["pixel_values"].to(torch.bfloat16)
    with torch.no_grad(): out=m(**inp)
    r=p.post_process_instance_segmentation(out,threshold=0.5,mask_threshold=0.5,target_sizes=inp.get("original_sizes").tolist())[0]
    return len(r["scores"]), (round(float(r["scores"].float().max()),3) if len(r["scores"]) else 0.0)
def main():
    cfg=sys.argv[1]
    torch.cuda.reset_peak_memory_stats()
    t=time.time(); m,p=load(cfg); load_s=time.time()-t
    weights=round(torch.cuda.memory_allocated()/2**20)
    imgs=[Image.open(f).convert("RGB") for f in FRAMES[:N]]
    torch.cuda.synchronize(); t=time.time(); one(m,p,imgs[0],"chair"); torch.cuda.synchronize(); cold=(time.time()-t)*1000
    for i in range(N_WARM): one(m,p,imgs[i%len(imgs)],"chair")
    torch.cuda.synchronize(); peak=round(torch.cuda.max_memory_allocated()/2**20); proc=pid_mib()
    lat=[]
    for i in range(N):
        torch.cuda.synchronize(); t=time.time(); one(m,p,imgs[i%len(imgs)],"chair"); torch.cuda.synchronize()
        lat.append((time.time()-t)*1000)
    a=np.array(lat)
    pct={k:round(float(np.percentile(a,q)),1) for k,q in [("p25",25),("p50",50),("p75",75),("p95",95),("p99",99),("max",100)]}
    pct["mean"]=round(float(a.mean()),1); pct["std"]=round(float(a.std()),1)
    print(json.dumps({"cfg":cfg,"N":N,"weights_mib":weights,"peak_mib":peak,"proc_mib":proc,
        "load_s":round(load_s,1),"cold_ms":round(cold,1),"latency_ms":pct}))
if __name__=="__main__": main()
