# Git Operations Ledger — FOR MANUAL REVIEW BY USER

> Claude is FORBIDDEN from running these. They are recorded here only.
> Nothing remote (push/fetch/PR) appears here. Review + run manually if you approve.

## Task 1 — px4_backend base + frame_convert + test
```bash
git add source/llm_to_action/px4_backend/frame_convert.hpp \
        source/llm_to_action/px4_backend/px4_backend_base.hpp \
        source/llm_to_action/px4_backend/test/frame_convert_test.cpp
git commit -m "feat(px4_backend): ROS-free frame_convert + base (absorb translator)"
```

<!-- Task 2/3/4 appended as they complete -->

## Task 2 — concrete PX4Backend class + CMake wiring
```bash
git add source/llm_to_action/px4_backend/px4_backend.hpp \
        source/llm_to_action/px4_backend/px4_backend.cpp \
        source/llm_to_action/CMakeLists.txt
git commit -m "feat(px4_backend): concrete PX4Backend (wire+handshake+stream), NED"
```

## Task 3 — FMU rewired onto PX4Backend verbs (NED parity); translator deleted
```bash
git add source/llm_to_action/fmu/fmu_node.hpp \
        source/llm_to_action/fmu/fmu_node_base.hpp \
        source/llm_to_action/CMakeLists.txt
git rm source/llm_to_action/fmu/offboard_translator.hpp
git commit -m "refactor(fmu): drive PX4Backend via verbs; remove inline wire layer (NED parity)"
```

## Debug instrumentation (on top of Task 3) — measVelNED + yawrate
```bash
git add source/llm_to_action/px4_backend/px4_backend.hpp \
        source/llm_to_action/px4_backend/px4_backend.cpp \
        source/llm_to_action/fmu/fmu_node.hpp \
        NOTES.md docs/superpowers/HANDOFF-2026-08-05.md
git commit -m "debug(px4_backend): expose measured vel + yawrate; NOTES root-cause GO spiral"
```

## NOTE: caveman-init rule files are untracked (user decides whether to commit)
#   .cursor/ .windsurf/ .clinerules/ .github/ .opencode/ + AGENTS.md (modified)
