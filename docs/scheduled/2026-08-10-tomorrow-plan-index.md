# Tomorrow — spec manifest, branches, and the 14-hour read

**Created:** 2026-08-10. Companion to `2026-08-09-slam-tello-bringup.md` (the narrative) — this is the
spec-file manifest, the branch split, and the honest scope read for multi-agent day.

## Two branches
- **`feature-llm-driver` (prep for the SITL showcase).** Lock this branch down as the guaranteed
  deliverable. Specs **A1–A4**.
- **`feature-slam-tello` (new, cut from the showcase branch after its commit).** The risky, hardware
  path. Specs **B1–B5**.

## Spec files
| Spec | Branch | Depends | Touches FMU hotspot? |
|------|--------|---------|----------------------|
| A1 sandbox + headless runner | showcase | — (do first) | no |
| A2 observability | showcase | A1 (soft) | small — serialize w/ A3 |
| A3 voice + termination | showcase | spec-1 | YES — take the lock |
| A4 showcase demos S1/S2/S3 | showcase | A1, A3 | no |
| B1 stella SITL bring-up | slam-tello | — (spike now) | no |
| B2 camera calibration | slam-tello | — (operator) | no |
| B3 slam pose → FMU | slam-tello | B1 | YES — serialize |
| B4 Tello bring-up + T1/T2 | slam-tello | feature commit | no |
| B5 stick cal + wind | slam-tello | B4 | no |

## Parallelization
Only A3 and B3 touch `fmu_node.hpp` — everything else is new files or a separate node, so agents run
in parallel without stepping on the hotspot. Follow `LOCKS.md`: take the lock right before the FMU
edit, release right after. A3 and B3 are on different branches, so they never collide.

## Is all of it realistic in ~14 hours? Honestly: no — and that is fine.
- **What fits and should be *committed*:** the SITL showcase (A1–A4) and a first position-free Tello
  flight (B4). A1–A4 are plumbing on a proven base; agents parallelize them; your SITL testing is the
  only serial cost. B4 is proven hardware from 2026-08-06 plus tuning.
- **What is a *spike*, not a commitment:** B1 (does stella track?) is unbounded — it could take an
  hour or eat the day. Timebox it. If it tracks, great; B3 becomes reachable. If not, fall back to B4.
- **What will *not* land reliably tomorrow:** B3 + B5 — SLAM-wired Tello autonomy. Hardware iteration
  (flights, batteries, wind, gremlins) does not compress with more agents.

**Plan the day so the showcase is safe by hour ~8, then spend the rest on the SLAM spike with a clean
fallback.** Do not gate the showcase on SLAM.

## Which tests get the human out of the loop
- **Fully automatable (headless SITL, once A1's capture-to-file lands):** every canned scenario —
  the existing 20 plus A3 (`--canned-voice` / `--canned-complete`), A4 (S1/S2 state-traces), B1
  (tracking-health vs EKF2 ground truth), B3 (return-to-start vs ground truth), A2 (topic-rate + log
  checks). Ground truth in sim is what makes SLAM assertable.
- **Desk-automatable without flying:** B4/B5 parser, odometry, latency, and stick→m/s mapping via a
  recorded-flight replay fixture (ROADMAP 2.3.6).
- **Human stays in the loop:** real Tello flights (T1/T2, wind hold), and VLM *plan quality* on the
  free-flight `vlm`/demo runs — the state-trace is asserted, the model's judgment is not.
