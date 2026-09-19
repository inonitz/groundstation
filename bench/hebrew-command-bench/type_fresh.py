import os,sys,time,json,datetime
os.environ.setdefault("MVD_HOME","integration_harden2"); os.environ.setdefault("MVD_TRANSLATOR","none")
BENCH="/root/groundstation/bench/hebrew-command-bench"; sys.path.insert(0,BENCH)
import bench
from bench import LlamaServer, MODELS, GEMMA4_EXTRA, PORT
from recognizer import recognize_direct
from pipeline import Pipeline
from cases_typing_fresh import FRESH
class W:
    def halt(self): return 200
    def fly_mission(self,m): return 200
def det_type(k): return {"mission":"move","emergency":"emergency","reject":"not_move","direct":"defer"}.get(k,k)
def gem_type(k):
    if k=="mission": return "move"
    if k in ("highlight","count","describe","perceive","perception","see","reject"): return "not_move"
    return "other"
rows=[]; t0=time.time()
with LlamaServer(MODELS["gemma4"], extra=GEMMA4_EXTRA):
    pipe=Pipeline(W(), qwen_port=PORT)
    for name,he,gt in FRESH:
        kind,payload,flags=recognize_direct(he)
        text=payload if kind=="direct" else he
        obj=pipe._plan2(text) or {}
        rows.append({"name":name,"he":he,"gt":gt,"det_kind":kind,"det":det_type(kind),
                     "gemma_kind":obj.get("kind"),"gemma":gem_type(obj.get("kind"))})
gtm=[r for r in rows if r["gt"]=="move"]; gtn=[r for r in rows if r["gt"]=="not_move"]
dd=[r for r in rows if r["det"]!="defer"]; dok=[r for r in dd if r["det"]==r["gt"]]
dff=[r for r in rows if r["det"]=="move" and r["gt"]=="not_move"]; drec=[r for r in gtm if r["det"]=="move"]
gok=[r for r in rows if r["gemma"]==r["gt"]]; gff=[r for r in rows if r["gemma"]=="move" and r["gt"]=="not_move"]
gmiss=[r for r in rows if r["gemma"]=="not_move" and r["gt"]=="move"]
L=[f"FRESH held-out: {len(rows)} cases (move={len(gtm)}, not_move={len(gtn)}); wall {time.time()-t0:.0f}s",
   "--- DETERMINISTIC bypass ---",
   f"  decides {len(dd)}/{len(rows)} ({100*len(dd)//len(rows)}%); correct on decided {len(dok)}/{len(dd)}",
   f"  movement caught as mission: {len(drec)}/{len(gtm)}; FALSE-FLY (question->mission): {len(dff)}",
   "--- GEMMA planner ---",
   f"  correct {len(gok)}/{len(rows)} ({100*len(gok)//len(rows)}%); FALSE-FLY (not_move->move): {len(gff)}; MISSED (move->not_move): {len(gmiss)}"]
print("\n".join(L))
day=datetime.date.today().isoformat()
json.dump({"rows":rows}, open(f"{BENCH}/results/{day}-type-compare-FRESH200.json","w"), ensure_ascii=False, indent=1)
print("wrote", f"{BENCH}/results/{day}-type-compare-FRESH200.json")
