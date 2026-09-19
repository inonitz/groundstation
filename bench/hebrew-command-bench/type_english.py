import os,sys,time,json,datetime
os.environ.setdefault("MVD_HOME","integration_harden2"); os.environ.setdefault("MVD_TRANSLATOR","none")
BENCH="/root/groundstation/bench/hebrew-command-bench"; sys.path.insert(0,BENCH)
import bench
from bench import LlamaServer, MODELS, GEMMA4_EXTRA, PORT
from pipeline import Pipeline
import cases_commands as C, cases_perception as P
from cases_typing_fresh import FRESH
from cases_typing_fresh_en import EN
class W:
    def halt(self): return 200
    def fly_mission(self,m): return 200
def gt_exp(e): return "not_move" if e==[] else "move"
def gem_type(k):
    if k=="mission": return "move"
    if k in ("highlight","count","describe","perceive","perception","see","reject"): return "not_move"
    return "other"
# build (label, english) sets
fresh=[(gt, EN[n]) for n,he,gt in FRESH]
exist=[(gt_exp(c[3]), c[2]) for c in C.CASES+C.VERBOSE_CASES] + [("not_move", c[2]) for c in P.PERC100+P.SLANG20]
def run(pipe, items):
    rows=[]
    for gt,en in items:
        obj=pipe._plan2(en) or {}
        rows.append((gt, gem_type(obj.get("kind")), obj.get("kind"), en))
    return rows
def score(rows, tag):
    ok=sum(1 for gt,g,_,_ in rows if g==gt)
    ff=sum(1 for gt,g,_,_ in rows if g=="move" and gt=="not_move")
    miss=sum(1 for gt,g,_,_ in rows if g=="not_move" and gt=="move")
    print(f"[{tag}] n={len(rows)}  Gemma-on-ENGLISH correct {ok}/{len(rows)} ({100*ok//len(rows)}%)  false-fly {ff}  missed {miss}")
    return {"n":len(rows),"ok":ok,"ff":ff,"miss":miss,"rows":rows}
with LlamaServer(MODELS["gemma4"], extra=GEMMA4_EXTRA):
    pipe=Pipeline(W(), qwen_port=PORT)
    for _,en in fresh[:6]: pipe._plan2(en)   # warmup
    t=time.time()
    fr=run(pipe, fresh); ex=run(pipe, exist)
print(f"(wall {time.time()-t:.0f}s)")
Rf=score(fr,"FRESH-200 english"); Re=score(ex,"EXISTING english")
print("compare: FRESH Hebrew was 174/200 (87%); EXISTING Hebrew (dev) was ~461/476 (97%)")
day=datetime.date.today().isoformat()
json.dump({"fresh":Rf,"existing":Re}, open(f"{BENCH}/results/{day}-type-compare-ENGLISH.json","w"), ensure_ascii=False, indent=1)
print("wrote", f"{BENCH}/results/{day}-type-compare-ENGLISH.json")
