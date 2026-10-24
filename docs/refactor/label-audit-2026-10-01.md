# Label audit of the 139 recordings, 2026-10-01

CLOSED 2026-10-01: the owner ruled every item in the joint review (ledger JR4-JR17). The labels are in
datasets/asr/recordings.json; this file keeps the audit as it was found.

## Objective
Check every saved label in datasets/asr/recordings.json before the joint review (road step 1).
The owner's Hebrew sentences are the reference (ruling JR2). This check covers the expected
results: the kind, the steps, the vision kind and the keyword groups.

## Method
- Each clip's sentence was read against its `expect` and its `draft`.
- The scoring rule is bench/recognizer/scorer.py `score_perception`.
- Every keyword group must match: the groups are joined by AND.
- Inside one group, one word is enough: the words of a group are joined by OR.
- A word matches when it appears inside "<kind words> the <Gemma target>".
- A hyphenated word therefore matches only when Gemma writes the same hyphens.

## Results
| count | state |
|---|---|
| 139 | clips in the file |
| 30 | removed (23 before; 67-72 and 82 removed today as inaudible, ruling QC1) |
| 109 | active |
| 79 | active clips with no finding |
| 16 | active clips with a finding below (groups A and B) |
| 14 | active clips that wait for an owner ruling already known (group C) |

### A. The expected result does not match the sentence
| clip | sentence | stored | finding | proposal |
|---|---|---|---|---|
| 103 | תסמן את המכונית בצד השמאלי של הבניין בכיוון הימני. | groups: highlight/mark, window, middle/center, building, right | copied from the unrelated case perception.json/i_mid_windows; the sentence asks for a car | vision highlight; groups: car/vehicle, left, building |
| 137 | תסמן את החולצה שהבן אדם לובש. | no vision kind; groups: shirt, wearing-shirt, person-wearing-shirt | the only new perception clip with no vision kind; see also B | vision highlight; one group: shirt |

### B. Groups that can fail on a correct answer
The owner typed comma-separated words. The page stored each word as its own group, so every
word is required. Several lists look like synonyms (any one would do), and several hold hyphens.

| clip | sentence | stored groups | why it can fail | proposal |
|---|---|---|---|---|
| 108 | סמן את המשקפיים שלי. | glasses + person-with-glasses | the hyphenated word must appear as written | glasses |
| 111 | סמן את הגיטרות בתוך התיקים שלהם. | guitars/guitar + encased-guitars | the hyphenated word | guitar + case |
| 112 | האם אתה רואה תיקי גיטרות? | guitar-case + many | hyphen; "many" is not in the sentence | guitar + case |
| 113 | האם אתה רואה תיקי גיטרות מתחת ללוח מאחוריי? | guitar-cases + board + below | the hyphenated word | guitar + case + board/whiteboard + below/under |
| 130 | סמן את הגוש של הבגדים מאחוריי. | clothing + lump-of-clothing + clothes + cloth-lump | four synonyms, all required | one group: clothing/clothes/cloth |
| 131 | סמן את הקייסים של הגיטרות מאחורי. | cases-guitar + guitar + cases | the hyphenated word | guitar + case |
| 134 | תסמן את החולצה שלי. | shirt + wearing-shirt | the hyphenated word | shirt |
| 135 | תסמן את החולצה של הבן אדם. | shirt + his-shirt + persons-shirt | two hyphenated words | shirt |
| 88 | תסמן את כל הגיטרות | guitar + all | Gemma's target may omit "all" | guitar |
| 91 | סמן את כל הגיטרות | guitars/guitar + all | as 88 | guitar |
| 99 | תסמן את ה-"לוגויים" על החולצה שלי | logo/logos + all | as 88; "all" is not in the sentence | logo + shirt |
| 126 | סמן את הקופסאות | boxes + box + many | "many" is not in the sentence | box |
| 119 | Highlight the pencils or the markers that you can see in the image | pencils + markers | the sentence says "or"; both are required | one group: pencil/marker |
| 94 | תסמן את השידה מאחוריי | drawer/cabinet | Gemma can write "dresser" | drawer/cabinet/dresser |

### C. Clips that wait for a known owner ruling
| clip | open question |
|---|---|
| 8, 23 | unclear intent (23 reads like clip 29's three steps) |
| 27 | a flight plus a photo: compound plans come after the freeze (CI1); graded as review |
| 38, 45, 50, 56, 59 | microphone overload: keep or remove |
| 60, 61 | scan requests: no scan capability yet |
| 98 | the Adidas logo: review, or a highlight with groups adidas + logo |
| 116, 117, 120 | highlight or describe |

### D. Other notes
- Clip 13 now reads "fly back 8 meters", as the handoff asked. Closed.
- Clips 64-139 carry `file`/`case` links to unrelated cases (for example commands.json/up10).
  The links are placeholders. The B2 run must score each clip by its own `expect`.
- Clips 1-60 keep their vision kind only in `draft` (the 144 drafted kinds, ruling SC1).
  Until the owner confirms them, the scorer does not check the vision kind of those clips.

### E. Cross-check with the B2 run (2026-10-01)
- On the owner's labels, 24 clips fail. 13 of them are clips flagged in groups A and B.
- The other 11 failures: 11, 17, 21, 24, 33, 34, 35, 47, 48, 79, 115.
- Clips 21 and 79 ("stop for 10 seconds") go to the emergency halt. The label expects a 10 s wait.
- Clip 35 asks whether landing is possible. Gemma plans a landing; nothing may fly.
- Clips 47 and 48 ("come back") plan `home`. The label expects a 10 m flight back.
- Clips 11, 17, 24, 33, 115: Gemma's words differ from the groups ("truck", "2", "held", "sign").
- Clip 34: Gemma's target drops "right" and "wall".
- Results: bench/recognizer/results/2026-10-01-recordings-labels.json and -whisper.json.

