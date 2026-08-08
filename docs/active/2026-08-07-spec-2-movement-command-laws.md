# Spec 2 — Movement command laws

**Status:** unassigned (for a spawned session). **ROADMAP:** 5.2 (GO redesign), 1.1.6 (ORBIT),
1.1.7 (SEARCH), 5.3 (safe-landing servo).
**Owns (edits):** `source/llm_to_action/fmu/fmu_node.hpp` (parser, dispatch switch, movement handler),
`.../fmu/fmu_node_base.hpp` (constants), `.../fmu/llm_base.hpp` (VLM action schemas).
Heavy overlap of the movement handler / dispatch switch / parser with Spec 1 & 4 — overseeing session
merges. Keep each command's code in its own clearly-labelled block.

> **Repo conventions (start-cold):** use `rtk read/grep/ls` (native Read/Grep/Glob are forbidden by
> `CLAUDE.md`); edit via python heredocs with `assert s.count(old)==1`. **Never touch the
> `GenericCommand` byte layout.** Follow the existing APPROACH servo (5.1) and GO cross-track patterns
> exactly. No full builds; human does build + SITL.

## Reference patterns (already in the tree — copy these, don't invent)
- **Parser** `translateToBaseCommands` (~line 819): `else if (action == "...")` branches build a
  `Cmd*` and enqueue. Add local `Cmd*` decls near the top with the others.
- **Dispatch** `switch (id)` (~line 632): `case CommandID::GO/APPROACH:` freeze per-command state at
  activation (target, speed) from `od = m_backend->odometry()`.
- **Movement** `if (m_hasActive)` chain (~line 427): `if (id==GO){...} else if (id==APPROACH){...}` —
  per-tick control law + `completeCurrent("..._ok")` / FAIL.
- **Live-detection aim:** `detectionByLabel` (5.1.1) + the APPROACH yaw-center/range-decel servo
  (5.1.2) already do "aim from the current frame." This is the substrate to reuse.

## Design
### 5.2 GO redesign (drift-free, self-contained)
Today GO freezes a world-ENU target **once** from drifting odometry (dispatch ~line 653). Redesign:
- If the `go` command names a target object (`"target_object"`), recompute the aim **per tick** from
  live perception (reuse the APPROACH aim substrate) → drift-free, re-grounds each tick.
- If it's a bare relative offset (no target), keep today's frozen start→target cross-track line
  (correct for dead-reckoned nudges).
- **Refactor requirement (user, explicit):** factor the per-tick "aim from live detection → world
  velocity" into ONE small reusable unit shared by APPROACH + GO (+ ORBIT + safe-landing). The code
  must read as self-contained, not hardcoded/inlined per command. Arbitrary world points (no target,
  no offset) are **out of scope** — that is Being-B/SLAM.

### 1.1.6 ORBIT (target-anchored)
Schema already advertised (`llm_base.hpp` ~line 56): `{"action":"orbit","target_object","radius_cm",
"angle_deg","direction":"cw|ccw","speed"}`. Add `CmdOrbit` (struct exists, line ~91) parse + dispatch
+ movement. Movement: hold `radius` from the tracked target (perception aim) while progressing around
the circle at `speed`; sweep `angle_deg` then `completeCurrent("orbit_ok")`. Target lost → FAIL
(mirror APPROACH lost-target). Perception-gated.

### 1.1.7 SEARCH (2D circle, no target)
**Check `llm_base.hpp` — SEARCH may not be advertised yet; if missing, add the schema + a line in the
system prompt.** `CmdSearch` struct exists (line ~99). Movement: fly a 2D circle / sweep pattern to
bring an object into view; `completeCurrent("search_ok")` when the named object appears in the
snapshot, or after a full sweep → FAIL/`search_exhausted`.

