# Agent 1 — FOLLOW verb (Demo A)
**Date: 2026-08-11**


**Mission**: implement a `follow` verb — a position-free visual servo that holds a fixed standoff on a
VLM-chosen target and keeps it centered — and prove it in SITL with a moving target. It is a near-copy
of APPROACH; keep it simple.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + coordination + LOCKS +
commit rules), then `CLAUDE.md`, `docs/code-guidelines.md`, `docs/writing-style.md`. Study the code:
`fmu_node.hpp` APPROACH branch (`792-955`) + `activateTask` (`~1648`) + parser loop (`~1943-1990`);
`source/llm_to_action/perception/detection_query.hpp` (`detectionByLabel:49-81`, `TargetRelative`);
`llm_base.hpp` verb specs + `buildDynamicPrompt` `[PERCEPTION]` block (`~1777-1793`);
`llamaclient.hpp buildPlanGrammar` (`111-132`). Grep `docs/NOTES.md` for approach/orbit/follow.

**Your place in the plan**: demo-critical. Independent — start now. Manual-fly tests need Agent 0's
keyboard fix; until it lands use `ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data:true}"`.

## Design (instance selection = VLM returns an index)

Detections carry no stable id, so resolve the VLM's `target_index` ONCE at activation to a label + bbox
center, then track by nearest-centroid each tick. APPROACH closes to standoff and completes; FOLLOW
holds standoff and never completes. The servo is vision-based (bbox/depth), so it works on the Tello
even though `od.pos` is zero there.

## Build

1. `CmdFollow{ i32 target_index; i32 standoff_cm; i32 speed; }` near `CmdApproach` (`fmu_node.hpp:126`);
   add `CommandID::FOLLOW` to enum (`105-118`), union (`136-158`), id-ctor (`160-181`).
2. Grammar: add `"\"follow\""` to the verb enum in `buildPlanGrammar` (`llamaclient.hpp:111-132`).
3. Prompt: `follow` spec after `approach` in `kSystemPrompt` (`llm_base.hpp:~63`):
   `{"action":"follow","target_index":<int>,"standoff_cm":<int>,"speed":<int>}`. In the `[PERCEPTION]`
   block of `buildDynamicPrompt` (`fmu_node.hpp:~1777`), **add an `index` field to each printed
   detection** so the VLM can reference one.
4. Parser branch `else if (action=="follow")` (`fmu_node.hpp:~1963`).
5. `activateTask` case (`~1648`): resolve `target_index` on `snapshot()` → store `m_followLabel` +
   `m_followLastCenter`; reset lost timers.
6. New matcher in `detection_query.hpp`: `detectionNearestCenter(snap,label,lastCenterPx,cam,now)` —
   among label matches pick the bbox nearest `lastCenterPx`; back-project to `TargetRelative`.
