# Writing style

Write prose the reader can follow on the first pass. They should never have to untangle a sentence before they understand it.

Keep sentences short. Put one idea in each sentence. Make each sentence lead into the next, so the reasoning flows instead of branching. Cut parentheticals and mid-sentence asides; give that content its own sentence, or drop it. Do not reach for bullet points to avoid writing clear sentences — fix the sentence itself.

This is about prose: explanations, reports, and messages. Code style is separate and lives in [code-guidelines.md](code-guidelines.md).

## Result documents (added 2026-09-02, owner-ruled)

Benchmark and test reports use the register of a senior robotics/software engineer:
Objective, Setup, Results (neutral tables, every column), Analysis (numbered, factual),
Conclusions or open decisions at the end. No metaphors, no narrative, no session references —
the document must stand alone. Define a project term once, then use only that term.

READMEs are the current state of a thing, never an archive: a 3-line introduction, a section
table, then only current content. Superseded results move next to their raw data (for example
results/HISTORY.md), marked superseded. New results update the scorecard in place; they never
stack a new dated section.
