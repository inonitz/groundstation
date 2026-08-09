# Spec 2 — Movement command laws

**Status:** ORBIT + SEARCH DONE -- both SITL PASS 2026-08-08 (see the Consolidated status board below).
**ROADMAP:** 1.1.6 (ORBIT) [x], 1.1.7 (SEARCH) [x]. GO/safe-land deferred.
**Owns (edits):** `source/llm_to_action/fmu/fmu_node.hpp` (parser, dispatch switch, movement handler),
`.../fmu/fmu_node_base.hpp` (constants), `.../fmu/llm_base.hpp` (VLM action schemas).
Heavy overlap of the movement handler / dispatch switch / parser with Spec 1 & 4 — overseeing session
merges. Keep each command's code in its own clearly-labelled block.

> **Repo conventions (start-cold):** use `rtk read/grep/ls` (native Read/Grep/Glob are forbidden by
> `CLAUDE.md`); edit via python heredocs with `assert s.count(old)==1`. **Never touch the
> `GenericCommand` byte layout.** Follow the existing APPROACH servo (5.1) and GO cross-track patterns
> exactly. No full builds; human does build + SITL.

## Consolidated status board (2026-08-08) -- read first

The chronological revision notes are at the bottom. This is the current picture in one place.

### Scope (settled)
ORBIT (1.1.6) + SEARCH (1.1.7) only. Everything below is deferred, not abandoned:
- **safe_land** -- needs real-flight testing, out of POC scope.
- **APPROACH refactor onto a shared aim helper** -- left untouched; the drafted `AimStatus`/`resolveLiveAim`
  helper was deleted as dead code. Gets a human review; if the Tello misbehaves, a combined debug+feature merge.
- **Runtime constants loader** -- deferred to ROADMAP 9.14; `constexpr` fallbacks for now; debt registered.

### ORBIT -- current architecture (alive)
The odometry circle, after two dead ends and one reverted addition:
- ~~v1 radius-from-per-frame-depth~~ dead (depth jitter wrecked the geometry).
- ~~v2 vision-drives-yaw + size + gyro~~ dead (the turn did two jobs and oscillated).
- ~~v3b slow vision "drift correction" of the center~~ **reverted** -- it fed vision back into the path and
  ran the center off "into narnia" in SITL, where there is no real drift to cancel. The lesson holds: keep
  vision out of the flight geometry.
- **v3 pure odometry circle (current):** latch one median-filtered center at start, then it stays FIXED;
  fly the circle from odometry only. Vision drives ONLY the camera aim -- aim at the locked center from
  odometry (no bbox chase, which killed the jitter), with a small `kOrbitAimTrimGain` nudge onto the real
  car. Odometry drift over one short orbit is the accepted trade.

### SEARCH -- current architecture (alive)
- ~~v1 30-degree turns~~ dead (made spokes, not a lawnmower).
- ~~v2 chords across a circle + 360 scans + 150-degree turns~~ dead (looked precise at first, then stopped
  following the pattern mid-run).
- **v3 parallel-track lawnmower (current):** straight lane, sideways step by the lane spacing, next lane
  back the other way, repeat -- parallel lanes over a rectangle. Direction is caller/VLM-set:
  `start_heading_deg` = first lane heading, `direction` = which side the lanes march. The
  `kSearchMinConfidence` floor rejects phantom hits (kept from v2).

### Open knobs (design settled, flight-unproven)
ORBIT: direction sign (`m_orbitDir`), startup-center accuracy, `kOrbitAimTrimGain`, `kOrbitRadialGainHz`.
SEARCH: lane length / spacing / max lanes (`kSearchLaneLengthM`, `kSearchLaneSpacingM`, `kSearchMaxLanes`), the `kSearchMinConfidence` value (0.50).

### Verified in SITL (2026-08-08)
Both flew clean. ORBIT: smooth full circle, camera steady on the car. SEARCH: lane -> cross -> lane
back the other way (heading flips 180 each lane), exhausts on timeout for the absent target. What was
the gate, for the record:
- `orbit/`: camera holds the car steady (no hard yaw)? one clean full circle? direction correct?
- `search/`: traces the lawnmower lanes (lane -> cross -> lane back the other way) without false-stopping on a ghost? swap target to `car` -> found-and-stop still works?

