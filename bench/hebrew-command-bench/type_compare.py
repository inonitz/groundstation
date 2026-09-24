import os, sys, time, json, argparse, datetime
os.environ.setdefault("MVD_HOME", "integration_harden2"); os.environ.setdefault("MVD_TRANSLATOR", "none")
BENCH="/root/groundstation/bench/hebrew-command-bench"; sys.path.insert(0, BENCH)
import bench
from bench import gemma_server
import cases_commands as C, cases_perception as P
from recognizer import recognize_direct
from recognizer import Recognizer

class W:
    def emergency_halt(self): return 200
    def fly(self, m): return 200
    def manual(self): return 200
    def auto(self): return None

def gt_type(expected):            # command GT: a mission expected (list or open None) = move; [] = not_move
    return "not_move" if expected == [] else "move"
def det_type(kind):
    return {"mission":"move","emergency":"emergency","reject":"not_move","direct":"defer"}.get(kind, kind)
def gemma_type(k):
    if k == "mission": return "move"
    if k in ("highlight","count","describe","perceive","perception","see","reject"): return "not_move"
    return "other"

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--smoke",action="store_true"); ap.add_argument("--tag",default="type-compare"); a=ap.parse_args()
    cut = 5 if a.smoke else None
    cases=[(c[0],c[1],gt_type(c[3])) for c in C.CASES[:cut]+C.VERBOSE_CASES[:cut]]
    cases+=[(c[0],c[1],"not_move") for c in P.PERC100[:cut]+P.SLANG20[:cut]]
    emerg=[(c[0],c[1]) for c in C.EMERGENCY_CASES[:cut]]
    rows=[]; t0=time.time()
    with gemma_server() as gemma:
        pipe=Recognizer(W(), None, gemma)
        for name, he, gt in cases:
            kind, payload, flags = recognize_direct(he)
            text = payload if kind=="direct" else he
            obj = pipe.plan(text) or {}
            rows.append({"name":name,"he":he,"gt":gt,"det_kind":kind,"det":det_type(kind),
                         "gemma_kind":obj.get("kind"),"gemma":gemma_type(obj.get("kind"))})
        for name, he in emerg:
            kind,_,_ = recognize_direct(he)
            rows.append({"name":name,"he":he,"gt":"emergency","det_kind":kind,"det":det_type(kind),"gemma_kind":None,"gemma":None})
    mv=[r for r in rows if r["gt"] in ("move","not_move")]
    gtm=[r for r in mv if r["gt"]=="move"]; gtn=[r for r in mv if r["gt"]=="not_move"]
    d_dec=[r for r in mv if r["det"]!="defer"]; d_ok=[r for r in d_dec if r["det"]==r["gt"]]
    d_ff=[r for r in mv if r["det"]=="move" and r["gt"]=="not_move"]
    d_rec=[r for r in gtm if r["det"]=="move"]
    g_ok=[r for r in mv if r["gemma"]==r["gt"]]; g_ff=[r for r in mv if r["gemma"]=="move" and r["gt"]=="not_move"]
    g_miss=[r for r in mv if r["gemma"]=="not_move" and r["gt"]=="move"]
    em=[r for r in rows if r["gt"]=="emergency"]; em_ok=[r for r in em if r["det"]=="emergency"]
    L=[f"typed cases: {len(mv)} (move={len(gtm)}, not_move={len(gtn)}); emergency={len(em)}; wall {time.time()-t0:.0f}s",
       "--- DETERMINISTIC bypass ---",
       f"  decides {len(d_dec)}/{len(mv)} (defers the rest to Gemma); correct on decided {len(d_ok)}/{len(d_dec)}",
       f"  movement caught as mission: {len(d_rec)}/{len(gtm)}; FALSE-FLY (question->mission): {len(d_ff)}",
       "--- GEMMA planner ---",
       f"  correct {len(g_ok)}/{len(mv)}; FALSE-FLY (not_move->move): {len(g_ff)}; MISSED (move->not_move): {len(g_miss)}",
       "--- EMERGENCY (stage 0) ---", f"  caught {len(em_ok)}/{len(em)}"]
    print("\n".join(L))
    day=datetime.date.today().isoformat()
    out=f"{BENCH}/results/{day}-{a.tag}{'-smoke' if a.smoke else ''}.json"
    json.dump({"rows":rows}, open(out,"w"), ensure_ascii=False, indent=1); print("wrote", out)

if __name__=="__main__": main()
