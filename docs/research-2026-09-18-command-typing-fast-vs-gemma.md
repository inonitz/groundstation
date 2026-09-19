# Command Typing: Deterministic Sieve vs Gemma Planner — Accuracy and Latency

Date: 2026-09-18. System: integration_harden2. GPU: single NVIDIA RTX 5070 Laptop GPU.

> UPDATE 2026-09-19: the deterministic "sieve" this study compares against was subsequently
> DELETED — command routing and typing moved to the one Gemma call. This study is the basis for
> that decision; it describes `recognize_direct`'s fast path as it stood on 2026-09-18.

## Objective

For a Hebrew utterance, determine which mechanism better assigns the command TYPE — a movement
command (should fly) versus a perception/other request (should not fly) — and at what latency cost:

- the deterministic sieve (`recognize_direct`: bypass + Hebrew rewrites), the fast path;
- the Gemma 4 E4B planner (`_plan2`), the slow path.

A secondary objective was to test whether the existing dataset biases the comparison.

## Method

### Paths under test
- Fast path: `recognize_direct(he)` returns `emergency` | `mission` (= move) | `reject` (= not-move) |
  `direct` (= defer to the planner). Pure Python, no GPU.
- Slow path: one `_plan2` call returns `mission` (= move) | `highlight`/`count`/`describe` (= perception) |
  `reject`. GPU-resident model.

### Typing metric
Binary intent: `move` (the drone should physically act) vs `not_move` (perception / status / negation).
Emergency is scored separately (stage 0, deterministic).

### Datasets
- Existing (dev): 487 labelled Hebrew cases (`cases_commands.py`, `cases_perception.py`). The recognizer
  was developed against these; it is the sieve's own dev set.
- Held-out: 200 new hand-authored cases (`cases_typing_fresh.py`), 100 move / 100 not_move, zero exact
  overlap with the existing set. Authored with knowledge of the sieve regexes, so the sieve numbers on
  this set are an upper bound, not a blind estimate.

### Harnesses
- Accuracy: `type_compare.py` (dev set), `type_fresh.py` (held-out). Per case, det type = the
  `recognize_direct` kind; Gemma type = the `_plan2` kind on the recognized text; both scored against
  the label. One llama-server (Gemma 4 E4B, thinking off, temp 0).
- Latency: `perf.py`, 688 utterances (fresh 200 + all existing sets). Fast = min of 7
  `recognize_direct` runs (deterministic; strips scheduler noise). Slow = one `_plan2` call. Six-call
  warmup discarded. `perf_counter`, milliseconds.

## Results

### Accuracy — existing (dev) set (476 typed + 12 emergency)
- Deterministic: decides 92/476 (19%); correct on decided 91/92; movement recall 83/283 (29%); false-fly 0.
- Gemma: 461/476 (97%); false-fly 2 (both military phrasing); missed 13.
- Emergency: 12/12.

### Accuracy — held-out fresh 200
- Deterministic: decides 16/200 (8%); correct on decided 15/16; movement recall 12/100 (12%); false-fly 0.
- Gemma: 174/200 (87%); false-fly 0; missed 26.

### Accuracy — English vs Hebrew (does translating help Gemma type?)
Gemma typed on gold English (fresh: hand-authored glosses `cases_typing_fresh_en.py`; existing: the
dataset `english_reference`).
| set | Gemma on Hebrew | Gemma on English |
|---|---|---|
| held-out fresh 200 | 174/200 (87%), 0 false-fly, 26 miss | 176/200 (88%), 0 false-fly, 24 miss |
| existing 476 | 461/476 (97%), 2 false-fly, 13 miss | 454/476 (95%), 11 false-fly, 11 miss |

Translating to English does not improve typing: a wash on held-out data (88% vs 87%), slightly worse on
the existing set, with false-flies rising 2 -> 11 (English imperatives like "Mark the door" read as flight
commands). A translator in the routing path would add latency and a model for no typing gain.

### Dataset bias (per subset)
| subset | n | det fires | det movement recall | Gemma correct |
|---|---|---|---|---|
| dev std/verbose (sieve tuned here) | 352 | 25% | 34% | 99% |
| l75 field (not tuned) | 59 | 8% | 7.5% | 85% |
| perception | 45 | 0% (defers all) | — | 100% |
| military | 20 | 0% (defers all) | — | 90% |

