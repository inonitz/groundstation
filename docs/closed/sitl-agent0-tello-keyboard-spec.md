# Agent 0 — Physical Tello + keyboard override (owner: human)

**Date: 2026-08-11** · Deadline: Wed evening 2026-08-12.

**Mission**: get the physical Tello flyable by keyboard and characterize its in-space drift. You also
run the physical tests other agents' SLAM/FOLLOW work depends on.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + LOCKS + commit rules),
then `CLAUDE.md`, `docs/code-guidelines.md`. Study:
`docs/active/2026-08-10-tello-physical-handoff.md`, `scripts/tello/README.md`,
`docs/tello_backend_notes.md`; `fmu_node.hpp` `keyCallback` (`1490-1513`) + `overrideCallback`
(`1443`) + the manual-override block in `controlLoop` (`538-543`).

**Your place in the plan**: you unblock manual flying for Agents 1 (FOLLOW test) and 5 (SLAM
assessment). The Tello build/config is already done.

## Root cause (keyboard "keys captured, no motion")

`keyCallback` (`fmu_node.hpp:1494`) drops all movement keys unless `m_manualOverride` is true. That
flag is set ONLY by the `/fmu/in/override` Bool topic — which **nothing publishes and no key toggles**.
So WASD are logged but inert. (`keyCallback` also only implements WASD/arrows/Space — no arm/takeoff/
land keys, despite the README.)

## Do

1. **Keyboard override fix**: in `keyCallback`, handle a toggle key (Enter — already bound/published by
   the keyboard node) **before** the `!m_manualOverride` early-return at line 1494, flipping
   `m_manualOverride` (+ `zeroManualVel()` on disengage) and logging the new state. Lock `fmu_node.hpp`
   in `docs/LOCKS.md` first (short hold).
2. Fix `scripts/tello/README.md` — it wrongly claims keyboard does arm/takeoff/land.
3. Fly bring-up + manual control. Characterize the **drift**: it is the whole airframe drifting in
   space (the Tello holds attitude, not position — no XY feedback), NOT a rotate-specific bug. This is
   the case for Agent 5's SLAM. Optionally test whether a lower `rotateMaxYawRate` (`config/tello.yaml`,
   no rebuild) reduces rotation wander.

**Interim workaround** (until step 1 lands): engage override manually with
`ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data:true}"`.

## Test

Press Enter → override engages; WASD = plane, arrows = alt/yaw, Space = hover, with no manual topic pub.
Enter again disengages.

## Locks

`fmu_node.hpp` (short hold for `keyCallback`).

## Constraints

No git writes — suggest `agent0: keyboard override toggle`. Prose per `docs/writing-style.md`.

## Report
_(append findings / blockers / the measured drift behavior below)_

### 2026-08-11 — steps 1 and 2 done, step 3 blocked on hardware

**Root cause confirmed as written.** `keyCallback` gated every key behind `m_manualOverride`,
and nothing in the running rig publishes `/fmu/in/override`. A toggle key placed after that
gate could never fire, so the gate had to move.

**Fix.** `keyCallback` now handles Enter before the override gate. The handler ignores the key
release, since the release would undo the toggle a few milliseconds after the press. Rather
than flip the atomic in place, it synthesises a `Bool` and calls `overrideCallback`. That keeps
one engage/disengage path for both the key and the topic, so the keyboard also gets the
interrupt reset and the handback re-plan instead of a bare flag flip. Tello target builds
clean; the only warning is the pre-existing packed-union one at `fmu_node.hpp:132`.

**Second defect, wider than the spec.** The keyboard has no arm, takeoff, or land key anywhere
in the FMU, and adding one was not in scope. Takeoff and landing reach the backend only as
plan commands from the VLM. So `run.sh` on its own cannot get a Tello off the ground. The
manual path is the `tello_teleop` harness under `tello_backend/test/`, which does have T and L.
The README now says this instead of claiming the keyboard lands the drone.

**Third defect, minor.** The README told the pilot to click the keyboard pane for focus. The
hook reads evdev globally, so focus is irrelevant, but it needs read access to `/dev/input`.
Corrected, since a pilot chasing focus would miss the real permission failure.

