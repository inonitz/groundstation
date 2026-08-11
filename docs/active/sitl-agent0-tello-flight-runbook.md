# Agent 0 runbook — physical Tello tests (fill in and hand back)

**Date: 2026-08-11.** Deadline Wed evening 2026-08-12. Owner: human (Agent 0).

Five tasks, in order. T1-T2 need no flight. T3-T5 fly. Do them in sequence -- each one's PASS is
the next one's precondition. Copy the **Report** block at the bottom, fill it in, hand it back.

## Before anything

- Charge several batteries. One gives about 10-13 minutes, and T3-T5 will outlast one.
- Join the host to the Tello's WiFi AP (`TELLO-XXXXXX`). Host becomes 192.168.10.2, drone is
  192.168.10.1. The IP is hardcoded, so there is no flag to set.
- Clear the flight area. The Tello holds attitude, not position, so it WILL wander -- that is the
  thing we are measuring, not a fault.
- **Run only one of `run.sh` or `tello_teleop` at a time.** Both bind the same Tello command socket
  and video port; running both together will fail in a confusing way.

---

## T1 -- Rig health, on the ground

**Why:** proves link, video and telemetry before anything spins.

```
cd /root/groundstation/scripts/tello && ./run.sh
```

Three panes: RX, FMU, keyboard.

**Watch for**
- RX pane: `GStreamer Receiver Node Active (Tello raw-H264 pipeline)`, a few state changes, then
  quiet. Quiet means frames are flowing. Loud means a pipeline error.
- FMU pane: Tello connect, `streamon` ack, then steady control and `[hb] rc(...)` keepalive lines.
- Keyboard pane: `AsyncKeyHook successfully attached`. If it says FATAL, stop -- report it.
- Telemetry parses without a flood of parse-error lines.

**Ignore:** `VLM HTTP error: Could not establish connection` and `plan JSON parse failed`. `run.sh`
does not launch a VLM. Also expected: `fs=0` forever and no takeoff. Nothing plans one.

**PASS:** all three panes healthy for 30 s with the drone on the ground.

---

## T2 -- Keyboard override, on the ground

**Why:** closes the Test line of `sitl-agent0-tello-keyboard-spec.md` on real hardware. Zero flight
risk. This is the one that unblocks Agents 1 and 5.

With T1 still running, on the **built-in laptop keyboard** (the HP OMEN has no device node in this
container unless you restarted it since the devenv change, or ran
`mknod /dev/input/event19 c 13 83`):

1. Press **Enter** once. FMU pane should log
   `MANUAL OVERRIDE engaged -> autonomy paused, operator in control.`
2. Press **W**, then release. Nothing should move -- the drone is on the ground with motors off.
   The point is only that the key is accepted while engaged.
3. Press **Enter** again. FMU pane should log
   `MANUAL OVERRIDE released -> autonomy resumes, VLM will re-plan.`
4. Repeat the pair once more, to prove the toggle is stable rather than a one-shot.

**PASS:** two clean engage/release cycles, driven entirely by Enter, with no `ros2 topic pub`.

**FAIL shapes worth reporting exactly:**
- Nothing logged at all -> the key never reached the FMU. Capture the keyboard pane.
- Engages but never releases -> the press-only guard is wrong.
- Toggles twice per press -> the key release is being counted.

Capture before you stop: `tmux capture-pane -S - -p > /root/groundstation/all_panes.txt`

---

## T3 -- First flight, manual control

**Why:** proves the airframe, ESCs and the 20 Hz control path with no autonomy in the loop.

Stop `run.sh` first (Ctrl-C the panes, or Ctrl-B then D and kill the session).

```
export LD_LIBRARY_PATH=/root/groundstation/build/release/shared/tello/bin:$LD_LIBRARY_PATH
/root/groundstation/build/release/shared/tello/bin/tello_teleop
```

Controls: **T** takeoff, **L** land, **W/S** forward/back, **A/D** left/right, **R/F** up/down,
**Q/E** yaw ccw/cw, **Space** hover, **Esc** land and quit. Hold to move, release to hover.
0.4 m/s and 1.0 rad/s, deliberately gentle for indoors.

1. **T** -- takeoff. Let it stabilise.
2. Short taps: forward, back, left, right. Confirm each axis matches the key. W should be forward
   in the drone's own body frame, not the room's.
