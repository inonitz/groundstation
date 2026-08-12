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
| source/llm_to_action/fmu/fmu_node.hpp | FREE | | agent2: verified A2 throttle live (temp debug added+removed); no code change vs prior. |
| source/llm_to_action/fmu/fmu_node_base.hpp | FREE | | agent1: added kFollow* constants (standoff/fwd-gain/lost-timeout) |
| source/llm_to_action/fmu/llm_base.hpp | FREE | | agent1: added follow verb spec |
| source/llm_to_action/fmu/llamaclient.hpp | FREE | | agent1: added follow to grammar verb enum |
| source/llm_to_action/fmu/plan_parse.hpp | FREE | | |
| source/llm_to_action/keyboard/keyboard_node.hpp | FREE | | |
| docs/code-guidelines.md | FREE | | |
| source/llm_to_action/perception/detection_query.hpp | FREE | | agent1: added detectionNearestCenter |
| docs/ROADMAP.md | FREE | | agent3: added 3.9 prompt-trim (DEFER) + 1.1.2 rotate/drift reframe as [GATE Agent-5 SLAM] |
| source/llm_to_action/fmu/fmu_node.cpp | FREE | | |
| scripts/simenv_llm.sh | DELETED | | superseded by scripts/test/lib/sim_core.sh + scripts/test/*/run.sh (2026-08-07) |
| source/llm_to_action/generic_backend/generic_backend_types.hpp | FREE | | |
| source/llm_to_action/px4_backend/px4_backend_base.hpp | FREE | | |
| source/llm_to_action/px4_backend/px4_backend.hpp | FREE | | |
| source/llm_to_action/px4_backend/px4_backend.cpp | FREE | | |
| source/llm_to_action/fmu/perception_runtime.hpp | FREE | | |
| source/llm_to_action/tello_backend/tello_backend.hpp | FREE | | agent0: expose m_tofCm + tof_cm() for VPS diagnosis |
| source/llm_to_action/tello_backend/tello_backend.cpp | FREE | | agent0: store st.tof in the state loop |
| source/llm_to_action/tello_backend/tello_backend_base.hpp | FREE | | |
| source/slam/slam2.hpp | FREE | | agent4: STELLA_CONFIG_PATH default now config/stella_config_px4.yaml (config move). |
| CMakeLists.txt (top-level) | FREE | | |
| config/stella_config_tello.yaml | FREE | | agent4: moved dependencies/ -> config/, all path refs updated; RMS 0.438 px. |