### 5.3 Safe-landing servo
Likely needs a new schema (`{"action":"safe_land","target_object"}` or landmark) — add to
`llm_base.hpp` + system prompt. Feedback law: keep the landmark centered under the drone (perception
aim → lateral correction) while descending; when centered within tolerance AND low → transition to
the normal LAND state machine (reuse the flare, Spec 4). VLM picks the spot; this executes the precise
go-over-and-descend. Do **not** duplicate the LAND descent — hand off to `FlightState::LANDING`.

## New constants (fmu_node_base.hpp)
Orbit: `kOrbitRadiusToleranceM`, `kOrbitTangentialGainHz`. Search: `kSearchSweepSpeed`,
`kSearchCircleRadiusM`. Safe-land: `kSafeLandCenterTolM`, `kSafeLandDescendStartAltEnu`. Tune in SITL.

## Testing (log-based, SITL)
Reuse the canned-approach rig with a detected object (vendored hatchback gz model). Canned plans:
takeoff → orbit/search/safe_land → assert `orbit_ok`/`search_ok`/safe-land handoff logs. Lost-target
paths assert FAIL. Coordinate canned infra with Spec 4.

## Out of scope
Collision avoidance during these maneuvers (Spec 1 owns the boundary/interrupt). Arbitrary-point GO
(Being B). Multi-orbit > 360°.

## Implementation report (session: append below, do not edit above)
<!-- files changed, the shared aim-unit's interface, schema additions, what was/wasn't SITL-tested -->

### Session handoff (2026-08-08) — design frozen, NOT implemented

**Status:** design complete, no code written. Two blockers (below) gate all implementation. Written to
be picked up by a fresh session that re-syncs with the codebase first.

#### Resume checklist — DO THESE FIRST (the tree moved under this design)
1. **Re-read `fmu_node.hpp` APPROACH branch (~L504-580) fresh.** Agent 2 landed a median-depth-to-target
   fix for APPROACH during this design. The STALE/recovery behavior below may already partly exist —
   Step 0's job is to *compose what exists* into the helper, not reinvent it. Diff before coding.
2. **`docs/LOCKS.md` is a HARD REQUIREMENT.** Before touching ANY file: read its `docs/LOCKS.md` entry, set yourself as
   holder + UTC time, save `docs/LOCKS.md` first, edit, then set holder=FREE with a note. Every file, every time.
3. **Confirm both blockers cleared** — nothing builds or tunes until they are.
4. Re-read this spec + `docs/code-guidelines.md`; check ROADMAP for status drift.

#### Blockers (owned by other agents)
1. **Constants runtime loader** — codebase can't distinguish DJI-Tello vs PX4-SITL constants. Every
   Step-5 tunable is meaningless until this exists.
2. **Depth-map accessor** — `PerceptionRuntime` keeps the metric depth map (`m_depthMap`, cv::Mat,
   meters) private; `snapshot()` exposes only per-detection `median_depth_cm`. safe_land needs a depth
   *region*, so the perception owner must add `depthMap()` / `groundFlatness(roi)` first.

#### Guardrails
rtk only. Heredoc edits with `assert s.count(old)==1`. **Never change the `GenericCommand` 64-byte
union layout.** Match `docs/code-guidelines.md`. Files edited (`source/llm_to_action/fmu/`):
`fmu_node.hpp`, `fmu_node_base.hpp`, `llm_base.hpp`.

#### Coordinate systems — every file that crosses a frame
Frames: **FLU** (body F/L/U), **ENU** (world E/N/Up+), **NED** (PX4 wire N/E/Down+), **pixel** (u,v).
**Keep coordinate suffixes on variable names, and keep conversions explicitly named** (state from->to at
the call site — the existing frame_convert.hpp philosophy; do not drop it).

