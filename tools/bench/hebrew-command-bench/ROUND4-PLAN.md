# Round 4 — RUN COMPLETE 2026-09-01. Results in README.md (round-4 section) + results/2026-09-01-round4-results.json + perception-dump.md. Open rulings listed at the bottom still stand.

State: rounds 1-3 done (README has results; round-3 = 190 cases, 8 arms, dicta->qwen-fs 176/190
(93%) wins translators, McNemar beats opus 42-10 p<1e-4, ties EN ceiling p=0.39). ASR round
queued AFTER owner reviews round 4. Owner gates every benchmark on an up-front duration estimate.

## Round-4 arms (estimate ~25-30 min, given before start per owner rule)
1. production-prompt x qwen2.5-coder-1.5b  — the app's EXACT "Deep Think" PLANNER path
   (NOT a translator — owner correction; same seat as Qwen3-VL). Model:
   /root/models/translate/qwen2.5-coder-1.5b-gguf/qwen2.5-coder-1.5b-instruct-q4_0.gguf
2. production-prompt x Qwen3-VL-4B
3. improved-prompt x Qwen3-VL-4B  (new ceiling)
4. improved-prompt x dicta pipeline (DictaLM-3.0-1.7B translate [2-shot+line-grammar] -> plan)
5. TranslateGemma-4b-it lane (Google 2026-01):
   /root/models/translate/translategemma-4b-it-gguf/translategemma-4b-it.Q4_K_M.gguf
6. ~40 authored complex-perception commands (highlight/track/count + attributes + spatial),
   scored by KEYWORD PRESERVATION (entities/attributes/spatial terms w/ synonyms) + full
   translation dump for owner eyeball; BLEU rejected as opaque.
7. latency-vs-length curve per stage (round-3 finding: e2e corr r=.98 with OUTPUT chars,
   ~5ms/char generation; long INPUT is cheap prefill — perception commands are the cheap direction).

## The improved prompt (build it from these measured deficits)
- SWITCH SCHEMA TO PRODUCTION: fly_by uses dx/dy/dz (+optional velocity -6..6), NOT x/y/z.
  Verified: app FlyBy.kt AND projects/integration_harden/dji_wire.py:142 both speak dx/dy/dz.
  Rounds 1-3 used x/y/z (internally consistent, relative results stand, absolute schema wrong).
- Production prompt found: exoskeletons SpeechResolving.kt:599-635 ("speech-to-intent engine",
  rules, semantics incl "x then y = multiple actions" hint, # Available Actions = JSON Schemas
  auto-generated from Kotlin action classes w/ per-field comments dx:"x+ is forward" etc).
- Its gaps = our measured failure classes: (a) NO verbal->sign map — MUST add
  "right turn = clockwise = positive degrees" (7/14 of round-3 top-arm fails were turn-right -> -N);
  (b) no negation/question -> [] rule; (c) no few-shot. Add 6 shots (5 from run_bench.py
  PLANNER_SHOTS + new "turn right 20 degrees" -> +20), keep production scaffold.
- Few-shot = N complete user->assistant example pairs + real query last; one prefill, one inference.

## Standing rulings (owner, this session — do not re-ask)
- 12B dicta: excluded. W4A16/vLLM: excluded (no new deps). madlad: parked (T5-gguf serving garbage).
- Cases: realistic > synthetic; grid generation allowed but balance with authored natural speech.
- Stats: percentiles as COLUMNS p25/50/75/95/99/max, runtime AND accuracy (Wilson+bootstrap),
  paired McNemar for rankings; temp-0 determinism PROVEN (10 identical reqs -> 1 output) so
  repeats add nothing, case count is the lever.
- Strictly sequential GPU (one model resident), no CPU fallbacks; bench manages its own
  llama-servers; announce any process left running at turn end.
- ASR round (after review): ivrit-ai whisper-large-v3-turbo via (a) CT2+VAD, (b) whisper.cpp
  Q4_K_M in our asr_server, (c) sherpa-onnx GPU + CPU. Accuracy vs an ivrit-ai public eval set
  (owner has no dataset). On-disk: /root/models/asr/ivrit_ai/whisper-large-v3-turbo (HF + ggml).
- GIT: owner runs ALL writes. The 2026-09-01 override was SINGLE-TURN, consumed. NEVER git add -A
  (it swept the owner's in-progress CMakeLists edits into dcf4a25 — see below).

## Open items owner has NOT ruled (still open)
- dcf4a25 keep-or-unwind (it contains owner's CMake edits swept by my add -A; unwind block was
  provided in chat: reset --mixed HEAD~1, re-add only the 4 A-work files).
- Formal adoption of DictaLM as backlog-B translator (measured winner; recommendation only).
- Hebrew Tier-1 short-imperative fast path in integration_harden (המראה/נחת/land-now class —
  failed in EVERY pipeline; deterministic regex territory).
- Whether bench work since round-1 is committed (commit blocks were provided in chat; check
  git status/log before assuming).

## CPU-offload lane (owner flagged 2026-09-01, staged — not yet run)
If GPU residency gets contended (translator + planner + ASR all resident), bench the chosen
translator CPU-only: llama.cpp CPU threads vs an onnxruntime export (optimum for seq2seq,
sherpa-onnx already staged for the ASR round). This machine's CPU is fast; production hardware
may not be — measure on both before relying on it. No new deps installed until the owner
greenlights the specific runtime.