### Latency (n = 688)
| percentile | fast — sieve | slow — Gemma | difference | ratio |
|---|---|---|---|---|
| p50 | 0.022 ms | 523.4 ms | 523.4 ms | ~24,000x |
| p90 | 0.049 ms | 798.8 ms | 798.7 ms | ~16,000x |
| p95 | 0.066 ms | 1009.5 ms | 1009.5 ms | ~15,000x |
| p99 | 0.090 ms | 1197.3 ms | 1197.2 ms | ~13,000x |
| max | 0.121 ms | 1421.4 ms | 1421.2 ms | ~12,000x |

Mean: fast 0.026 ms, slow 547.2 ms. Figure: `bench/hebrew-command-bench/results/2026-09-18-path-latency.png`.

### GPU contention (SAM3 vision vs Gemma routing, one GPU)
`contention.py`. SAM3 and Gemma both resident; each latency measured isolated vs under the other's
continuous load; GPU sampled via nvidia-smi.
| component | isolated p50 | under load p50 | slowdown |
|---|---|---|---|
| SAM3 detect | 415 ms | 623 ms | 1.50x |
| Gemma routing | 498 ms | 1258 ms | 2.53x |
IMPORTANT: this is a SATURATION upper bound, NOT the live cadence -- both SAM3 and Gemma were driven
continuously. The real system rate-limits SAM3 to ~1 forward/sec (SCENE_SAM3_PERIOD) and runs Gemma only
per command, so they overlap intermittently and the true contention is LESS than 2.53x/1.5x. The
real-cadence measurement below (2026-09-18) supplies the live figure: routing is ~free. GPU util is 100% on SAM3 alone.
Result + figure: `results/2026-09-18-gpu-contention.{json,png}`. Caveat: laptop GPU; desktop/embedded differ.

## Analysis

1. The dataset bias is confirmed. Off its dev set, the sieve's coverage falls 25% -> 8% and its movement
   recall 34% -> 7.5%; Gemma degrades gracefully 99% -> 85%. The existing dataset flatters the
   deterministic method.
2. Gemma is the accurate classifier at ~87% on unseen Hebrew. The sieve catches ~1 in 8 movement
   commands there, so it is near-irrelevant for accuracy on new input.
3. The sieve is a latency optimisation, not an accuracy mechanism: 0.022 ms vs 523 ms at the median
   (~24,000x). It answers instantly and uses no GPU for whatever it catches.
4. Held-out Gemma failure modes (26 misses):
   - Special verbs are unreachable in Hebrew (~14): follow / come-home / track / scan / orbit / wave /
     gimbal. The router's verb patterns are English, so Hebrew never matches, and Gemma rejects them.
   - Relative / conversational commands rejected (~9): "a bit higher", "closer", "a bit right", "slowly".
   - A few directives mistyped as perception (~3): takeoff, scan returned as "describe".
5. Safety: the utterance "תפסיק לדבר" ("stop talking") tripped the broad emergency regex and would halt
   the drone. The emergency tier is broad by design; this is a false-positive worth tightening.

## Open questions
1. Field command mix: what fraction of real commands are the common, templated ones the sieve catches.
   Requires session data, not a hand-authored set.
2. Whisper (ASR) contention: measured SAM3<->Gemma only; whisper contention still to add (needs the
   persistent whisper-server). SAM3<->Gemma contention is now measured (see above).

## Artifacts
- `bench/hebrew-command-bench/cases_typing_fresh.py` — the held-out 200.
- `results/2026-09-18-type-compare.json` — dev-set accuracy rows.
- `results/2026-09-18-type-compare-FRESH200.json` — held-out accuracy rows.
- `results/2026-09-18-path-latency.json` / `.png` — latency data and figure.
- `type_compare.py`, `type_fresh.py`, `perf.py` — harnesses.

## Status / direction (owner, 2026-09-18; leaning, not final)
Likely move to using Gemma to determine the command layer/type, pending the contention result. This
dataset and benchmark become the regression harness for future comparisons as the system improves.

## Real-cadence contention measurement (measured 2026-09-18, Approach A)

