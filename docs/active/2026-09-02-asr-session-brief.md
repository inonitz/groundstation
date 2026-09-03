# ASR session brief — for the delegated agent (written 2026-09-02, owner-commissioned)

You are a measurement agent on the groundstation repo, tasked with ONE thing: the ASR round.
Read before anything, in this order:
1. docs/active/2026-09-02-manager-handoff.md — protocol, rails, measurement method.
2. docs/active/2026-09-02-state-and-next.md — current system state and the rulings in force.
3. tools/bench/model-cpu-or-gpu/README.md and RECORDING-SPEC.md — your workbench.
4. tools/bench/hebrew-command-bench/README.md — a FINISHED scorecard: mirror its structure,
   register, and statistics in yours.
5. docs/writing-style.md (result-doc register) and docs/code-guidelines.md (commit style
   for the blocks you suggest). CLAUDE.md binds you fully:
RTK wrappers for every read/search, NO git writes (suggest commit blocks, the human runs them),
no drone commands ever, decisions into repo docs the same turn they are ruled.

## Objective

Pick the ASR for the Hebrew voice loop: whisper.cpp quant ladder (q4_0/q5_1/q8_0, staged) vs
the wav2vec2 + pyctcdecode/KenLM challenger (downloaded). Output: a measured scorecard and a
recommendation — the OWNER decides. Recommendations are not decisions.

## System context

Chain: ASR => Recognizer => VLM/LLM => REST API. The Recognizer is measured (301/364, commands
at the planner ceiling) and integrated behind the router; the E2E Hebrew text path was verified
against the mock on 2026-09-02. ASR is the missing measured link. GPU budget: Qwen3-VL + OmDet +
SAM2.1 + ASR = 5.5/8 GiB measured — the ASR slot is ~0.1 GiB on GPU, or CPU. One model
resident on the GPU at a time during measurement.

## Gates (in order, before any measurement)

1. Scripted installs for faster-whisper and pyctcdecode + kenlm: add to
   tools/devenv/Dockerfile (ruling 2026-09-02: deps bake into the Dockerfile;
   tools/devenv/install-runtime-deps.sh is only the stopgap for running containers).
   The container wipes ad-hoc installs — never install by hand without scripting it.
2. Team recordings per tools/bench/model-cpu-or-gpu/RECORDING-SPEC.md. No synthetic-only
   corpus: canned audio proves nothing about our speakers.

## Method (non-negotiable, from the handoff)

- Deterministic decode (greedy/temp 0), one pass per case; case count is the confidence lever.
- Wilson 95% intervals; exact McNemar for model pairs; latency percentiles (p25/p50/p75/p95/max)
  as table columns. Duration estimate stated BEFORE every run.
- Primary metric: WER on the team recordings. Secondary (the one the owner cares about):
  feed each model's transcripts through the Recognizer and report the E2E outcome delta —
  a transcript error that the sieve absorbs is not a real error.
- Full result tables in chat, never abbreviated. Raw per-case JSON to results/ files.
- After any refactor of measured code: re-run and compare counts before claiming equivalence.

## Privacy rail (hard)

ASR recordings and transcripts hold real speaker names and voices. They NEVER enter git —
keep bench_out/ and every audio/transcript dir gitignored, and verify with git status before
suggesting any commit.

## Deliverables

1. Scorecard README in tools/bench/model-cpu-or-gpu — senior-engineer register
   (Objective/Setup/Results/Analysis/Conclusions), updated in place, history to results/.
2. Raw run JSONs under results/ with every input/output pair.
3. docs/active/2026-09-02-state-and-next.md updated with the outcome + open decisions.
4. Suggested commit block(s) in the house style. The human runs all git.

## Owner protocol (audited)

Answer every numbered point by number; never fuse or skip. Label every unmeasured number
"unverified". Lead with disagreement when you have it. Background output to files, short
summaries + full tables in chat.
