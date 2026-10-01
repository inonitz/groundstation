# harden2: where we stand

The one-page human overview of the harden2 work: where we are, what comes next, what is decided, and
where each detail lives. It holds the current state only; the history is in docs/HISTORY.md.
Last updated: 2026-10-01.

| section | content |
|---|---|
| The goal | what harden2 is for |
| The road to the freeze | the owner's order, with the state of each step |
| What the refactor delivered | the results that matter, with numbers |
| After the freeze | the planned releases |
| Open with the owner | what still needs a decision |
| Where the details live | every record document, what it holds, who it is for |

## The goal
A drone that a person commands by voice in Hebrew, that understands what its camera sees, and that acts.
harden2 is the live system: Hebrew speech, one Gemma planner, SAM3 vision, and guards that check each plan.

## The road to the freeze
The owner's order (ruling RM1, 2026-10-01). A freeze tags the exact commit that passed the field test.

| # | step | state |
|---|---|---|
| 1 | Joint review: every recording label, the 34 expected-result drafts, the 144 vision-kind drafts | next |
| 2 | Run whisper and the recognizer on the recordings (B2); rerun the recognizer benchmark | after 1 |
| 3 | Finish the cleanup and the refactor | almost done |
| 4 | Code review with the review tools, then fix what they find | after 3 |
| 5 | The owner's live webcam test, with a microphone input-level check | after the owner's review of the state with the new agent |
| 6 | The field test on the real drone, secured, until done | after 5 |
| 7 | A walk-through, so the owner understands the whole system | after 6 |
| 8 | The doc sweep and the owner's commits, then the freeze | last |

## What the refactor delivered
| area | result |
|---|---|
| speed | a highlight shows its first box about 0.95 s after the transcript (it was 3.8 s on first use); a planned mission takes 0.77 s |
| recognizer | the number guard reads 40 of 40 test sentences (it read 7); every test sentence is stored once (545); honest score 458 of 545 |
| vision | one image encoding per pass (a three-name search 1126 -> 744 ms); SAM3 in its own folder; SAM3 saved ready in 4-bit form |
| start-up | the app's import takes 0.15 s (it took 1.3 s); every status row is UP after about 13 s, warm-ups included |
| tests | 248 tests pass; every try/except is in one audited place (5) |
| tools | a labelling page for the recordings: tools/asr-verify-transcript |
| research | SAM3 and SAM3.1 video tracking fit the 8 GiB GPU in 4-bit form; where the command-to-action time goes |

## Known limits at the freeze
| limit | value |
|---|---|
| one SAM3 pass | about 410 ms for one name, about 740 ms for three |
| command to first box | about 0.95 s from the transcript (speech recognition adds about 0.3 s) |
| identity | none: each refresh detects again, so boxes can jump between objects |
| view | only the camera's current view; no scan yet |
| relations | "on", "under", "held by" by box geometry; colour by hue; others unverified |
| sharing the GPU | SAM3 is 51 % slower while Gemma answers |
| start | every row UP after about 13 s; the video stutters for the first 9-11 s |
| accuracy (137 labelled rows) | 105 correct, 16 partial, 8 false draws |
| low light | not measured |
| boxes | only SAM3 draws boxes; Gemma answers and verifies, never draws (owner 2026-09-22: it was inaccurate) |

## After the freeze
Each release ends with a new field test.
1. Benchmarks: whisper under noise; SAM3 in low light.
2. The recognizer: a shorter plan answer (about 0.45 s faster per mission, estimate) and a flight plus a
   vision request in one sentence; a larger military-slang set.
3. Near-term architecture: SAM3 in its own process (no start stutter; a SAM3 failure no longer ends the
   app). SAM3.1 and EOVSAM are evaluated by the owner and Claude together.
4. Vision, a big feature: a tracker that keeps one identity per object, then scan beyond the camera's view,
   then vision-driven action.
5. Far: the fusion onto the C++ llm_to_action engine.

## Open with the owner
- The joint review (step 1). It includes clips 116, 117 and 120 (highlight or describe?) and the removal of
  the inaudible clips 67-73 and 82.
- Nothing is committed yet: the owner commits just before the freeze.
- First: the owner reviews the current state with the new agent.

## Where the details live
| document | what it holds | readability |
|---|---|---|
| docs/harden2-status.md | this overview | written for people |
| docs/task-active-harden2-refactor-handoff.md, section 9h | the road to the freeze and after, step by step | for people and agents |
| docs/spec-harden2-cleanup.md, "Decision ledger" | every owner ruling, word for word, with its decision (about 250 rows) | an audit record: dense |
| docs/HISTORY.md | every finished piece of work, dated, with its measurements and verdicts | readable entries; long |
| docs/research-complete-*.md | the result documents (SAM3, video tracking, latency, retired benchmarks) | for engineers |
| docs/guidelines.md | every standing rule for the work | for people and agents |
| docs/task-active-harden2-session-log-2026-09-23.md | line 1: where an agent resumes; then a dense progress list | for agents |
| docs/refactor/<agent>_doc.md | each agent's brief, notes and evidence | for agents |
| docs/ROADMAP.md | the long-term phases | out of date (2026-09-14); the doc sweep updates it |
