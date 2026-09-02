# State and next points — written 2026-09-02 ~04:00 for the owner's morning

Everything below is measured unless labeled otherwise. All bench work is UNCOMMITTED as of
this writing — commit block at the bottom.

## What stands (the numbers that matter)

- Winning config (round 6): SPLIT — DictaLM for commands (94.2%), TranslateGemma for
  perception (78%, 96% of keyword groups). Control: 99.5% / 100%.
- Refine idea: measured and rejected (66% vs 78%, p=0.043, slowest).
- Direct-Hebrew planning on DictaLM (new tonight): 88.4% after 3 quick iterations, vs 94.2%
  pipeline (p=0.043). Trade: −5.8 pp for a translation-free, 1.6 GiB, CPU-capable command path.
- VRAM census (8 GiB RTX 5070 Laptop): qwen3vl 3.8 GiB / tgemma 3.0 / dicta 1.6.
  qwen3vl+tgemma DOES NOT FIT together. DictaLM on CPU: p50 199 ms — passes any voice budget.
  TranslateGemma on CPU: p50 624 ms — fine only for non-inner-loop perception commands.
- Military phraseology (20-case probe): acronyms and procedure words die in every model
  (עבור, רות, נ.צ., כטב"ם); TranslateGemma reinterprets dangerously. Deterministic Tier-1
  glossary after ASR is the confirmed fix direction; fine-tuning is third in line.

## Where everything lives

- tools/bench/hebrew-command-bench/ — 4 files (bench.py / prompts.py / 2 case files), README
  has run+modify docs and all round tables. `bench.py` reproduces the round-6 table;
  `--slang`, `--direct`, `--audit`, `--smoke`, `--refine` are the lanes.
- tools/bench/serving-bench/ — census.py + results (VRAM/CPU numbers), RECORDING-SPEC.md +
  RECORDING-SCRIPT.md (65 sentences for the team, 4 envs, outdoor-wind first).
- docs/research/2026-09-02-hebrew-intent-parsing.md — parser-replacement lane + candidate ladder.
- docs/research/2026-09-02-finetune-data-plan.md — dataset sizes/structure, ASR-abbreviation
  mitigation ladder (answers to the owner's fine-tuning questions).

## Open rulings (owner) — nothing below is decided

1. Adopt the SPLIT in production? (my recommendation: yes) And given the census, its
   topology: tgemma on CPU for perception (0.6–1.2 s) vs dicta-everywhere vs direct-Hebrew.
2. Adopt the revised prompt in the phone app (56%→94% on its own engine, prompt-only change).
3. Direct-Hebrew lane: accept 88.4% now, or push more shots / LoRA (~1–5k pairs) first?
4. Tier-1 glossary/canonicalizer build (Hebrew short-imperatives + military lexicon) — the
   cheapest confirmed win, sits after ASR, fixes ASR+MT in one layer.
5. dcf4a25 keep-or-unwind (owner's swept CMake edits; unwind block was provided in chat).
6. DictaLM-Thinking download for the parser ladder (~1 GB pull, needs scripted install).
7. ASR round go: needs faster-whisper + sherpa-onnx scripted installs, ivrit-ai eval set
   download, and the team's recordings (spec ready).

## Suggested next-session order

1. Owner rules on 1–3 (they gate integration work).
2. ASR round prep: scripted installs + run whisper serving comparison on the public ivrit-ai
   eval set while waiting for team recordings.
3. Tier-1 glossary implementation in integration_harden (deterministic, no model risk).
4. Census part 2: OmDet+SAM2.1 vision pair (needs smart-scene env) to finalize the topology.
5. Backlog C (Qwen decomposition wiring) and D (TTS out) resume once B's adoption is ruled.
