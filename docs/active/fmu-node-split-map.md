# fmu_node.hpp split map (proposal — approve the SHAPE before any code moves)

`fmu_node.hpp` is **3166 LOC, one class (`FmuNode`), all methods inline**. That's ~8x the
~400 LOC review ceiling and ~1.5x the ~2000 LOC "can't-reason-about-it-as-a-unit" line from
`code-guidelines.md`. Three units alone are past the ceiling:

- **`controlLoop`** — lines **715-1584 (~870 LOC)**. The single worst offender; the per-verb
  servos (FOLLOW/APPROACH/ORBIT/SEARCH/LAND/HOVER) all live inside it.
- **`injectCanned*Plan` x ~22** — **2697-~3050 (~450 LOC)**. Test/demo scaffolding.
- **`activateTask`** — **1987-2257 (~270 LOC)**.

## Proposed grouping (behavior-identical, by responsibility)

| Unit (new `.ipp` included into the class) | Methods | Lines | ~LOC |
|---|---|---|---|
| **core** (stays in `fmu_node.hpp`) | members, ctor, `start`, subscriptions | 1-400 + tail | ~350 |
| **input** | `imgCallback`, `asrCallback`, `handleAsrCommand`, `overrideCallback`, `keyCallback`, `resetInterruptState`, `zeroManualVel` | 473-561, 1861-1949 | ~180 |
| **control** | `controlLoop` + extracted per-verb servos | 715-1584 | ~870 → split internally |
| **tasks** | `activateTask`, `completeCurrent`, `raiseInterrupt`, range medians | 1950-2344 | ~390 |
| **planning** | `maybePlan`, `publishVlmContext`, `buildDynamicPrompt`, `callLlamaServer`, `translateToBaseCommands` | 1584-1633, 2344-2697 | ~400 |
| **perception-geom** | `approachMotionNominal`, `bboxRangeDir`, `bboxToEnuAnchor`, `updateCannedApproachRig` | 616-715 | ~99 |
| **safety** | `emergencyLandNow`, `emergencyHoldNow`, `batteryFailsafeTick`, `returnToOrigin` | 561-616, 1802-1861 | ~110 |
| **observability** | `nowUs`, `publishAnnotatedFrame`/`DepthColormap`, `hudTask`/`hudDet`/`publishHud`, `makeVlmLogPath`, `appendVlmLog` | 1633-1802 | ~170 |
| **canned-plans** | all `injectCanned*Plan` | 2697-~3050 | ~450 → **move out AND prune** |

Mechanism: keep the `FmuNode` declaration in `fmu_node.hpp`; move method **definitions** out-of-line
into the `.ipp` files above, `#include`d at the end. Zero semantic change.

## Two phases

- **Phase 1 (now): mechanical split — behavior-IDENTICAL.** File layout only, no logic changes.
  Contract: **existing tests pass UNCHANGED.** Compile after each unit moves.
- **Phase 2 (later, optional): composition.** `controlLoop` (per-verb servos), the planning path,
  and observability are the natural candidates to become **composed helper objects** the node
  holds (composition is our default) — but that's a structural change, done deliberately after
  Phase 1 lands and only where it improves the design.

## Cleanup intersection (do alongside)

- **canned-plans is mostly dead code.** ~22 `injectCanned*Plan` are old demo/test scaffolding.
  Before moving, grep each for a live caller; **prune the unused ones** (biggest single line
  reduction in the file). Removed canned plans -> remove the tests that reference them.
- The abandoned ORBIT/APPROACH-bbox demo geometry (`updateCannedApproachRig`, bbox anchor path)
  may be dead if the modular arch replaces it — **gate on the measurement result**, don't strip yet.

## Change-impact

| Change | Behavior touched | Breaks it? | Test impact |
|---|---|---|---|
| Phase 1 file split | none | no (identical) | regression tests re-run **unchanged** |
| Prune dead canned plans | removes unused demo paths | only if a "dead" one is live — **grep first** | delete their tests |
| controlLoop internal servo extraction | none (same logic, new functions) | no | unchanged |

## LOCKS / coordination

`controlLoop` contains the **SEARCH/APPROACH branches the Manager rewrote (LOCKED)**. Coordinate
before splitting those; do the safe units first.

## Suggested execution order (safest -> riskiest)

1. **observability** + **safety** + **perception-geom** (self-contained, low risk).
2. **canned-plans** (move out + prune — big, low logic risk once callers are grep-checked).
3. **input** + **tasks** + **planning**.
4. **control** last (LOCKED branches; also the Phase-2 composition candidate).
