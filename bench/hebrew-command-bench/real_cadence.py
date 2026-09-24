# Real-cadence GPU contention: SAM3 held at 1 forward/sec (the live cadence) while
# Gemma plan() calls fire per command. Measures the LIVE per-command cost, not the
# saturation bound in contention.py. See docs/research-2026-09-18-command-typing-fast-vs-gemma.md.
import os,sys,time,subprocess,threading,json,datetime
os.environ.setdefault("MVD_HOME","integration_harden2"); os.environ.setdefault("MVD_TRANSLATOR","none")
HARDEN="/root/groundstation/projects/integration_harden2"; sys.path.insert(0,HARDEN)
BENCH="/root/groundstation/bench/hebrew-command-bench"; sys.path.insert(0,BENCH)
import numpy as np, bench
from bench import gemma_server
from recognizer import Recognizer
from perception2.sam3_backend import Sam3Backend

CMD="טוס קדימה חמישה מטרים"     # deployed-style movement command
GAP=1.5                          # s between Gemma calls in the loaded phase
N_LOAD=40                        # Gemma calls per repeat in loaded phase
N_ISO=20                         # isolated warm samples
REPEATS=3

def pct(a,q):
    a=sorted(a); 
    return a[min(len(a)-1,int(round(q/100*(len(a)-1))))] if a else float("nan")
def stats(a): return {"n":len(a),"p50":pct(a,50),"p95":pct(a,95),"p99":pct(a,99),"mean":(sum(a)/len(a) if a else float("nan"))}
def nv():
    try:
        o=subprocess.check_output(["nvidia-smi","--query-gpu=name,utilization.gpu,memory.used",
            "--format=csv,noheader,nounits"],text=True).strip().splitlines()[0].split(",")
        return o[0].strip(), float(o[1]), float(o[2])
    except Exception: return None,None,None

class Sampler(threading.Thread):
    def __init__(s): super().__init__(daemon=True); s.on=True; s.u=[]
    def run(s):
        while s.on:
            _,u,_=nv()
            if u is not None: s.u.append(u)
            time.sleep(0.2)
    def stop(s): s.on=False; s.join()

class W:
    def emergency_halt(self): return 200
    def fly(self,m): return 200
    def manual(self): return 200
    def auto(self): return None

# SAM3 background at exactly 1 forward/sec, recording each forward interval.
class Sam3Cadence(threading.Thread):
    def __init__(s,sam3,frame,period=1.0):
        super().__init__(daemon=True); s.sam3=sam3; s.frame=frame; s.period=period
        s.on=True; s.intervals=[]; s.lat=[]; s.lock=threading.Lock()
    def run(s):
        while s.on:
            rec=[time.perf_counter(),None]     # mark the forward in-flight at its START
            with s.lock: s.intervals.append(rec)
            s.sam3.detect(s.frame,"person",0.3)
            rec[1]=time.perf_counter()          # close it at END
            with s.lock: s.lat.append((rec[1]-rec[0])*1000.0)
            dt=rec[1]-rec[0]
            if dt<s.period: time.sleep(s.period-dt)
    def stop(s): s.on=False; s.join(timeout=5)
    def snapshot(s):
        with s.lock: return [list(r) for r in s.intervals], list(s.lat)

def overlaps(g0,g1,ivals):
    # a forward with end=None is still running -> it overlaps if it started before g1
    for (s0,s1) in ivals:
        if s0< g1 and (s1 is None or s1> g0): return True
    return False

name,_,_=nv(); print("GPU:",name,flush=True)
print("loading SAM3...",flush=True)
sam3=Sam3Backend()
frame=(np.random.rand(720,1280,3)*255).astype(np.uint8)
sam3.detect(frame,"person",0.3)  # warmup

res={"gpu":name,"cmd":CMD,"gap_s":GAP,"n_load":N_LOAD,"repeats":REPEATS,
     "sam3_iso":[], "gem_iso":[], "gem_overlap":[], "gem_free":[], "sam3_underload":[],
     "overlap_rate":[], "util_loaded":[]}

