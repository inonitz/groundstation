# B3 — SLAM pose → FMU (Tello position + return-to-start)

**Status:** scheduled / not started. **Created:** 2026-08-10. **Revised:** 2026-08-09 (session review —
see Revision log — **scope larger than originally specced**). **Branch:** `feature-slam-tello`
concept — in practice, whichever checkout B1 lands in first (see B1/B4's "Where this runs" notes).
**Depends:** B1 (must track first — and per B1's revision, B1 itself now has a build-bring-up gate
before tracking is even askable, so B3 is gated on TWO things landing, not one).
**ROADMAP:** 7.4, 2.3. **Lock:** `fmu_node.hpp` + `TelloBackend` files (`tello_backend.hpp`,
`tello_backend.cpp`, `tello_backend_base.hpp` — **add these three to `docs/LOCKS.md`'s table**, they
are untracked today, meaning implicitly free but about to become genuinely contended by this spec).
Serialize `fmu_node.hpp` with A3 if both are in flight (different checkouts per the branch note above
makes this moot in practice, but note it if B-track ever merges back into the showcase checkout before
A3 lands).

## Objective
Once stella tracks, feed `slam/pose` into the FMU as the Tello's horizontal position and add
return-to-start — the capability the Tello physically cannot do today.

## Grounding (verified against this checkout, 2026-08-09 — corrects the original spec materially)
- **Tello's x/y position is not "unintegrated" or "drifting" — it is a literal hardcoded zero, always.**
  The only write to `Odometry.pos` in `TelloBackend` is `tello_backend.cpp:154`:
  ```cpp
  od.pos = { 0.0f, 0.0f, __scast(f32, m_heightCm.load(...)) / 100.0f };
  ```
  There is no Simpson-rule integration, no dead-reckoning, no position-accumulator state anywhere in
  `tello_backend.{hpp,cpp}` or `tello_backend_base.hpp` (grepped, zero hits for "simpson"/`integrat*`).
  `docs/tello_backend_notes.md`'s "integrate body vgx/vgy... Simpson over 3 samples" is a design note
  that was never implemented — treat "consume slam/pose as x/y" as replacing a **constant zero**, not
  refining a drifting estimate. This doesn't change B3's plan, but it changes the risk: there's no
  fallback dead-reckoning to compare against if slam/pose misbehaves, so a sanity/bounds check on the
  incoming pose (e.g. reject a wild jump) matters more than "consume and trust" implies.
- **`TelloBackend` is ROS-free by design and cannot subscribe to `slam/pose` itself — this is new
  plumbing, not a wiring exercise.** `TelloBackend`'s constructor takes no node/callback-group params
  (`tello_backend.hpp:37`); `make_active_backend()` confirms explicitly (`active_backend.hpp:26-29`):
  ```cpp
  make_active_backend(rclcpp::Node* node, rclcpp::CallbackGroup::SharedPtr cbg) {
      (void)node; (void)cbg;   /* Tello is ROS-free: needs neither. */
      return std::make_unique<TelloBackend>();
  }
  ```
  `fmu_node.hpp:234-238`'s own comment: "Tello, being ROS-free, ignores them... no ROS leaks into a
  ROS-free backend." **B3 must add two things, not one:** (a) a `slam/pose` subscription in `FmuNode`
  itself (the locked file), and (b) a new setter on `TelloBackend`, e.g.
  `set_external_pose(f32 x, f32 y, f32 yaw)`, that the FMU's callback calls to inject pose — overriding
  the hardcoded-zero `od.pos.x/y`. This is real new cross-file plumbing, not "subscribe to a topic."
- **`returnToOrigin()` already exists and is directly reusable — genuinely less work than the original
  spec assumed.** `fmu_node.hpp:1155-1177` (currently called from the battery-RTH failsafe path,
  `fmu_node.hpp:1142-1147`):
  ```cpp
  Odometry od = m_backend->odometry();
  Vec3 homeFlu = enu_to_flu(Vec3{ -od.pos.x, -od.pos.y, 0.0f }, od.yaw);
  CmdGo g{}; g.x = homeFlu.x*100.0f; g.y = homeFlu.y*100.0f; g.z = 0.0f; g.speed = 80.0f;
  ```
  This is generic — it works purely off `od.pos`/`od.yaw`, so once B3 makes Tello's `od.pos.x/y` real
  (via the new setter above), `returnToOrigin()` needs **zero changes** to serve as B3's return-to-start.
  Call it directly rather than writing new fly-home logic. "Origin" is implicitly wherever `pos` was
  `(0,0)` at spawn, which is correct now that pos actually moves once slam/pose flows in (today it's
  always `(0,0)` since it never changes, so origin and current position are trivially and uselessly
  identical — this only becomes meaningful once B3 lands).
- **ToF-based scale anchor needs new plumbing too.** `TelloState` (`tello_backend_base.hpp:94-103`) has
  both `tof` (cm) and `h` (baro, cm) fields, but `stateLoop()` only stores `st.h` into `m_heightCm`
  (`tello_backend.cpp:171`) — `st.tof` is parsed and immediately discarded. Add an `m_tof` atomic +
  store it in `stateLoop()` + a getter, before it can be used as a scale anchor.
- `docs/LOCKS.md` confirmed `fmu_node.hpp` FREE; the three `TelloBackend` files aren't in the table at
  all (untracked, implicitly free per protocol) — add them once this spec starts, since it's about to
  make them genuinely contended (B5 also touches `tello_backend_base.hpp`'s velocity constants).

## Scope
- **In:** add `set_external_pose(f32 x, f32 y, f32 yaw)` to `TelloBackend`, called from a new
  `slam/pose` subscription in `fmu_node.hpp` (replaces the hardcoded `0.0f, 0.0f` in `od.pos`); add a
  basic sanity/bounds check on incoming pose (reject an implausible jump — no dead-reckoning fallback
  exists to fall back on, so this is the only guard); add `m_tof` storage + getter for the scale anchor;
  reuse `returnToOrigin()` (`fmu_node.hpp:1155`) directly for the return-to-start command, do not write
  new fly-home logic.
- **Out:** OctoMap / A* planning (post-POC, ROADMAP 7.2-7.3).

## Files
- Modify: `source/llm_to_action/fmu/fmu_node.hpp` (subscription, wiring to `set_external_pose`).
- Modify: `source/llm_to_action/tello_backend/tello_backend.hpp` (`set_external_pose` declaration, `m_tof`).
- Modify: `source/llm_to_action/tello_backend/tello_backend.cpp` (`set_external_pose` impl, `stateLoop()`
  storing `st.tof`).

## Tests to create
- **[AUTO]** SITL canned return-to-start driven by `slam/pose` -> assert the drone returns to origin
  within tolerance (ground truth available in sim) — this can reuse the existing `returnToOrigin()` path
  end to end, so the assertion looks like the existing battery-RTH test's return-distance check.
- **[AUTO]** a synthetic wild-jump pose gets rejected by the sanity check, not applied to `od.pos`
  (new — the original spec had no test for the one new guard this revision adds).
- **[HUMAN]** hardware return-to-start once stella runs on the real drone.

## Acceptance
Return-to-start works in sim on slam pose; the FMU consumes it as Tello odometry via the new
`set_external_pose` path; a wild/implausible pose reading does not corrupt `od.pos`.

## Change-impact (per `docs/code-guidelines.md`)
- **What this changes:** `TelloBackend.od.pos.x/y` goes from a hardcoded constant `0.0f` to a live,
  externally-set value — this is a real behavior change for anything reading Tello odometry position
  (currently nothing meaningfully does, since it's always zero today).
- **Breaks existing behavior:** no existing SITL scenario uses `TelloBackend` (all 20 are PX4), so
  nothing regresses there. Any prior manual Tello testing that assumed `pos` is always `(0,0)` would see
  different behavior — expected and intended.
- **Tests that re-run as-is:** all 20 SITL scenarios (A1) — PX4-only, unaffected.
- **Tests that are new:** the two listed above.

## Agent notes
Gated on B1 landing (both its build-bring-up stage and its tracking-quality stage — see B1's revised
Agent notes). This is the only slam-branch spec that touches the FMU hotspot; add the three
`TelloBackend` files to `docs/LOCKS.md`'s table when starting, since B5 also touches
`tello_backend_base.hpp` and the two should not run concurrently on that file.

## Revision log
- 2026-08-09: corrected "unintegrated/drifting" framing — position is a literal hardcoded zero, not a
  drifting dead-reckoned estimate, meaning there's no existing fallback to sanity-check new pose
  readings against (added a sanity-check task and test as a result); found `TelloBackend` is ROS-free
  and cannot subscribe to `slam/pose` itself, requiring a new FMU-side subscription + backend setter,
  not just "consume a topic"; found `returnToOrigin()` already exists and is directly reusable with zero
  changes, once `od.pos` is real — genuinely less work than assumed on that front; found ToF is parsed
  but discarded, needs new storage before use as a scale anchor; flagged that B5 also touches
  `tello_backend_base.hpp`, so the two specs need explicit lock coordination beyond what the original
  spec noted.
