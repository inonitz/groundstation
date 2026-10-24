# Roadmap

Where we are going, in order, with status. The running record of what happened is `HISTORY.md`;
the deep parked flight-core objective tree lives in `spec-fmu-architecture.md` and git history.

## North star

A drone a human commands by voice, that understands the scene it sees, and acts. The LIVE system is
`integration_harden2` (Hebrew voice -> one Gemma-4 planner + SAM3 perception, recognizer-gated). The
C++ `llm_to_action` FMU engine is the destination product; harden2's voice+guard+SAM3 layer folds onto
it eventually. `integration_tts` is the frozen English fallback.

## The road to the freeze (owner ruling RM1, 2026-10-01; replaces the phase arc of 2026-09-14)

| # | step | state (2026-10-01) |
|---|---|---|
| 1 | Joint review: every recording label, the expected-result drafts, the vision-kind drafts | done 2026-10-01 |
| 2 | B2 (whisper + the recognizer on the recordings); the recognizer benchmark rerun | done 2026-10-01: 473 of 545 PASS; whisper 9.6 % |
| 3 | Finish the cleanup and the refactor | done 2026-10-01 |
| 4 | Code review with the review tools (/code-review, /thermo-nuclear-code-quality-review); fix the issues | in progress |
| 5 | The owner's live webcam test, with a microphone input-level check | after 4 |
| 6 | The field test on the real drone, secured, until done (the owner runs it) | after 5 |
| 7 | A walk-through, so the owner understands the whole system | after 6 |
| 8 | The doc sweep (F1, incl. every doc and header in the owner's terms) and the owner's commits; then the freeze (a git tag) | last |

Rule: the field test validates the FINAL system; that exact commit is frozen. Any change after the freeze
that touches harden2 behaviour forces a retest and a new freeze. After a successful freeze, the branch
merges into master (owner CP3). Invariants: temperature 0, full bench tables, the owner runs every boot
of the real drone and every git write.

## After the freeze (owner ruling POST (2)); each release ends with a new field test

| # | release | content |
|---|---|---|
| 1 | Benchmarks | whisper under noise; SAM3 in low light |
| 2 | The recognizer | a shorter plan answer (L3, about 0.45 s per mission, estimate); a flight and a vision request in one sentence (CI1); a larger military-slang set |
| 3 | Near-term architecture | SAM3 in its own process; SAM3.1 and EOVSAM evaluated by the owner and the agent together |
| 4 | Vision (a big feature) | a tracker with one identity per object (the box way, VT6); scan beyond the camera's view; vision-driven action; mission context |
| 5 | Far | fuse harden2's layer onto the C++ llm_to_action engine |

## Parked: the C++ flight-core (llm_to_action)

SITL-verified flight-core work (20 Hz control loop; ROTATE / TAKEOFF / LAND / ORBIT / SEARCH / APPROACH
verbs; battery failsafe; GenericBackend over PX4 + DJI) is real but deferred behind harden2. Full design
and status: `spec-fmu-architecture.md`. Open there: Tello/SLAM-era hardware bring-up (retired path),
cross-hardware odometry abstraction, right-sizing the VLM context window for target hardware.

## Proven / not-yet-proven

See `HISTORY.md` ("Extracted rulings"): the MVD is field-tested end to end; NOT proven are
command->action latency < 1 s on the real link, the video glass->Linux latency number, gimbal control,
and the C++ engine flying end to end.
