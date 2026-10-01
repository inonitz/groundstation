## GAPS

The most important finding is a contradiction: C1 below (the live webcam test). Read it first.
Six items are in no record. No owner question is still open. Most important first.
The full item table: docs/refactor/audit-transcript-2026-10-01-full.md.

### G1. How the target words of a vision request work (clips 98, 99)
- Date: 2026-09-30 (M148).
- The owner: "Do all of the nouns/words I use inside the "highlight-box" count?" and
  "or do I have to say "adidas-logo-on-shirt" as a single unit here?"
- The answer exists only in the chat (2026-09-30 08:15). In the app, Gemma writes one English target.
  The vision system splits it: the main object, the relation, the related object.
  SAM3 searches the main object as one phrase; verify then checks the relation and the related object.
  In the labelling page, the owner types words separated by commas.
  Each word must appear in Gemma's target, in any order; "logo, shirt" also matches "logos".
- Why it matters: the joint review (handoff section 5, step 1) checks these labels again.
  The open question on clips 116, 117 and 120 (highlight or describe) depends on the same rule.
  Ledger row B4 (8) says only "98/99: answered".
- Pieces exist outside the records: the page format in docs/refactor/bench_doc.md line 589,
  the scorer rule in docs/refactor/recognizer_doc.md line 106, the split in
  docs/api-harden2/perception.h. The answer to the owner's question is in none of the records.
- Where it belongs: ledger B4 (8), decision cell (the answer in two lines, with these pointers);
  handoff section 5, step 1.

### G2. The limits of the vision system at the freeze
- Date: 2026-09-30 (M145).
- The owner: "What are the limits of the soon-to-be-finished vision system?"
- The question is in the ledger (row B-vision). The answer is not: the row says "given 2026-09-30".
  The chat answer (2026-09-30 06:35) was a table:
  - time per SAM3 pass: about 410 ms for one name, 740 ms for three;
  - command to first box: 3.5 s then; about 0.95 s after L1 + L2 (handoff section 4);
  - identity: none; each refresh detects again, so boxes can jump between objects;
  - view: only the camera's current view; no scan (clips 60, 61);
  - relations: "on", "under", "held by" by box geometry; colour by hue; others unverified;
  - SAM3 is 51 % slower while Gemma answers (this one is in research-complete-sam3-assessment.md);
  - start: SAM3 ready after about 9 s; the video stutters until then;
  - accuracy on 137 labelled rows: 105 correct, 16 partial, 8 false draws;
  - low light: not measured.
- Why it matters: the owner's road (RM1) ends with "Make sure that I understand what is going on in
  the system". The walk-through and the field test need these limits in writing.
- Where it belongs: docs/harden2-status.md (a "known limits" table, numbers refreshed);
  ledger B-vision.

### G3. A test that can pass without checking anything is a bad test
- Date: 2026-09-27 (M102, point R6).
- The owner: "The fact that a test can pass without checking anything just tells me that same test is
  not good. What else can be said about said test?"
- Ledger R6 keeps only "I agree with everything besides mutation checks".
  The handoff (section 9) lists "a test that checked only a shape" as an agent overclaim, not as a rule.
- Why it matters: it is the owner's standard for the test review and for the code review (road step 4).
- Where it belongs: docs/guidelines.md, "Project rules learned in harden2", Tests; ledger R6.

### G4. Why Gemma never draws boxes
- Date: 2026-09-22 (M4, M10).
- The owner: "We don't use Gemma to creating bounding boxes since its not designed for this task.
  Qwen3-VL was better at this, but not better than SAM3." and
  "We don't use Gemma for this, we stopped doing that BECAUSE it was inaccurate!"
- Why it matters: a fresh agent can propose Gemma or a VLM as a box source, for example as a SAM3
  fallback. The reason against it is not written.
- Where it belongs: docs/research-complete-sam3-assessment.md, or the architecture notes of the
  harden2 README (one line: boxes come only from SAM3; Gemma answers and verifies).

### G5. A diagram for the owner shows the full control flow
- Date: 2026-09-22 (M13).
- The owner: "I don't like that you didn't draw the interaction with the Task Queue" and
  "Diagrams are for someone else to understand the high level details, but I wanted to really
  understand everything that is happening".
- Why it matters: road step 7 is a walk-through so the owner understands the system.
  A high-level diagram failed this need once already.
- Where it belongs: handoff section 2 (how to work with this owner), or guidelines,
  "Working with the owner".

### G6. The fatal.py rename, never closed
- Date: 2026-09-23 (M48).
- The owner, on fatal.py: "maybe rename it."
- The refactor handoff (line 410) says "propose a name at step 3". No proposal or ruling was found.
  runtime/fatal.py keeps its name.
- Why it matters: a small owner suggestion that no open list carries.
- Where it belongs: handoff section 6 (open items), or a ledger row once the owner rules.

### Questions without an answer
None is still open. One question got no direct reply: "Am I notified of the failure?"
(2026-09-22, M19). The status-panel rulings of the same day settled it: a failed system turns its row red.

