# Agent 5 — laptop handoff (SLAM hover-hold), 2026-08-12

For the Agent 5 session running on the **laptop** (the machine on the Tello WiFi, `mint0`). The
workstation session did all it can offline; hover-hold validation is hardware-only and lives here now.

Read the full context in the spec Report first:
`docs/active/sitl-agent5-slam-stabilization-spec.md` (2026-08-12 entries). This file is the actionable
runbook on top of it.

---

## TL;DR — is this even on the demo's critical path?

**No, probably not for tomorrow.** If a small textured platform/pad sits under the flight zone, the Tello
**VPS holds station for free** — so the SLAM hover-hold is not needed for the demo. Tomorrow's Demo 3 is:
FOLLOW (Agent 1) does the following, VPS holds idle, native `land()` is the emergency. The must-have is
**FOLLOW working real-time after the VLM** (Agent 1's lane), not this.

This hover-hold work is the **2-week contest build**. Worth closing out the diagnosis, but it blocks
nothing tomorrow. Don't let it.

**Surface caveat:** a textured pad also RE-MASKS the SLAM test — the VPS holds, so you can't tell if SLAM
held. To validate SLAM *specifically* you still need **bare floor** (VPS blind). For the demo, bare floor
is irrelevant; use the pad.

---

## Current state (what's already built)

- `tello_slam_hold` node: built + instrumented. Reads `slam/pose` + `slam/tracking_state`, holds the
  engaged position via `set_body_velocity`, lands on sustained loss. Per-tick `[hold]` diagnostic; gains
  env-tunable.
- Frame mapping validated in C1: stella map is camera-optical (`+x right, +y down, +z forward`); Tello
  horizontal plane = map `(x,z)`, up = `-y`.
- C1 go/no-go: PASS on textured forward scenes (~27 Hz, ~100% uptime).
- Offline unit tests: 4/4 pass (`scripts/tello/slam/runtests.sh`).
- **Open blocker:** first bare-floor hover-hold flights did not visibly stabilize. Mid weak-authority-vs-
  sign-bug diagnosis. The instrumented log resolves it (below).

---

## Setup checklist (do these once, in a batch)

1. **Sync the repo.** The workstation edits (instrumented node + `test3.sh`) must be on the laptop. After
   the human commits + pushes `feature-llm-driver` from the workstation: `git pull` here. Confirm you have
   `scripts/tello/slam/test3.sh` and the instrumented `source/llm_to_action/tello_backend/test/tello_slam_hold.cpp`
   (it contains `TELLO_HOLD_KP` and `[hold] HOLD alive=` strings).
2. **Build both trees on the laptop:**
   ```bash
   cd ~/groundstation
   # SLAM tree (stella):
   cmake -B build/release/slam -S . -DGROUNDSTATION_BUILD_SLAM=ON   # + your usual release flags
   cmake --build build/release/slam --target stella_vslam_monocular -j
   # Tello tree (RX + hover node):
   cmake -B build/release/shared -S . -DGROUNDSTATION_BUILD_EXECUTABLE=ON -DGROUNDSTATION_BUILD_BACKEND_TELLO=ON
   cmake --build build/release/shared --target tello_slam_hold llm_to_action_gstreamer_rx -j
   ```
   `test3.sh` expects the binaries in `build/release/shared/tello/bin/`. If the Tello output dir differs
   on the laptop, either fix `TELLO_BIN_DIR` at the top of `test3.sh` or copy the built binaries there.
   Sanity: `build/release/slam/bin/stella_vslam_monocular` and
   `build/release/shared/tello/bin/{tello_slam_hold,llm_to_action_gstreamer_rx}` must exist + be `+x`.
3. **Tello:** charged, on its WiFi (`TELLO-XXXXXX`; host becomes `192.168.10.2`). `/dev/input` access for
   the keyboard hook (input group or run with sudo).
4. **Space:** a small BARE-floor area (~2×2 m is enough) for the honest SLAM test. Textured forward scene
   (room walls / furniture / a poster) so stella tracks — the forward camera, NOT the floor.
5. **Fixed phone on a tripod** to film the hover for physical drift (`scripts/tello/measure_drift.py`).

---

## The diagnostic run (this is the one thing that matters here)

```bash
cd ~/groundstation/scripts/tello/slam
./test3.sh
```
It prints a `hold log : runs/hold_<stamp>.log` path. In the **3rd pane** (`tello_slam_hold`):
`T` takeoff → fly up ~1 m over bare floor → `H` engage hold → **leave the sticks alone ~15–20 s** →
`L` land → `Esc`.

Read `runs/hold_<stamp>.log`. The line to read, twice a second:
```
[hold] HOLD alive=1 err(E=+0.32 N=-0.10)m scale=1.42 h=0.90 vcmd(F=+0.15 L=-0.08 U=+0.02)m/s
```
- `err` is WORLD ENU metres (setpoint − measured). `vcmd` is BODY FLU m/s (forward, left, up).
- At the engage heading, a CORRECT hold has `sign(F) = sign(errN)` and `sign(L) = sign(−errE)`.

### Decision tree
- **`alive=0` or lots of `LOST-HOLD` lines** → tracking_state/pose not reaching the node. Check
  `ros2 topic echo /slam/tracking_state` and `/slam/pose` while flying. If pose flows but state doesn't,
  it's a QoS/topic issue — ping the workstation Agent 5.
- **Correct sign, but `|vcmd|` tiny or pinned at the maxVel cap (0.4)** → **WEAK (case C)**. Raise
  authority and re-fly:
  ```bash
  export TELLO_HOLD_MAXV=0.8 TELLO_HOLD_KP=1.2
  ./test3.sh
  ```
  Escalate `TELLO_HOLD_MAXV` toward 1.0 if still weak. If it starts oscillating as you raise it, back
  `TELLO_HOLD_KP` down (0.8–1.0). This is the leading hypothesis — `tello_teleop.cpp` warns 0.4 m/s is too
  little to fight indoor drift.
- **`vcmd` pushes the SAME way `err` grows (drone accelerates away)** → **SIGN/FRAME bug (case A)**. The
  transform to check is `worldErrToBody` + the axis remap in `tello_slam_hold.cpp`. Concretely: place the
  drone, `H`, then hand-nudge it EAST (right); `errE` should go negative and `vcmd L` should go negative
  (push right→ actually left-stick to return... verify against the printed signs). If a sign is inverted,
  flip it in `worldErrToBody` and rebuild. Log the fix in the spec.
- **`scale` wildly off** (not ~1–2; e.g. 0.01 or 1000) → the metre error is garbage → looks weak or
  unstable. Check `tof` is valid in flight (the height feeding `scale = tof/(-y)`).

### What to report back (to the spec + workstation Agent 5)
- The `hold_<stamp>.log` (or the decisive `[hold] HOLD` lines).
- Which case (A/C/alive/scale) it was, and whether raising authority fixed it.
- If validated: film hold-ON vs hold-OFF over bare floor, run `../measure_drift.py` on each, report the
  two drift numbers (metres). That's the C2 result.

---

## Design gotchas (so you don't re-learn them the hard way)

- **VPS looks DOWN, stella looks FORWARD — different surfaces.** Floor mats feed the VPS, not stella. A
  "good" hold over mats is the VPS, not SLAM. Validate SLAM over BARE floor only.
- **`feature_scout.py` "POOR" lies.** The measure node (`[TELLO_SLAM]`) is the truth. It read 100% uptime
  while the scout said POOR. Trust the measure node.
- **`return/peak` in the C1 digest is NOT drift** — it's an up-to-scale return-to-start proxy for a manual
  path. Physical drift = fixed-camera clip + `measure_drift.py`.
- **Heading is pinned at engage (`yaw0=0`).** The ENU→body mapping is exact only while the drone holds its
  engage heading. Do NOT engage a hold after a large yaw — the live-heading rotation (`worldErrToBody`,
  `headingRad`) is a wired-but-unvalidated seam (C1 logged position only, not the quaternion).
- **No dead-reckoning on the Tello.** `vgx/vgy` read false-zero when the VPS is blind. Loss → hold ~2 s →
  land. There is no SLAM↔DR switch; it's SLAM↔hold↔land.

## ArUco fallback
`scripts/tello/slam/aruco_pose.py` exists, self-test passes, NOT integrated. Wire as a second pose source
behind a switch (SLAM primary, ArUco on loss) AFTER hover-hold validates — the controller is
source-agnostic, so it's a wiring job. The tag must be a PHYSICAL marker in the FORWARD camera view
(on-screen fails: rolling shutter × refresh; floor tag is invisible to the forward-only camera).

## No git writes
The human owns all git. Suggest commits in house style; do not stage/commit/push.
