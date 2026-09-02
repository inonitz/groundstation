#!/usr/bin/env python3
"""Serving census: where does the VRAM go, and what can move to CPU?

Machine truth (owner 2026-09-02): 8 GiB VRAM (RTX 5070 Laptop), 16 GiB RAM. The desktop session
must survive, so this NEVER loads everything at once:
  1. Each model alone on GPU: load -> one warm request (forces compute buffers) -> read
     nvidia-smi -> unload. Per-component resident cost.
  2. Pairs, guarded: a second model loads ONLY if free VRAM >= its measured solo cost + 1 GiB
     margin. Skipped pairs are reported as "would not fit", which is itself the answer.
  3. CPU offload: DictaLM and TranslateGemma with -ngl 0, 20 real command translations each,
     p50/p95 vs the known GPU numbers. RAM-guarded (needs >= model size + 2 GiB available).
Not covered yet: OmDet+SAM2.1 vision pair (needs the smart-scene python env), whisper CT2
(faster-whisper not installed; lands with the ASR round). Reruns as-is on production hardware.
Usage: python3 census.py -> prints tables, writes results/<date>-census.json"""
import json, os, subprocess, sys, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.abspath(os.path.join(HERE, "..", "hebrew-command-bench"))
sys.path.insert(0, BENCH)
from llama import LlamaServer, chat, port_up, MODELS, QWEN3VL_EXTRA, PORT

# TranslateGemma left the bench when it was deferred; the census still measures it.
TGEMMA_GGUF = "/root/models/translate/translategemma-4b-it-gguf/translategemma-4b-it.Q4_K_M.gguf"


def pct(xs, p):
    import math
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100.0
    f = math.floor(k)
    c2 = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c2] - xs[f]) * (k - f)

from prompts import TRANSLATE_SYS, TRANSLATE_SHOTS, LINE_GRAMMAR, TGEMMA_PROMPT
from cases_commands import CASES

MARGIN_MB = 1024

def vram():
    out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free",
                                   "--format=csv,noheader,nounits"], text=True).strip()
    t, u, f = [int(x) for x in out.split(",")]
    return {"total": t, "used": u, "free": f}

def ram_avail_mb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"): return int(line.split()[1]) // 1024
    return 0

def warm(kind):
    if kind == "tgemma":
        completion(PORT, TGEMMA_PROMPT.format(he="טוס קדימה חמישה מטרים"), max_tokens=40, grammar=LINE_GRAMMAR)
    else:
        chat(PORT, TRANSLATE_SYS, "טוס קדימה חמישה מטרים", max_tokens=40,
             grammar=LINE_GRAMMAR, shots=TRANSLATE_SHOTS)

SPECS = {"dicta": (MODELS["dicta"], ()), "tgemma": (TGEMMA_GGUF, ("--chat-template", "gemma")),
         "qwen3vl": (MODELS["qwen3vl"], QWEN3VL_EXTRA)}