## CONTRADICTIONS

### C1. The live webcam test: "now, if possible" against "step 5, do not reorder" (high)
- The owner, 2026-10-01 04:34 (M151, "locally", point 8, the live webcam test):
  "If possible, we'll do this now."
- The agent's own reply at 04:35 said: "Your live webcam test: now, if possible."
- The records say otherwise:
  - docs/task-active-harden2-handoff-2026-10-01.md, section 5: step 5, after the code review,
    under "Do not reorder it.";
  - docs/harden2-status.md, road row 5: "after 4";
  - docs/task-active-harden2-refactor-handoff.md, 9h, step 5.
- RM1's own words do not place the webcam test. The order came from the agent's list.
- Fix: the live webcam test, with the QC2 input-level check, runs now if possible. It does not wait
  for steps 1-4. Record the owner's words in the ledger (a new row, for example QC2 (2) or RM1 (2)).

### C2. The ledger calls every ruling "word for word", but it starts on 2026-09-26 (medium)
- The handoff (section 0, item 5) and the status page call the Decision ledger "every owner ruling"
  and "the AUTHORITY". The handoff (line 3) says the work lasted five days, 2026-09-26 .. 2026-10-01.
- The conversation began on 2026-09-21. 97 of the 279 recorded items live only in the older spec
  sections "Owner rulings 2026-09-21" .. "2026-09-25" (spec lines 170-585).
  Examples: the gemma package, the status panel, the generic supervisor, the app lifecycle, util/,
  the code-style reference, OOM -> die, the logging check at start.
- Most of them also reached the guidelines ("Project rules learned in harden2"), but not all.
- Fix: in handoff section 0 and in the status page, name the older spec sections as the record of
  2026-09-21 .. 2026-09-25, and correct the dates on line 3.

### C3. J3 reversed by the agent, not by the owner (low)
- The owner, 2026-09-28: J3 "option A" (step_text moves into app/).
- Ledger J3 (2) and handoff section 9 drop the move as "(fact, 2026-09-29)". No owner word follows.
- The reason is sound: the labelling tool also uses step_text, and the guidelines put a helper of two
  modules in util/. But CLAUDE.md says a recommendation is not a decision.
- Fix: mark J3 (2) "agent decision, open to the owner" and add it to "Open with the owner".

### C4. Old lines still read as in force, with no "superseded" mark (low)
- spec line 235 (2026-09-23): "Commit everything now, in stages ... BUILD BROKEN".
  Superseded by ledger D, K3, CP1 and RM1 (the owner commits just before the freeze).
- spec line 253 (2026-09-23): "Dependencies: one file checks every dependency at start-up".
  Superseded by ledger Q5 and 3.2.3 (no check in main.py; the preflight is its one place).
- refactor handoff line 72 (also lines 240, 320, 422, 541): "Global phase 7, after the webcam mock
  test: SAM3.1 + EOVSAM". Superseded by S6 (2) and POST (2): after the freeze, with the owner.
- Fix: append "SUPERSEDED by <row>" to each line.

## Coverage

Mechanical (tools/audit/transcript_coverage.py; reproducible: two runs, same md5):

| count | value |
|---|---|
| owner messages | 157 (143 typed + 14 typed while the agent worked), 2026-09-21 21:08 .. 2026-10-01 05:22 |
| entries dropped | 6 slash commands, 6 interrupts, 5 local commands, 5 task notifications, 4 compaction summaries, 1400 tool results |
| sentences | 2175; 913 under 4 words (not checked) |
| EXACT | 288 |
| NEAR (>= 0.6 of the 3-grams) | 74 (31 of them under 0.75) |
| NONE | 900 |

Judgment (items, docs/refactor/audit-transcript-2026-10-01-full.md):

| class | items | sentences (NONE + NEAR under 0.75) |
|---|---|---|
| RECORDED | 279 | 758 |
| SUPERSEDED | 15 | 42 |
| ANSWERED | 38 | 81 |
| NOISE | 16 | 36 |
| MISSING | 7 (6 gaps: M4.1 and M10.1 are one) | 13 |
| CONTRADICTED | 1 (C1; C2-C4 come from the reverse check) | 1 |
| total | 356 | 931 |

What is mechanical and what is judgment:
- Mechanical: the message filter, the sentence split, EXACT / NEAR / NONE and the best file:line.
  Re-run: `python3 /root/groundstation/tools/audit/transcript_coverage.py --until 2026-10-01T05:23:00Z
  --tsv /root/groundstation/docs/refactor/audit-transcript-2026-10-01-coverage.tsv`.
  A change to a record changes the result; that is the point of a re-run.
- Judgment: the split of a message into items, each item's class and evidence, and the reverse check.
- Join: docs/refactor/audit-transcript-2026-10-01-judgment.tsv gives each NONE and low-NEAR sentence
  its item. Gap sentences are assigned by hand; the rest by the largest word overlap in the message.
- Limits: EXACT on a question means only the question is recorded (G2 is an EXACT). Short answers
  ("Option A", "Yes") are under 4 words; the items of their message carry them.
