#!/usr/bin/env python3
"""Hebrew ASR benchmark, one file.

Compares three model paths on the FLEURS he_il test set:
  - whisper-large-v3-turbo (ivrit-ai) via whisper.cpp, at fp16/q8_0/q5_1/q4_0
  - the same model via faster-whisper/CTranslate2, at fp16/int8 on GPU or CPU
  - wav2vec2-xls-r-300m-lm-hebrew via transformers, with and without its KenLM

Run everything:            python asr_bench.py
Quick subset:              python asr_bench.py --n 30 --lanes fp16,ct2_int8_gpu,w2v2
Only one step:             python asr_bench.py --step prep   (or bench / stats)

Corpus and the CT2 model download themselves on first run. whisper.cpp models and the
whisper-cli binary are host-local (see README prerequisites). Deterministic decode throughout.
Sections below run top to bottom: config, corpus, scoring, the three lanes, stats, main().
"""
import os, re, sys, json, time, glob, random, argparse, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = "/root/groundstation/build/release/shared/dji/bin"          # whisper-cli + its .so libs
WCLI = os.path.join(BIN, "whisper-cli")
WHISPER_MODELS = {                                                # ivrit turbo, GGML for whisper.cpp
    "fp16": "/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model.bin",
    "q8_0": "/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q8_0.bin",
    "q5_1": "/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q5_1.bin",
    "q4_0": "/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q4_0.bin",
}
W2V2_DIR = "/root/models/asr/wav2vec2-xls-r-300m-lm-hebrew"       # ships its KenLM under language_model/
CT2_REPO = "ivrit-ai/whisper-large-v3-turbo-ct2"                  # auto-downloaded to CT2_DIR
CT2_DIR = os.path.join(HERE, "data", "ivrit-turbo-ct2")
CT2_LANES = {"ct2_fp16_gpu": ("cuda", "float16"),
             "ct2_int8_gpu": ("cuda", "int8_float16"),
             "ct2_int8_cpu": ("cpu", "int8")}
WHISPER_QUANTS = ("fp16", "q8_0", "q5_1", "q4_0")
DEFAULT_LANES = "fp16,q8_0,q5_1,q4_0,ct2_fp16_gpu,ct2_int8_gpu,w2v2,w2v2_nolm"
MANIFEST = os.path.join(HERE, "manifests", "fleurs_he_il_test.json")
RESULTS = os.path.join(HERE, "results")
DATA_WAV = os.path.join(HERE, "data", "fleurs_wav")
THREADS = "8"
SR = 16000
PUNCT = re.compile(r'[,?.!\-;:"%\(\)\[\]־׳״“”‘’—…–�]')


# ============================ corpus prep (FLEURS -> wav + manifest + noise) ==================
def est_snr_db(x):
    import numpy as np, math
    n = 400
    if len(x) < n:
        return None, None
    frames = [x[i:i + n] for i in range(0, len(x) - n, n)]
    rms = np.array([math.sqrt(float(np.mean(f * f)) + 1e-12) for f in frames])
    noise, speech = float(np.percentile(rms, 10)), float(np.percentile(rms, 90))
    snr = 20.0 * math.log10(speech / max(noise, 1e-9)) if noise > 0 else None
    return (round(snr, 1) if snr else None), round(20.0 * math.log10(float(np.sqrt(np.mean(x * x)) + 1e-12)), 1)


