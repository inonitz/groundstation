# A3 — Voice interrupt + mission termination

**Status:** scheduled / not started. **Created:** 2026-08-10. **Branch:** feature-llm-driver (SITL showcase).
**Depends:** spec-1 interrupt path (landed in the feature commit). **ROADMAP:** 3.7, 5.1, 6 (termination).
**Lock:** touches `fmu_node.hpp` (interrupt hook + prompt) and `llm_base.hpp` — the contended hotspot; hold short, coordinate with A2.

## Objective
Let a human end or redirect a mission by voice, and let the model judge its own completion. Route the
ASR transcript into an interrupt with a `[USER]` prompt block, and make each reassess emit a
structured completion verdict first, standing the drone down when the objective is met.

## Scope
- **In:** `ASRStandaloneNode` transcript topic → `raiseInterrupt("user_command")` + stash text;
  `buildDynamicPrompt` appends a `[USER]` block; reassess prompt emits
  `{"objective_complete":bool,"reason":"..."}` first, then `land`/`stop` if complete else plan.
- **Out:** wake-word vs push-to-talk UX (pick one, note it); RTH-on-voice (needs metric origin).

## Files
- `fmu_node.hpp` (interrupt hook, prompt assembly), `llm_base.hpp` (verdict schema), ASR topic wire.

## Tests to create
- **[AUTO]** `--canned-voice`: inject a transcript → assert an interrupt is raised and the `[USER]`
  block appears in the next prompt.
- **[AUTO]** `--canned-complete`: a met objective → assert an `objective_complete` verdict + a
  terminal `land`/`stop`, and NO further planning.
- **[HUMAN]** live spoken "done, land" stands the drone down (one confirmation run).

## Acceptance
Canned voice stands the drone down; the completion verdict fires on a met objective in SITL; live
voice confirmed once.

## Agent notes
The one spec that must serialize on `fmu_node.hpp`. Take the lock, land the interrupt hook, release,
then the prompt work. Gates demo S3 (A4).