def main():
    assert not port_up(PORT), "llama-server already running"
    res = {"gpu": subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True).strip(),
           "baseline": vram(), "solo": {}, "pairs": {}, "cpu": {}}
    print(f"GPU: {res['gpu']}  baseline: {res['baseline']}", flush=True)

    print("== solo residency (load -> warm request -> measure -> unload) ==", flush=True)
    for kind, (model, extra) in SPECS.items():
        with LlamaServer(model, extra=extra):
            warm(kind)
            time.sleep(1)
            v = vram()
            cost = v["used"] - res["baseline"]["used"]
            res["solo"][kind] = {"resident_mb": cost, "free_after_mb": v["free"]}
            print(f"  {kind:8s} resident {cost} MiB, free {v['free']} MiB", flush=True)
        time.sleep(2)

    print("== guarded pairs (second model loads only if free >= solo cost + margin) ==", flush=True)
    for pair in (("qwen3vl", "dicta"), ("qwen3vl", "tgemma")):
        a, b = pair
        with LlamaServer(*[SPECS[a][0]], extra=SPECS[a][1]):
            warm(a); time.sleep(1)
            free = vram()["free"]
            need = res["solo"][b]["resident_mb"] + MARGIN_MB
            if free < need:
                res["pairs"]["+".join(pair)] = {"fits": False, "free_mb": free, "need_mb": need}
                print(f"  {a}+{b}: SKIPPED, would not fit (free {free} < need {need})", flush=True)
                continue
            with LlamaServer(SPECS[b][0], port=PORT + 1, extra=SPECS[b][1]):
                time.sleep(1)
                v = vram()
                res["pairs"]["+".join(pair)] = {"fits": True, "used_mb": v["used"] - res["baseline"]["used"],
                                                "free_mb": v["free"]}
                print(f"  {a}+{b}: fits, combined {v['used']-res['baseline']['used']} MiB, free {v['free']} MiB", flush=True)
        time.sleep(2)

    print("== CPU offload latency (-ngl 0, 20 real command translations) ==", flush=True)
    sub = CASES[:20]
    for kind in ("dicta", "tgemma"):
        need_mb = os.path.getsize(SPECS[kind][0]) // 2**20 + 2048
        if ram_avail_mb() < need_mb:
            res["cpu"][kind] = {"skipped": f"RAM guard: available {ram_avail_mb()} < {need_mb} MiB"}
            print(f"  {kind}: SKIPPED by RAM guard", flush=True)
            continue
        model, extra = SPECS[kind]
        srv = LlamaServer(model, extra=extra)
        srv.args = [a for a in srv.args]
        i = srv.args.index("-ngl"); srv.args[i+1] = "0"
        i = srv.args.index("-dev"); del srv.args[i:i+2]
        threads = str(max(4, os.cpu_count() // 2))
        i = srv.args.index("--threads"); srv.args[i+1] = threads
        with srv:
            tr = []
            for case in sub:
                if kind == "tgemma":
                    payload = {"prompt": TGEMMA_PROMPT.format(he=case[1]), "n_predict": 80,
                               "temperature": 0.0, "grammar": LINE_GRAMMAR}
                    import urllib.request as _u
                    req = _u.Request(f"http://127.0.0.1:{PORT}/completion",
                                     __import__("json").dumps(payload).encode(),
                                     {"Content-Type": "application/json"})
                    t0_ = time.time()
                    with _u.urlopen(req, timeout=180) as r_:
                        text = __import__("json").load(r_)["content"]
                    tr.append((case[0], text.strip(), time.time() - t0_))
                else:
                    text, dt = chat(PORT, TRANSLATE_SYS, case[1], max_tokens=80,
                                    grammar=LINE_GRAMMAR, shots=TRANSLATE_SHOTS)
                    tr.append((case[0], text.strip(), dt))
            lats = [round(dt*1000) for _, _, dt in tr]
            res["cpu"][kind] = {"threads": int(threads), "n": len(lats),
                                "p50_ms": round(pct(lats, 50)), "p95_ms": round(pct(lats, 95)),
                                "max_ms": max(lats), "ram_after_avail_mb": ram_avail_mb()}
            print(f"  {kind} CPU x{threads}t: p50 {res['cpu'][kind]['p50_ms']} p95 {res['cpu'][kind]['p95_ms']} max {max(lats)} ms", flush=True)
        time.sleep(2)

    stamp = datetime.date.today().isoformat()
    out = os.path.join(HERE, "results", f"{stamp}-census.json")
    json.dump(res, open(out, "w"), indent=1)
    print(f"\nresults -> {out}", flush=True)

def stack_census():
    import torch
    steps, prev = [], vram()
    base = prev
    def mark(name):
        nonlocal prev
        time.sleep(1); v = vram()
        steps.append({"step": name, "delta_mb": v["used"] - prev["used"],
                      "total_used_mb": v["used"] - base["used"], "free_mb": v["free"]})
        print(f"  {name:28s} +{v['used']-prev['used']:>5d} MiB  total {v['used']-base['used']:>5d}  free {v['free']:>5d}", flush=True)
        prev = v

    print(f"baseline: {base}", flush=True)
    with LlamaServer(MODELS["qwen3vl"], extra=QWEN3VL_EXTRA):
        chat(PORT, TRANSLATE_SYS, "טוס קדימה חמישה מטרים", max_tokens=30, grammar=LINE_GRAMMAR, shots=TRANSLATE_SHOTS)
        mark("qwen3vl (llama-server)")

        from transformers import AutoProcessor, OmDetTurboForObjectDetection
        r = "/root/models/vision/omdet-turbo-swin-tiny"
        proc = AutoProcessor.from_pretrained(r, local_files_only=True)
        omdet = OmDetTurboForObjectDetection.from_pretrained(r, local_files_only=True).to("cuda").eval()
        img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        with torch.no_grad():
            inp = proc(images=img, text=["person", "car"], return_tensors="pt").to("cuda")
            omdet(**inp)
        mark("omdet-turbo swin-tiny")

        from ultralytics import SAM
        sam = SAM("/root/models/vision/sam2.1_b.pt")
        sam.to("cuda")
        sam(img, bboxes=[[100, 100, 300, 300]], verbose=False)
        mark("sam2.1-base (ultralytics)")

        try:
            from transformers import Wav2Vec2ForCTC
            w2v = Wav2Vec2ForCTC.from_pretrained("/root/models/asr/wav2vec2-xls-r-300m-lm-hebrew",
                                                 local_files_only=True, torch_dtype=torch.float16).to("cuda").eval()
            with torch.no_grad():
                w2v(torch.randn(1, 16000, dtype=torch.float16, device="cuda"))
            mark("wav2vec2-300m fp16 (ASR)")
        except Exception as e:
            print(f"  wav2vec2 skipped: {e}", flush=True)

        print("\nall resident together:", vram(), flush=True)
    stamp = datetime.date.today().isoformat()
    out = os.path.join(HERE, "results", f"{stamp}-census2.json")
    json.dump({"baseline": base, "steps": steps}, open(out, "w"), indent=1)
    print(f"results -> {out}", flush=True)



if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", action="store_true",
                    help="demo-stack co-residency: qwen3vl + omdet + sam2.1 + wav2vec2")
    if ap.parse_args().stack: stack_census()
    else: main()

