# Agent 1 follow-up — ORBIT geometry: honour radius, derive speed from a period (owner: agent)

**Date: 2026-08-11** - Deadline: Wed evening 2026-08-12. Raised by Agent 0 from a live SITL log;
the verb and the plan path are yours.

**Mission**: make ORBIT do what the operator asked. A plan that says "orbit the car 5 m out for two
minutes" must fly a 5 m circle in two minutes. Today the radius is ignored and the speed is an
unbounded integer the VLM guesses.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md`, `CLAUDE.md`,
`docs/code-guidelines.md`, `docs/NOTES.md`. Study `fmu_node.hpp` ORBIT lock (`1043-1070`),
radial/tangential control (`1085-1115`), ORBIT dispatch (`1765-1780`), the prompt schema in
`llm_base.hpp` (`56-59`, and the "Keep speed low" line at `99`), and the grammar in
`llamaclient.hpp` (`125`).

## What actually happens now (measured, not guessed)

A live SITL run produced this plan and then appeared to hover for the whole capture:

```json
{"action":"orbit","target_object":"car","radius_cm":200,"angle_deg":360,"direction":"cw","speed":1}
```

- `speed` is cm/s. `m_orbitSpeed = orb.speed / 100.0f` (`1768`), so `1` became **0.01 m/s**.
- The circle locked at R=4.00 m, so a full lap is ~25 m: about **42 minutes**. `swept` crawled
  0.00 -> 0.34 rad across the entire log. It was orbiting, far too slowly to see.
- `radius_cm` was 200 but the radius came out 4.00. The field is parsed at `2097` and never read.
  `m_orbitRadius` is set at `1056` to the measured distance from the drone to the locked centre --
  wherever the drone happened to be standing.
- Completion is angle-only (`m_orbitSweptRad >= m_orbitTargetRad`, `1106`). `m_orbitStartUs` feeds
  only a target-lost timeout (`1064`). **There is no duration bound**, so a slow speed stalls the
  task indefinitely.
- The VLM is not at fault. The orbit schema says `"speed": <int>` with no units -- units appear
  once, for `go` (`llm_base.hpp:45`) -- and line 99 instructs "Keep speed low". It obeyed. The
  grammar has no numeric rule for `speed` either.

## Do

1. **Honour `radius_cm`.** Set `m_orbitRadius` from the plan when it is given, and let the existing
   radial term (`1087-1089`) fly the drone out to it before the sweep starts. The controller already
   corrects radius error every tick; it is only ever fed a measured value today.
2. **Derive speed from a period, do not accept one.** `m_orbitSpeed = (m_orbitRadius * m_orbitTargetRad) / period`.
   A 360 orbit then takes the same wall-clock time whether it locks at 2 m or 6 m, and an absurd
   speed becomes unrepresentable.
3. **Add the defaults as config, not constants.** New `drone_config` keys with entries in BOTH
   `config/tello.yaml` and `config/px4_sitl.yaml`: `orbitDefaultRadiusM`, `orbitDefaultPeriodS`,
   `orbitMaxRadiusM`, `orbitMaxTurns`. There is no indoor/outdoor flag in the code and you should not
   add runtime detection -- the two YAMLs already encode that split (`tello.yaml` is the indoor rig:
   `boundaryBaseM` 0.5, `orbitDefaultSpeedMps` 0.2, "gentler indoors" throughout). Indoors means a
   small default radius and `orbitMaxTurns: 1`; the SITL world can be looser.
4. **Resolve the four cases in dispatch**, in this order:
   - radius and duration both given -> use both verbatim.
   - duration missing -> `orbitDefaultPeriodS` at the requested radius.
   - radius missing -> smallest radius that clears a full lap: target extent + `boundaryBaseM` +
     margin, floored by the measured lock distance, capped by `orbitMaxRadiusM` and by
     `m_perception->nearestFreeDepthM()` (both already feed the boundary check at `702-718`).
   - neither given -> `orbitDefaultRadiusM` and `orbitDefaultPeriodS` from the rig's YAML.
5. **Fix the schema and the grammar.** Give `radius_cm` units in `llm_base.hpp`, add an optional
   `duration_s`, and drop `speed` from the orbit verb -- the FMU owns it now. Add numeric bounds to
   the grammar in `llamaclient.hpp`, which currently constrains nothing. Leave `speed` alone on the
   other verbs unless you are fixing those too; if you leave them, at least state the units.
6. **Bound the task.** With a period, a duration cap falls out: abandon or complete the orbit if it
   overruns its period by a healthy margin, and log why.

## Test

- Canned first: `injectCannedOrbitPlan` already sends `radius_cm:300`. It must fly a 3.00 m circle,
  not lock at whatever range it starts from. Assert `ORBIT center locked ... R=3.00` in the log.
- A 360 orbit at the default period finishes within that period, within tolerance.
- A plan with an explicit `duration_s` finishes in that time at the requested radius.
- A plan with neither field completes at the rig's configured default and does not stall.
- `scripts/test/SITL/orbit/` is the existing scenario; extend its filter rather than adding a new one.

## Locks

`fmu_node.hpp`, `llm_base.hpp`, `llamaclient.hpp`, `drone_config.hpp` -- all in `docs/LOCKS.md`.
Short holds, `fmu_node.hpp` last since it is the contended one.

## Constraints

No git writes -- suggest `agent1: orbit honours radius and derives speed from a period`. Prose per
`docs/writing-style.md`. Note the blast radius: this changes ORBIT's observable behaviour, so the
existing `orbit` filter will need updating, and that is a real behaviour change, not a refactor.

## Report
_(append findings / blockers / decisions below)_
