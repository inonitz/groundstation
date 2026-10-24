# harden2 API rev4: the API being devised with the owner (2026-10-02, DRAFT)

rev3 was the ground truth "as ruled" (rev2 plus the rulings). The owner then reviewed rev3 module by
module and is redesigning the API with the agent: this folder. NOTHING is implemented. A new agent
implements the version the owner approves.

Rules of these headers (owner HDR1, HDR3):
- They are written for the OWNER to understand the internals and the intent, not as a library API.
  Nothing is hidden: the internal steps are declared, in the order they run.
- Every struct shows its data members. Opaque only: OS primitives and third-party objects.
- A header that does not explain itself is not good.
- The layout follows docs/guidelines.md (owner HDR4): one member per line, aligned; field notes in an
  "@field:" block above the struct; one enum value per line; one argument per line in a long
  prototype; no line over 95 characters. Tool: tools/style/header_layout.py (run it on a new header).

| file | state |
|---|---|
| REVIEW-2-owner.md | the owner's round-2 review, word for word (round 1: ../rev3/REVIEW-1-owner.md) |
| REVIEW-3-owner.md | the owner's round-3 review of the laid-out headers, word for word (HDR5) |
| REVIEW-3-answers.md | the agent's answers to round 3 (rejected in round 4: the designs restated the code) |
| REVIEW-4-owner.md | the owner's round-4 review and his answers in the plan-mode session, word for word (HDR6) |
| REVIEW-4-answers.md | every round-4 point with its full picture: the system, today's code, the owner's words, the proposal as code (CODE1, ONE1, CTX1) |
| DESIGN.md | the agent's answers to round 1, with the facts of today's code |
| status.h, runtime.h, frames.h, video.h, sam3.h, gemma.h, flight.h, audio.h, log.h, perf.h, perception.h, recognizer.h, app.h | rev4 drafts, written 2026-10-02 after round 2; they compile |
| util.h, keys.h, scripted_run.h, dji_app.h | carried from rev3 (dji_app.h: the probe explained, the transmit switch moved to flight.h) |

What rev4 changes against the code (each is PROPOSED until the owner rules it):
- SAM3 in its own process; frames in ONE shared-memory ring (frames.h); a request names a frame
  number; boxes and masks come back together with that number.
- Speech in: one ROS2 transcript topic; the phone gets a small bridge; one subscriber.
- flight.h: FlightController, six calls, an atomic manual flag, no lock, no transmit switch in dji_app.
- gemma.h: one handle from GemmaStartServer; no create / close.
- log.h: a Turn in three parts; vision jobs are their own list; SessionLog keeps both lists.
- perception.h: Job (the jobs pane reads them); several highlights; the steps of each job declared.
- recognizer.h: the six steps of Route declared in order; the warm-up inside Create.
- app.h: one App struct; the Screen borrows the jobs from Vision; no callbacks struct, no TurnHandler.
Still to do: the owner reviews REVIEW-4-answers.md; then, in plan mode, one system at a time with its full picture first (the vision system, then audio, runtime, telemetry and perf, dji_app and the dispatcher, the app): a spec the owner approves, then that header; then preflight.h; then GAPS for rev4. The house rules of round 4: Begin/End for every process (PROC2), the app owns every handle (OWN1), opaque only for OS resources (TEL1, PRF2), pure functions for a pipeline stage (REC1), `_Atomic` types (ATM1), code as the shared language (CODE1), one place per answer (ONE1), the full picture before a design question (CTX1).