**Blocked.** Step 3 is the flight itself: bring-up, manual control, and the drift
characterization for Agent 5. It needs the physical Tello, so the human owner flies it. The
keyboard fix is ready for that flight. Worth checking in the air whether Enter mid-flight
hands back cleanly, because handback drains the task queue and forces a VLM re-plan.

**Change impact.**

| Change | Behavior touched | Breaks it? | Test impact |
|---|---|---|---|
| Enter toggle in `keyCallback` | Enter was inert; movement keys were inert without a manual topic pub | No. Additive. WASD/arrows/Space semantics unchanged once engaged | No existing test covers `keyCallback`. Gate is the physical flight in step 3 |
| Enter routed via `overrideCallback` | Keyboard engage/disengage now drains the queue and re-plans, matching the topic path | No. This is the topic path's existing behavior, reused | Same physical gate |
| `scripts/tello/README.md` | Docs only | No | None |

### 2026-08-11 — three infra bugs blocked verification, all fixed

The first SITL override run produced no `MANUAL OVERRIDE` lines at all. None of it was the
keyboard fix.

**The keyboard hook never started.** `/dev/input/event18` failed to open, and the producer
treated any failed open as fatal, discarding the nine devices it had already opened. Root
cause is the container: `/dev` is a tmpfs snapshot taken at creation, while
`/proc/bus/input/devices` is the host kernel's live view, so devices plugged in later are
listed with no node behind them. Six were phantoms here, including the operator's own HP OMEN
keyboard on `event19`. Fixed in `async_key.cpp`: discovery drops paths with no node, the open
loop skips failures, and only an empty set is fatal. The loop also leaked a descriptor for
every non-keyboard it opened; that is closed now. `scripts/devenv.sh` bind-mounts `/dev/input`
so hotplugged keyboards exist inside the container at all.

**llama-server never started.** `${VLM_KV_ARG--cache-type-k ...}` in `scripts/test/lib/sim_core.sh`
spends its first dash on the `-` default-value operator, so llama-server saw `-cache-type-k`
and refused. Without a VLM the FMU got 0-char plans and sat at `fs=0`, so nothing ever took
off. `${VLM_NGL_ARG--ngl 99}` on the same line has the identical shape and survives only
because `-ngl` is a real short flag; both now carry a space.

Verified after the fix: the hook logs `AsyncKeyHook successfully attached` and binds keycode 28.
Only `event4`, the built-in keyboard, is a real keyboard here. The HP OMEN needs a container
restart to pick up the new mount, or `mknod /dev/input/event19 c 13 83` to test before that.

The `rotateMaxYawRate` experiment is untouched. `config/tello.yaml` already sits at 0.6 rad/s
against a 0.8 default, so the gentler value is in place and needs no rebuild to change.

### 2026-08-11 — spec closed on real hardware

T1 rig health PASS. T2 keyboard override PASS on the physical Tello: 10 Enter presses produced
exactly 10 toggles, 5 engage and 5 release, and all 10 key releases produced zero spurious toggles.
The press-only guard holds. That closes the Test line of this spec on real hardware.

T3 flew. All axes correct, yaw good, takeoff stable. Teleop authority was too low (0.4 m/s maps to
only 40 of 100 stick); raised to 0.8 m/s and made env-tunable.

The drift mission item resolved differently than the spec assumed. The spec framed the drift as an
inherent property of the airframe for Agent 5 to correct. It is not. It is a Vision Positioning
System failure over unreadable floors. Over hard matte mats the same drone held a 38 s hands-off
hover; over the original reflective floor it could not manage 3 s. See the NOTES entry.

No drift figure in centimetres. `vgx`/`vgy` report 0 both when the VPS is blind and when the drone
is genuinely still, so telemetry cannot measure it. `scripts/tello/measure_drift.py` (written and
self-tested against a synthetic clip) is the route if a number is wanted.

Agent 5 impact: SLAM does not have to supply everything. On a VPS-readable surface the Tello has
real position hold, so SLAM corrects an already-stable drone. The surface is the precondition.

