# Docs/Code Discrepancy Remediation

**Date:** 2026-08-06
**Status:** active
**Source:** three parallel read-only audit agents cross-checking `docs/ARCHITECTURE.md`,
`docs/ROADMAP.md`, `docs/specs/*`, and `docs/project_overview.md` against the actual current
code. 30 confirmed/plausible discrepancies found. Nothing fixed yet.

Default resolution for every item below is "make the doc match reality" (docs were wrong, code
is truth) unless explicitly flagged `FLAG FOR HUMAN` — those need a decision this doc can't make
from reading code alone.

Groups are ordered **smallest time-estimate first** — work bottom-up through this list.

---

## G1 — docs/project_overview.md sync (S, ~15 min)

- APPROACH listed as "specced" only -> it's built + flight-tested (ROADMAP 5.1.5).
- Visual servoing framed as future ("the plan is...") -> shipped, SITL-verified.
- No mention of Tello real-hardware flight (2026-08-06, telemetry/odometry/camera all live).

## G2 — specs/2026-08-05-visual-servoing-approach-design.md §10 tunables (S, ~15 min)

- `kApproachStandoffM` 0.5 -> 2.0, `kApproachSpeedDefault` 30 -> 80 cm/s,
  `kApproachFwdGainHz` 0.5 -> 0.35, `kApproachLostTimeoutMs` 500 -> 3000.
- Two new tunables the spec doesn't mention at all: `kApproachFreshMs`, `kApproachCoastSpeedMps`
  — implement a two-threshold fresh-vs-lost model the spec's single-threshold pseudocode
  never had.

## G3 — specs/2026-08-04-drone-backend-abstraction-design.md (S-M, ~30 min)

- Threading model reversed: spec says single-threaded/no atomics; code uses
  `MultiThreadedExecutor` + atomics throughout.
- "No CRTP" contradicted by `GenericBackend<Derived>` now existing.
- "No TelloBackend ships here" — full `TelloBackend` exists.
- Verb signatures don't match shipped API (`takeoff(altEnu)` vs actual no-arg `takeoff()`;
  spec's `BackendStatus`-returning verbs vs actual `void`; spec's `engaged()` doesn't exist).
- Minor: M2 folder name `drone_backend/` vs actual `generic_backend/`; spec's
  `enu_yaw_from_ned_quat` vs actual scalar-only `enu_yaw_from_ned`.

## G4 — docs/ARCHITECTURE.md text sync, one pass (M, ~30-45 min)

16 items in one file — fix in a single careful read-through:

- §4 table: ROTATE/ORBIT/SEARCH/CURVE shown as working; only takeoff/land/stop/go/approach are
  parsed, everything else silently dropped or auto-completes as noop.
- §4 table: GO "two impls (go_vel/go_pos)" — neither name exists, one law only.
- §4 table: APPROACH missing entirely despite being fully shipped.
- §2/§7/§12: "~100Hz" offboard publish — actual 30Hz (PX4) / 20Hz (Tello).
- §2 vs §9 (same doc): seg/depth rates swapped (depth is the slow ~12.5Hz one, not seg).
- §5/§12: "wake via `condition_variable::notify_one()`" — no condition_variable in
  fmu_node.hpp; wake is 20Hz-poll-based.
- §6: "active pending queue" in prompt — not in `buildDynamicPrompt()`.
- §6: "marked image" sent to VLM — actual frame is unannotated.
- §9: "APPROACH next, gated on perception" — stale, it shipped (§15 already says so).
- §2/§5: `m_emergencyStop` atomic referenced — doesn't exist anywhere in the tree.
- §5.1: `TaskState::STOPPED` referenced — never assigned in code.
- §0/§15: FORK-A "`-c 4096` DONE" — live script uses `-c 65536` (16x). **NEEDS HUMAN CONFIRM**
  which value is the intended current one before writing a number into the doc.
- §16 open item "adapt BUILD_YOLO behind perception contract" — already done, just uncheck.
- §16 open item "rephrase interruption text -> Appendix A" — already done, just uncheck.
- §14: still lists FORK-C as an open choice — resolved everywhere else in the same doc.
- §13 Known Risks: describes the deprecated `simenv.sh`, not the live `simenv_llm.sh`.

## G5 — specs/2026-08-05-perception-library-design.md (M, ~30 min)

- Model paths stale: spec says `.../vision/yolo26n-seg.onnx`; actual is nested
  `.../vision/vision/yolo26n-seg-384.onnx`.
- `fuse(frame)` signature wrong; actual `vision::fuse(seg, depth, frame, conf, iou)` — and the
  FMU doesn't even call it (`PerceptionRuntime` reimplements fusion by design, two-rate).
- **FLAG FOR HUMAN:** same-day doc conflict — `ROADMAP.md` says "seg MEETS target (30.5ms)",
  `docs/scheduled/2026-08-06-build-yolo-vision-generic-backend-refactor.md` says "seg misses
  2.1x". Can't resolve from reading code; needs either a re-benchmark or the user to say which
  number is current.

## G6 — build.ps1 real code fix (L, scope TBD — FLAG FOR HUMAN)

- Unreachable branches (`buildpx4`/`buildtello` not in the script's own `ValidateSet`) and
  references to undefined vars (`$BUILD_FMU_DEFS`, `$FMU_BUILD_TARGET`).
- This is an actual bug, not a stale-doc issue. Two possible scopes, very different time cost:
  (a) delete the dead unreachable branches (S, ~15 min cleanup), or (b) actually wire up
  per-target build on Windows to match what those branches imply was intended (L, real feature
  work, ties into ROADMAP 9.6/9.10). Needs a human call on which before starting.

---

## Not included (already accurate, confirmed by audit — no action)

GO cross-track law description (§15), 2.4 CMake split, 9.2 zero `../` includes, 2.1 CRTP,
9.5 dead build option, 1.4 backpressure TODO, 2.3.2 Tello odometry stub, 9.10 build.sh
hardcoded to "all", §11 battery stub — ROADMAP/ARCHITECTURE already describe these correctly
as incomplete/known gaps.