3. R and F for altitude, Q and E for yaw.
4. **L** -- land.

**PASS:** clean takeoff, stable hover, every axis correct, clean land, no telemetry parse-error
flood.

**Report:** any axis that is inverted or swapped. That is a body-frame bug and matters to Agent 5.

---

## T4 -- Drift characterization (the deliverable)

**Why:** Agent 5's SLAM work is blocked on this number. The Tello holds attitude but has no XY
position feedback, so the whole airframe drifts in space. We need to know how fast, and whether it
is consistent.

Mark the takeoff spot on the floor with tape. Have a tape measure ready.

**Run A -- pure hover, hands off**
1. **T**, climb to roughly 1 m, then **Space** to zero every axis.
2. **Touch nothing for 30 s.** Time it.
3. **L**. Measure the horizontal distance from the tape to where it landed, and note the compass
   direction of the drift relative to the drone's start heading.
4. Repeat three times, same spot.

**Run B -- drift while yawing**
1. **T**, climb to about 1 m.
2. **E** or **Q** for a slow full 360, then **Space**.
3. **L**, measure displacement as above.
4. Repeat twice.

**What we are answering**
- How many cm per 30 s does it wander in a plain hover?
- Is the direction repeatable across runs, or random each time?
- Does yawing make it materially worse, or about the same?

That last one matters: the spec's claim is that this is whole-airframe drift, not a rotate-specific
bug. If Run B is roughly Run A, the claim holds. If Run B is much worse, we have a second problem
and Agent 5 needs to know.

**Also note:** any wall, curtain or open window nearby. The Tello's downward vision positioning
degrades over featureless or reflective floors, and airflow near walls pushes it.

---

## T5 -- Optional: gentler yaw rate

**Why:** cheap experiment, no rebuild. `config/tello.yaml` already sits at `rotateMaxYawRate: 0.6`
rad/s against a 0.8 default.

Lower it (0.3), rerun **Run B** from T4, and see whether rotation wander drops. This only affects
the FMU path, so it needs `run.sh` with a canned plan rather than `tello_teleop`:

```
cd /root/groundstation/scripts/tello && FMU_FLAG=--canned-rotate ./run.sh
```

That flies takeoff, 90 cw, 200 ccw, land, with no VLM.

**Report:** displacement at 0.6 vs 0.3, or say you skipped it.

---

## T6 -- Translation across the matted area (NOT YET RUN)

**Why:** T4 proved the VPS holds during a stationary hover over one mat. It did NOT prove the lock
survives while the drone MOVES across a surface whose texture changes. Crossing a mat edge onto bare
floor is a lock-drop mid-flight, at speed, and that is the case the demo actually flies.

Cover the whole flight envelope plus a margin, edges taped. Then:

1. **T**, settle at ~1 m near one corner.
2. Translate corner to corner with **W**, slowly, and back.
3. Repeat across the other diagonal.
4. **L**.

**PASS:** the drone tracks the commanded direction and stops where you release, with no lurch or
runaway as it crosses seams.

**Report:** whether hold survived in motion, and whether any seam or edge caused a visible jump.
This is the last open question before trusting a matted floor for the demo.

## Report block -- copy, fill, hand back

### RESULTS -- 2026-08-11 (measured, from the logs handed back)

