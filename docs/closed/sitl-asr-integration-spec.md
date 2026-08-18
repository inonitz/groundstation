# ASR integration — one-hour finish (owner: agent + human)

**Date: 2026-08-12** · Deadline: Wed evening 2026-08-12. Demo MUST include voice.

**Reality check — the node is already built.** `source/llm_to_action/asr/asr_node.cpp` captures on a
push-to-talk key, resamples, runs Parakeet-q4, and publishes the transcript on
`/asr_server/transcribe` (`asr_node_base.hpp`, `std_msgs/String`). It logs `>>> TRANSCRIBED (Xms)`.
`scripts/simenv.sh` already points at the parakeet-q4 model; `devenv.sh` mounts `/root/models/asr`.
Do NOT rebuild any of this.

**The only real gap: nothing consumes the transcript.** The FMU still reads its objective from
`argv[1]` (`fmu_node.cpp:35`). The transcript is published into the void. Closing that seam, plus two
tiny enables, is the whole job — and it fits in an hour.

**Precondition work (DONE, do not redo):** Parakeet-q4 on raw audio is the model; no denoise; confidence does NOT gate accuracy (tested — the model scores wrong transcripts higher than right ones, so operator read-back replaces it); noise filtering (GTCRN / SpeexDSP / classical) all tested net-negative, so raw audio ships; VLM cold first-plan (~27 s) is cut to ~9 s by a boot warmup.

## REQUIRED reading (process, before any code)

`docs/active/sitl-orchestration-plan.md` (the whole plan + the LOCKS protocol + the commit rules),
`CLAUDE.md` (RTK wrappers, economy, NO git writes), `docs/code-guidelines.md` (house code style +
commit message style), `docs/writing-style.md` (prose for your Report and commit bodies),
`docs/project_overview.md` and `docs/ARCHITECTURE.md` (system context: where the FMU objective seam and
the VLM sit), `docs/NOTES.md` (grep `ASR` / `VLM` / `VRAM` for prior gotchas), `docs/LOCKS.md` (acquire
the `fmu_node.hpp` lock before editing it). Docs drift — trust the code over the docs and flag any
mismatch in your Report.

## The hour (three code steps)

**Step 1 — operator read-back, NOT a confidence gate (~10 min).** The "ask again if confidence low" idea was tested and killed: on 44 clips, token-probability confidence does not track correctness — failing transcriptions averaged cf 0.971 vs 0.964 for passing ones, and no threshold separates them. Do NOT gate on confidence for accuracy. Instead echo the transcript for a human to confirm before it runs: on each transcript, log it prominently (`[ASR] heard: "<text>" — <key> run / <key> redo`) so a mis-hear is caught before the drone acts. That is the reliable safety net for a noisy room. (Want the confidence number for logs only? The fork stores the raw logit in `.plog`, so use `.p`; blanks are never in the token list, nothing to filter.)

**Step 2 — FMU consumes the transcript (~25 min).** In `fmu_node.hpp`, add a subscription to
`/asr_server/transcribe` (`std_msgs/String`). In the callback: if `FlightState == STANDBY`, call
`start(text)` to launch the mission from the spoken objective; if already flying, route `text` into the
existing re-plan path (the same seam `callLlamaServer` uses for re-assess) so a spoken command replans
mid-flight. Lock `fmu_node.hpp` in `docs/LOCKS.md` first — Agents 0/1/2 also touch it; keep the hold
short. This is the seam that makes the demo voice-driven.

**Step 3 — co-residency + prewarm + launch (~20 min).** Parakeet-q4 (~400 MB) now shares the 4 GB GPU
with the VLM. Drop the VLM context so both fit: set `VLM_CTX_SIZE` low (start 1024, the old co-run
value) in `scripts/test/lib/sim_core.sh` / `simenv.sh`. Add a boot-time warmup request to `llama-server`
(one throwaway `/v1/chat/completions` with the system prompt) so the first real plan is ~9 s not ~27 s.
Make sure the ASR node is actually launched in the SITL harness (it is wired in `simenv.sh`; mirror it
into the test launcher if missing).

## Tests — the clock (three tiers, ~30 min total)

**Simple (5 min) — ASR alone.** Launch just the ASR node. `ros2 topic echo /asr_server/transcribe`.
Press the PTT key, speak "hold position". Transcript appears on the topic and is echoed as `[ASR] heard: "..."`. Pass = transcript published + read-back line shown.

**Not-so-simple (10 min) — FMU consumes it, both models resident.** Bring up the FMU + llama-server
headless (no drone). Publish or speak a transcript; confirm the FMU logs `Mission started ... objective:
<the spoken text>` from the topic, not from argv. In parallel watch `nvidia-smi`: VLM + Parakeet both
resident, no OOM; total app RSS < 8 GiB. Pass = spoken text drives the FMU objective with both models
co-resident.

**Full demo (15 min) — end-to-end voice hat-follow.** Full SITL stack. On the ground, press PTT and
speak "find the person in the hat and follow them". The transcript reaches the FMU, the VLM plans, the
drone takes off and runs FOLLOW on the hatted target. Speak the objective **before takeoff** — prop
noise wrecks in-flight capture, and this is the physics limit, not a code bug. Pass = a spoken sentence
flies the hat-follow demo with no typed objective.

## Files

Change: `asr_node.cpp`, `asr_node.hpp`, `asr_node_base.hpp`, `fmu_node.hpp` (+ maybe `fmu_node.cpp`),
`scripts/test/lib/sim_core.sh`, `scripts/simenv.sh`, `config/*.yaml` (threshold + `VLM_CTX_SIZE`).
Read first: the full `asr_node.*`, `fmu_node.hpp` `start()` (`364`) + `callLlamaServer`/re-assess path,
`asr_node_base.hpp`, `simenv.sh`.

## Constraints

Both models must fit 4 GB VRAM; total app < 8 GiB. Speak the objective on the ground. No git writes —
suggest atomic commits (`asr: transcript read-back`, `asr: fmu consumes transcript`,
`asr: vram refit + vlm prewarm`). Prose per `docs/writing-style.md`.

## Report
_(append: chosen `VLM_CTX_SIZE` + measured VRAM/RSS, prewarm before/after,
which test tiers passed, blockers)_