def prep_corpus():
    import io, numpy as np, soundfile as sf
    from datasets import load_dataset, Audio
    os.makedirs(DATA_WAV, exist_ok=True)
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    ds = load_dataset("google/fleurs", "he_il", split="test").cast_column("audio", Audio(decode=False))
    man, durs, snrs = [], [], []
    for i, row in enumerate(ds):
        b = row["audio"].get("bytes") or open(row["audio"]["path"], "rb").read()
        x, sr = sf.read(io.BytesIO(b), dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        cid = f"c{i:04d}"
        wav = os.path.join(DATA_WAV, f"{cid}.wav")
        sf.write(wav, x, SR, subtype="PCM_16")
        snr, dbfs = est_snr_db(x)
        dur = round(len(x) / SR, 2)
        man.append({"id": cid, "fleurs_id": str(row.get("id")), "wav": wav, "dur_s": dur,
                    "ref": row.get("raw_transcription") or row.get("transcription") or "",
                    "est_snr_db": snr, "rms_dbfs": dbfs, "gender": row.get("gender")})
        durs.append(dur)
        if snr:
            snrs.append(snr)
    json.dump(man, open(MANIFEST, "w"), ensure_ascii=False, indent=1)
    print(f"[prep] clips={len(man)} minutes={sum(durs)/60:.1f} "
          f"est_snr_db p10/p50/p90={pct(snrs,10)}/{pct(snrs,50)}/{pct(snrs,90)}")
    return man


# ============================ normalization + scoring ========================================
def normalize_he(t):
    t = PUNCT.sub("", t.lower())
    t = "".join("" if 1456 <= ord(c) <= 1479 else c for c in t)
    return " ".join(t.split())


def wav_id(w):
    return os.path.splitext(os.path.basename(w))[0]


def score(refs, hyps):
    import jiwer
    ids = sorted(refs)
    R = [normalize_he(refs[i]) for i in ids]
    H = [normalize_he(hyps.get(i, "")) for i in ids]
    pairs = [{"id": i, "ref": r, "hyp": h} for i, r, h in zip(ids, R, H)]
    return jiwer.wer(R, H) * 100.0, jiwer.cer(R, H) * 100.0, pairs


# ============================ lane: whisper.cpp ==============================================
def _wargs(model):
    return [WCLI, "-m", model, "-l", "he", "-bs", "1", "-bo", "1", "-tp", "0.0", "-nf", "-nt", "-t", THREADS]


def whisper_transcribe_all(quant, wavs):
    env = {**os.environ, "LD_LIBRARY_PATH": f"{BIN}:{os.environ.get('LD_LIBRARY_PATH','')}"}
    for w in wavs:
        for c in glob.glob(os.path.splitext(w)[0] + "*.txt") + [w + ".txt"]:
            if os.path.exists(c):
                os.remove(c)
    subprocess.run(_wargs(WHISPER_MODELS[quant]) + ["-np", "-otxt"] + wavs, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    out = {}
    for w in wavs:
        cands = [w + ".txt"] + glob.glob(os.path.splitext(w)[0] + "*.txt")
        txt = next((c for c in cands if os.path.exists(c)), None)
        out[wav_id(w)] = open(txt, encoding="utf-8").read().strip() if txt else ""
    return out


def whisper_latency(quant, wavs):
    env = {**os.environ, "LD_LIBRARY_PATH": f"{BIN}:{os.environ.get('LD_LIBRARY_PATH','')}"}
    lat = []
    for w in wavs:
        r = subprocess.run(_wargs(WHISPER_MODELS[quant]) + [w], env=env, capture_output=True, text=True)
        t = {k: float(m.group(1)) if (m := re.search(p + r"\s*=\s*([\d.]+)\s*ms", r.stderr)) else 0.0
             for k, p in (("load", "load time"), ("total", "total time"))}
        lat.append(round(t["total"] - t["load"], 1))
    return lat


# ============================ lane: faster-whisper / CT2 =====================================
def ensure_ct2():
    if not os.path.exists(os.path.join(CT2_DIR, "model.bin")):
        from huggingface_hub import snapshot_download
        print(f"[ct2] downloading {CT2_REPO} ...")
        snapshot_download(CT2_REPO, local_dir=CT2_DIR)


def ct2_run(lane, items):
    from faster_whisper import WhisperModel
    device, compute = CT2_LANES[lane]
    ensure_ct2()
    kw = {"cpu_threads": 8} if device == "cpu" else {}
    model = WhisperModel(CT2_DIR, device=device, compute_type=compute, **kw)
    hyps, lat = {}, []
    for cid, wav in items:
        t0 = time.perf_counter()
        segs, _ = model.transcribe(wav, language="he", beam_size=1, temperature=0.0,
                                   condition_on_previous_text=False, vad_filter=False)
        text = "".join(s.text for s in segs)
        lat.append(round((time.perf_counter() - t0) * 1000.0, 1))
        hyps[cid] = text
    return hyps, lat


# ============================ lane: wav2vec2 + KenLM =========================================
def build_w2v2(device):
    import torch
    from transformers import Wav2Vec2ForCTC, Wav2Vec2FeatureExtractor
    from pyctcdecode import build_ctcdecoder
    model = Wav2Vec2ForCTC.from_pretrained(W2V2_DIR).eval()
    dev = "cuda" if device >= 0 and torch.cuda.is_available() else "cpu"
    model.to(dev)
    fe = Wav2Vec2FeatureExtractor.from_pretrained(W2V2_DIR)
    labels = json.load(open(os.path.join(W2V2_DIR, "alphabet.json")))["labels"]
    attrs = json.load(open(os.path.join(W2V2_DIR, "language_model", "attrs.json")))
    unigrams = [w.strip() for w in open(os.path.join(W2V2_DIR, "language_model", "unigrams.txt"),
                                        encoding="utf-8") if w.strip()]
    decoder = build_ctcdecoder(
        labels, kenlm_model_path=os.path.join(W2V2_DIR, "language_model", "5gram.bin"),
        unigrams=unigrams, alpha=attrs["alpha"], beta=attrs["beta"])
    return model, fe, decoder, dev, labels


def run_w2v2(items, device, use_lm=True):
    import torch, soundfile as sf
    model, fe, decoder, dev, labels = build_w2v2(device)
    hyps, lat = {}, []
    for cid, wav in items:
        x, sr = sf.read(wav, dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        iv = fe(x, sampling_rate=sr, return_tensors="pt").input_values.to(dev)
        t0 = time.perf_counter()
        with torch.no_grad():
            logits = model(iv).logits[0].cpu().numpy()
        if use_lm:
            text = decoder.decode(logits)                       # pyctcdecode beam over KenLM 5-gram
        else:
            prev, merged = None, []                             # plain CTC argmax + collapse repeats
            for tk in [labels[i] for i in logits.argmax(-1)]:
                if tk != prev and tk not in ("", "<s>", "</s>", "\u2047"):
                    merged.append(tk)
                prev = tk
            text = "".join(merged)
        lat.append(round((time.perf_counter() - t0) * 1000.0, 1))
        hyps[cid] = text
    return hyps, lat


# ============================ stats =========================================================
def pct(v, p):
    if not v:
        return 0.0
    v = sorted(v)
    return round(v[min(len(v) - 1, int(round(p / 100.0 * (len(v) - 1))))], 1)


def wer_ci(per, B=2000):
    random.seed(0)
    E, R = sum(e for e, r in per), sum(r for e, r in per)
    n, boots = len(per), []
    for _ in range(B):
        idx = [random.randrange(n) for _ in range(n)]
        e = sum(per[i][0] for i in idx)
        r = sum(per[i][1] for i in idx)
        boots.append(e / r * 100 if r else 0)
    boots.sort()
    return E / R * 100, boots[int(0.025 * B)], boots[int(0.975 * B)]


def _table(headers, rows):
    """Fixed-width aligned table: first column left, the rest right, two-space gutter."""
    cols = list(zip(*([headers] + rows)))
    w = [max(len(str(c)) for c in col) for col in cols]
    line = lambda r: "  ".join((str(c).ljust(w[i]) if i == 0 else str(c).rjust(w[i]))
                               for i, c in enumerate(r))
    print(line(headers))
    print("  ".join("-" * w[i] for i in range(len(w))))
    for r in rows:
        print(line(r))


def print_stats(results):
    import jiwer
    from scipy.stats import binomtest

    def counts(ref, hyp):
        o = jiwer.process_words([ref], [hyp])
        return o.substitutions + o.deletions + o.insertions, o.hits + o.substitutions + o.deletions

    per = {ln: {p["id"]: counts(p["ref"], p["hyp"]) for p in d["pairs"]} for ln, d in results.items()}
    order = list(dict.fromkeys(l for l in DEFAULT_LANES.split(",") + ["ct2_int8_cpu"] if l in per))
    exact, wer_rows, lat_rows = {}, [], []
    for ln in order:
        vals = list(per[ln].values())
        w, lo, hi = wer_ci(vals)
        exact[ln] = {i: (1 if e == 0 else 0) for i, (e, r) in per[ln].items()}
        ex = sum(1 for e, r in vals if e == 0) / len(vals) * 100
        cer = results[ln].get("cer", 0.0)
        wer_rows.append([ln, f"{w:.2f}", f"[{lo:.2f}, {hi:.2f}]", f"{cer:.2f}", f"{ex:.1f}", len(vals)])
        lt = results[ln].get("lat_ms", [])
        lat_rows.append([ln, pct(lt, 25), pct(lt, 50), pct(lt, 75), pct(lt, 95),
                         round(max(lt), 1) if lt else 0])
    print("\nAccuracy (WER/CER %, bootstrap 95% CI on WER):")
    _table(["lane", "WER", "95% CI", "CER", "sent-exact", "n"], wer_rows)
    print("\nLatency (inference ms, model resident):")
    _table(["lane", "p25", "p50", "p75", "p95", "max"], lat_rows)
    print("\nExact McNemar (sentence-exact-match; b=first-only, c=second-only wins):")
    mc_rows = []
    for a, b in (("fp16", "q4_0"), ("fp16", "ct2_int8_gpu"), ("fp16", "w2v2")):
        if a in exact and b in exact:
            ids = sorted(set(exact[a]) & set(exact[b]))
            bc = sum(1 for i in ids if exact[a][i] and not exact[b][i])
            cc = sum(1 for i in ids if not exact[a][i] and exact[b][i])
            p = binomtest(min(bc, cc), bc + cc, 0.5).pvalue if (bc + cc) else 1.0
            mc_rows.append([f"{a} vs {b}", bc, cc, f"{p:.4g}"])
    _table(["pair", "b", "c", "p"], mc_rows)


# ============================ main ==========================================================
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", choices=("prep", "bench", "stats", "all"), default="all")
    ap.add_argument("--n", type=int, default=0, help="cap clips for WER (0 = all 792)")
    ap.add_argument("--lat-n", type=int, default=50, help="clips for the latency subset")
    ap.add_argument("--lanes", default=DEFAULT_LANES)
    ap.add_argument("--device", type=int, default=0, help="wav2vec2 device: 0 GPU, -1 CPU")
    args = ap.parse_args()
    os.makedirs(RESULTS, exist_ok=True)

    if args.step in ("prep", "all") and not os.path.exists(MANIFEST):
        prep_corpus()
    if args.step == "prep":
        return

    man = json.load(open(MANIFEST, encoding="utf-8"))
    if args.n:
        man = man[:args.n]
    wavs = [m["wav"] for m in man]
    refs = {wav_id(m["wav"]): m["ref"] for m in man}
    items = [(wav_id(w), w) for w in wavs]
    lat_wavs = wavs[:args.lat_n]
    lanes = args.lanes.split(",")
    results = {}

    if args.step in ("bench", "all"):
        for lane in lanes:
            t0 = time.time()
            if lane in WHISPER_QUANTS:
                hyps = whisper_transcribe_all(lane, wavs)
                lat = whisper_latency(lane, lat_wavs)
            elif lane in CT2_LANES:
                hyps, lat_all = ct2_run(lane, items)
                lat = lat_all[:args.lat_n]
            elif lane in ("w2v2", "w2v2_nolm"):
                hyps, lat_all = run_w2v2(items, args.device, use_lm=(lane == "w2v2"))
                lat = lat_all[:args.lat_n]
            else:
                print(f"[skip] unknown lane {lane}")
                continue
            wer, cer, pairs = score(refs, hyps)
            json.dump({"lane": lane, "wer": wer, "cer": cer, "pairs": pairs, "lat_ms": lat},
                      open(os.path.join(RESULTS, f"{lane}.json"), "w"), ensure_ascii=False, indent=1)
            results[lane] = {"wer": wer, "cer": cer, "lat_ms": lat, "pairs": pairs}
            print(f"[{lane:>12}] WER={wer:6.2f}  CER={cer:6.2f}  n={len(refs):4d}  "
                  f"lat_p50={pct(lat,50):7.1f}ms  wall={round(time.time()-t0,1):6.1f}s", flush=True)

    if args.step in ("stats", "all"):
        if not results:  # stats-only run: read what bench wrote earlier
            for lane in lanes:
                fp = os.path.join(RESULTS, f"{lane}.json")
                if os.path.exists(fp):
                    results[lane] = json.load(open(fp, encoding="utf-8"))
        print_stats(results)


if __name__ == "__main__":
    main()
