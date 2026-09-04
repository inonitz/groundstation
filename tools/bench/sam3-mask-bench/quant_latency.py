#!/usr/bin/env python3
"""SAM3 latency across the 8-bit family, isolated one mode per subprocess (one model resident).

Measures on a FIXED image+concept with real detections. Reports load time, VRAM peak, forward-only
p50/p90, full p50 (forward + post_process, which upsamples masks to original resolution), and det
count so we confirm quality parity, not just speed. Deterministic: SAM3 has no sampling.

    python3 quant_latency.py               # run every mode, write the markdown table
    python3 quant_latency.py <mode> <out>  # worker: one mode -> out.json
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "candidates", "street-crowd-0.jpg")
CONCEPT = "person"
MODEL = "/root/models/vision/sam3-official"
REPS = 20
MODES = ["bf16", "nf4", "int8-bnb", "int8-ao", "fp8-wo", "fp8-dyn"]


def _load(mode):
    import torch
    from transformers import Sam3Model, Sam3Processor, BitsAndBytesConfig, TorchAoConfig
    kw = {"dtype": torch.bfloat16}
    if mode == "bf16":
        pass
    elif mode == "nf4":
        kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    elif mode == "int8-bnb":
        kw["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
    elif mode in ("int8-ao", "fp8-wo", "fp8-dyn"):
        # transformers' TorchAoConfig converter calls Sam3Model.get_input_embeddings(), which the
        # class does not implement -> load bf16, then quantize in place with torchao's direct API.
        model = Sam3Model.from_pretrained(MODEL, dtype=torch.bfloat16).eval().to("cuda")
        from torchao.quantization import (quantize_, Int8WeightOnlyConfig, Float8WeightOnlyConfig,
                                          Float8DynamicActivationFloat8WeightConfig)
        cfg = {"int8-ao": Int8WeightOnlyConfig(), "fp8-wo": Float8WeightOnlyConfig(),
               "fp8-dyn": Float8DynamicActivationFloat8WeightConfig()}[mode]
        quantize_(model, cfg)
        return model, Sam3Processor.from_pretrained(MODEL)
    model = Sam3Model.from_pretrained(MODEL, **kw).eval()
    if "quantization_config" not in kw:           # bf16 needs an explicit move; quantizers place it
        model = model.to("cuda")
    proc = Sam3Processor.from_pretrained(MODEL)
    return model, proc


def worker(mode, out):
    import torch, cv2
    import numpy as np
    from PIL import Image
    res = {"mode": mode}
    try:
        torch.cuda.reset_peak_memory_stats()
        t0 = time.time()
        model, proc = _load(mode[:-2] if mode.endswith("-c") else mode)
        if mode.endswith("-c"):
            model = torch.compile(model)
        res["load_s"] = round(time.time() - t0, 1)
        frame = cv2.imread(IMG)
        pil = Image.fromarray(frame[:, :, ::-1])
        inputs = proc(images=pil, text=CONCEPT, return_tensors="pt").to("cuda")
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
        tgt = inputs.get("original_sizes").tolist()

        def fwd():
            with torch.no_grad():
                return model(**inputs)
        for _ in range(8 if mode.endswith("-c") else 3):   # warmup (compile builds on 1st call)
            out_ = fwd(); torch.cuda.synchronize()
        fwd_ms, full_ms = [], []
        n = 0
        for _ in range(REPS):
            torch.cuda.synchronize(); t = time.time()
            out_ = fwd(); torch.cuda.synchronize()
            fwd_ms.append((time.time() - t) * 1000)
            t = time.time()
            r = proc.post_process_instance_segmentation(out_, threshold=0.5, mask_threshold=0.5,
                                                         target_sizes=tgt)[0]
            torch.cuda.synchronize()
            full_ms.append(fwd_ms[-1] + (time.time() - t) * 1000)
            n = int(len(r["scores"]))
        res["vram_mib"] = round(torch.cuda.max_memory_allocated() / 2**20)
        res["fwd_p50"] = round(float(np.percentile(fwd_ms, 50)), 1)
        res["fwd_p90"] = round(float(np.percentile(fwd_ms, 90)), 1)
        res["full_p50"] = round(float(np.percentile(full_ms, 50)), 1)
        res["dets"] = n
    except Exception as e:
        res["error"] = repr(e)[:200]
    json.dump(res, open(out, "w"))
    print(f"[{mode}] {res.get('fwd_p50','ERR')} ms fwd | {res.get('vram_mib','?')} MiB | "
          f"{res.get('dets','?')} dets {res.get('error','')}", flush=True)


def main():
    import subprocess
    if len(sys.argv) == 3:
        worker(sys.argv[1], sys.argv[2]); return
    rows = []
    for mode in MODES:
        out = os.path.join(HERE, "results", f"_ql_{mode}.json")
        print(f"=== {mode} ===", flush=True)
        subprocess.run([sys.executable, __file__, mode, out], check=False, env=dict(os.environ))
        if os.path.exists(out):
            rows.append(json.load(open(out)))
    lines = ["# SAM3 latency across the 8-bit family (RTX 5070, sm120 Blackwell)", "",
             f"Fixed input: `{os.path.basename(IMG)}` + concept `{CONCEPT}`, {REPS} warm reps, "
             "deterministic. `full` = forward + post_process (mask upsample to original res).", "",
             "| mode | load s | VRAM MiB | fwd p50 ms | fwd p90 ms | full p50 ms | dets |",
             "|------|-------:|---------:|-----------:|-----------:|------------:|-----:|"]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['mode']} | - | - | ERR | - | - | {r['error']} |")
        else:
            lines.append(f"| {r['mode']} | {r['load_s']} | {r['vram_mib']} | {r['fwd_p50']} | "
                         f"{r['fwd_p90']} | {r['full_p50']} | {r['dets']} |")
    rep = "\n".join(lines) + "\n"
    rp = os.path.join(HERE, "results", "2026-09-03-sam3-quant-latency.md")
    open(rp, "w").write(rep)
    print("\n" + rep + f"\n(written to {rp})")


if __name__ == "__main__":
    main()
