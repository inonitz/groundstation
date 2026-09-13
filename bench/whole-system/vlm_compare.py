#!/usr/bin/env python3
"""Qwen3-VL vs Gemma 4 on the VLM's two production jobs, scored against SAM3 as the reference.
No labels exist for these images (tests/README.md), so this measures AGREEMENT with SAM3, not truth --
the same reference for both models, which makes the comparison fair. Jobs: (1) the presence gate
("Point at and highlight the X.": present or not, plus a box -> IoU with SAM3's top box), including the
adversarial absent phrase "boiler"; (2) counting people (integer vs SAM3's person count). Modes:
"prod" = the production prompt as-is; "grammar" = the same prompt with a GBNF that forces the
LONG/SHORT/HIGHLIGHT/VLM_BOX format (Gemma narrates a thinking preamble without it). Temperature 0.
Images: the 17 bench candidates + 8 desk-camera frames. One llama-server at a time; SAM3 in-process.
    python3 vlm_compare.py [--models qwen3vl,gemma4] [--out results/<date>-vlm-compare]
"""
import argparse, base64, glob, json, os, re, subprocess, sys, time, datetime
import cv2, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BENCH = os.path.join(ROOT, "tools", "bench", "sam3-mask-bench")      # the image data only
HARDEN = os.path.join(ROOT, "projects", "integration_harden2")
BIN = os.path.join(ROOT, "build", "release", "shared", "dji", "bin")
sys.path.insert(0, HARDEN)
from perception import vlm_client
from perception.engine import scale_vlm_box
from perception2.sam3_backend import Sam3Backend

MODELS = {
    "qwen3vl": ["-m", "/root/models/vlm/Qwen3-VL-4B-Instruct/Qwen3-VL-4B-Instruct-Q4_K_M.gguf",
                "--mmproj", "/root/models/vlm/Qwen3-VL-4B-Instruct/mmproj-BF16.gguf",
                "--flash-attn", "on", "--image-min-tokens", "1024", "--cache-type-k", "q4_0", "--cache-type-v", "q4_0"],
    "gemma4": ["-m", "/root/models/vlm/Gemma-4-E4B/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf",
               "--mmproj", "/root/models/vlm/Gemma-4-E4B/mmproj-BF16.gguf", "--reasoning-budget", "0"],
}
GRAMMAR = r'''
root ::= "LONG RESPONSE: " line "\nSHORT RESPONSE: " line "\nHIGHLIGHT: " hl "\nVLM_BOX: " box
line ::= [^\n]+
hl ::= "none" | [^\n]+
box ::= "none" | num "," num "," num "," num
num ::= [0-9]+ ("." [0-9]+)?
'''
CAND_PHRASES = ["person", "car", "window", "boiler"]          # boiler = adversarial absent
DESK_PHRASES = ["person", "chair", "monitor", "boiler"]
PORT = 18090


def vram():
    return int(subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True).strip())


def start_server(name):
    cmd = [os.path.join(BIN, "llama-server"), *MODELS[name], "-dev", "Vulkan0", "-ngl", "99", "-c", "4096", "-np", "1",
           "--temp", "0.0", "--host", "127.0.0.1", "--port", str(PORT), "--threads", "1"]
    log = open(f"/tmp/vlm-compare-{name}.log", "ab")
    p = subprocess.Popen(cmd, env=dict(os.environ, LD_LIBRARY_PATH=BIN), stdout=log, stderr=log, start_new_session=True)
    import urllib.request
    for _ in range(300):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1); return p
        except Exception:
            if p.poll() is not None:
                raise RuntimeError(f"{name} server died; see /tmp/vlm-compare-{name}.log")
            time.sleep(1)
    raise RuntimeError(f"{name} server not healthy after 300 s")


def stop_server(p):
    import signal
    try: os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except Exception: pass
    time.sleep(5)
    try: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except Exception: pass
    time.sleep(2)


