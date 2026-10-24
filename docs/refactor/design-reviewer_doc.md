# design-reviewer: the brief (2026-10-08), then the agent's notes and progress

## The brief
Context. harden2 is a Hebrew voice-commanded drone ground station (projects/integration_harden2).
Its architecture was redesigned in docs/api-harden2/rev5 with the owner (the ledger rows SYS1 to
SK6 in docs/spec-harden2-cleanup.md hold his words). The design is now one document. Nothing is
implemented; the headers come after this review.

The ONE document you review: docs/api-harden2/rev5/01-system-architecture.md, with its drawing
docs/api-harden2/rev5/01-system-architecture.html (open the .html as text; the SVG is inline).
For the sources of its numbers you may read docs/api-harden2/rev5/01-system-sketch.md section 4
and the benchmark READMEs it names. For the owner's own words you may read the ledger rows
SYS1, STA1, NAM3, SK1 to SK6 in docs/spec-harden2-cleanup.md. Read nothing else first; today's
code (projects/integration_harden2) only when a finding needs a fact from it.

Objective. A complete system-design review of that document with the four methods of your
definition, in order. Two emphases: the frame buffer protocol (section 6: the atomic counts, the
"latest" index, who holds a slot and when) and the removal test (method 4) over every component.

Output. Four files, one per method, in this order:
- docs/api-harden2/rev5/04-review-premortem.md
- docs/api-harden2/rev5/04-review-atam.md
- docs/api-harden2/rev5/04-review-design-doc-checks.md
- docs/api-harden2/rev5/04-review-first-principles.md
Each file: a two-line header (the method, the document reviewed, the date), the findings ranked
CRITICAL, HIGH, MEDIUM, LOW in the five-line form of your definition, then a closing list of the
questions for the owner. Every finding cites a section of the document.

Checks before you finish: every finding has its five lines; every finding cites a section; no
finding restates the design without a fault; the uncertain ones are marked. Write a progress
line at the bottom of this file after each method.

Return exactly one line: `done: <the four paths>`.

## The agent's notes

## Progress

- 2026-10-08 method 1 (pre-mortem) written: docs/api-harden2/rev5/04-review-premortem.md, 18 findings (4 CRITICAL, 6 HIGH, 6 MEDIUM, 2 LOW).
- 2026-10-08 method 2 (ATAM) written: docs/api-harden2/rev5/04-review-atam.md, 25 scenarios, 20 risks (4 CRITICAL, 8 HIGH, 8 MEDIUM), 7 non-risks, 7 sensitivity points, 7 tradeoff points.
- 2026-10-08 method 3 (design-doc checks) written: docs/api-harden2/rev5/04-review-design-doc-checks.md, 15 findings (2 CRITICAL, 5 HIGH, 5 MEDIUM, 3 LOW).
- 2026-10-08 method 4 (first principles) written: docs/api-harden2/rev5/04-review-first-principles.md, 25 removal rows, 13 findings (1 CRITICAL, 4 HIGH, 6 MEDIUM, 2 LOW), 10 unproven assumptions.
