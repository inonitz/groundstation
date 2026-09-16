# Scheduled — harden2 field test and freeze

Runs AFTER the cleanup+restructure lands (owner-confirmed order 2026-09-14).

Sequence: webcam smoke test -> nuclear code-quality review (/thermo-nuclear-code-quality-review)
-> outdoor field test on the real drone (human-run, aircraft secured) -> freeze the validated
commit as the baseline (git tag).

Done when: harden2 performs well outdoors and the exact tested commit is tagged as the baseline.
Invariants: temperature 0, one model on the GPU, full bench tables, owner runs every boot and git write.
Becomes a tasks-active/<date>-... folder when started.
