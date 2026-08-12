# P1 disarm verify (SITL)

Proves the FLIGHT->FAULT reconcile fix (`px4_backend.cpp` + `fmu_node.hpp` lost-flight
guard, commit 5f935e0): if the drone is force-disarmed **in the air**, the FMU must catch
it, reconcile to STANDBY, and abort the task -- not keep streaming flight commands to a
dead drone.

## Run it (3 steps)

1. **Open QGroundControl.** PX4 will NOT arm without it (no GCS link = "Arming denied").
   Also make sure no Tello work is running -- this binds the Tello UDP ports (11111/8889/8890).

2. **Run the test:**
   ```
   cd scripts/test/SITL/disarm-verify
   ./run.sh
   ```
   It arms, takes off, starts an orbit, then ~8s in it fires `commander disarm -f`.
   **Watch QGroundControl:** the drone should drop out of the orbit mid-circle and go
   **DISARMED** (it must NOT complete a full clean circle -- that would mean the disarm
   missed). The run tears itself down when done.

3. **Get the verdict:**
   ```
   ./filter.sh
   ```
   Prints an automatic **PASS/FAIL** -- it checks the four reconcile lines are in the log,
   in order, and echoes them.

## Watch it live in Gazebo (with your own eyes)

The default `./run.sh` is headless (no Gazebo window) so it can run unattended. To watch the
drone in the Gazebo GUI, either:

**Option A -- attended run (simplest):**
```
cd scripts/test/SITL/disarm-verify
GUI=1 ./run.sh
```
A Gazebo window opens and the terminal attaches to the tmux session. Watch the drone: it
takes off, starts the orbit, then ~8s in it force-disarms and drops. When it is down, press
**Ctrl-B then D** to detach -- that triggers cleanup. Then run `./filter.sh`.

**Option B -- headless run + pop the GUI yourself (bulletproof):**
Run `./run.sh` as usual, and in a SECOND terminal immediately open a Gazebo GUI client
attached to the running sim:
```
gz sim -g
```
This connects to the running server no matter how it was launched. Watch the drone there,
then `./filter.sh` after it finishes.

In both, the eyeball tell is the same: PASS = the orbit is **cut short mid-circle** by the
disarm; FAIL = a **full clean circle**.

## What PASS looks like

```
  [ ok ] 1. Reached FLIGHT (armed + offboard confirmed)
  [ ok ] 2. In-flight disarm caught -> FLIGHT->FAULT
  [ ok ] 3. FMU stopped, reconciled to STANDBY, aborted task
  [ ok ] 4. Task aborted with reason backend_lost_flight
>>> RESULT: PASS -- in-flight disarm was caught and the task was aborted.
```

## Grep the raw log yourself

The four lines to look for in `captured_panes_log.txt`, in this order:

```
OFFBOARD+ARM CONFIRMED                 <- reached FLIGHT
unexpected disarm while airborne ... FLIGHT->FAULT
backend left FLIGHT ... reconcile STANDBY, abort task
task complete status=backend_lost_flight
```

## If it FAILs

- **Full clean orbit, no disarm lines** -> the disarm never reached the drone. Re-run.
- **Never reached FLIGHT / stuck at altitude 0** -> PX4 never armed. Open QGroundControl,
  or the headless waiver `PX4_PARAM_NAV_DLL_ACT=0` (already set in `run.sh`) plus QGC.

## Files

- `run.sh` -- launches SITL + the auto-injector. Prints watch/verdict banners.
- `filter.sh` -- automatic PASS/FAIL from the captured log.
- `captured_panes_log.txt`, `inject.log`, `*_stdout.log`, `px4_pane.log` -- per-run
  artifacts, regenerated each run (git-ignored; do not commit).
