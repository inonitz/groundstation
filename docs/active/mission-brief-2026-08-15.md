# Mission brief — shared context for all agents (2026-08-15)

**Supersedes `agent1-context-brief-2026-08-14.md`.** This is the single shared context for
the multi-agent effort: the challenge, what's decided, what's open, the plan, and the agent
roster. Read the CURRENT STATE box first — much has changed in 2 days.

## CURRENT STATE — read first

- **The demo is NOT locked.** It is a *design task* driven by the judges' criteria. Do not
  treat any single scenario (e.g. audience-follow) as decided. The secret sauce is the
  *system*, not a canned scene.
- **Platform decided by elimination:** Tello is out (no X/Y position source, VPS false-zeros
  over bare floor). Parrot is out (~20k ILS — enterprise-only since Parrot exited consumer).
  Target = **DJI Mini 4 Pro / Mini 5 Pro**, controlled via **MSDK v5** (Android-only), bridged
  by an **emulated Android kernel in Docker** (research spec: `spec-android-docker-bridge.md`)
  or a cheap dedicated Android device — never a VM emulator gamble, never a phone we interact with.
- **Measure before we rebuild.** The current program is profiled first; its bottleneck decides
  whether we optimize the VLM path or commit to the modular arch. This gates the benchmark and
  modular specs.

## The challenge (MOD) — the demo must hit these

Operate a robot/drone by **natural-language voice** commands against a **live visual scene**:
interpret intent, analyse the environment with CV, execute a physical action.

- **Success = a complex command in an *unplanned* environment** (flagship: "exit through the door").
- **Fixed (thresholds):** runs on **local hardware, no cloud**; **<1 s** from end-of-command to
  start-of-action; platform-agnostic; works under **noise / limited light / dynamic scene**;
  Hebrew support.
- **Scored high:** noise robustness; intent-parse accuracy; visual-parse accuracy; **minimal
  extra hardware**; action-vs-intent accuracy.
- **Scored medium:** understand a **sequence of commands** to build context; low latency.
- **Scored low:** speaker ID.

**Hebrew is deprioritized.** The point is *fast, accurate ASR*, not the language. Demo in
English on Parakeet; Hebrew is a Parakeet-TDT fine-tune + data problem, out of scope for the
deadline. Do not spend the deadline on Hebrew.

## Architecture direction

Hierarchical, VLM-out-of-the-hot-path (the SOTA-endorsed shape): **voice -> intent parse ->
open-vocab perception -> deterministic control**. The heavy image-VLM is *not* in the per-frame
loop; if kept at all, it only parses command text or answers occasional open-ended queries.

- **Perception is general, not an attribute enum.** Ground the command by **embedding the
  command text and each detection into a shared space and matching by similarity** — any
  description, no `{color,gesture,free_text}` taxonomy. Open-vocab detector (YOLO-World /
  Grounding DINO) for described objects; YOLO26 for canonical classes.
- **Tracking = appearance fingerprinting.** Replace the weak tracker: each detection -> a
  **Re-ID feature vector (fingerprint)** in a **vector index (ANN / cosine similarity)** — a
  hash-table for identities that survives occlusion + re-entry. Selection and tracking share
  the one embedding space.
- **Control** rides the resolved track_id by bearing (errX/errY) + apparent size from a hover —
  no absolute position needed (survives a position-limited drone indoors).

## Plan & priorities

**NOW (human + main session; all agents on standby):**
1. **Measure the current program** — instrument the VLM path + profile hot loops; find the real
   bottleneck. Make/break for whether the modular arch is even needed.
2. **Cleanup:** split `fmu_node.hpp` (183 KB, ~20x the review ceiling — map in
   `fmu-node-split-map.md`); remove dead/abandoned-demo code (ask before stripping commented
   blocks); dedupe genuine repetition; **prune useless tests**; **augment `code-guidelines.md`**
   with an explicit principles apply/skip map.

**PARALLEL RESEARCH (now, non-colliding):** Android-kernel-in-Docker bridge feasibility
(`spec-android-docker-bridge.md`) — an agent spins this up in the background.

**BENCHED (agents wait until NOW is done):** benchmark harness, modular-perception, drone backend.

## Agent roster (on standby)

Each inherits this brief. **No agent runs git. Use `rtk` for reads/greps. Follow
`code-guidelines.md`. No virtual dispatch, no exceptions — CRTP + tagged dispatch. <1 s via
stream-first-action, not a bigger model. Don't touch another agent's files; the SEARCH/APPROACH
FMU branches are LOCKED (pull before touching).**

- **Agent-Bench** — benchmark & metrics harness (SITL): SR, grounding, validity, latency; the
  judge table; VLM-vs-modular comparison. Does **not** own `scripts/test` (test pruning is cleanup).
- **Agent-Percep** — open-vocab grounding + Re-ID fingerprinting (above): command+detection ->
  shared embedding -> matched track_id + bearing/size for FOLLOW. New module under
  `source/llm_to_action/perception/`; test on recorded frames + SITL vs "correct target among N".
- **Agent-Backend** — `DroneBackend` CRTP impl for DJI (telemetry->Odometry, setpoint->virtual
  stick, video path). Benched until the drone lands; the Docker-bridge research is its precursor.
- **Agent-Latency** — VLM_PROF + `stream:true` first-action for <1 s. May fold into Bench or Percep.

## Hard rules (all agents)

- **Human owns the entire git workflow** — no `add`/commit/push/stage. Suggest commands + a
  house-style message; the human runs every git write.
- **Reads/greps via `rtk` wrappers**, not native tools.
- **`code-guidelines.md` is law**, including the principles map: KISS/YAGNI yes; **composition
  almost-always-preferred**; **DRY only for genuinely shared data/rules, perf-neutral, and only
  if it aids readability**; no SOLID-via-virtuals; no forced abstraction; flat structs + direct
  access are deliberate.
