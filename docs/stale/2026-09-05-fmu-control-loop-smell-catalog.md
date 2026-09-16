# FMU control-loop smell catalog — COMPLETE sweep (2026-09-05)

Author: groundstation-13 [8501ec] (llm_to_action presentation agent). Owner instruction (2026-09-05): pull every code smell that is not
real-system function out of the control loop; testing should be testing and real function should be
real function; catalog everything first, then refactor together. This is the catalog. Nothing is
changed. Line numbers are from the current tree.

`controlLoop()` = `fmu_node.hpp:591-1494`. Per-command laws: GO 839, ROTATE 886, APPROACH 912,
FOLLOW 1136, ORBIT 1233, SEARCH 1305, HOVER 1451. Setup switch `activateTask` starts at 1951. Test
wiring is in `fmu_node.cpp::runTestScenario`.

## 1. Test-only scaffolding INSIDE controlLoop (the genuine "testing in the flight loop")

Each flag is set ONLY in `fmu_node.cpp` (test scenarios). In real flight all are false, so none fire.
The smell: their `if (flag)` checks sit physically inside `controlLoop`, so the flight loop carries
test branches that never run in production.

| # | Hook | Set at (cpp) | Checked in loop | Injects |
|---|---|---|---|---|
| 1 | `m_floodArmed` | 70 | 681 | Mid-flight queue-overflow flood. |
| 2 | `m_batForceArmed`/`Value` | battery scenarios | 691 | A forced fake battery % to trip the failsafe. |
| 3 | `m_obstacleArmed` | 82, 86 | 769, 783 | A synthetic close-obstacle window. |
| 4 | `m_useCannedApproachRig` | 58, 92 | 913 | Synthetic perception (`updateCannedApproachRig`). |
| 5 | `m_forceApproachImpact` | 91 | 485 | A forced off-nominal impact in a motion-gate helper. |

This is the only genuine test code in the loop. The fmu-cleanup tasklist already flags 1-3 for
extraction.

## 2. Deliberate hardcodes in the LIVE laws (NOT test artifacts)

These run in real flight. The code's own comments say why they exist: monocular depth
(`yolo26n-depth`) and detection are too noisy to trust, and the planner is weak. They are deliberate
workarounds, not careless hacks.

- **APPROACH bbox-anchor** (setup 2052-2067; law 913, 918-950). When the VLM returns a bounding box
  for a non-COCO target, the FMU projects it to a world ENU anchor and flies there by odometry,
  bypassing live vision. Reason (code): flaky detection + noisy depth. `m_approachBboxRig` is set in
  the LIVE path (2063).
- **ORBIT hardcoded fixed circle** (1238-1264). It orbits a geometric point `kOrbitFixedRadiusM`
  straight ahead of where the orbit starts -- NOT the target -- at an altitude floored to
  `kOrbitFixedAltM` (4 m). Reason (code, verbatim): "Monocular depth range proved too noisy for an
  autonomous building-orbit -- every depth-seeded version placed the centre wrong and flung the drone
  into the terrain." Commanded `radius_cm` is honoured (clamped); unset falls back to the hardcoded
  default.
- **Auto-land after APPROACH** (2239-2246). On APPROACH completion the FMU auto-enqueues a LAND.
  Reason (code): a "weak planner that may skip the land". Gated by a plan field (2532), so a plan can
  opt out.

## 3. Naming conflation (APPROACH)

The real bbox-anchor feature reuses the canned TEST rig's state and methods --
`m_cannedApproachTargetEnu`, `updateCannedApproachRig`, `m_perception->injectSynthetic` -- and the
"canned / synthetic / rig" vocabulary. A reader cannot tell the real feature from the test by name.
This is cosmetic; behaviour is unaffected.

## 4. Laws with no scaffolding or unjustified hardcode

GO, ROTATE, FOLLOW, HOVER, LAND, TAKEOFF use control gains and completion thresholds only -- normal
tuning, not smells. SEARCH scans at a fixed altitude (1426) -- minor, listed for completeness.

## Analysis (factual, no fix chosen)

1. The only genuine "testing in the loop" is the fault-injection in section 1. It is inert in real
   flight but physically lives inside `controlLoop`.
2. Every hardcode in the live laws (section 2) is a stated workaround for two root causes: schizo
   monocular depth and flaky detection, plus a weak planner. They are deliberate.
3. The one pure-cosmetic smell is the shared canned/rig naming in section 3.
4. Consequence: a better depth model and a stronger planner (4B) are the levers that would let the
   section-2 hardcodes be replaced with real target-relative behaviour. That is a root-cause fix, not
   a delete.

## Open (owner decides the refactor)

- Whether to lift the section-1 fault-injection out of `controlLoop` into a test-only path.
- Whether, and when, to replace the section-2 depth workarounds -- gated on the depth/planner quality
  work, not a blind removal.
- Whether to rename the section-3 canned/rig vocabulary so real and test are distinct.
