import os,sys,time,json,datetime,statistics
os.environ.setdefault("MVD_HOME","integration_harden2"); os.environ.setdefault("MVD_TRANSLATOR","none")
BENCH="/root/groundstation/bench/hebrew-command-bench"; sys.path.insert(0,BENCH)
import bench
from bench import gemma_server
from recognizer import recognize_direct
from recognizer import Recognizer
import cases_commands as C, cases_perception as P
from cases_typing_fresh import FRESH
class W:
    def emergency_halt(self): return 200
    def fly(self,m): return 200
    def manual(self): return 200
    def auto(self): return None
utt=[c[1] for c in FRESH] + [c[1] for c in C.CASES+C.VERBOSE_CASES+C.EMERGENCY_CASES] + [c[1] for c in P.PERC100+P.SLANG20]
def pct(a,q):
    a=sorted(a); return a[min(len(a)-1, int(round(q/100*(len(a)-1))))]
fast=[]; slow=[]
with gemma_server() as gemma:
    pipe=Recognizer(W(), None, gemma)
    for he in utt[:6]:                       # warmup, discarded
        try: pipe.plan(he)
        except Exception: pass
    for he in utt:
        ts=[]
        for _ in range(7):                   # fast path: min of 7 (deterministic; strips scheduler noise)
            t=time.perf_counter(); recognize_direct(he); ts.append((time.perf_counter()-t)*1000)
        fast.append(min(ts))
        kind,payload,flags=recognize_direct(he)
        text=payload if kind=="direct" else he
        t=time.perf_counter()                # slow path: the one Gemma call
        try: pipe.plan(text)
        except Exception: pass
        slow.append((time.perf_counter()-t)*1000)
print(f"n={len(utt)} utterances  (fast = deterministic sieve; slow = one Gemma plan() call)")
print(f"{'pct':>4} | {'fast_ms':>10} | {'slow_ms':>9} | {'diff_ms':>9} | {'slow/fast':>9}")
for q in (50,90,95,99):
    f=pct(fast,q); s=pct(slow,q); print(f"{'p'+str(q):>4} | {f:10.3f} | {s:9.1f} | {s-f:9.1f} | {s/f:8.0f}x")
f=max(fast); s=max(slow); print(f"{'max':>4} | {f:10.3f} | {s:9.1f} | {s-f:9.1f} | {s/f:8.0f}x")
print(f"mean: fast {statistics.mean(fast):.3f} ms | slow {statistics.mean(slow):.1f} ms")
day=datetime.date.today().isoformat()
json.dump({"n":len(utt),"fast_ms":fast,"slow_ms":slow}, open(f"{BENCH}/results/{day}-path-latency.json","w"), indent=1)
print("wrote", f"{BENCH}/results/{day}-path-latency.json")
