# harden2 API rev3: the ground truth (2026-10-02)

The revisions of the API headers (owner, 2026-10-02: one folder per revision):
| folder | what it is |
|---|---|
| docs/api-harden2/rev1/ | the headers as they stood on 2026-10-02 before this work (v2.4 / v2.5: partly changed by agents to fit the code) |
| docs/api-harden2/rev2/ | the v2.3 headers of 2026-09-24 (git f3776de), the version nearest the owner's approval; read-only |
| docs/api-harden2/rev3/ | THIS folder: rev2 plus every later ruling; every struct populated; the ground truth |
A later revision goes into rev4/, and so on; an older revision is never edited.


Why this folder exists: the API headers (docs/api-harden2/rev1) and the Python code drifted apart, so
neither is a ground truth (owner, 2026-10-02, ledger API1, API1 (2), GT1). The owner's procedure
below builds one. The rulings decide every gap (GT1 (3)). The previous agent wrote the ground truth and the gaps; the next
agent implements GAPS.md.

| section | content |
|---|---|
| The procedure | the owner's seven steps, word for word, with the state of each |
| What is here | the files of this folder |
| Method | how each step is done, so a new agent can continue |
| Known gaps | what this session already found (input for steps 5 and 6) |

## The procedure (owner, 2026-10-02, GT1)
"Currently integration_harden2 should match most systems/modules built."
| # | the owner's words | state |
|---|---|---|
| 1 | "build the 2.3 headers" | DONE: docs/api-harden2/rev2/ (git f3776de, 2026-09-24; 11 headers + README; they compile) |
| 2 | "List what the rulings are" | DONE: RULINGS.md (37 ledger rulings + 8 from the spec; the owner's words copied by script) |
| 3 | "Make sure the rulings reflect the v2.3 code" | DRAFT: the rev3 headers in this folder (today's headers, each v2.3 -> v2.4 change checked against a ruling, drift corrected, the new rulings applied; every change is tagged "[rev3: ID]"; they compile) |
| 4 | "Now we have a ground-truth." | IN FORCE: the rev3 headers plus RULINGS.md (the owner set no approval step; GT1 (3)) |
| 5 | "Use the ground truth and compare it to the current state." | DONE on paper: GAPS.md (19 gaps) and AS-BUILT.md (100 names in no header) |
| 6 | "Address the gaps and see how we should change the current code to accomodate the new ground truth." | DECIDED per gap in GAPS.md, each by a named ruling (kind, change, tests); nothing implemented yet: the next agent builds |
| 7 | "This is not set in stone. There might be features or code currently that is indeed faithful to our decisions, we might just not reflect it in our docs." | applies to steps 5 and 6 |

## What is here
- docs/api-harden2/rev2/: the headers as committed on 2026-09-24 (v2.3), the version nearest the owner's approval
  of API v2 (2026-09-23; control, recognizer, app followed as v2.1). Read-only: never edit it.
- RULINGS.md (step 2): every owner ruling that changes the API.
- *.h (step 3): the rev3 headers; search "[rev3" for every change and its ruling. Every struct shows
  its data members (owner HDR1); keys.h and scripted_run.h are split from app.h.
- GAPS.md (steps 5, 6): the gaps and the proposed change for each. AS-BUILT.md: the 100 names no header declares.

## Method
- Step 2. Sources, in this order of authority: docs/spec-harden2-cleanup.md "Decision ledger" (the
  LAST row of an ID is in force), the spec's older owner sections (2026-09-21 .. 09-25), the refactor
  handoff "4a. Rulings in force". Take every ruling dated 2026-09-24 or later that changes what a
  module offers or how modules meet; also the earlier ones v2.3 does not yet show. One row each:
  date, ID, the owner's words, the header and declaration it changes.
- Step 3. Copy docs/api-harden2/rev2 to this folder's top level, apply the rulings one by one, cite each.
  A ruling v2.3 already shows needs no change (note it). Compile: `for f in *.h; do gcc
  -fsyntax-only -x c $f; done`.
- Step 5. Three comparisons: rev3 against docs/api-harden2/rev1 (v2.4 / v2.5: which later edits were
  rulings, which were agents syncing to the code); rev3 against the code, name by name (the script of
  2026-10-02: every public Python class, method and function matched to header identifiers; 262
  names, 100 in no header); rev3 against behaviour (the findings below).
- Step 6. For each gap: "the code is right, the docs lag" (step 7: add it to rev3, for the owner's
  review) or "the code deviates" (change the code). The owner rules each group.
- Then, and only after the owner approves: the fix pass, each part with its tests; a test that fails
  on any header/code mismatch; the gate; the end-to-end test; the benchmark rerun; one final review.

## Known gaps
Moved to GAPS.md (each gap: the design, the code, what a user sees, the proposed change).