| File | Edited? | Frames touched | Converts (from -> to) | Internal convention |
|------|---------|----------------|-----------------------|---------------------|
| `frame/frame_convert.hpp` | no (used) | FLU, ENU, NED, yaw CW/CCW | the named conversions (FLU<->NED, NED<->ENU, FLU<->ENU, yaw CW<->CCW) | none — it *is* the converter; world target = ENU |
| `perception/detection_query.hpp` | no (used) | pixel, FLU | pixel(u,v)+depth -> body-FLU dir + range | body-FLU out |
| `fmu/llm_base.hpp` | yes | FLU (semantics only) | none — prompt tells the VLM its commands are body-FLU (cm/deg) | FLU (to VLM) |
| `fmu/fmu_node.hpp` | yes | FLU (VLM cmd + perception aim), ENU (odometry, control, backend I/O) | body-FLU -> ENU via `flu_to_enu` at activation + per aim tick | ENU |
| `fmu/fmu_node_base.hpp` | yes | ENU-referenced constants (altitudes, climb/descend vels — Up+); rest frame-neutral scalars (gains 1/s, timeouts, loop rates) | none (constants) | ENU for altitude/velocity constants; N/A for scalars |
| `backend px4_backend.*` | no (boundary) | ENU (from FMU), NED (wire) | ENU -> NED at the wire | NED |

**Follow-ups (not Spec 2 — flag to overseer):**
- Control-loop locals `n/e/d` are mislabeled (`n = pos.x`, which is *East*). Codebase-wide rename.
- **Tello device-coordinate frame is unknown/unverified** — must measure what frame the Tello backend
  reports odometry in (PX4 is NED->ENU; Tello TBD). Blocks correct frame handling on the Tello path.
- **Document this table in the codebase** (a `docs/` frames page or a `frame_convert.hpp` header comment).

#### Step 0 — Shared aim helper (do FIRST; APPROACH + ORBIT use it)
Compose APPROACH's existing detection+recovery logic into one helper:
```cpp
enum class AimStatus : u8 { TRACKING, STALE, LOST };
struct AimSample { AimStatus status; TargetRelative tr; Vec3 holdVelEnu; };  // tr valid iff TRACKING
AimSample resolveLiveAim(char const* label, u64 tnow);
void      resetAim();  // at each command activation
```
- **TRACKING** — fresh detection this frame (`found && age <= kApproachFreshUs = 200ms`); `tr` = live aim.
- **STALE** — had a lock, but this frame's detection is missing or older than 200ms, and last-good aim is
  `<= kApproachLostTimeoutUs = 3000ms` old. Fly the last-known bearing briefly
  (`holdVelEnu` = last bearing x `kApproachCoastSpeedMps`), distrusting it as current truth — just not
  failing on one dropped frame (real YOLO/depth stalls ~1s under load).
