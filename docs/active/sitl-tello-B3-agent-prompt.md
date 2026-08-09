# Agent prompt — B3: SLAM pose → FMU (Tello position + return-to-start)

Paste this whole file as the task for a fresh agent. It has no memory of any prior session — everything
it needs is below or in the referenced spec.

## Before you start — check this is actually ready

This task is gated on **B1 Task 5** (does stella_vslam actually track in SITL — see
`docs/active/sitl-B1-task5-agent-prompt.md`). Check
`docs/active/sitl-2026-08-10-spec-B1-stella-vslam-sitl-bringup.md`'s Status line before starting:
- If it still says Task 5 open / no verdict recorded: **you can still do the code-writing steps below**
  (they don't need live SLAM data), but the final SITL acceptance test (return-to-start driven by real
  `slam/pose`) can't run yet — stop after the code + the synthetic sanity-check test, and say so plainly
  in your report rather than skipping or faking the live test.
- If it says B1 tracking failed: still write the code (it's needed regardless, and B4's fallback doesn't
  make this dead work), but flag in your report that the live acceptance test has no path to pass yet.
- If it says B1 passed with real numbers: do everything below including the live SITL test.

Full spec: `docs/active/sitl-tello-2026-08-10-spec-B3-slam-pose-into-fmu.md`.

## Your task

The Tello's x/y position is a **literal hardcoded zero** today — not a drifting estimate, an actual
constant (`tello_backend.cpp:154`: `od.pos = { 0.0f, 0.0f, height }`). Make it real by feeding
`slam/pose` in, and give the drone a working return-to-start.

## Key facts (verified against this checkout 2026-08-09 — don't re-derive these, they're already checked)

- **`TelloBackend` is ROS-free by design** — it cannot subscribe to `slam/pose` itself.
  `make_active_backend()` in `active_backend.hpp:26-29` explicitly discards the node/callback-group args
  for Tello (`(void)node; (void)cbg;`). This means real new plumbing: (a) a `slam/pose` subscription in
  `FmuNode` itself (`fmu_node.hpp` — this file is locked, see below), and (b) a new setter on
  `TelloBackend`, e.g. `set_external_pose(f32 x, f32 y, f32 yaw)`, that the FMU's subscription callback
  calls. This is not "just wire a topic" — it's cross-file plumbing.
- **`returnToOrigin()` already exists and needs zero changes to serve as return-to-start.**
  `fmu_node.hpp:1155-1177` (currently called from the battery-RTH failsafe path) works purely off
  `m_backend->odometry()`'s `pos`/`yaw`. Once your setter makes `od.pos.x/y` real, call this function
  directly for B3's return-to-start — do not write new fly-home logic.
- **No existing fallback to sanity-check pose against** — because position was always zero, there's no
  dead-reckoning estimate to compare an incoming `slam/pose` reading to. This means a sanity/bounds check
  on the incoming pose (reject an implausible jump) is the *only* guard against a bad SLAM reading
  corrupting `od.pos` — treat this as required, not optional polish.
- **ToF is parsed but discarded** — `TelloState` (`tello_backend_base.hpp:94-103`) has a `tof` (cm) field;
  `stateLoop()` (`tello_backend.cpp:171`) only stores `st.h` (baro) into `m_heightCm`, `st.tof` is dropped.
  Add an `m_tof` atomic + store it in `stateLoop()` + a getter — this is prep for a scale anchor, not
  fully wiring scale correction (out of scope here, just make the value available).

## Standing rules for this repo

- No git writes. Read-only git is fine. End with suggested commit commands.
- Native `Read`/`Grep`/`Glob`/`View`/`Echo` are project-denied. Use `rtk read`/`rtk grep`/`rtk ls`/`rtk find`/`rtk git`.
- To edit an existing file: native `Edit` requires a prior native `Read` (denied) — use a Python heredoc
  (`assert s.count(old) == 1` before replacing).
- **Lock protocol:** `fmu_node.hpp` and the three `TelloBackend` files
  (`tello_backend.hpp`/`tello_backend.cpp`/`tello_backend_base.hpp`) are the contended hotspot.
  `docs/LOCKS.md` — check it first, add an entry for these files before you start editing, remove it when
  you're done. B5 (Tello stick calibration) also touches `tello_backend_base.hpp` — if `docs/LOCKS.md`
  shows a B5 agent already has it locked, stop and report rather than editing concurrently.

## Files

- Modify: `source/llm_to_action/fmu/fmu_node.hpp` (new `slam/pose` subscription, wiring to
  `set_external_pose`, plus a call to `returnToOrigin()` on whatever trigger the spec/your judgment
  decides for return-to-start — check how the existing battery-RTH path triggers it as precedent).
- Modify: `source/llm_to_action/tello_backend/tello_backend.hpp` (`set_external_pose` declaration, `m_tof`
  member).
- Modify: `source/llm_to_action/tello_backend/tello_backend.cpp` (`set_external_pose` implementation,
  `stateLoop()` storing `st.tof`).

## Steps

1. Take the `docs/LOCKS.md` entry for the four files above.
2. Add `set_external_pose(f32 x, f32 y, f32 yaw)` to `TelloBackend` — implementation should set the
   backing fields that `odometry_impl()` reads for `pos.x`/`pos.y` (and yaw if applicable — check how yaw
   is currently sourced before assuming it needs to change too).
3. Add the sanity/bounds check: reject a pose update that implies an implausible jump (pick a reasonable
   bound — e.g. max plausible displacement between consecutive updates given the Tello's real speed
   envelope, check `tello_backend_base.hpp` or the spec for existing velocity constants to ground this
   number, don't invent one arbitrarily).
4. Add `m_tof` atomic + getter to `TelloBackend`; store `st.tof` in `stateLoop()` alongside the existing
   `st.h` handling.
5. Add the `slam/pose` subscription in `fmu_node.hpp`, calling `set_external_pose()` in its callback.
6. Wire return-to-start to call the existing `returnToOrigin()` (`fmu_node.hpp:1155`) — do not duplicate
   its logic.
7. Build:
   ```bash
   cmake --build build/release/tello --target all -j"$(nproc)"
   ```
   (or whichever Tello build tree already exists from B4 — check `rtk ls build/release/` first rather
   than assuming the path.)
8. Release the `docs/LOCKS.md` entry once your edits are done (even if tests are still pending).

## Tests

- **[if B1 has a passing verdict] Live SITL test:** run a canned return-to-start scenario driven by real
  `slam/pose` from B1's pipeline (`scripts/test/slam/run.sh` or a variant), assert the drone returns to
  origin within a reasonable tolerance using sim ground truth — same shape of assertion as the existing
  battery-RTH test's return-distance check (find that test and mirror its structure, don't invent a new
  pattern).
- **[always, regardless of B1's status] Synthetic sanity-check test:** feed `set_external_pose()` a wild,
  implausible jump directly (bypassing SLAM entirely — just call the setter in a small standalone test) and
  assert it's rejected, `od.pos` unchanged. This doesn't need B1 or live SLAM at all — write and run it
  either way.

## Report back (required)

1. Confirm the four-file lock was taken and released in `docs/LOCKS.md`.
2. Whether B1 had a passing verdict at the time you ran — and therefore whether the live SITL test ran,
   and its result if so.
3. The synthetic sanity-check test result — this should always be reportable regardless of B1's status.
4. Build confirmation (exact binary path).
5. Anything you found that contradicts the "Key facts" section above — if `returnToOrigin()` or the
   `TelloBackend` ROS-free assumption turned out stale by the time you're running this, say so explicitly,
   don't silently work around it.
6. Suggested commit command(s) for the human.