def ask(frame, question, grammar):
    import requests
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    content = [{"type": "text", "text": f"Detector found:\n(none)\n\nUser asks: {question}"},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf).decode()}}]
    body = {"messages": [{"role": "system", "content": vlm_client.SYSTEM}, {"role": "user", "content": content}],
            "temperature": 0.0, "max_tokens": 300}
    if grammar:
        body["grammar"] = GRAMMAR
    t0 = time.time()
    r = requests.post(f"http://127.0.0.1:{PORT}/v1/chat/completions", json=body, timeout=240)
    r.raise_for_status()
    txt = r.json()["choices"][0]["message"]["content"].strip()
    return txt, (time.time() - t0) * 1000


def iou(a, b):
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    iw = max(0, min(ax2, bx2) - max(ax1, bx1)); ih = max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih; ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def pct(xs, q):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="qwen3vl,gemma4")
    ap.add_argument("--modes", default="qwen3vl:prod,gemma4:grammar", help="model:mode pairs to run")
    ap.add_argument("--out", default=os.path.join(HERE, "results", datetime.date.today().isoformat(), "vlm-compare"))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    cands = sorted(glob.glob(os.path.join(BENCH, "candidates", "*")))
    desk = sorted(glob.glob("/root/models/vision/sam3-desk-frames/*.jpg"))[::15][:8]
    images = [(p, CAND_PHRASES) for p in cands] + [(p, DESK_PHRASES) for p in desk]
    frames = {p: cv2.imread(p) for p, _ in images}
    for p in list(frames):
        f = frames[p]
        if f is None: images = [x for x in images if x[0] != p]; continue
        if f.shape[1] > 1280:
            s = 1280 / f.shape[1]; frames[p] = cv2.resize(f, (1280, int(f.shape[0] * s)))
    t0 = time.time()
    print(f"[ref] SAM3 on {len(images)} images ...", flush=True)
    sam3 = Sam3Backend()
    ref = {}
    for p, phrases in images:
        fr = frames[p]
        for ph in phrases + ["person"]:
            if (p, ph) in ref: continue
            dets = sam3.detect(fr, ph, conf=0.5, topk=50)
            ref[(p, ph)] = {"present": len(dets) > 0, "count": len(dets), "box": dets[0]["box"] if dets else None}
    print(f"[ref] done in {time.time()-t0:.0f} s", flush=True)
    del sam3
    import torch; torch.cuda.empty_cache()

    rows, summary = [], {}
    pairs = [m.split(":") for m in a.modes.split(",")]
    for name in a.models.split(","):
        for mode in [md for nm, md in pairs if nm == name]:
            print(f"[{name}/{mode}] starting server", flush=True)
            proc = start_server(name); base_vram = vram()
            lat, agree, fmt_ok, ious, boiler_fp, cnt_exact, cnt_pm1, n_cnt = [], 0, 0, [], 0, 0, 0, 0
            n = 0
            for p, phrases in images:
                fr = frames[p]
                for ph in phrases:
                    txt, ms = ask(fr, f"Point at and highlight the {ph}.", mode == "grammar")
                    long_, tgt, box, short = vlm_client.parse_reply(txt)
                    present = tgt is not None
                    r = ref[(p, ph)]
                    ok_fmt = bool(re.search(r"LONG RESPONSE:", txt) and re.search(r"SHORT RESPONSE:", txt))
                    fmt_ok += ok_fmt; n += 1; lat.append(ms)
                    agree += (present == r["present"])
                    if ph == "boiler" and present: boiler_fp += 1
                    bi = None
                    if present and r["present"] and box and r["box"]:
                        try: bi = iou(scale_vlm_box(box, fr.shape), r["box"]); ious.append(bi)
                        except Exception: pass
                    rows.append({"model": name, "mode": mode, "image": os.path.basename(p), "phrase": ph, "job": "gate",
                                 "sam3_present": r["present"], "sam3_count": r["count"], "sam3_box": r["box"], "vlm_present": present,
                                 "vlm_target": tgt, "vlm_box": list(box) if box else None, "iou": bi, "format_ok": ok_fmt,
                                 "ms": round(ms), "reply": txt})
                txt, ms = ask(fr, "How many people are in the image?", mode == "grammar")
                long_, tgt, box, short = vlm_client.parse_reply(txt)
                m = re.match(r"\s*(\d+)", short) or re.match(r"\s*(\d+)", long_)
                got = int(m.group(1)) if m else None
                want = ref[(p, "person")]["count"]; n_cnt += 1; lat.append(ms)
                if got is not None:
                    cnt_exact += (got == want); cnt_pm1 += (abs(got - want) <= 1)
                rows.append({"model": name, "mode": mode, "image": os.path.basename(p), "phrase": "people count", "job": "count",
                             "sam3_count": want, "vlm_count": got, "ms": round(ms), "reply": txt[:300]})
                print(f"  {os.path.basename(p)[:28]:28s} count vlm={got} sam3={want}", flush=True)
            summary[f"{name}/{mode}"] = {"gate_agreement": f"{agree}/{n}", "boiler_false_present": f"{boiler_fp}/{len(images)}",
                                          "box_iou_median": round(pct(ious, .5), 2) if ious else None, "boxes_compared": len(ious),
                                          "count_exact": f"{cnt_exact}/{n_cnt}", "count_within_1": f"{cnt_pm1}/{n_cnt}",
                                          "format_ok": f"{fmt_ok}/{n}", "latency_p50_ms": round(pct(lat, .5)), "latency_p95_ms": round(pct(lat, .95)),
                                          "vram_resident_mib": base_vram}
            print(f"[{name}/{mode}] {summary[f'{name}/{mode}']}", flush=True)
            stop_server(proc)
    json.dump({"summary": summary, "rows": rows, "wall_s": round(time.time() - t0)}, open(a.out + ".json", "w"), ensure_ascii=False, indent=1)
    lines = ["# Qwen3-VL vs Gemma 4 E4B — VLM jobs scored against SAM3 (reference, not truth)", "",
             f"{len(images)} images (17 bench candidates + {len(desk)} desk frames), gate phrases per image, one people count per image. Temperature 0.",
             "", "| model/mode | gate agreement with SAM3 | 'boiler' falsely present | box IoU median (n) | people count exact | within 1 | format ok | latency p50/p95 ms | VRAM MiB |", "|---|---|---|---|---|---|---|---|---|"]
    for k, s in summary.items():
        lines.append(f"| {k} | {s['gate_agreement']} | {s['boiler_false_present']} | {s['box_iou_median']} ({s['boxes_compared']}) | {s['count_exact']} | {s['count_within_1']} | {s['format_ok']} | {s['latency_p50_ms']}/{s['latency_p95_ms']} | {s['vram_resident_mib']} |")
    lines += ["", "## Side by side (for the owner's eyes)", "", "| image | phrase | SAM3 | " + " | ".join(summary.keys()) + " |", "|---|---|---|" + "---|" * len(summary)]
    keys = sorted({(r["image"], r["phrase"]) for r in rows})
    for img, ph in keys:
        cells = []
        for k in summary:
            name, mode = k.split("/")
            rr = [r for r in rows if r["model"] == name and r["mode"] == mode and r["image"] == img and r["phrase"] == ph]
            if not rr: cells.append(""); continue
            r = rr[0]
            cells.append((f"count={r['vlm_count']}" if r["job"] == "count" else f"{'present' if r['vlm_present'] else 'absent'}: {r['vlm_target'] or '-'}" + (f" IoU {r['iou']:.2f}" if r.get("iou") is not None else "")))
        r0 = [r for r in rows if r["image"] == img and r["phrase"] == ph][0]
        sref = f"count={r0['sam3_count']}" if r0["job"] == "count" else f"{'present' if r0['sam3_present'] else 'absent'} ({r0['sam3_count']})"
        lines.append(f"| {img} | {ph} | {sref} | " + " | ".join(cells) + " |")
    open(a.out + ".md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:12])); print(f"-> {a.out}.md / .json   wall {round(time.time()-t0)} s")


if __name__ == "__main__":
    main()