- **LOST** — last-good aim older than 3000ms -> caller FAILs.
Keep the single-detection fallback. Rename shared members `m_approachLastAim*` -> `m_aimLast*`. Rewrite
APPROACH to call the helper; behavior identical (incl. Agent 2's median-depth fix).

#### Step 1 — GO: no change
GO-to-target = APPROACH with ~0 standoff, a duplicate servo. VLM emits APPROACH for targets; GO stays
relative-offset. No struct/schema change. APPROACH (via Step 0) already delivers 5.2's drift-free
re-grounding.

#### Step 2 — ORBIT (target-anchored)
`CmdOrbit` + schema exist. Parser fills radius/angle_deg/speed/cw_or_ccw/target.
- Dispatch freezes radius, speed, dir(+1 ccw/-1 cw), targetRad, sweptRad=0, prevBearing unseeded, resetAim.
- Movement: `resolveLiveAim(target)` -> LOST=`"orbit_lost_failed"`, STALE=hold on `holdVelEnu`.
  TRACKING: aimEnu=`flu_to_enu(tr.dirFlu,yaw)`; radialUnit=normalize(aimEnu.xy); tangent=`dir*(-ry,rx)`;
  radial speed=`kOrbitRadialGainHz*(range-radius)` (continuous P, tight tol); tangential=`speed`; combine
  (hold altitude), yaw-center on `errX`, clamp. **Swept = closed-loop:** accumulate
  `|wrap_pi(bearing - prevBearing)|` from measured target bearing (not `speed/radius*dt`) so error can't
  accumulate. `swept >= targetRad -> "orbit_ok"`.

#### Step 3 — SEARCH (zig-zag inside a circle, fixed altitude, no target lock)
`CmdSearch` + schema exist. Parser fills target/expected_time/timeout.
- Pattern: **zig-zag/boustrophedon bounded by a circle of radius R, constant altitude**, with **~30deg
  between each zig and zag leg**. **Before turning from a zig leg to the next zag leg, do a full 360deg
  yaw rotation and scan the surroundings** so nothing is missed by only looking forward. R is a wide,
  tunable default (support wide scans).
- Detection: each tick check `detectionByLabel(snap, target).found`.
- **On success:** `completeCurrent("search_ok")` AND **notify the user of the detection**, posting the
  **full diagnostics — label, confidence, depth, bbox** — so the operator can judge whether the search
  genuinely succeeded (guard against a low-confidence false positive).
- Exhausted (pattern done OR elapsed>timeout) -> `completeCurrent("search_exhausted")`.

#### Step 4 — safe_land (depth-uniformity, no target, three steps)
Reuses the existing descend/flare; does NOT reimplement landing. Blocked on the depth accessor.
- `CommandID`: add `SAFE_LAND`, bump `MAX_ID`. `struct CmdSafeLand{}`, union member,
  `GenericCommand(CmdSafeLand)` ctor (copy CmdStop's) — 64-byte layout unchanged.
- `llm_base.hpp`: add `{"action":"safe_land"}` schema + one system-prompt line.
- Parser `"safe_land"` -> `CmdSafeLand`.
- Movement: (1) **Assess** — sample a depth ROI (lower-center = ground ahead/below), mean+variance.
  (2) **Decide** — flat if `variance < kSafeLandDepthVarTol` AND close if `mean < kSafeLandGroundNearM`
  (not a 5m drop); else `completeCurrent("safe_land_no_spot")`. (3) **Descend** — center over the patch,
  then `m_flightState = LANDING` + `completeCurrent("safe_land_handoff")`; existing flare finishes.

#### Step 5 — Constants (fmu_node_base.hpp) — all `/* SITL-tune, pending constants loader */`
```
Orbit:  kOrbitRadiusToleranceM = 0.05f;   // was 0.30f — 30cm let the circle drift
        kOrbitRadialGainHz     = 0.5f;
        kOrbitTangentialGainHz = 0.2f;     // small
Search: kSearchSweepSpeed   = 40.0f;       // cm/s
        kSearchCircleRadiusM = 10.0f;      // wide; ideally a command param
        kSearchZigStepDeg    = 30.0f;      // ~30 deg between zig and zag legs
Safe:   kSafeLandDepthVarTol = <tune>;  kSafeLandGroundNearM = <tune>;  kSafeLandCenterGainHz = 0.3f;
```

#### Testing — REQUIRED, at least one per command (+ edge cases)
Rig: `scripts/test/<name>/{run.sh,filter.sh,README.md}`, sharing `lib/sim_core.sh`; `approach/` (canned
rig) is the reference; `land-flare/` + `terrain-land/` are the safe-land relatives. Add:
- `scripts/test/orbit/` — assert `orbit_ok`; edge: lost mid-orbit -> `orbit_lost_failed`; STALE frame ->
  holds, doesn't fail; sweep count reaches `angle_deg`.
- `scripts/test/search/` — assert `search_ok` + the diagnostic notification fires; edge: object never
  appears -> `search_exhausted`; timeout path; the 360deg scan actually runs between legs.
- `scripts/test/safe-land/` — assert `safe_land_handoff` over flat ground; edge: non-flat ->
  `safe_land_no_spot`; too-high (mean depth large) -> no descend.
These `scripts/test/*` dirs are new and Spec-2-owned -> no `docs/LOCKS.md` entry needed, but confirm before creating.

#### Open questions for next session
- Is adding the `depthMap()` accessor to `PerceptionRuntime` Spec 2's job, or the perception owner's?
- Search radius R: constant, or a new schema field on `search`?
- Where should the coordinate table live in the codebase?
