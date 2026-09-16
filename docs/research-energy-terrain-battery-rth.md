# Scheduled — Smart Return-to-Home: energy modeling + terrain-aware landing

**Status:** scheduled (deferred subsystem). **Source:** distilled from
`gemini_battery_monitor_system_log.pdf` (core ideas only, not copied verbatim).
**Relation to shipped POC:** Spec 3 ships the KISS floor — `≤20% → return-to-origin`,
`≤10% → land in place`. Everything below is the *smart* version that replaces those stubs once the
supporting sensing exists.

## Why deferred
The full policy needs inputs the POC doesn't have yet: an integrated distance-travelled odometry
signal, battery **voltage/capacity** (energy, not just percent), and **downward depth perception**
for terrain. Smart free-space navigation would also want a map ("Being-B" / SLAM). Until those land,
percent-thresholded RTH + land-in-place is the honest behavior.

## Core design (state machine with persistent intent)
Deterministic state machine keyed on battery, with **persistent intent flags**: once a full return
is validated at 20%, lower thresholds must **not** override the return unless real-time consumption
strays past the predicted safety bounds. This prevents threshold thrashing near the boundaries.

### Energy estimation — take the worst case
Return is viable iff `E_remaining ≥ E_req`, where `E_req = max(E_A, E_B)`:
- **Method A — max-drain projection (worst-case headwind).** Track peak power draw/second over the
  flight; `E_A = P_max · T_return`, with `T_return = dist_to_origin / v_cruise`, plus a safety margin.
- **Method B — historical efficiency.** Average energy burned per metre flown so far;
  `E_B = dist_to_origin · e_per_metre + descent_reserve`.
- `E_remaining ≈ C_remaining(mAh) · V_pack`.

### Thresholds
- **20% (primary decision):** run the models. If `RTH_VALIDATED` → command return to origin. Else set
  `LAND_NEAR_ORIGIN` → vector toward origin and pick the closest viable landing site in reach.
- **10–15% (monitor / fallback window):** if `RTH_VALIDATED` and consumption stays on-budget, hold
  the return path; if not validated or flight params degrade, divert to the nearest safe landing site.
- **<10% (critical):** if `RTH_VALIDATED`, trust the 20% pre-calc and continue to origin; else execute
  immediate `EMERGENCY_LAND` using downward perception.

### Terrain-aware landing (for the <10% emergency + LAND_NEAR_ORIGIN)
Pick a **flat, non-bumpy** site before touchdown:
- **Surface pitch/roll:** compute the ground-plane normal from optical-flow / depth data; reject sites
  whose inclination exceeds a small threshold.
- **Roughness index:** point-cloud variance across the candidate patch to filter brush, rocks, and
  uneven ground.

## Dependencies to unblock this
- Odometry distance integral (already have per-tick ENU pose).
- Battery voltage + pack capacity fields from the backend (percent alone is insufficient for energy).
- Downward depth perception (SLAM-adjacent) for terrain flatness/roughness.
- A world map for smart free-space routing home ("Being-B").
