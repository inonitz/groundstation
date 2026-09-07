# VRAM + Translator Campaign — Results
Owner: groundstation-05 (ref 55e80f), live-test agent. Date: 2026-09-07. Host: RTX 5070 Laptop, 8 GB.
Sorted/compacted report. Chronological raw log: docs/stale/2026-09-07-campaign-rawlog.md.
Raw JSON: tools/bench/hebrew-command-bench/results/2026-09-07-*.json.

## 1. Decision (owner-ruled 2026-09-07)
- **DEPLOY Hy-MT2 as a SINGLE model for everything** (Q4 preferred, Q6 if VRAM allows). The DictaLM
  split is REJECTED — needless complexity for marginal gain; Hy-MT2 is ~never wrong on simple commands.
- **Deploy Hy-MT2** as the Hebrew→English translator. Fits the card,
  answer-mode 0, ~2x faster than tgemma.
- **tgemma+few-shots is the most accurate (90%) but VRAM-blocked (2,478 MiB)** — not deployable here.
- **DictaLM stays the command path on CPU** (99% commands) if a split is chosen; weak perception, CPU tail.
- **SAM3 is a PREREQUISITE** for any GPU translator (see §4). Until it lands, translation stays on CPU.
- Universal lever = **few-shots** (2 is optimal). Low-bit (<Q4) not usable on this x86 host.

## 2. Accuracy — full 413 cases, every model at best recipe (system prompt + 2 few-shots)
| set | DictaLM | tgemma | Hy-MT2-Q4 | Hy-MT2-Q6 | Hy-MT2-Q8 |
|---|---|---|---|---|---|
| emergency | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| std-204 command | 197/199 (99%) | 196/200 (98%) | 193/201 (96%) | 193/200 (96%) | 194/200 (97%) |
| verbose-54 | 47/51 (92%) | 47/54 (87%) | 43/54 (80%) | 48/54 (89%) | 47/54 (87%) |
| perception-128 | 78/128 (61%) | 112/128 (88%) | 92/128 (72%) | 92/128 (72%) | 88/128 (69%) |
| military-20 | 10/20 (50%) | 7/20 (35%) | 10/20 (50%) | 12/20 (60%) | 11/20 (55%) |
| ALL | 339/405 (84%) | 369/409 (90%) | 345/410 (84%) | 352/409 (86%) | 347/409 (85%) |

**Notes:** DictaLM answer-modes on questions (perception 61%). tgemma & Hy-MT2 answer-mode 0. Every model
craters ~6-12pp on commands if run zero-shot — that was the (corrected) reason tgemma once looked weak.
Shot count: 2 is optimal; Hy-MT2-Q6 at 3/4 shots drifts down (86->85->84%).

## 3. Performance (translation stage, temp 0)
Full-dataset latency, 406 cases (ms) + throughput:
| model | p50 | p95 | p99 | tok/s | runs on |
|---|---|---|---|---|---|
| DictaLM | 79 | 233 | 346 | 178 | GPU-ref (deploys CPU) |
| tgemma-Q4 | 205 | 499 | 583 | 88 | GPU |
| Hy-MT2-Q4 | 81 | 207 | 243 | 182 | GPU |
| Hy-MT2-Q6 | 100 | 249 | 293 | 157 | GPU |
| Hy-MT2-Q8 | 104 | 295 | 358 | 136 | GPU |
**Per-subset latency — GPU, in milliseconds (p50 / p95). These are LATENCY, not accuracy.**

| model | command ms | verbose ms | perception ms | military ms |
|---|---|---|---|---|
| DictaLM | 60/142 | 196/311 | 98/159 | 78/104 |
| tgemma-Q4 | 167/293 | 456/605 | 264/368 | 227/279 |
| Hy-MT2-Q4 | 74/156 | 214/300 | 109/170 | 99/113 |
| Hy-MT2-Q6 | 65/136 | 223/299 | 127/194 | 114/131 |
| Hy-MT2-Q8 | 70/167 | 273/368 | 144/223 | 122/152 |

DictaLM CPU thread sweep, per-subset p50/p95 (deployment target = CPU):
| thr | command | verbose | perception | military | ALL p50/p95/p99 |
|---|---|---|---|---|---|
| 2 | 293/740 | 1104/1729 | 568/1054 | 424/578 | 405/1280/2025 |
| 4 | 201/579 | 875/1406 | 445/842 | 339/450 | 317/1046/1806 |
| 6 | 172/522 | 805/1317 | 410/780 | 311/412 | 290/971/1716 |
| 8 | 157/493 | 768/1265 | 387/740 | 296/389 | 273/937/1666 |

DictaLM-CPU tail is heavy (p99 1.7s even at 8 thr) -> perception belongs on the GPU translator.

## 4. VRAM fit (Step 3) — SAM3 REQUIRED

Model footprints (resident MiB):