with gemma_server() as gemma:
    pipe=Recognizer(W(), None, gemma); pipe.plan(CMD)  # warmup

    def t_gem_once():
        t=time.perf_counter(); pipe.plan(CMD); return (time.perf_counter()-t)*1000.0
    def t_sam3_once():
        t=time.perf_counter(); sam3.detect(frame,"person",0.3); return (time.perf_counter()-t)*1000.0

    for r in range(REPEATS):
        print(f"repeat {r+1}/{REPEATS}",flush=True)
        # isolated baselines
        res["sam3_iso"] += [t_sam3_once() for _ in range(N_ISO)]
        res["gem_iso"]  += [t_gem_once()  for _ in range(N_ISO)]
        # loaded phase: SAM3 at 1/sec background, Gemma per command
        cad=Sam3Cadence(sam3,frame,1.0); cad.start()
        smp=Sampler(); smp.start(); time.sleep(1.5)  # let cadence settle
        ov=0
        for i in range(N_LOAD):
            g0=time.perf_counter(); pipe.plan(CMD); g1=time.perf_counter()
            ivals,_=cad.snapshot()
            hit=overlaps(g0,g1,ivals)
            lat=(g1-g0)*1000.0
            (res["gem_overlap"] if hit else res["gem_free"]).append(lat)
            ov+= 1 if hit else 0
            time.sleep(GAP)
        smp.stop(); cad.stop()
        _,sam3_lat=cad.snapshot()
        res["sam3_underload"] += sam3_lat
        res["overlap_rate"].append(ov/N_LOAD)
        res["util_loaded"] += smp.u

    res["summary"]={
        "sam3_iso":stats(res["sam3_iso"]),
        "gem_iso":stats(res["gem_iso"]),
        "gem_free":stats(res["gem_free"]),        # command did NOT overlap a SAM3 forward
        "gem_overlap":stats(res["gem_overlap"]),  # command overlapped a SAM3 forward
        "gem_all_loaded":stats(res["gem_free"]+res["gem_overlap"]),
        "sam3_underload":stats(res["sam3_underload"]),
        "overlap_rate":sum(res["overlap_rate"])/len(res["overlap_rate"]),
        "util_loaded_p50":pct(res["util_loaded"],50),
    }

out="/root/groundstation/bench/hebrew-command-bench/results/2026-09-18-real-cadence-contention.json"
with open(out,"w") as f: json.dump(res,f,indent=1,ensure_ascii=False)
print("WROTE",out,flush=True)
s=res["summary"]
def line(k,d): print(f"  {k:16s} n={d['n']:3d}  p50={d['p50']:7.1f}  p95={d['p95']:7.1f}  p99={d['p99']:7.1f}")
print("=== REAL-CADENCE CONTENTION (ms) ===",flush=True)
line("SAM3 isolated",s["sam3_iso"]); line("SAM3 under load",s["sam3_underload"])
line("Gemma isolated",s["gem_iso"]); line("Gemma no-overlap",s["gem_free"])
line("Gemma overlap",s["gem_overlap"]); line("Gemma all-loaded",s["gem_all_loaded"])
print(f"  overlap_rate = {s['overlap_rate']*100:.0f}%   GPU util p50 loaded = {s['util_loaded_p50']:.0f}%",flush=True)

# graph
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(11,4.2))
    def cdf(ax,data,lab):
        d=sorted(data); 
        if not d: return
        y=[(i+1)/len(d) for i in range(len(d))]; ax.plot(d,y,label=lab,lw=1.8)
    cdf(ax1,res["gem_iso"],"Gemma isolated")
    cdf(ax1,res["gem_free"],"Gemma no-overlap")
    cdf(ax1,res["gem_overlap"],"Gemma overlap SAM3")
    ax1.set_title("Gemma plan() latency (real cadence)"); ax1.set_xlabel("ms"); ax1.set_ylabel("CDF"); ax1.legend(); ax1.grid(alpha=0.3)
    cats=["SAM3\niso","SAM3\nunder\nload","Gemma\niso","Gemma\nno-ov","Gemma\noverlap"]
    vals=[s["sam3_iso"]["p50"],s["sam3_underload"]["p50"],s["gem_iso"]["p50"],s["gem_free"]["p50"],s["gem_overlap"]["p50"]]
    p99=[s["sam3_iso"]["p99"],s["sam3_underload"]["p99"],s["gem_iso"]["p99"],s["gem_free"]["p99"],s["gem_overlap"]["p99"]]
    x=range(len(cats)); ax2.bar(x,vals,label="p50"); ax2.bar(x,[a-b for a,b in zip(p99,vals)],bottom=vals,alpha=0.4,label="p50->p99")
    ax2.set_xticks(list(x)); ax2.set_xticklabels(cats,fontsize=8); ax2.set_ylabel("ms"); ax2.set_title(f"p50/p99  (overlap rate {s['overlap_rate']*100:.0f}%)"); ax2.legend(); ax2.grid(alpha=0.3,axis="y")
    png="/root/groundstation/bench/hebrew-command-bench/results/2026-09-18-real-cadence-contention.png"
    fig.tight_layout(); fig.savefig(png,dpi=110); print("WROTE",png,flush=True)
except Exception as e:
    print("graph skipped:",e,flush=True)
print("DONE",flush=True)