### Test furthermore -- beyond SITL
- ORBIT accepts odometry drift over one short orbit (the in-loop vision correction was reverted). On the
  real Tello, if drift proves too large over the orbit, the fix is a PROPERLY band-limited correction, not
  the naive per-tick one -- or simply a shorter/faster orbit. Do not re-add vision to the path lightly.

## Revision (2026-08-08, 6th pass -- BOTH SITL PASS)

Third SITL run. Both commands flew clean and are DONE for the POC.
- ORBIT: smooth full odometry circle, camera held steady on the car. No wobble, no runaway.
- SEARCH: the parallel-track lawnmower traced correctly -- lane to the end, sideways cross step, next
  lane back the other way (heading flips ~180 each lane: -0.11 -> 3.03 -> -0.11 ...), crosses marching
  the same side, exhausts on the 90 s timeout for the absent target. Log tags lane/cross as intended.

Accepted, not-blocking: the lawnmower length and lane count are fixed constants. A future improvement is
to let the caller/VLM parameterize lane length and count (like ORBIT's angle/radius). Noted, deferred.

ROADMAP 1.1.6 and 1.1.7 are now [x] with SITL PASS; the test-matrix rows read PASS. Spec-2 scope complete.
- Real Tello bring-up -- the actual bottleneck and biggest unknown (VIO drift, no stabilization, real depth noise).
- APPROACH on the Tello -- the deferred review, plus wiring it to the same aim idea.
- Edge paths: orbit-never-locked -> fail; search timeout/exhausted.

### Priority (POC deadline)
1. Build + SITL-validate ORBIT and SEARCH (the gate above).
2. Real Tello bring-up -- that is where the untested risk lives.
3. Leave safe_land and the APPROACH refactor parked unless the Tello forces the APPROACH merge.

## Overseer update (2026-08-08) -- read before the Session handoff below
Specs 3 and 4 shipped and moved to `docs/closed/` (spec-3 failsafe + backpressure, spec-4 rotate +
land). Read their reports before you build on them -- the code under you changed. APPROACH now brakes
on a dead-reckoned travel budget with a 3.0 m standoff, not a live-depth servo at 2.0 m; your shared
aim helper (Step 0) composes over that shipped APPROACH, so re-diff the branch first. ROTATE is
accumulated-angle and LAND has a flare taper -- safe_land (Step 4) hands off to that shipped flare, do
not reimplement it. Spec 4 is no longer an active co-editor; its shared canned-plan rig is in the tree
-- reuse it, do not coordinate live.

Your new orbit/search/safe-land gains are runtime-config debt and are NOT yet listed in
`docs/scheduled/2026-08-08-runtime-drone-config-constants.md` (ROADMAP 9.14) -- add them there when
you add them to `fmu_node_base.hpp`. One binary must load per-drone profiles; SITL numbers are only
the fallback.

Your new `scripts/test/{orbit,search,safe-land}/` dirs must also land as rows in the ROADMAP "SITL
test matrix" (now 15/15 green) once they pass. Creating the dir is not enough -- the matrix is what
the overseer checks. ROADMAP 9.12-9.14 are taken (AGL, off-heading, runtime-constants); pick fresh
numbers for new debt.

Commit messages: `docs/code-guidelines.md` "Review & commits" now carries the hard rule --
intent-first, `|`-separated, ASCII only. Follow it.

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

---

### Implementation (2026-08-08) -- SHIPPED (ORBIT + SEARCH), build+SITL pending

**Scope actually shipped.** ORBIT (1.1.6) and SEARCH (1.1.7) only. Both were already advertised to
the VLM in `llm_base.hpp` but silently dropped by the parser -- a real correctness hole this closes.
**Deferred by decision:** safe_land (depends on ground depth the Tello can't be trusted on -- crash
risk, no HW validation) and the APPROACH-onto-helper refactor (touches the one verified servo; pure
risk, no POC payoff). Both stay in the frozen design above.

**Files changed**
- `fmu/fmu_node.hpp`: `AimStatus`/`AimSample` types + `resolveLiveAim()`/`resetAim()` helper; ORBIT +
  SEARCH parser branches, dispatch cases, movement arms; new aim/orbit/search members; hoisted
  controlLoop locals; two canned test plans (`injectCannedOrbitPlan`/`injectCannedSearchPlan`) +
  `start()` flags. **APPROACH branch untouched.**
- `fmu/fmu_node_base.hpp`: ORBIT + SEARCH tuning constants (`constexpr` SITL fallbacks).
- `fmu/fmu_node.cpp`: `--canned-orbit` / `--canned-search` flags.
- `perception_runtime.hpp`, `llm_base.hpp`: **not touched** -- ORBIT/SEARCH need no new perception
  accessor and their schemas already existed.
- `scripts/test/orbit/`, `scripts/test/search/`: new rigs (real-perception, target `car`).
- Debt registered in `docs/scheduled/2026-08-08-runtime-drone-config-constants.md`; ROADMAP 1.1.6/1.1.7
  marked impl + two SITL-matrix rows added.

**The shared aim helper (interface as built)**
```cpp
enum class AimStatus : u8 { TRACKING, STALE, LOST };
struct AimSample { AimStatus status; TargetRelative tr; Vec3 holdVelFlu; };  // tr valid iff TRACKING
AimSample resolveLiveAim(char const* label, u64 tnow);  // reads m_perception->snapshot()
void      resetAim();                                   // at each maneuver activation
```
NEW code (not a refactor). It reuses the APPROACH substrate -- `detectionByLabel`, single-detection
fallback, `kApproachFreshUs` freshness, `kApproachLostTimeoutUs` coast window -- and owns only detect +
freshness + last-aim recovery. ORBIT uses it; SEARCH reads the snapshot directly (it needs presence +
confidence/bbox, not an aim vector). A code note on `AimSample` flags that the shipped APPROACH still
inlines the same logic and should be migrated onto this helper after a human re-verifies APPROACH in
SITL and on the Tello -- with any APPROACH-on-Tello fixes folded into that same migration.

**Design notes**
- ORBIT swept angle is closed-loop from the measured target bearing (`|wrap_pi(dBearing)|`), so it
  cannot drift open-loop. Radial P term holds the radius; tangential velocity IS the commanded orbit
  speed (no separate tangential gain). LOST -> `orbit_lost_failed`; STALE -> hold; `orbit_ok` on sweep.
- SEARCH is a leg/scan sub-FSM at fixed altitude, bounded by a circle about the start pose, legs
  rotated `kSearchZigStepDeg` apart, a full 360 yaw scan before each leg advance. A per-leg timeout
  advances the pattern even when odometry drift stops the circle bound from tripping (Tello-safe). On
  a hit it logs one prominent `[FMU_NODE] SEARCH DETECTED ... conf=.. depth_cm=.. bbox=(..)` line --
  that log IS the operator notification -- then `search_ok`. Leg cap or timeout -> `search_exhausted`.

**Change impact (per the new code-guidelines rule)**
- One existing behavior touched: none. APPROACH, GO, ROTATE, LAND, the servo, and the byte layout are
  all unchanged. ORBIT/SEARCH previously parsed to nothing / auto-completed as `noop_ok`; now they run.
- **Tests to re-run unchanged (regression gate, must stay green):** the full 15-row SITL matrix,
  since the parser / dispatch switch / movement chain / `start()` signature are shared -- logically
  additive, but shared surface. Priority: `approach`, `approach-real`, `rotate-land`, `cross`.
- **Tests rewritten:** none. A required edit to an existing test would signal an unintended change.
- **New tests:** `orbit`, `search` (happy path auto-milestoned; the lost/exhausted edges are noted in
  each README as manual SITL steps -- hard to force deterministically with real perception).

**What was NOT verified**
No build, no SITL run this session (human owns build + flight). Nothing here has been compiled. The two
new rigs are wired to their canned flags and runnable after a rebuild, but are unrun -- ROADMAP matrix
rows say `NEW (... ; unrun)`.

**Open questions carried forward**
- ORBIT/SEARCH edge cases (lost mid-orbit, search exhausted) want a synthetic-detection rig to script
  deterministically; today they lean on real perception. Generalizing `updateCannedApproachRig` to
  project a world-fixed target during ORBIT/SEARCH would let `filter.sh` auto-assert those.
- SEARCH radius/leg-step are `constexpr`; promoting radius to a `search` schema field would let the VLM
  size the sweep.


---

### Revision (2026-08-08 pm) -- ORBIT + SEARCH reworked after first SITL run

First SITL run of both maneuvers failed, and the fixes changed the approach enough to supersede parts
of the report above. What changed:

**ORBIT — rewritten.** The first version leaned on the depth number (which flips 3-7 m frame to frame
in SITL) and accumulated swept angle from the measured target bearing -- so detection noise inflated
the angle and it "completed" a 90 deg arc while barely moving, drifting inward on every stale frame.
The rewrite uses only reliable cues: the target's horizontal position in the image to turn and keep it
centered, its apparent size in frame to hold distance, and the drone's OWN heading change (gyro) to
count progress -- one full loop is 360 deg of turning. No depth number, no odometry position (both
drift, especially on Tello). Default is now a full circle. Constants: dropped `kOrbitRadiusToleranceM`
/ `kOrbitRadialGainHz`; added `kOrbitYawGain`, `kOrbitSizeGain`, `kOrbitMaxDurationMs`. Open SITL item:
verify the cw/ccw strafe sign (`m_orbitDir`).

**SEARCH — turn angle fixed.** The pattern turned +30 deg per leg, so legs fanned out from the start
like spokes and never crossed back into the circle. Fixed: each leg is a straight chord across the
circle, a 360 look-around runs at the far edge, then the heading turns ~150 deg (180 - 30) so the next
chord crosses back rotated 30 deg -- the chords fan around to cover the disc. Added a leg-boundary gate
(a leg must pass near the center before the edge can end it) so a chord that starts at the edge is not
cut short. Circle radius tightened 10 -> 5 m and sweep speed 0.40 -> 0.50 m/s so a few chords fit the
demo window.

**Aim helper removed.** The shared `resolveLiveAim` / `AimSample` from the first cut is gone -- the
reworked ORBIT and SEARCH read the frame directly (they need apparent size / presence, not the helper's
coast-toward-target behavior, which was wrong for a circle). APPROACH stays untouched, as before.

Still no build or SITL pass on the reworked code -- handed back for build + flight.

---

### Revision (2026-08-08, 2nd pass) -- ORBIT rebuilt on odometry; SEARCH direction is caller-set

Second SITL run after the first rework. Both failed again in a way that pointed to design, not tuning.

**ORBIT -- rebuilt (again), now an odometry circle.** The vision-only version oscillated: the turn was
driven by the target's image position AND had to carry the drone around, so the two fought and the
drone did half-circles both ways while drifting closer -- and the swept-angle count, being a sum of
absolute turning, still hit 360 from the wobble. Chosen fix (user picked it, aware of the drift trade):
at the start, median a few depth reads into ONE fixed car position; then fly a fixed circle around that
point using odometry only. The geometry inputs (fixed center + smooth odometry) carry no depth jitter,
so there is no feedback loop to oscillate. The camera turns separately to keep the real car in view.
Swept angle now comes from the drone's odometry angle around the center (smooth), not the noisy bearing.
Trade-offs, both accepted: the circle center is only as good as the medianed startup depth, and it
leans on odometry over the ~20-30 s maneuver (short enough that drift stays small). Constants: dropped
`kOrbitSizeGain` / the gyro-count constants; `kOrbitRadialGainHz` holds the radius, `kOrbitYawGain`
aims the camera.

**SEARCH -- direction is now caller-set.** The pattern shape was right, but which way it swept first was
arbitrary (always the spawn heading). The `search` command now takes `start_heading_deg` (relative to
current facing) and `direction` (cw|ccw); the VLM sets them from where it expects the target -- that is
how it decides which half of the area to sweep first. `CmdSearch` gained those two fields (union layout
unchanged), the schema and system prompt advertise them, and the leg turn + the 360 scan follow the
chosen direction. The canned test now targets an absent object ("person") and spawns centered, so the
full circle gets traced to timeout for inspection instead of stopping early on a detection.

Still no build or SITL pass on this code -- handed back for build + flight.

## Revision (2026-08-08, 3rd pass -- first SITL fixes)

First flight surfaced one real bug in each command; both are now fixed.

**ORBIT -- camera aim moved onto odometry.** The circle path was already flown from odometry, but the
camera aim still chased the bbox (`yawRate = -kOrbitYawGain*errX`). While the drone translated along the
circle, the noisy bbox forced hard, jittery yaw corrections that kept losing the car. The aim now points
at the locked center computed from odometry (a slowly-drifting look-angle, so no hard chase), with a
small `kOrbitAimTrimGain` vision nudge on top to sit on the real car if the center is slightly off. This
is the same odometry-first idea the path already used, applied to the aim.

**SEARCH -- weak detections no longer end the search.** A phantom `person conf=0.29` completed the search
on leg 0 and the drone landed after one leg. There was no confidence floor: any label match finished it.
Added `kSearchMinConfidence` (0.50); a sub-floor hit logs `SEARCH ignoring weak ...` and the pattern
continues. Real detections clear the floor and still stop the search.

New constants `kOrbitAimTrimGain` and `kSearchMinConfidence` are registered in the runtime-config debt
doc. Still SITL-unverified after these edits -- handed back for another build + flight.

## Revision (2026-08-08, 4th pass -- ORBIT drift correction)

Reviewer raised the core weakness of the odometry circle: the latched center lives in the odometry
frame, so as that frame drifts against the world (wind the drone senses is already handled by the radius
loop; drift is what odometry cannot see), the circle slowly slides off the real car. Vision is the only
drift-free reference to the car.

Fix: a complementary filter on the center. The fast path is still the smooth odometry circle. In parallel,
when a detection above `kOrbitMinConfidence` is in frame, the latched center is slewed toward the
vision-measured car position (reliable bearing + median-filtered range) with a small `kOrbitDriftCorrectGain`.
The gain is low so the jittery depth is heavily low-passed and cannot re-introduce the wobble we removed;
it only cancels the slow drift. Swept-angle progress now measures the drone's angle change around the
current center for both samples, so the slow center slew adds no false sweep (`m_orbitPrevAngle` became
`m_orbitPrevPos`).

Note: SITL (Gazebo) odometry is near-ground-truth, so the correction may show little visible effect in
sim -- it mainly de-risks the real Tello, where VIO genuinely drifts. To exercise it in SITL you would need
to inject a disturbance. New constants `kOrbitDriftCorrectGain`, `kOrbitMinConfidence` are in the debt doc.
Still SITL-unverified after these edits -- handed back for build + flight.

## Revision (2026-08-08, 5th pass -- ORBIT drift-correction reverted; SEARCH -> parallel track)

Second SITL run. ORBIT: the drift correction from the 4th pass dragged the center away and the drone flew
off into a huge, wrong orbit ("into narnia"). Root cause: it reintroduced the exact thing we removed across
v1/v2 -- vision feeding the flight geometry. And in SITL there is no real drift to correct, so it could only
add error. Reverted to the pure odometry circle: fixed center, path from odometry, vision only for the
camera aim. Constants `kOrbitDriftCorrectGain` and `kOrbitMinConfidence` removed.

SEARCH: the chord/circle pattern looked precise at first but stopped following the rule mid-run. Per the
reviewer, switched to a parallel-track (lawnmower) pattern: straight lane, sideways step of one lane
spacing, next lane back the other way, capped at `kSearchMaxLanes`. Simpler and more robust; a per-phase
timeout advances it under drift. The command fields (`start_heading_deg`, `direction`) carry over with
lawnmower semantics (first lane heading; which side the lanes march). New constants `kSearchLaneLengthM`,
`kSearchLaneSpacingM`, `kSearchMaxLanes`; removed `kSearchCircleRadiusM`, `kSearchZigStepDeg`. Log tags are
now `SEARCH lane`/`SEARCH cross` (filter greps updated). VLM schema reworded. Still SITL-unverified.