| model | VRAM (MiB) |
|---|---|
| Qwen3-VL-4B (prod flags) | 3,822 |
| Hy-MT2 Q4 / Q6 / Q8 | 1,188 / 1,514 / 1,928 |
| tgemma-4B | 2,478 |
| DictaLM | CPU (~1.2 GB RAM); 1,583 GPU-ref |
| whisper q5_k / q4_k | 838 / 743 |
| YOLO26n-seg | 286 |
| OmDet-Turbo | 863 |
| SAM2.1 | 728 |
| SAM3-nf4 | 886 |

Measured co-resident (Qwen + Hy-MT2-Q6 + whisper-q5_k + YOLO) = 6,553 MiB used, 1,156 free. Ceiling ~7,708.
<!-- FORMATTING TODO: reformat this perception-engine fit table into clearer columns (total MiB + verdict split; the '8,144 — OVER 436' cells are cramped). -->
| perception engine | + Hy-MT2-Q6 | + Hy-MT2-Q4 |
|---|---|---|
| current: OmDet + SAM2.1 (both) | 8,144 — OVER 436 | 7,818 — OVER 110 |
| SAM3 (unifies both) | 7,439 — FITS 269 free | 7,113 — FITS 595 free |

**Conclusion**

- Current OmDet + SAM2.1: no room for a GPU translator — even Q4 is 110 MiB over.
- SAM3 (unifies both, saves ~705 MiB) is the prerequisite. With SAM3, prefer Q4 (595 MiB free); Q6's 269 MiB free is eaten by Qwen's +89 MiB image-encode spikes.
- Caveat: the perception footprints (OmDet / SAM2.1 / SAM3) are census numbers measured in isolation, not loaded in this co-resident run — so the fit is four-measured-together plus SAM3 added on paper. A live all-five load is the final confirmation (not yet run).

## 5. VRAM overhead decomposition (Step 4)
| model | file | resident | overhead source |
|---|---|---|---|
| tgemma default (4-slot/4096) | 2,374 | 3,029 | KV 4x4096 (~550) + compute/ctx (~105) |
| tgemma lean (c512/1-slot) | 2,374 | 2,552 | KV(512) + compute + Vulkan ctx |
| whisper q5_k | ~547 | 838 | +291 encoder buffers + ctx (fixed) |
| Hy-MT2-Q4 (c256) | 1,080 | 1,150 | +70 small KV + ctx |
Lever: serve lean (1 slot, small ctx) — the "3 GB tgemma" was the 4-slot/4096 default, not the model.

## 6. Number guard (Step 6)

Firing rate (current data): 8/388 cases (1/203 commands); PATCHED 0. Near-inert.

Measured contribution (sieve ablation, verbose + std-190 sets):

| configuration | verbose | std-190 |
|---|---|---|
| no guard (baseline) | 37/54 (69%) | 179/190 (94%) |
| + number check + corrective retry | 42/54 (78%) | 180/190 (95%) |
| + single-token digit patch | 46/54 (85%) | 181/190 (95.3%) |

- The **retry** is the safe win (+9 pp verbose) on the number-corruption register (עשרים → "ten").
- The **patch** adds +7 pp verbose but is the risky layer — it caused the חצי-סיבוב = 0.5 bug (extractor read חצי as 0.5 and overwrote a correct "180 degrees").
- Recommendation: keep check + retry; gate or fix the patch so it treats חצי-of-a-unit as a fraction. Bench-gated.
- Emergency stage-0 regex: 7/7, untouched.

## 7. Low-bit — no sub-Q4 option on x86
tencent 1.25-bit (PR #22836 ARM NEON) and 2-bit (PR #19357 ARM SME2): unmerged + ARM-only -> unrunnable
on x86. Self-quant standard Q2_K: runs but incoherent (1.8B collapses at 2-bit). Floor = Q4_K_M.

<!-- FORMATTING TODO: tidy this section's layout (owner flagged it reads poorly). -->
## 8. Remaining work (all decisions made — this is engineering + one optional benchmark)

1. **Integrate SAM3** into integration_harden — HARD PREREQUISITE (§4): without it, no GPU translator fits.
2. **Wire in Hy-MT2** as the single-model translator; drop the DictaLM split option.
3. **Confirm the fit** with one live all-five co-resident load (Qwen + SAM3 + YOLO + whisper + Hy-MT2) once SAM3 is in.
4. **(Optional, low value) Step 5 — whisper k-quant WER/CER.** jiwer removed and a local scorer patched into asr_bench; remaining blocker is a stale FLEURS manifest (points at a dead scratchpad). Fix: `cd tools/bench/hebrew_asr && rm manifests/*.json && bash run.sh --step prep && bash run.sh --lanes q4_k,q5_k,q6_k`. Classic quants already scored: fp16 18.72 / q8_0 18.73 / q5_1 18.79 / q4_0 19.59 WER — k-quants expected similar.
