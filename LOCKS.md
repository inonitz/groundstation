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
| file | holder | since (UTC) | notes |
|------|--------|-------------|-------|
| source/llm_to_action/fmu/fmu_node.hpp | FREE |  | spec-3 COMPLETE + SITL-verified 2026-08-08 (failsafe laws, RTH, override, backpressure, battery tests) |
| source/llm_to_action/fmu/fmu_node_base.hpp | FREE |  | kApproachStandoffM 2.0->3.0m: margin for target parts protruding past measured point |
| source/llm_to_action/fmu/llm_base.hpp | FREE | | VLM action schemas (Spec 2: orbit / search / safe_land) |
| source/llm_to_action/keyboard/keyboard_node.hpp | FREE | | spec-3 DONE: construct m_rawKeyEvent publisher |
| docs/ROADMAP.md | FREE | | 6.4 updated (servo partial-mitigation); added 5.1.6 depth-backstop + 9.12 off-heading drift |
| source/llm_to_action/fmu/fmu_node.cpp | FREE |  | spec-3 COMPLETE (canned test flags) + spec-4 rotate/land args |
| scripts/simenv_llm.sh | DELETED | | superseded by scripts/test/lib/sim_core.sh + scripts/test/*/run.sh (2026-08-07) |
| source/llm_to_action/generic_backend/generic_backend_types.hpp | FREE | | spec-3 DONE: kBatteryReadingUnknown added |
| source/llm_to_action/px4_backend/px4_backend_base.hpp | FREE | | spec-3 DONE: battery topic + include |
| source/llm_to_action/px4_backend/px4_backend.hpp | FREE | | spec-3 DONE: battery sub member + real battery_pct_impl |
| source/llm_to_action/px4_backend/px4_backend.cpp | FREE | | spec-3 DONE: battery subscription + callback |
| source/llm_to_action/fmu/perception_runtime.hpp | FREE | | ready() health check live; temporary PERCEPTION_DEBUG logging removed (shipped clean) |
