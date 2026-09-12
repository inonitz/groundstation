#!/usr/bin/env python3
"""Whisper push-to-talk latency on the CPU vs the GPU, on REAL recorded clips (the session recorder's
float32 WAVs). Same whisper.cpp build and Hebrew model as the ASR node. Per clip: whisper-cli's own
"total time" minus "load time" (model load excluded: the node loads once). Reports p50/p95 latency and
the real-time factor per thread count.
    python3 cpu_latency.py [session_clips_dir] [--threads 4,6,8] [--n 20]
"""
import argparse, glob, os, re, struct, subprocess, sys, time
BIN = "/root/groundstation/build/release/shared/dji/bin"
MODEL = "/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q5_k.bin"
DEFAULT_CLIPS = "/root/groundstation/projects/integration_harden/sessions/session-20260908-010129-rog/clips"


def wav_seconds(path):
    with open(path, "rb") as f:
        head = f.read(64)
    rate = struct.unpack_from("<I", head, 24)[0]
    ch = struct.unpack_from("<H", head, 22)[0]
    bits = struct.unpack_from("<H", head, 34)[0]
    data = os.path.getsize(path) - 44
    return data / (rate * ch * bits / 8)


def run(clip, threads, gpu):
    cmd = [f"{BIN}/whisper-cli", "-m", MODEL, "-l", "he", "-bs", "4", "-nt", "-fa", "-t", str(threads), "-f", clip]
    if not gpu:
        cmd.insert(1, "-ng")
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, LD_LIBRARY_PATH=BIN))
    wall = time.time() - t0
    load = total = None
    for line in p.stderr.splitlines():
        m = re.search(r"load time\s*=\s*([\d.]+) ms", line)
        if m: load = float(m.group(1))
        m = re.search(r"total time\s*=\s*([\d.]+) ms", line)
        if m: total = float(m.group(1))
    text = p.stdout.strip().replace("\n", " ")
    lat = (total - load) / 1000 if (total is not None and load is not None) else wall
    return lat, text


def pct(xs, q):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="?", default=DEFAULT_CLIPS)
    ap.add_argument("--threads", default="4,6,8")
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    clips = sorted(glob.glob(os.path.join(a.clips, "*.wav")), key=wav_seconds)
    step = max(1, len(clips) // a.n)
    clips = clips[::step][:a.n]                      # spread across durations
    durs = [wav_seconds(c) for c in clips]
    print(f"{len(clips)} clips, duration s: p50 {pct(durs, .5):.1f}  p95 {pct(durs, .95):.1f}  max {max(durs):.1f}   model {os.path.basename(MODEL)}  beam 4")
    print("| lane | latency p50 s | latency p95 s | max s | RTF median |\n|---|---|---|---|---|")
    lanes = [(f"CPU {t} threads", int(t), False) for t in a.threads.split(",")] + [("GPU Vulkan (node config)", 1, True)]
    for name, t, gpu in lanes:
        lats, rtfs = [], []
        for c, d in zip(clips, durs):
            lat, _ = run(c, t, gpu); lats.append(lat); rtfs.append(lat / d)
        print(f"| {name} | {pct(lats, .5):.2f} | {pct(lats, .95):.2f} | {max(lats):.2f} | {pct(rtfs, .5):.2f} |", flush=True)


if __name__ == "__main__":
    main()
