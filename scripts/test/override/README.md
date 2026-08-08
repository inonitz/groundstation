# override test

Manual operator override (spec-3, ROADMAP 6.2 / ARCH 11) — reversible takeover, NOT a kill.

- **Override toggle topic:** `/fmu/in/override` (`std_msgs/Bool`)
- **Movement input:** `/keyboard/in/raw` (the keyboard node pane, launched by sim_core.sh)
- **VLM:** on (`LAUNCH_VLM=1`) so a handback re-plans from the current pose
- **World:** `default_car`   **Spawn:** `0,7,3`

## Run
```
cd scripts/test/override
./run.sh            # sim + VLM + keyboard node come up; let it take off & start flying
```

## Manual steps (this test is interactive)
1. Once airborne under VLM control, **engage override** (2nd terminal):
   ```
   ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data: true}"
   ```
   → FMU logs `MANUAL OVERRIDE engaged`; autonomy pauses (drone hovers).
2. **Fly it manually** — focus the keyboard-node pane (it hooks /dev/input globally, so
   needs input perms) and press: `W/S`=fwd/back, `A/D`=left/right, `↑/↓`=up/down,
   `←/→`=yaw, `Space`=hover. The drone should move under your keys, not the VLM.
3. **Hand control back**:
   ```
   ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data: false}"
   ```
   → FMU logs `MANUAL OVERRIDE released ... VLM will re-plan`; autonomy resumes and the
   VLM plans fresh from the current pose.
4. (optional) Confirm the **battery failsafe still outranks manual** — see the `battery`
   test; a low-battery RTH/land fires even while overridden.

## Then
```
./filter.sh         # -> captured_override_log.txt (this folder) + digest + PASS/FAIL
```

## Expected
- `MANUAL OVERRIDE engaged` on true, `MANUAL OVERRIDE released` + a re-plan on false.
- Keys visibly move the drone while engaged; the VLM does not command it until handback.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
