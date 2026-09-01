# Agent File Locks

Coordination registry for parallel Claude sessions (Specs 1–4). **One aggregate file — do NOT create
per-file lock files.** The contended hotspot is `source/llm_to_action/fmu/fmu_node.hpp`, which every
spec edits; the locks below serialize access to it and the other shared FMU files.

## Protocol — every session MUST follow
1. **Before editing ANY file in the Locks table, read this file first.**
2. If that file's `holder` is not `FREE` and not you → **do NOT edit it.** Pick other work instead:
   another listed file that is `FREE`, an unlisted file your spec alone owns (e.g. a new test
   script), or — if nothing of yours is free — stop, write `blocked on <file> held by <holder>` in
   your spec's report section, and wait for the overseer.
3. **Acquire:** set `holder` to your session id and `since` to the current UTC time, **save this
   file first**, then edit the source file.
4. **Release:** the moment you're done with that file, set `holder` back to `FREE`, clear `since`,
   and put a one-line summary in `notes`. Never hold a lock while thinking or idle.
5. Keep holds short — acquire right before a focused edit, release right after. Prefer many short
   holds over one long hold so others can interleave on `fmu_node.hpp`.
6. Files you alone create (new test scripts / headers nobody else touches) do **not** need a lock.
7. Stale lock (`since` > ~30 min with no progress in the holder's report): flag it in `notes`. Only
   the **overseer** clears someone else's lock.

## Locks

Notes below were last refreshed 2026-08-10. Everything is `FREE` right now -- entries predating
2026-08-09 (spec-1/2/3 era) were cleared because their notes described work from several sessions ago
and had stopped reflecting reality; a stale note is worse than no note since it misleads a reader
checking here before an edit. Fill in `notes` with what you actually did, not what a prior session did.

| file | holder | since (UTC) | notes |
|------|--------|-------------|-------|
| source/llm_to_action/fmu/fmu_node.hpp | FREE | | agent1: reverted image448 + VISIBLE-NOW (back to 640 + plain JSON perception) | agent1: VISIBLE-NOW directive in [PERCEPTION] (stop 2B hallucinating not-visible->search) + image 448 (speed); px4 clean | agent1: FOLLOW loss = HOLD only (sweep removed - was spinning open-loop on flicker); px4 clean | agent1: FOLLOW coasts brief flickers (hold), sweeps only on sustained loss - kills flicker-spinning; px4 clean | agent1: [PERCEPTION] coasts blank frames + first plan waits for first detection (kills false 'no detections'->spin-search); px4 clean | agent1: FOLLOW centre-detection fallback (locks person even when VLM track_id is wrong); px4 clean | agent1: kFollowYawGain 3.0 + yaw cap (snappier follow centering); px4 clean | agent1: drop zero-go (no hover-starve); FOLLOW loss sweeps yaw to last-seen (4s bound); px4 clean | agent1: SEARCH-by-tag done (CmdSearch.target_id, tag-aware hit, surface track_id in SEARCH DETECTED); px4 clean | agent2: /fmu/rates publisher (perception refresh + publish Hz, obs-gated, ~1Hz). |
| source/llm_to_action/fmu/fmu_node_base.hpp | FREE | | agent1: kFollowYawGain 5.0 (snappier) | agent1: kFollowCoastMs/Us=800ms | agent1: kPerceptionCoastMs/Us + kPerceptionWarmupMs/Us | agent1: kFollowYawGain=3.0 kFollowYawMaxRps=1.5 | agent1: kFollowSweepMs/Us + kFollowSweepYawMaxRps | agent2: kFmuRatesTopic. |
| source/llm_to_action/fmu/llm_base.hpp | FREE | | agent1: rule 12 no-guess-ids + act-on-search_ok; px4 clean | agent1: SEARCH confirm-by-tag flow + optional search track_id | agent1: hover only when NO target; follow=hold+watch (fixed model choosing hover over follow) | agent1: incremental/target-visible/no-go-to-hold rules + hover verb doc | manager: camera->go frame bridge (image LEFT=+y/RIGHT=-y, always drive +x forward) -- clean, additive |
| source/llm_to_action/fmu/llamaclient.hpp | FREE | | agent1: single verb list, no takeoff in action slots (kills double-takeoff) | agent1: typed-member GBNF (kills parameters blob), airborne verb drops takeoff, added hover |
| source/llm_to_action/fmu/plan_parse.hpp | FREE | | |
| source/llm_to_action/keyboard/keyboard_node.hpp | FREE | | |
| docs/code-guidelines.md | FREE | | |
| source/llm_to_action/perception/detection_query.hpp | FREE | | agent1: detectionByTrackId helper |
| docs/ROADMAP.md | FREE | | agent3: added 3.9 prompt-trim (DEFER) + 1.1.2 rotate/drift reframe as [GATE Agent-5 SLAM] |
| source/llm_to_action/fmu/fmu_node.cpp | FREE | | |
| scripts/simenv_llm.sh | DELETED | | superseded by scripts/test/lib/sim_core.sh + scripts/test/*/run.sh (2026-08-07) |
| source/llm_to_action/generic_backend/generic_backend_types.hpp | FREE | | |
| source/llm_to_action/px4_backend/px4_backend_base.hpp | FREE | | |
| source/llm_to_action/px4_backend/px4_backend.hpp | FREE | | |
| source/llm_to_action/px4_backend/px4_backend.cpp | FREE | | |
| source/llm_to_action/fmu/perception_runtime.hpp | FREE | | agent2: seg/depth iteration counters + segIters()/depthIters() getters. |
| source/llm_to_action/tello_backend/tello_backend.hpp | FREE | | agent0: expose m_tofCm + tof_cm() for VPS diagnosis |
| source/llm_to_action/tello_backend/tello_backend.cpp | FREE | | agent0: store st.tof in the state loop |
| source/llm_to_action/tello_backend/tello_backend_base.hpp | FREE | | |
| source/slam/slam2.hpp | FREE | | agent5: added slam/tracking_state (Bool, !tracker_is_paused) published every worker cycle. Compiles + links (stella_vslam_monocular built). |
| CMakeLists.txt (top-level) | FREE | | |
| config/stella_config_tello.yaml | FREE | | agent4: moved dependencies/ -> config/, all path refs updated; RMS 0.438 px. |

- 2026-08-13 agent1: llm_base.hpp -- added DECISION RULE 13 "SEE IT? FLY TO IT" and scoped rule 12's
  search clause to genuinely-invisible targets. Purpose: DEMO 1 -- the RED person is 12-16m out (YOLO
  can't box at range), so [PERCEPTION] is empty and the 2B searched blindly instead of flying toward
  the red person it can SEE. Now it drives +x toward the visible colour target (uses your camera->go
  bridge) until YOLO detects it, then follows by track_id. Additive to your bridge; bridge untouched.

- 2026-08-13 agent1: scripts/test/lib/sim_core.sh -- upgraded the VLM prewarm from text-only to a
  real 640x640 IMAGE request, so the vision projector (mmproj) compiles during bring-up instead of on
  the operator's first plan. Addresses the long first-plan latency (the residual your own NOTE flagged).

- 2026-08-13 agent1: scripts/test/lib/sim_core.sh -- swapped the VLM from Qwen3-VL-2B-Q4 to
  Qwen3.5-9B-Q4_K_M (+ its mmproj). The 4GB VRAM limit was the LAPTOP; this workstation is an AMD
  RX 7900 GRE (16GB), which fits a 9B easily. The 2B was the root of bbox-omission + weird plans.

- 2026-08-13 manager: fmu_node.hpp + fmu_node_base.hpp -- Demo-1 crash fixes (see NOTES post-mortem).
  (1) SEARCH activation: when perception is EMPTY at activation, promote size to LARGE (reach ~24m) so a
  blind search actually reaches a far target. Complements agent1's rule-13 "fly to what you see" -- if the
  VLM still emits a blind search, this makes it reach; if rule 13 makes it fly toward the visible target,
  this stays dormant. No conflict. (2) APPROACH: new kApproachMinAnchorAltEnu=0.8m; clamp the bbox anchor Z
  and guard the visual-servo descent so an approach can NEVER sink below ground (the 2B fabricated a bbox
  that anchored at z=-1.87 and flew the drone into the dirt). Safety net, model-independent. agent1: pull
  before touching SEARCH activation or the APPROACH branch in fmu_node.hpp.
- 2026-08-13 manager: scripts/test/lib/sim_core.sh -- added `rm -f "$LOG_FILE"` right after the LOG_FILE
  default (top of file), so each run starts with a fresh capture. Distinct region from agent1's VLM-prewarm
  edit; merges cleanly.
