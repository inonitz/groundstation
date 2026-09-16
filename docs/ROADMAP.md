# Roadmap

Where we are going, in order, with status. The running record of what happened is `HISTORY.md`;
the deep parked flight-core objective tree lives in `spec-fmu-architecture.md` and git history.

## North star

A drone a human commands by voice, that understands the scene it sees, and acts. The LIVE system is
`integration_harden2` (Hebrew voice -> one Gemma-4 planner + SAM3 perception, recognizer-gated). The
C++ `llm_to_action` FMU engine is the destination product; harden2's voice+guard+SAM3 layer folds onto
it eventually. `integration_tts` is the frozen English fallback.

## Phase arc (current order, owner-ruled 2026-09-14)

| # | Phase | Status |
|---|---|---|
| 1 | Cleanup & restructure (repo, bench, docs) | in progress (~done) |
| 2 | Webcam smoke test on the fresh repo | next |
| 3 | Nuclear code-quality review (`/thermo-nuclear-code-quality-review`) | pending |
| 4 | Outdoor field test on the real drone (human-run) -> freeze the validated commit as the baseline (git tag) | pending |
| 5 | Post-freeze benchmarks: whisper-Hebrew noise (SNR sweep), SAM3 low-light | scheduled |
| 6 | New features off the baseline: vision-conditioned action (mark -> approach/pass an opening), operator mission+phase context, military slang | scheduled |
| 7 | Fuse harden2's layer onto the C++ `llm_to_action` engine | scheduled |

Rule: cleanup finishes first; the field test validates the FINAL system, then that exact commit is
frozen. Any change after the freeze that touches harden2 behaviour forces a retest and re-freeze.
Invariants: temperature 0, one model on the GPU at a time, full bench tables, the owner runs every
boot and every git write.

## Parked: the C++ flight-core (llm_to_action)

SITL-verified flight-core work (20 Hz control loop; ROTATE / TAKEOFF / LAND / ORBIT / SEARCH / APPROACH
verbs; battery failsafe; GenericBackend over PX4 + DJI) is real but deferred behind harden2. Full design
and status: `spec-fmu-architecture.md`. Open there: Tello/SLAM-era hardware bring-up (retired path),
cross-hardware odometry abstraction, right-sizing the VLM context window for target hardware.

## Proven / not-yet-proven

See `HISTORY.md` ("Extracted rulings"): the MVD is field-tested end to end; NOT proven are
command->action latency < 1 s on the real link, the video glass->Linux latency number, gimbal control,
and the C++ engine flying end to end.
