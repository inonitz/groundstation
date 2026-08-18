# interrupt-storm test

Verifies interrupt-storm escalation AND recovery (spec 2026-08-07-spec-1 §D, ROADMAP 6.3). When
`kInterruptMaxRetries` interrupts fire within `kInterruptStormWindowMs`, the FMU sets `escalated=1`
and the next VLM prompt carries an `[ESCALATION]` block telling the model to reason about the root
cause and find a creative escape. A later clean task completion resets the detector.

- **Scenario:** `--scenario-storm`
- **VLM:** on (`LAUNCH_VLM=1`) — needed for the escalated prompt AND the recovery re-plan.
- **World:** `rubicon_targets`   **Spawn:** `0,7,3`
- **Filter:** Auto PASS/FAIL on escalation; RECOVERY is a soft, operator-confirmed signal.

## How it's triggered
`--scenario-storm` takes off, then injects a synthetic close-obstacle burst for ~1.5 s. That trips
the boundary many times inside the window (deterministic `escalated=1`), then clears. The prompt
text is not logged, so the FMU logs `ESCALATION block added to reassess prompt` when it adds the
block — that is what the filter greps.

## Why rubicon_targets (not empty)
The point of escalation is that the model actually RECOVERS. In an empty world the VLM has nothing
to see or escape, so it never completes a task and escalation never clears — escalation fires but is
never shown to work. `rubicon_targets` is the Rubicon terrain plus two people and two cars in the
drone's forward view (`dependencies/rubicon_targets.sdf`). After the burst clears, real perception
shows the VLM an actual scene, so the escalated reassess can plan a real escape and complete it.

Models used as targets live in `dependencies/gz_models/`: `person_standing`, `person_walking`
(downloaded from Gazebo Fuel), `hatchback`, `hatchback_blue`. YOLO reads the people as "person" and
the cars as "car". If any model floats or buries on the sloped terrain, nudge its `z` in
`dependencies/rubicon_targets.sdf`.

## PASS condition
Hard: `>= 3` `INTERRUPT (reason=...)`, at least one `escalated=1`, and at least one
`ESCALATION block added to reassess prompt`. Soft (RECOVERY): a non-`takeoff_ok` `task complete`
AFTER the storm — the VLM escaped the loop. Recovery is operator-confirmed (a 2B VLM may not always
escape); watch whether the drone actually leaves the spot.

## Run
```
cd scripts/test/interrupt-storm
./run.sh            # needs the Qwen3-VL llama-server (LAUNCH_VLM=1 handles it)
./filter.sh         # -> PASS/FAIL + RECOVERY line
```

## Observed (fill in per run)
- **date:**
- **what I saw:** (did the drone leave the spot after the storm?)
- **filter digest:**
