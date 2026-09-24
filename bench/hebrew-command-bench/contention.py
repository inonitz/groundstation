import os,sys,time,subprocess,threading,json,datetime
os.environ.setdefault("MVD_HOME","integration_harden2"); os.environ.setdefault("MVD_TRANSLATOR","none")
HARDEN="/root/groundstation/projects/integration_harden2"; sys.path.insert(0,HARDEN)
BENCH="/root/groundstation/bench/hebrew-command-bench"; sys.path.insert(0,BENCH)
import numpy as np, bench
from bench import gemma_server
from recognizer import Recognizer
from perception2.sam3_backend import Sam3Backend
def pct(a,q): a=sorted(a); return a[min(len(a)-1,int(round(q/100*(len(a)-1))))]
def nv():
    try:
        o=subprocess.check_output(["nvidia-smi","--query-gpu=name,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits"],text=True).strip().splitlines()[0].split(",")
        return o[0].strip(), float(o[1]), float(o[2])
    except Exception: return None,None,None
class Sampler(threading.Thread):
    def __init__(s): super().__init__(daemon=True); s.on=True; s.u=[]; s.m=[]
    def run(s):
        while s.on:
            n,u,m=nv()
            if u is not None: s.u.append(u); s.m.append(m)
            time.sleep(0.2)
    def stop(s): s.on=False; s.join()
class W:
    def emergency_halt(self): return 200
    def fly(self,m): return 200
    def manual(self): return 200
    def auto(self): return None
name,_,_=nv(); print("GPU:",name,flush=True)
print("loading SAM3 (this can take a bit)...",flush=True)
sam3=Sam3Backend()
frame=(np.random.rand(720,1280,3)*255).astype(np.uint8)
sam3.detect(frame,"person",0.3)   # warmup
def t_sam3(n):
    o=[]
    for _ in range(n):
        t=time.perf_counter(); sam3.detect(frame,"person",0.3); o.append((time.perf_counter()-t)*1000)
    return o
res={"gpu":name}
with gemma_server() as gemma:
    pipe=Recognizer(W(), None, gemma); pipe.plan("טוס קדימה")   # warmup
    def t_gem(n):
        o=[]
        for _ in range(n):
            t=time.perf_counter(); pipe.plan("טוס קדימה חמישה מטרים"); o.append((time.perf_counter()-t)*1000)
        return o
    # --- SAM3 isolated ---
    s=Sampler(); s.start(); res["sam3_iso"]=t_sam3(30); res["u_sam3_iso"]=s.u; s.stop()
    # --- Gemma isolated ---
    s=Sampler(); s.start(); res["gem_iso"]=t_gem(20); res["u_gem_iso"]=s.u; s.stop()
    # --- SAM3 under continuous Gemma load ---
    stop=threading.Event(); gc=[0]
    def gload():
        while not stop.is_set():
            try: pipe.plan("טוס קדימה חמישה מטרים"); gc[0]+=1
            except Exception: pass
    gt=threading.Thread(target=gload,daemon=True); gt.start(); time.sleep(2)
    s=Sampler(); s.start(); res["sam3_con"]=t_sam3(30); res["u_sam3_con"]=s.u; s.stop()
    stop.set(); gt.join(timeout=5); res["gem_calls_during"]=gc[0]
    # --- Gemma under continuous SAM3 load ---
    stop2=threading.Event(); sc=[0]
    def sload():
        while not stop2.is_set():
            sam3.detect(frame,"person",0.3); sc[0]+=1
    st=threading.Thread(target=sload,daemon=True); st.start(); time.sleep(2)
    s=Sampler(); s.start(); res["gem_con"]=t_gem(20); res["u_gem_con"]=s.u; s.stop()
    stop2.set(); st.join(timeout=5)
def L(tag,iso,con):
    return f"{tag:10s} isolated p50 {pct(iso,50):7.0f}ms p95 {pct(iso,95):7.0f}ms  ->  contended p50 {pct(con,50):7.0f}ms p95 {pct(con,95):7.0f}ms  (x{pct(con,50)/pct(iso,50):.2f} at p50)"
print("GPU:",res["gpu"])
print(L("SAM3", res["sam3_iso"], res["sam3_con"]),"  <- vision under Gemma routing load")
print(L("Gemma", res["gem_iso"], res["gem_con"]),"  <- routing under vision load")
def gu(tag,u): print(f"  {tag:22s} util p50 {pct(u,50):.0f}% max {max(u):.0f}%" if u else f"  {tag}: no gpu samples")
gu("SAM3 isolated",res["u_sam3_iso"]); gu("SAM3 under Gemma",res["u_sam3_con"])
day=datetime.date.today().isoformat()
json.dump(res, open(f"{BENCH}/results/{day}-gpu-contention.json","w"), indent=1)
print("wrote", f"{BENCH}/results/{day}-gpu-contention.json")