7. Control branch after APPROACH (`~955`): snapshot → `detectionNearestCenter` → update
   `m_followLastCenter`; `yawRate=-kApproachYawGain*errX`, `vUp=-kApproachVertGain*errY`,
   `spF=kFollowFwdGain*(range-standoff)` (ALLOW negative — back off when too close);
   `flu_to_enu({spF,0,vUp}, od.yaw)` → `set_velocity`. On target-lost: coast-then-hover (reuse
   APPROACH's lost logic) and **never `completeCurrent`** — FOLLOW runs until re-assess/stop.
8. Constants `kFollowStandoffM / kFollowFwdGain / kFollowLostTimeoutMs` (`fmu_node_base.hpp`), reuse
   `kApproachYawGain`/`kApproachVertGain`; add `followStandoffM` to `drone_config.hpp` + `config/*.yaml`.
9. **Moving-target world**: add a simple Gazebo mover (a person/box translating left-right or randomly
   within a cone) to a SITL world for testing.

## Tests (manual-verify OK; automated nice-to-have)

- Target moves → drone follows, holds standoff, keeps it centered (errX/errY → 0), backs off when close.
- You fly the drone manually → it re-centers on a static target.
- Debug FOLLOW ENTIRELY here (not in the dashboard agent's scope).
Run via `scripts/test/SITL/<your-scenario>/run.sh` (paths fixed by manager). Grammar already enforces
`follow` as a valid verb once you add it to the enum.

## Locks (docs/LOCKS.md — acquire before editing, release right after)

`fmu_node.hpp`, `fmu_node_base.hpp`, `llm_base.hpp`, `llamaclient.hpp`, `detection_query.hpp`. New world
files and any new test script are yours alone (no lock).

## Constraints

Concise intentful code, comment only the non-obvious. No git writes — suggest an agent-labeled commit
(`agent1: follow verb + control`) when a unit is done. Prose per `docs/writing-style.md`.

## Report
_(append findings / blockers / decisions below)_

---

## Recovery checkpoint — 2026-08-12 (agent1)

This section is the durable source of truth for resuming FOLLOW/HOVER/SEARCH/tracker/grammar/perception
work. A fresh session should be able to continue from here alone, plus the code.

### Current state, one line
FOLLOW flight logic is solid (locks, tracks, no spinning). Every open risk is now the VLM brain
(Qwen3-VL-2B on a 4 GB GPU): speed and reliability, not the flight code.

### DONE (landed; px4 + tello both build clean)
- **FOLLOW verb** — position-free yaw-only visual servo. Hovers in place, yaws (+ vertical) to keep the
  target centred. Forward is hard-clamped ≤ 0 (never advances); it backs off only if range < standoff.
  `standoff_cm` = MINIMUM SAFE distance. Never self-completes.
  - Target resolution happens ONCE at activation, against the frozen prompt frame (`m_lastPromptTracked`):
    prefer VLM `track_id` → `target_index` → **centre-detection fallback** (nearest box to frame centre).
  - Per-tick tracking is by **label + nearest-centroid** with a jump gate — NOT by track_id. The id only
    picks the target once.
  - Yaw gain `kFollowYawGain = 5.0`, capped at `kFollowYawMaxRps = 1.5`.
  - Loss behaviour = **HOLD + re-acquire** (see gotcha below). The sweep-to-last-seen was removed.
- **HOVER verb** — persistent hold, never completes, never wakes the VLM.
- **SEARCH-by-tag** — `CmdSearch.target_id`; on a find, logs `SEARCH DETECTED ... track_id=N`.
- **Stable-id tracker** — `perception/target_tracker.hpp` (greedy IoU+centroid, coast `maxAgeFrames = 15`,
  monotonic never-reused ids). Wired into `perception_runtime` (`publish()` runs it, atomic-stores the
  `TrackedSnapshot`; `snapshot()` is an aliasing ptr into it; `trackedSnapshot()` returns it). Drawn on
  the annotated frame. Unit test `fmu/test/target_tracker_test.cpp` (7/7 green via g++).
- **Grammar hardening** (`llamaclient.hpp` `buildPlanGrammar`) — members are TYPED per key (kills the
  free-form `{"parameters":"x: 0,..."}` blob that parsed every field as its default); one verb list that
  never contains `takeoff` (the only takeoff is the pinned first element of a grounded plan); `hover` added.
- **Perception robustness** (`fmu_node.hpp buildDynamicPrompt` + `maybePlan`) — the `[PERCEPTION]` block
  COASTS a blank frame (feeds the last-seen detection if it was within `kPerceptionCoastMs = 1500`), and
  the FIRST plan waits for the first real detection (`kPerceptionWarmupMs = 6000`). Zero-vector `go` is
  dropped in the parser.
- **Prompt** (`llm_base.hpp`) — rules 10 (holding/objective-complete), 11 (target-visible → follow, plan
  only what remains), 12 (never guess a track_id; act on `search_ok`).
- **VLM infra** — the llama-server OOM on the 4 GB GPU is fixed by running it with `--parallel 1 -c 4096`
  (drops n_slots 4→1 and ctx 8192→4096; that is an 8× cut in KV-cache VRAM). It then survives the run.
- **Tooling** — `scripts/test/SITL/logtest.sh` (unique timestamped logs under `runs/`, `hires` option),
  `digest.sh` (self-reporting: outcomes, responsiveness, HUD perception, what the VLM was told, empty-
  response count, action timeline), `TESTING.md`, `crowd/` (three_people world), `search_follow/` (drone
  faces away → forces a search), `follow/watch.sh`; `dependencies/three_people.sdf`.

### Gotchas / reasoning (why things are the way they are — read before changing)
1. **FOLLOW is yaw-only on purpose.** It was first built translating toward the target (like APPROACH);
   that is wrong for "follow in place". It hovers and turns its head. Forward is clamped ≤ 0.
2. **The loss-sweep was REMOVED (do not re-add naively).** On a lost box it used to yaw open-loop toward
   the last-seen side for up to 4 s → up to ~137° of rotation → the drone spun in circles. Root cause:
   detection FLICKERS (~20 % of frames blank even while the person is centred and in view), so a "loss"
   is almost always a flicker, not a real exit; and in these scenarios the person paces WITHIN the FOV and
   never actually leaves. Sweeping then points the drone away from someone still there → more gaps → a
   self-feeding spin. Current behaviour: on any gap, HOLD (zero velocity) and re-lock when the box returns.
   A real look-where-lost needs non-flickery detection to gate it (only sweep when the target was near the
   EDGE when lost); left out until detection is reliable.
3. **[PERCEPTION] must coast blank frames.** The block was built from the raw current-frame detections,
   so a flicker/warm-up frame told the VLM literally `(no detections)`. The 2B believed it and started
   searching. The coast (feed last-seen < 1.5 s) + first-plan-waits-for-detection stopped the false search.
4. **Centre-detection fallback exists because the 2B guesses track_ids that don't exist** (it emitted
   `follow track_id=0/1/10` when the real id was different) → `follow_no_target` loop. The fallback locks
   the nearest-centre person so a single-target follow never needs a correct id; a valid id is still
   honoured when the VLM supplies one.
5. **Zero-`go` is dropped, not converted to hover.** It was briefly converted to a persistent HOVER, which
   STARVED any `follow` queued behind it (hover never completes) → the drone hovered instead of following.
6. **VLM "not visible" hallucination — UNSOLVED at the model level.** Even with a person clearly in
   `[PERCEPTION]` (JSON with track_id/label/conf), the 2B sometimes reasons "person is not visible → search".
   Prompt rule 12 reduces but does not eliminate it. An FMU-side guard (drop a `search` when the objective
   is follow and a person IS detected) is the deterministic fix — PROPOSED, not built, awaiting the human.
   **Do NOT** re-add the "VISIBLE NOW" directive in the perception block or shrink the VLM image — the human
   explicitly rejected both (biasing the model / degrading what it sees). Those were reverted.
7. **errX still spikes ~0.96 on the worst gaps.** The yaw servo is a P-controller (yawRate = −gain·errX);
   gain went 1.0 → 3.0 → 5.0 to cut the steady-state trailing (at gain 1 it trailed to ~0.6 constant).
   During a detection gap it HOLDS (no yaw), so the person drifts to the edge, then re-locks at high errX.
   Reducing this further needs either less-flickery detection or coasting the servo on the last aim through
   a gap (not done — HOLD was chosen for safety).
8. **VLM speed is the top demo risk and is UNSOLVED.** On the 4 GB GPU, prompt processing is ~28–30 s
   (≈111 tok/s) for a ~3341-token prompt, ~2048 of which are the 640×640 image. That was `task 0` (includes
   one-time graph compilation); steady-state was never measured because the server OOM'd after one call
   before `--parallel 1 -c 4096` was applied. For FOLLOW this is a ONE-TIME cost (the VLM plans once, then
   the servo runs in-FMU forever), so a single ~30 s "thinking" beat after the command, then smooth
   following. Fixes considered and REJECTED by the human: image 640→448, a perception directive. Remaining
   honest levers: pre-warm the server before the demo; measure steady-state (task 2+); or better GPU.
9. **Tracker coast is 15 frames** (was 5). With 5, a single actor's id churned 13→50→86 as detection
   flickered. 15 keeps the id stable across blinks; association still gates on label+geometry so a genuinely
   new person does not inherit a coasting id.

### Files changed by agent1
`source/llm_to_action/fmu/{fmu_node.hpp, fmu_node_base.hpp, llm_base.hpp, llamaclient.hpp,
perception_runtime.hpp, CMakeLists.txt}`, `source/llm_to_action/perception/{detection_query.hpp,
detection_query_test.cpp}`; NEW: `source/llm_to_action/perception/target_tracker.hpp`,
`source/llm_to_action/fmu/test/target_tracker_test.cpp`, `dependencies/three_people.sdf`,
`scripts/test/SITL/{logtest.sh, digest.sh, TESTING.md, crowd/, search_follow/, follow/watch.sh}`;
`docs/NOTES.md`, `docs/LOCKS.md`.

Suggested commit (house style):
`fmu: FOLLOW visual servo + HOVER + SEARCH-by-tag + stable-id tracker + perception-coast; grammar hardening; SITL follow test tooling`

### WIP / open
- VLM speed (~30 s/plan) — top risk, unsolved (see gotcha 8).
- VLM search-hallucination — FMU-side guard proposed, not built (gotcha 6).
- FOLLOW responsiveness — errX spikes on gaps (gotcha 7).

### TODO (not started)
- SITL ground-truth PASS/FAIL assertion (`scripts/test/lib/wait_for_ground_truth.sh` — drone ends near the
  intended actor, not others).
- Rename/sort all `scripts/test/SITL/*` dirs (naming is inconsistent: hyphens vs underscores).
- `confirmed_target` metadata on tracks — needs a seg-thread-safe passthrough (the tracker is written only
  by the seg thread; writing from the control thread would race). Deferred.
- Appearance-embedding re-ID (flag-gated, empirical cosine-separation gate first). Deferred.

### How to test (no display needed — Gazebo GUI can't open on this box, 4 GB VRAM)
1. Start the VLM standalone and confirm it: `llama-server ... -dev Vulkan0 -ngl 99 --parallel 1 -c 4096 ...`
   then `curl -s http://127.0.0.1:8080/health` must be `{"status":"ok"}`. On CPU fallback use `-ngl 0`.
2. `cd scripts/test/SITL && LAUNCH_VLM=0 ./logtest.sh follow` (or `crowd`, `search_follow`).
3. `./digest.sh` — reads the newest run + the newest `vlm_logs` prompt file. Key lines: `VLM empty
   responses` (>0 = server down), `prompts saying no-detections` (>0 = perception lied), `SEARCH activated`
   (should be 0 for a plain follow), `loss-sweep` (should be 0 — sweep removed), servo ticks, max |errX|.
