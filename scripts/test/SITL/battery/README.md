# battery test (real-drain patrol)

Battery failsafe with a **real, uncontrolled PX4 drain** (spec-3, ROADMAP 6.2) — the realistic
demo. The drone patrols out and away; whenever the *actual* pack crosses **20%**, OUR failsafe
returns it to origin and lands. Distinct from the deterministic `../battery-rth` /
`../battery-landnow` (which force a fixed % at a fixed time for fast, repeatable checks).

## Why it looks the way it does
- **Patrol, not cross:** it flies a box **6-10m out** and never sits at origin, so RTH actually
  covers ground (the old cross plan returned home every leg — RTH was a no-op).
- **PX4's own low-battery failsafe is DISABLED** (`COM_LOW_BAT_ACT=0`). Without this, PX4 hit
  "Critical battery", entered **Hold**, froze our descent at ~0.34m and dropped the drone — the
  landing was *PX4/physics, not us*. With it off, PX4 only warns and OUR FMU owns the reaction.
- **Brisk RTH** (0.8 m/s) so the drone gets home before the pack empties.

## Run  (this is a ~2-3 min test — you're watching a real drain)
```
cd scripts/test/battery
./run.sh            # takes off, patrols out; ~112s in the real 20% crossing fires RTH
# after it flies home and lands:
./filter.sh         # -> captured_battery_log.txt + digest + PASS/FAIL
```

## Tuning (HITL)
`SIM_BAT_DRAIN` = seconds-to-empty from arm. Each run **randomizes it in 140..200s**, so the 20%
crossing — and the spot the drone breaks off the patrol to fly home — is different every time
(a real drain isn't perfectly repeatable). To reproduce one run, pin it:
`PX4_PARAM_SIM_BAT_DRAIN=170 ./run.sh` (the run echoes the value it used). Bounds: too small →
dies before it can RTH home; too big → the patrol lands before 20% fires. The window must leave
enough charge after 20% for the ~0.8 m/s return + land.

## PASS requires (all)
- reached FLIGHT; `maxDist > 3m` (patrolled out); OUR `<=20% RETURN` fired; `landDist < 1.5m`
  (RTH brought it home); `LANDING->STANDBY` (landed AND disarmed); **PX4 did NOT enter Hold**.

## Observed (fill in per run, then hand this whole file back)
- **date:**   **what I saw:**   **filter digest:**   **my comment:**