### 2026-08-11 — what is left

Two things are open, and neither blocks another agent.

**T6, translation across a matted floor.** The 38 s result was a stationary hover over one mat. It
does not prove the lock survives while the drone moves across a surface whose texture changes, and
crossing a mat edge onto bare floor is exactly a mid-flight lock drop. This is the last question
before trusting a matted floor for the demo. Written up as T6 in the flight runbook.

**The drift figure in centimetres.** Not obtainable from telemetry, for the reason above.
`scripts/tello/measure_drift.py` against a phone video is the route if a number is wanted. With the
surface cause understood, the number is now a nice-to-have rather than a deliverable.

Also not run: the `rotateMaxYawRate` 0.3 rad/s comparison from Do item 3. The 0.6 rad/s arc was
flown on the bad surface, so that comparison should be repeated on mats or dropped.

### 2026-08-11 — T6 passed, drift measured, spec fully closed

The translation test ran over four chair mats: takeoff, 10 s hands-off in the middle, then ~1 s
pushes in each direction. The VPS lock survives translation. Velocity reporting rose from 0% while
genuinely stationary to 62% once the drone was commanded to move, and held at 35-36% through the
rest of the manoeuvring. On the reflective floor the same drone drifted hard and reported 0 across
277 samples, so motion producing measurement is the proof the lock held.

**Drift over a readable surface: mean 0.2 cm/s, worst window 0.7 cm/s, across 35.9 s of hands-off
windows.** The longest clean window was 13.2 s at 0.0 cm/s. Treat about 1 cm/s as the ceiling, since
80% of idle samples fall below the field's 1 cm/s integer resolution.

That closes Do item 3. The drift figure the spec asked for exists, and it is small.

One trap for anyone reading these logs: a zero velocity reading means EITHER the VPS is blind OR the
drone is genuinely still. The two are indistinguishable from the field alone. Always cross-check the
commanded-stick column before calling a zero a lock failure. I made exactly that mistake once while
reading the T6 bins.

Still not run: the `rotateMaxYawRate` 0.3 rad/s comparison. The 0.6 rad/s arc was flown on the bad
surface, so that data is confounded and the comparison should be repeated on mats or dropped.

### 2026-08-11 — correction: the drift figure was measured on a 5% anchor

Conditions that belong with every number above, and which I failed to record at the time: the room
is 3-3.5 m by 6-7 m, and the chair mats covered about 1 m2. That is roughly 5% of the floor.

Across the 49 s translation flight the drone reported velocity for 13.8 s, 28% of airborne time.
The remaining 35.3 s produced no measurement, and the operator reports the drone was drifting
quickly through those stretches. A blind VPS reports zero and integrating zero reads as stationary,
so those fast excursions are invisible in the telemetry by construction.

**The 0.2 cm/s therefore describes drift while the lock held, sampled from the best 28% of the
flight. It is a floor on the good case, not a figure to plan a demo around.** 29% of
commanded-motion time was also unmeasured, which is consistent with the drone leaving a 1 m2 patch
within a second of translation.

What survives from the earlier conclusions: the VPS is alive, the surface determines whether it
locks, and a readable surface produces genuine station-keeping. What does not survive is any claim
that mats solved the problem. A patch is a weak anchor. Coverage has to span the whole flight
envelope, which for a room this size is about 24 m2 -- roughly 100 tiles of 50 cm.

I over-claimed twice from this data: first reading a hands-off hover as a lock failure, then reading
a 1 m2 anchor as a solution. Both errors came from treating a zero velocity reading as information.
It is not; it is the absence of information.

### 2026-08-11 — SITL override docs brought in line with the fix

`scripts/test/SITL/override/README.md` still told the operator to publish `/fmu/in/override` and to
focus the keyboard pane. The Bool publish was the workaround for the bug this spec fixed, and the
focus advice was never true -- the hook reads evdev globally. Both corrected, with the topic kept as
a documented fallback for headless runs. `filter.sh`'s FAIL and WARN text asked for the same publish;
it now names the Enter key. `scripts/tello/run.sh` carried the same two false claims in its own
startup echoes and is corrected too.