```
T1 rig health:      PASS
  RX quiet, streamon acked, AsyncKeyHook attached, 0 parse errors.

T2 override:        PASS  (closes this spec's Test line on real hardware)
  10 Enter presses -> exactly 10 toggles (5 engaged, 5 released).
  All 10 key RELEASES produced 0 spurious toggles: the press-only guard holds.
  No topic publish used at any point.

T3 first flight:    PASS with findings
  Takeoff stable, hover stable, all axes correct, yaw good, clean land.
  Teleop authority too low: 0.4 m/s mapped to only 40/100 stick. Raised to 0.8 m/s,
  env-tunable via TELLO_MOVE_MPS / TELLO_YAW_RADPS.
  Environment: WiFi degrades badly through walls. Household fans pull the drone in
  and win outright. The drone's own downwash perturbs it near surfaces.

T4 drift:           CAUSE FOUND, no cm figure
  Not measurable from telemetry: vgx/vgy read 0 both when the VPS is blind and when
  the drone is genuinely still, so the field cannot distinguish the two.
  VPS surface comparison, airborne samples with non-zero horizontal velocity:
    original reflective floor    0 / 277
    bed, floral pattern          1 / 123
    hard flat chair mats        72 / 118
  Over mats: 38 s hands-off hover, altitude drift only +0.20 m, no crash.
  On the original floor it could not hold 3 s and flew into a wall.
  Same drone, same room, same binary. Only the surface changed.

T5 yaw rate:        PARTIAL
  At 0.6 rad/s the drone traced an outward arc of roughly a quarter circle while
  rotating and never held station, ending in a wall. The bias travels with the
  airframe (body-fixed), and its magnitude grew rather than closing a circle.
  NOT RUN: the same test at 0.3 rad/s. Superseded in priority by the VPS finding,
  since that rotation test was flown on the bad surface.

T6 translation:     QUALIFIED -- lock survives motion, but coverage was far too small
  Protocol flown: takeoff, 10 s hands-off in the middle of the mats, then ~1 s
  pushes in each direction. Operator was on the sticks 14% of the time, mostly
  after the 20 s mark, nudging it back from the mat edges.
  Lock survived translation. Velocity reporting by 10 s bin:
      0-20 s   0% reporting, 0% stick   -- hands-off hover, genuinely still
     20-30 s  62% reporting, 29% stick  -- translating, lock holding
     30-40 s  35% reporting, 18% stick  -- translating, lock holding
     40-50 s  36% reporting, 13% stick  -- translating, lock holding
  Contrast: on the reflective floor the drone drifted hard and reported 0/277.
  Motion producing measurement is the proof the lock held.
  MEASURED DRIFT, hands-off windows totalling 35.9 s: mean 0.2 cm/s,
  worst single window 0.7 cm/s, longest clean window 13.2 s at 0.0 cm/s.
  Read as a ceiling of about 1 cm/s: 80% of idle samples fall below the
  field's 1 cm/s integer resolution.
  CAVEAT 1: a zero reading means EITHER the VPS is blind OR the drone is still.
  Never read zero alone as a lock failure; cross-check the stick column.
  CAVEAT 2 -- this is the important one. Conditions: room 3-3.5 m x 6-7 m, mats
  covering about 1 m2, so roughly 5% of the floor. Over the 49 s airborne window
  the drone reported velocity for only 13.8 s (28%); 35.3 s (72%) produced no
  measurement at all, and the operator reports it drifted QUICKLY during those.
  So the 0.2 cm/s above is drift WHILE THE LOCK HELD, sampled from the good 28%.
  It is a floor on the best case, NOT the drift you should plan a demo around.
  29% of commanded-motion time was also unmeasured -- the drone leaves a 1 m2
  patch in under a second of translation.

Batteries used: several.
```

### Blank template (for future runs)

```
T1 rig health:      PASS / FAIL
  RX quiet?                 y/n
  streamon ack?             y/n
  AsyncKeyHook attached?    y/n
  notes:

T2 override:        PASS / FAIL
  "MANUAL OVERRIDE engaged" on Enter?     y/n
  "MANUAL OVERRIDE released" on Enter 2?  y/n
  two clean cycles?                       y/n
  any topic publish needed?               y/n
  notes:

T3 first flight:    PASS / FAIL
  takeoff clean?            y/n
  hover stable?             y/n
  axes correct (W fwd, A left, R up, Q ccw)?  y/n
  land clean?               y/n
  notes:

T4 drift:
  Run A hover, 30 s, hands off
    run 1: ____ cm, direction ________
    run 2: ____ cm, direction ________
    run 3: ____ cm, direction ________
  Run B hover + 360 yaw
    run 1: ____ cm, direction ________
    run 2: ____ cm, direction ________
  direction repeatable across runs?  y/n
  yaw materially worse than hover?   y/n
  floor surface / nearby walls:
  notes:

T5 yaw rate (optional):  DONE / SKIPPED
  0.6 rad/s: ____ cm     0.3 rad/s: ____ cm

Batteries used: ____
Anything that scared you:
```

Attach `all_panes.txt` (captured with `tmux capture-pane -S - -p`) for T1-T2.