The contention run above is a SATURATION bound (both models flat-out). This measures the LIVE per-command
cost at the real cadence.

Cadence to reproduce:
- SAM3: one forward/sec (SCENE_SAM3_PERIOD=1.0) -> ~415 ms work per 1000 ms, ~40% GPU duty.
- Gemma: one _plan2 per command, swept over realistic inter-command intervals (2 s / 4 s / 8 s).
- whisper: one transcription per utterance (add via the persistent whisper-server; whisper-cli reloads the
  model per call, too noisy to isolate).

Approach A (synthetic, controlled):
1. Background thread runs SAM3.detect() in a loop, sleeping to hold exactly 1 forward/sec.
2. Foreground fires N Gemma _plan2 calls at the chosen interval; time each and tag whether it overlapped a
   SAM3 forward.
3. Time each SAM3 forward too. Sample nvidia-smi util/mem throughout.
4. Report: per-command Gemma latency distribution (p50/p95/p99) at each interval; SAM3 forward latency
   distribution; the % of commands that overlapped a forward; added latency vs isolated.

Approach B (full-stack, most realistic, optional):
- Run mvd.py on webcam+mock (SCENE_TTS=off), inject 20-30 predefined Hebrew commands via the phone-ASR HTTP
  endpoint (POST /input), and read the per-request timings the session trace (trace.jsonl) already records.
  This is the actual app cadence, no synthetic assumptions.

Decision output:
- Live per-command routing latency (vs isolated 498 ms and saturation 1258 ms).
- Per-command SAM3 slowdown when a command overlaps (vs isolated 415 ms).
- Together these price "route everything through Gemma" at the real cadence.

Controls: warm up; deployed model flags; 3 repeats; report medians.

### Result (measured 2026-09-18, Approach A; RTX 5070 Laptop)

Deviation from the plan: I held SAM3 at exactly 1 forward/sec and fired Gemma at a single realistic
gap (1.5 s), not the 2/4/8 s sweep. Per-command latency is set by the SAM3 background duty, not the
command interval, so the sweep adds no signal. Controls: 3 repeats, warmup, deployed flags. 120 loaded
Gemma calls, 246 SAM3 forwards. Harness: `real_cadence.py`.

| path | p50 | p95 | p99 | n |
|---|---|---|---|---|
| SAM3 isolated | 411 | 451 | 461 | 60 |
| SAM3 under load (1/s + Gemma per cmd) | 401 | 413 | 420 | 246 |
| Gemma isolated | 493 | 502 | 504 | 60 |
| Gemma, no SAM3 overlap | 499 | 506 | 508 | 109 |
| Gemma, overlapped a SAM3 forward | 500 | 516 | 516 | 11 |
| Gemma all loaded | 499 | 506 | 509 | 120 |

Overlap rate 9%. GPU util p50 52% (coarse 0.2 s sampling).

Interpretation:
- At the live cadence, Gemma routing costs +6 ms p50 / +5 ms p99 over isolated. Negligible.
- The +760 ms saturation penalty does NOT apply; it needed both models flat-out.
- Only 9% of commands overlap a SAM3 forward. SAM3 (1/sec) and Gemma (per command) share one process
  and largely serialize on the GPU/GIL, so they rarely run at the same instant.
- Even overlapping commands cost only +7 ms p50 / +12 ms p99 vs isolated.
- SAM3 is unaffected (401 vs 411 ms, within noise).

Caveats:
- Synthetic (Approach A). Approach B (full-stack phone-ASR injection, read from trace.jsonl) is the
  most-realistic confirmation and stays optional.
- whisper contention not included (needs the persistent whisper-server).
- Laptop GPU; desktop and embedded differ.

Result + figure: `results/2026-09-18-real-cadence-contention.{json,png}`.

Decision: contention does NOT block routing every command through Gemma. The live per-command cost is
~500 ms whether or not SAM3 runs. The gate for "move command-typing to Gemma" is CLEARED on latency;
accuracy (fresh-200: Gemma 87% vs sieve 12% movement recall) already favored it.

Ruling 2026-09-19 (owner): move command routing/typing to Gemma is APPROVED -- it also matches the
intended production design. Approach B (full-stack contention) and whisper contention are DEFERRED to
production; measuring application-wide contention now adds noise, not signal.
