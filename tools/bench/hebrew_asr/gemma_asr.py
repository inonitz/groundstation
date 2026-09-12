def _u(root):  # the per-utterance log: trace.jsonl (2026-09-12), then legacy utterances.jsonl layouts
    import os as _o
    for c in ("trace.jsonl", "asr/utterances.jsonl", "utterances.jsonl"):
        p = _o.path.join(root, *c.split("/"))
        if _o.path.exists(p):
            return p
    return _o.path.join(root, "trace.jsonl")
def _clips_dir(root):  # clips dir: asr_clips/ (2026-09-12), then legacy asr/clips and clips
    import os as _o
    for c in ("asr_clips", "asr/clips", "clips"):
        p = _o.path.join(root, *c.split("/"))
        if _o.path.isdir(p):
            return p
    return _o.path.join(root, "asr_clips")

#!/usr/bin/env python3
"""Gemma 4 E4B as the ASR (owner note 2026-09-08). Every recorded push-to-talk clip of the two live sessions goes
through llama-mtmd-cli (the audio conformer lives in mmproj-BF16.gguf; the HTTP server has no audio route yet),
and the transcript is scored against the matched live-test line (CER / WER, token-overlap match >= 0.34) next to
whisper q5_k's transcript of the SAME clip (heard_he in utterances.jsonl). Unmatched clips get Gemma-vs-whisper
agreement only. One CLI process per clip (model reload each time); GPU; ~7 s per clip.
    python3 gemma_asr.py [--limit N]     -> bench_out/gemma-asr-<date>.{json,md} (bench_out is gitignored: transcripts)"""
import os, sys, re, json, glob, time, argparse, subprocess, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE); from asr_bench import normalize_he
BIN = os.path.join(ROOT, "build", "release", "shared", "dji", "bin"); D = "/root/models/vlm/Gemma-4-E4B"
SESS = [("session-20260908-003702-rog", "tools/desk-test/live-test-50.md"), ("session-20260908-010129-rog", "tools/desk-test/live-test-75.md")]
PROMPT = "Transcribe this Hebrew speech exactly. Output only the Hebrew words, nothing else."
HEB = re.compile(r"[א-ת]")
GRAMMAR = "root ::= [\\u05D0-\\u05EA0-9 ,.?!]+"      # Hebrew letters, digits, punctuation only

def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def cer(ref, hyp): r, h = normalize_he(ref), normalize_he(hyp); return lev(r, h) / max(1, len(r))
def wer(ref, hyp): r, h = normalize_he(ref).split(), normalize_he(hyp).split(); return lev(r, h) / max(1, len(r))
def toks(s): return set(normalize_he(s).split())
def lines_of(p): return [(int(m.group(1)), m.group(2).strip()) for m in re.finditer(r"^(\d+)\. (.*?) ->", open(p, encoding="utf-8").read(), re.M)]
def match(text, lines):
    best = (0.0, None)
    for n, t in lines:
        a, b = toks(text), toks(t); j = len(a & b) / max(1, len(a | b))
        if j > best[0]: best = (j, (n, t))
    return best[1] if best[0] >= 0.34 else None

def gemma(wav):
    cmd = [os.path.join(BIN, "llama-mtmd-cli"), "-m", f"{D}/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf", "--mmproj", f"{D}/mmproj-BF16.gguf",
           "-dev", "Vulkan0", "-ngl", "99", "-c", "2048", "--temp", "0", "--jinja", "-n", "48", "--grammar", GRAMMAR, "--audio", wav, "-p", PROMPT]   # the grammar keeps the thinking narration out (the CLI has no enable_thinking switch)
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env={**os.environ, "LD_LIBRARY_PATH": BIN})
    txt = " ".join(l.strip() for l in r.stdout.splitlines() if HEB.search(l))
    return txt, (time.time() - t0) * 1000

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=0); a = ap.parse_args()
    out = os.path.join(HERE, "bench_out", f"gemma-asr-{datetime.date.today().isoformat()}"); rows = []
    for sess, lst in SESS:
        sd = os.path.join(ROOT, "projects", "integration_harden", "sessions", sess)
        clips = sorted(glob.glob(os.path.join(_clips_dir(sd), "*.wav"))); utts = [json.loads(l) for l in open(_u(sd), encoding="utf-8")]
        lines = lines_of(os.path.join(ROOT, lst))
        for i, wav in enumerate(clips[:a.limit] if a.limit else clips):
            heard = utts[i]["heard_he"] if i < len(utts) else ""
            g, ms = gemma(wav)
            ref = match(heard, lines) or match(g, lines)
            row = {"session": sess, "clip": os.path.basename(wav), "whisper": heard, "gemma": g, "ms": round(ms), "line": ref[0] if ref else None, "ref": ref[1] if ref else None}
            if ref:
                row.update(w_cer=cer(ref[1], heard), w_wer=wer(ref[1], heard), g_cer=cer(ref[1], g), g_wer=wer(ref[1], g))
            row["gw_cer"] = cer(heard, g) if heard else None
            rows.append(row); print(f"{sess[-10:]} {i:3d} {ms:6.0f} ms | line {row['line']} | whisper: {heard[:40]} | gemma: {g[:40]}", flush=True)
            json.dump(rows, open(out + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    m = [r for r in rows if r.get("ref")]; mean = lambda k: sum(r[k] for r in m) / max(1, len(m)) * 100
    p50 = sorted(r["ms"] for r in rows)[len(rows) // 2] if rows else 0
    md = ["# Gemma 4 E4B as the ASR vs whisper q5_k, same push-to-talk clips", "",
          f"{len(rows)} clips from two live sessions; {len(m)} matched to a live-test line (token overlap >= 0.34). Gemma through llama-mtmd-cli, one process per clip.", "",
          "| ASR | CER % (matched) | WER % (matched) | p50 ms per clip |", "|---|---|---|---|",
          f"| whisper q5_k (ASR node, beam 4) | {mean('w_cer'):.1f} | {mean('w_wer'):.1f} | ~290 (measured 2026-09-08, GPU) |",
          f"| Gemma 4 E4B, audio conformer, CLI | {mean('g_cer'):.1f} | {mean('g_wer'):.1f} | {p50} (includes the model load) |", "",
          f"Gemma-vs-whisper CER over all {len(rows)} clips: {sum(r['gw_cer'] for r in rows if r['gw_cer'] is not None) / max(1, sum(1 for r in rows if r['gw_cer'] is not None)) * 100:.1f} %", "",
          "## Per clip", "", "| session | clip | line | reference | whisper | Gemma | whisper CER | Gemma CER |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['session'][-10:]} | {r['clip'][6:12]} | {r['line'] or '-'} | {(r['ref'] or '-')[:50]} | {r['whisper'][:50]} | {r['gemma'][:50]} | {('%.2f' % r['w_cer']) if r.get('ref') else '-'} | {('%.2f' % r['g_cer']) if r.get('ref') else '-'} |")
    open(out + ".md", "w", encoding="utf-8").write("\n".join(md) + "\n"); open(out + ".done", "w").write("done\n"); print("\n".join(md[:10]))

if __name__ == "__main__":
    main()
