# ASR integration — voice objective into the FMU (owner: agent + human)

**Date: 2026-08-12** · Deadline: Wed evening 2026-08-12.

**Mission**: wire the already-built speech-to-text stack into the drone command path, so a spoken
objective ("find the person in the hat and follow them") reaches the VLM planner the same way a typed
one does. The model selection and measurement are DONE — this spec is integration, not research.

## Precondition work — DONE (do not redo)

Measured in `sttserv` (`bench.sh`); full write-up in that repo's README. Settled:
- **Model: Parakeet TDT 0.6B v3, q4_k, on RAW audio.** ~0.15–1.5 s/clip (median 0.59 s), 397 MB,
  best pass rate. whisper-large models are ~12× slower for no gain.
- **No denoise.** GTCRN speech-enhancement in front of Parakeet is net-negative (37/44 → 27/44); it
  cannot recover speech that noise has drowned. Ship raw audio.
- **Loudness handling = ASR confidence, not SNR.** Gate on decode confidence and ask the speaker to
  repeat; do not SNR-gate a denoiser.
- **VLM first-plan latency** is prefill-bound (~27 s cold). A warmup request at server boot (or
  `--prompt-cache`) prewarms the system-prompt KV → ~8–10 s. Identified, not yet wired.

## REQUIRED reading

`docs/active/sitl-orchestration-plan.md`, `CLAUDE.md`, `docs/code-guidelines.md`,
`docs/writing-style.md`. Study the OLD reference node on the other branch — it already did capture +
transcribe + publish and is the template to port from, not reinvent:
`git show feature-showcase-v2 -- <path to speech_to_action>` (locate it with
`rtk git ls-tree -r --name-only feature-showcase-v2 | rtk grep -i speech`). Study the sttserv library
surface (`sttserv/include/sttserv/`: `backend.hpp`, `audio2.hpp`, `async_key.hpp`) and how the FMU
takes an objective today (the keyboard/objective path into `buildDynamicPrompt` / `userQuery`).

## Do

1. **ASR node.** Bring sttserv into the ROS graph as a node: push-to-talk key → capture → Parakeet-q4
   transcribe (raw audio) → publish transcript + confidence. Port from the old `speech_to_action`
   node; keep it lean. Parakeet-q4 shares the 4 GB GPU with the VLM, so it must not blow the budget.
2. **Confidence gate + ask-again.** If decode confidence is below threshold, do not forward the
   transcript — prompt the operator to repeat (TTS beep or a printed line is fine). Threshold is
   tunable via config.
3. **Transcript → FMU objective.** Wire the accepted transcript into the FMU as the objective/userQuery,
   the same slot a typed goal uses. One clean seam; do not duplicate the planning path.
4. **VLM VRAM refit.** `scripts/test/lib/sim_core.sh` runs the VLM at `-c 8192`. With Parakeet-q4
   (~400 MB) co-resident, re-fit both on 4 GB: shrink `-c` (the old co-run used `-c 1024`) and measure
   VRAM + total RSS. Deliver the `-c` value that holds both without OOM. Keep the change env-tunable
   (`VLM_CTX_SIZE`) so it is one flag, not a rebuild.
5. **VLM prewarm.** Add the boot-time warmup request (or `--prompt-cache`) so the first real plan is
   ~8–10 s, not ~27 s. Measure the before/after.
6. **Listen-mode decision (write it down).** Push-to-talk (key → listen → transcribe) is the default
   and enough for the demo: one objective at the start. An always-on VAD background listener is only
   needed for barge-in commands ("stop"/"halt") mid-flight, and it costs a constantly-running capture +
   VAD. Recommend push-to-talk for Wednesday, VAD as a stretch, and state which you built.

## Tests (with the human)

Speak an objective → transcript appears with a confidence number → a low-confidence mumble triggers
ask-again → a clean objective reaches the FMU and the VLM plans from it. Confirm VLM + Parakeet both
resident on the 4 GB GPU with no OOM, and first-plan latency improved by the prewarm.

## Locks (docs/LOCKS.md)

`scripts/test/lib/sim_core.sh` (VLM flags — Agent 1 may also touch it; short hold). New ASR node files
are yours alone. The FMU objective seam touches `fmu_node.hpp` — coordinate with Agents 0/1/2 there.

## Constraints

RAM budget is hard: total app must stay under 8 GiB and both models must fit 4 GB VRAM — leanness wins.
No git writes — suggest atomic, agent-labelled commits (`asr: node + transcript wiring`,
`asr: vlm vram refit + prewarm`). Prose per `docs/writing-style.md`.

## Report
_(append the chosen `-c` value + measured VRAM/RSS, prewarm before/after, listen-mode built, blockers)_
