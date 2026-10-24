# harden2 API rev5: the architecture review, one system at a time (started 2026-10-04)

rev4 (and its rounds 1 to 4) is withdrawn as a design: the owner's verdict on the last revision
was "Its horrible" (ledger REV5). rev5 starts from the architecture, not from today's code.
Nothing is implemented. Nothing in rev4 is copied here; rev4 stays as the record of what was
rejected and why (its REVIEW-*-owner.md files are the owner's words).

## The procedure (agreed by the owner, 2026-10-04, BRN1; every step runs through /superpowers:brainstorming)
1. **The system sketch, top-down, one page, first.** The layers (the outside processes; the
   services; the systems; the app), who owns what (the app owns every handle), the data flow
   with every thread, queue and hand-off drawn, and the few cross-cutting patterns decided ONCE
   for the whole app: how a background worker hands a result to the main thread; how a process
   is begun and ended; how data reaches a logger. Round 4 failed on exactly these: they were
   asked inside one module, without the picture.
2. **The module reviews, bottom-up, by dependency.** A module is reviewed only after every
   module it depends on is settled. The order: perf; telemetry; runtime (die, the supervisor,
   ROS2); the frame buffer; the llama-server; the SAM3 server; the phone-app client and its mock;
   speech in; speech out; the recognizer; the platform command dispatcher; the frame source; the
   vision system (the scheduler, the ops, the jobs); the keys; the screen and the app.
3. **The app last**, as the check that every interface fits the sketch of step 1.

Each review, in plan mode, with the owner:
- the full picture of that one module first: its job in one sentence; how it works today, with
  the files; the rulings that bind it; the open points;
- the design gate, answered at the top of the header: ownership, data in and out, the mutable
  state and its owner, the threads and their stops, the processes and their stop protocol;
- no option menus: the context, the forces, the reasoning, pseudocode, then the conversation (BRN2);
- the header, as code, in this folder; the owner approves it before the next module.

## The house rules of rev5 (the ledger holds the owner's words)
| rule | ledger |
|---|---|
| a design answer is code; prose only for the why | CODE1 |
| each answer in one place; no forward references | ONE1 |
| the full picture of a system before any design question | CTX1 |
| every process and worker: XxxCreate / XxxDestroy, a graceful stop | PROC2, NAM3 |
| the app owns every handle; handles are plain structs by value; no Attach | OWN1 |
| opaque only for OS resources with no app state; sinks take const data | TEL1, PRF2 |
| a pipeline stage is a bundle of pure functions | REC1 |
| `_Atomic` types, named as what they are | ATM1 |
| no comment on the implementation | NAM2 |
| the layout of docs/guidelines.md | HDR4 |

## Checking a drawing
Every drawing in this folder passes `python3 /root/groundstation/tools/style/svg_text_check.py <file.html>`:
it measures each text with the font metrics and reports text past its box, text off the canvas, and
text crossed by a line. Zero faults before a drawing is shown (the owner, 2026-10-06).

## State
| step | state |
|---|---|
| the order of the review | agreed (BRN1) |
| the method | the brainstorming skill, called explicitly for each step |
| 1. the system sketch | DONE as 01-system-architecture.md (the design document; its drawing 01-system-architecture.html is identical to the rev-2 sketch). The sessions: SYS1, STA1, NAM3 decided; the record is 01-system-sketch.md (sections 7-11); the drawings are 01-system-sketch.html (the first sketch), 02-system-sketch-ponytail.html (the lazy build) and 03-system-sketch-rev2.html (the sketch after the owner's answers, the changes marked); open: none on the sketch; the TCP benchmark is being looked for |
| 1b. the design review | DONE 2026-10-08: 04-review-*.md (four methods) and 05-review-summary.md (merged; 12 questions). The owner's answers: ledger RVW2 to RVW7. Next: apply them to 01-system-architecture.md, regenerate and compare the drawing |
| 2. the modules | started 2026-10-12: perf (modules/01-perf/) APPROVED (PRF3 to PRF5); telemetry (modules/02-telemetry/) proposed; the state table is modules/README.md |
| 3. the app | not started |
