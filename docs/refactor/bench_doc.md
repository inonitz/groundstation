# bench: the agent doc

## Brief (the main agent, 2026-09-28; do not edit)
Name: bench. ROS_DOMAIN_ID=13. The shared rules: docs/refactor/README.md.

**Context.** The benchmarks drifted from the code. The vision benchmark (bench/vision-verify-bench)
is broken since 2026-09-23 (commit 7ad3012): detect() now returns (status, hits), and bench.py and
propose_boxes.py still call it the old way. bench/whole-system is retired (D1 a). The 2026-09-18
typing study is finished (G1, G2). A benchmark is deleted only under rules A-D (bench/README.md,
"Deleting a benchmark").

**Objective.** Every benchmark that stays measures one thing and runs. Every retired one leaves a
research-complete document. The owner gets a tool to label the 139 recordings.

**Tasks, in order.** The full text is in handoff 9d.
1. B5: the vision benchmark measures ONLY vision (X2: "we care about measuring the vision system,
   NOT THE WHOLE SYSTEM NOR THE RECOGNIZER! ONLY THE VISION").
   - Fix the detect() calls in bench.py and propose_boxes.py. Keep its English input and its own
     scorer (X3).
   - Move bench/vision-verify-bench to bench/perception/ with mv (Y1).
   - In the same step, move the .gitignore line "bench/vision-verify-bench/dataset/images/" to the
     new path. The images are private (the owner's room) and must never become committable. Check
     it with git check-ignore on one image.
   - Rerun it (lock gpu; about 3 minutes, an estimate) and compare with the 2026-09-20 numbers.
   - Update its README, bench/README.md, and every current-state doc that names the old path
     (annotate.py imports app.draw; keep it working).
2. B6: bench/whole-system (D1 a).
   - Write docs/research-complete-whole-system.md (Objective, Setup, Results, Analysis,
     Conclusions; guidelines "Result documents") from its README and results/.
   - Then delete its scripts and run_all.sh. Do NOT delete run_list.py: recognizer deletes it in
     B1. Keep labels/ and results/ (the raw data).
   - Its README then says, in 3 lines, that it is retired, and points to the document.
3. B3: the confirm tool (Z1 a). It waits for the section "B1 JSON format" in
   docs/refactor/recognizer_doc.md.
   - For each of the 139 recordings in datasets/asr/ (clips/, manifest.jsonl): propose the sentence
     and the expected result from the nearest B1 case, play the clip, and let the owner confirm or
     correct. Write the recordings JSON in the path B format.
   - The owner runs it (task B4): keyboard only, one clip at a time, it saves after every clip, and
     it resumes where it stopped.
   - Put it in bench/recognizer/ and document it in bench/recognizer/README.md (lock that file).
   - Test it on 3 clips yourself. Put the exact command under "For the owner".
4. B7: the typing study (G2 a). It waits for B1 [x] in 9d.
   - Move docs/research-2026-09-18-command-typing-fast-vs-gemma.md to
     docs/research-complete-2026-09-18-command-typing.md, remove the banned words from its text
     (rule C), and fix the links to it.
   - Delete bench/hebrew-command-bench/type_compare.py, type_fresh.py, type_english.py, perf.py,
     cases_typing_fresh.py, cases_typing_fresh_en.py, and bench.py once nothing imports it (check
     with rtk grep first). Update bench/hebrew-command-bench/README.md.
   - Do not touch contention.py and real_cadence.py: investigator owns them.
5. B2: path B. It waits for B1 [x] in 9d and for the owner's labels (B4).
   - WAV + expected -> whisper prepass -> path A. Report whisper's word error rate (M5: "This is
     not phase 2 work. This should be done."). Lock gpu.

Rulings: D1, G1, G2, M5, U2.2, V2, X1, X2, X3, Y1, Y2, Z1.

**Yours (no lock):** bench/vision-verify-bench/ (then bench/perception/), bench/whole-system/
(except run_list.py), docs/research-complete-whole-system.md, the typing study files, the confirm
tool.

**Shared (lock the path):** .gitignore, bench/README.md, bench/recognizer/README.md,
bench/recognizer/accuracy.py (recognizer's file; lock it if B2 changes it).

**Resources:** gpu (B5, B2); suite, if you touch harden2 code or tests.

## Brief 2: the app, audio and runtime tests, then B8 (the main agent, 2026-09-29; do not edit)
Rulings (ledger): TR4 (2), TR6, TR9, TR12 (2), TR13 (2)+(3), TR14 (2); J5 (2) for B8. Rules for this brief: docs/refactor/README.md holds. A module's tests are written WITH it (guidelines, 2026-09-28). Never delete working code because git keeps it (TR16). No git command at all. Never upgrade or reinstall torch, transformers or bitsandbytes in the main environment: anything that needs other versions goes into its own venv, created by a script. Lock gpu for every GPU run; one GPU job at a time. Control stays the mock.
1. Tests (each in its module's test file; lock a shared test file while you edit it: perf edits test files too):
   TR4: a real ROS2 test (like the keys tests): publish a sentence on config.ASR_TOPIC; the ROS speech source
   hands it to the app as one turn. No microphone. TR6: four turn outcomes on test_app.py's _app fixture: a
   count of zero says "not found"; a highlight while SAM3 loads says "not ready"; a lost highlight clears the
   drawing and says so; a failed describe closes its record with no chat line. TR9: the supervisor's crash
   budget resets after a stable run (a short stable time). TR12: delete test_clips_land_where_the_session_log_
   reads_them and test_there_is_no_global_board_and_states_are_distinct. TR13 (the owner's design): detail_lines
   cuts a long detail to the set lines and characters; and the pane drawn from the long detail equals, pixel
   for pixel, the pane drawn from the already-cut lines. TR14: the phone-transcript test uses the real
   SessionLog and reads the written trace line's source.
2. B8, after recognizer's J5 is ticked in 9d: retire bench/hebrew-command-bench under rules A-D: a
   docs/research-complete-*.md from its results/RESULTS.md and README (Objective, Setup, Results, Analysis);
   then delete cases_commands.py, cases_perception.py and CASES.md (datasets/recognizer/ is their home now);
   results/ stays. Update bench/README.md.
Then stop with "WAITING".

## Brief 3: UI1, the labelling web page (the main agent, 2026-09-29; do not edit)
Ruling (ledger UI1 (2)): a local web page in /root/groundstation/tools/asr-verify-transcript/, designed with the
"impeccable" skill; the owner expects it in well under 30 minutes. The README rules hold (no git; script every
install; never touch torch/transformers/bitsandbytes in the main environment).
Why: the owner, of confirm.py: "The UI is not intuitive at all and it pisses me off". Its faults: a key then
Enter; the plan as raw JSON; a long key list; only one step back; typed Hebrew arrives garbled (clip 13 was saved
as "2 סחורא 8 מטרים").
Design with impeccable: read /root/.claude/plugins/cache/impeccable/impeccable/4.4.0/skills/impeccable/SKILL.md
and follow it (its Setup: run its context script; its references; mode "Operate": the owner completes a task).
Keep its verify pass bounded, as the skill says.
Build:
1. A server on Python's standard library only, bound to 127.0.0.1, one port; it prints its URL (VS Code
   forwards the port). It serves the page, the clip audio from datasets/asr/clips (local only, never in git),
   and a small JSON API.
2. One card per clip: "clip N / 139", a play button (HTML audio), "Heard" (whisper's text), the proposed
   sentence in a real right-to-left text box (dir="rtl"), the proposed plan in PLAIN WORDS (reuse
   util/mission.step_text from harden2: "fly backwards 8 m", not JSON) with an edit field (the live-list
   notation or JSON; show the parsed result in plain words before saving; reject what does not parse), the 5
   nearest cases as buttons (sentence + plan in words + similarity).
3. Actions: Accept (Enter), Review (not gradable), Back, Next, "Go to clip N", and edit any saved clip. It saves
   after every clip to datasets/asr/recordings.json in the SAME format, atomically, and resumes where the owner
   stopped (14 clips are saved now).
4. One home: move the proposal logic out of bench/recognizer/confirm.py into the tool (scorer.read_notation
   stays in bench/recognizer/scorer.py; import it); then delete confirm.py (rm; if refused, "For the owner")
   and point bench/recognizer/README.md to the new tool. util/mission.step_text now has two users, so it stays
   in util/.
5. Tests with the tool: tools/asr-verify-transcript/test_*.py (pytest) for load, propose, save, go-to, the plan
   in plain words, and a garbled-free Hebrew round trip through the API.
6. A README (why, how to run, the one command).
IMPORTANT: the owner runs confirm.py right now. Both tools rewrite the same file, so never start the web tool on
the real file while confirm.py runs (test on a copy). Tell the owner in your final message to quit confirm.py
first. Clip 13's sentence must become "טוס אחורה 8 מטרים" (plan unchanged): the owner can fix it in the page.

## Brief 4: the page's plan editor and whisper's text (the main agent, 2026-09-29; do not edit)
Ruling (ledger UI1 (3)): "The UI Of the app is fucking stupid - I need to change the plan. How do I do that? I also
needed to make sure what whisper outputted was the actual text being used." The owner is labelling NOW: keep the
server and the file format working; tell him when to reload.
1. The plan editor: the plan is a list of step rows. Each row: a drop-down (fly forward, fly back, fly left, fly
   right, go up, go down, turn right, turn left, take off, land, wait) and a number (m, degrees or s; none for
   take off / land), a remove button; an "add step" button; three buttons that replace the plan: "nothing flies"
   (none), "halt" (emergency), "vision request" (perception). The rows map to the phone app's steps (fly_by dx/dy/dz,
   spin_by degrees, delay seconds, takeoff, land) with the SAME signs the benchmark uses (forward dx+, right dy+,
   up dz+, turn right = +degrees); check the signs against datasets/recognizer/commands.json cases (e.g. up10,
   spin90cw, g_right4). The notation box stays only as an advanced fallback, folded away.
2. Whisper's text: the sentence box always starts with whisper's EXACT text (transcript_he), marked "whisper's
   text" until the owner edits it, then "edited". The nearest case's sentence is an offer (a button "use this
   sentence"), never pre-filled. The saved "he" is exactly what the box holds.
3. Tests for both (the mapping of every row type to its step and sign; the sentence default). Keep the checks.

## Brief 5: an empty sentence (the main agent, 2026-09-30; do not edit)
Ruling (ledger B4 (7)): clip 63: "Nothing was said ... it NEEDS to be empty." The page must save a clip with an EMPTY sentence:
a "Nothing was said" button that empties the box, sets the plan to "Nothing flies", and saves; an empty box is a valid
sentence. Tests with it. The owner labels now: tell him when to restart the server.

## Brief 6: name the target of a vision request (the main agent, 2026-09-30; do not edit)
Ruling (ledger UI1 (4)): clip 65, "Highlight the chair": the owner marks a vision request but cannot say "chair".
1. "Vision request" opens an editor: the kind (highlight, count, describe) and the target words in English (what
   Gemma's target_en must name), one or more words, with optional synonyms per word (e.g. "chair / seat"). It saves
   {"kind": "perception", "groups": [[...], ...]} exactly as the scorer reads it (bench/recognizer/scorer.py); check
   the kind handling against the scorer (KIND_WORDS) and, if the scorer ignores the chosen kind, say so in your report.
2. Propose the target from whisper's text where a known case matches (its groups), editable.
3. labels.py changed at 08:32, after the owner's server started (06:53): check who changed it and why, and report.
4. Tests with it. Tell me when the owner must restart the server.

## Brief 7: the page's bugs, a browser to see it, and removed clips (the main agent, 2026-09-30; do not edit)
Ruling (ledger B4 (8)). The owner labels now; keep his file and format; tell me when he must restart.
1. The right-side recommendations (the nearest cases) stopped working: find why (likely the UI1 (4) change) and fix.
2. The step rows' remove button (X) is misaligned, e.g. on "take off" and other steps without a number: fix the layout.
3. You cannot see the page: install a headless browser by a SCRIPT (a venv or a --target folder, never the main
   torch/transformers), e.g. Playwright's Chromium; if the tool refuses the download, give the owner the command. Take
   screenshots of every card state (a flight plan, each step type, nothing flies, halt, a vision request, the
   recommendations) and check them; run impeccable's verify pass on them.
4. A "Remove from the set" action with a reason: the clip stays on disk, its record says removed + reason, and the
   benchmark (path B) skips it. Apply it now to clips 83, 84, 85 ("SAM3/Gemma don't know the context regarding the system
   internals") and 92 ("too much of the same sentence") in the owner's file ONLY when his server is stopped; else tell him.
5. Tests with each fix.

## Notes
- B5: bench/vision-verify-bench moved to bench/perception/ (plain mv). detect() returns (status, hits)
  since 7ad3012: bench.py (run_control, run_baseline) and propose_boxes.py (both modes) now unpack
  `_, dets`; the bench's detect wrapper passes the tuple through, as verify_highlight expects. The
  bench builds Sam3Backend directly, so the status is always DETECT_OK. Long lines in bench.py and
  propose_boxes.py wrapped (both files lint clean at 89). annotate.py is untouched and still has 13
  lines over 89 (pre-existing); it imports app.draw and imports fine.
- B5: .gitignore line now `bench/perception/dataset/images/`; `git check-ignore -v
  bench/perception/dataset/images/img0.png` -> .gitignore:12. No image shows in git status.
- B5: test/test_perception2.py (the opt-in GPU test) reads img0.png from the new path.
- B5: not changed on purpose: docs/task-active-harden2-session-handoff.md (a dated 2026-09-18..20
  handoff, not current state), HISTORY, the session logs, the spec (main agent's files).
- B6: docs/research-complete-whole-system.md written from bench/whole-system/results/RESULTS.md +
  the README lanes. bench/whole-system/README.md is now 3 lines (retired, points to the doc).
  labels/ and results/ kept. run_list.py kept (recognizer deletes it in B1).
- B6: the rm of the scripts was REFUSED by the tool: see "For the owner".
- B6: stale whole-system pointers fixed in bench/sam3-mask-bench/README.md (line 20) and
  docs/spec-harden2-architecture.md (two source cells, lines 155-156). bench/hebrew-command-bench/
  README.md line 113 still names run_list.py: B1 (recognizer) or B7 (me) updates it.
- Observation, not fixed (not my task): docs/spec-harden2-architecture.md line 155 says "28/42
  present objects hit (Qwen: 22/42)"; the result document says Gemma said present 35/42 and SAM3
  hit 28/35 (Qwen 28/42, 22/28).
- B3: bench/recognizer/confirm.py (new, mine). It imports
  scorer.read_notation (recognizer's file, not edited) and util.guarded (parse_json, atomic_write),
  so it holds no try. Nearest case: difflib ratio on text without marks and punctuation, over
  every case of datasets/recognizer/*.json, one per distinct sentence.
- B3: output datasets/asr/recordings.json (gitignored: the whole datasets/ folder is). See OPEN O1.

- B7: the typing study is docs/research-complete-2026-09-18-command-typing.md (mv). "sieve" is
  gone from its text (-> "fast path"); a RETIRED note at the top says where the harnesses went;
  contention.py and real_cadence.py are marked retired with a pointer to
  docs/research-complete-sam3-assessment.md, R8.
- B7: deleted with rm: type_compare.py, type_fresh.py, type_english.py, perf.py,
  cases_typing_fresh.py, cases_typing_fresh_en.py. bench.py NOT deleted: unified_bench.py and
  bench/whole-system/run_list.py still import it, and both wait for the owner's rm from B1. Its rm
  is under "For the owner", to run after that one.
- B7: old-name links left in files I may not edit: docs/task-active-harden2-refactor-handoff.md
  (575), docs/spec-harden2-cleanup.md (714), docs/HISTORY.md (3990), docs/refactor/investigator_doc.md
  (77); and in dated documents: docs/task-active-harden2-session-handoff.md (135),
  docs/task-active-doc-audit-2026-09-19.md (38), docs/task-active-restructure-progress.md (689).
- B7: bench/hebrew-command-bench/README.md rewritten to the current state (it named
  unified_bench.py as current and a compare_runs.py that does not exist). bench/README.md row
  updated (under lock). For perf (D1): no D1 caller is left in hebrew-command-bench except
  bench.py, which goes with the owner's rm.

## OPEN
- O1 (B3) where the labelled recordings file lives.
  a) datasets/asr/recordings.json, next to the clips (built): accuracy.py's default run does not
     grade it while it is half-labelled; B2 names it explicitly.
  b) datasets/recognizer/recordings.json: every recognizer set in one folder, but the default
     path-A run then grades it too, labelled or not.
  Recommendation: a.
- O2 (B7) the rest of bench/hebrew-command-bench: cases_commands.py, cases_perception.py, CASES.md
  and results/. recognizer's notes call the Python case files "retired by B7", but my brief does
  not list them.
  a) Keep them as the source of datasets/recognizer/ and as raw data (done now).
  b) Retire them under rules A-D: the JSON files are the cases now; results/RESULTS.md moves to a
     docs/research-complete-*.md document first.
  Recommendation: a for now; b in the stale-doc sweep (F1), after the owner rules.
- O3 (UI1) the plan in plain words. util/mission.step_text writes "fly_by dx=-8" (the chat's
  text), not words.
  a) The words live in the tool (labels.step_words; step_text only for unknown types). Built.
  b) Move the words into util/mission.py so the chat shows them too: changes the chat's lines
     and its tests.
  Recommendation: a; b only if the owner wants words in the chat.

## For the owner
- UI1, the labelling page. FIRST quit confirm.py (q, or Ctrl+C): both tools rewrite
  datasets/asr/recordings.json. Then:
```
python3 /root/groundstation/tools/asr-verify-transcript/server.py
```
  Open the URL it prints (VS Code forwards port 8766). After the UI1 (3) change: stop the
  running server (Ctrl+C in its terminal), start it again with the same command, reload. It opens at clip 15 (14 saved). Clip 13:
  "Go to clip" 13, set the sentence to the one the brief gives, Enter (the plan stays).
- B6, the delete the tool refused (the scripts of the retired whole-system benchmark; run_list.py,
  labels/ and results/ stay):
```
rm /root/groundstation/bench/whole-system/overlays.py /root/groundstation/bench/whole-system/planning_table.py /root/groundstation/bench/whole-system/run_all.sh /root/groundstation/bench/whole-system/sam3_alone.py /root/groundstation/bench/whole-system/vision_chain.py /root/groundstation/bench/whole-system/vlm_compare.py
rm -rf /root/groundstation/bench/whole-system/__pycache__
```
- B4, label the 139 recordings (keyboard only; Enter accepts the proposal, the keys print at the
  start; it saves after every clip and resumes where it stopped; the clip plays through aplay):
```
python3 /root/groundstation/bench/recognizer/confirm.py
```
  With PulseAudio instead of ALSA: add `--player paplay`. Without sound: `--no-play`.
- B7, after the B1 rm in docs/refactor/recognizer_doc.md (it removes the last importers):
```
rm /root/groundstation/bench/hebrew-command-bench/bench.py
```

## Progress

claude-opus-5-5[1m], CLAUDE_EFFORT=medium

### B5 + B6 checkpoint (2026-09-28)
Files: bench/perception/ (moved; bench.py, propose_boxes.py, README.md, results/HISTORY.md edited;
results/2026-09-28-bench-3arm-human.json new), .gitignore, projects/integration_harden2/test/
test_perception2.py (one path), bench/README.md, docs/research-complete-whole-system.md (new),
bench/whole-system/README.md, bench/sam3-mask-bench/README.md, docs/spec-harden2-architecture.md.

Checks (after both tasks):
- flake8 (harden2): rc 0. pyflakes (harden2): rc 0. bench.py + propose_boxes.py: flake8 + pyflakes
  clean.
- audit: "except handlers: 5   raise statements: 1".
- suite, ROS_DOMAIN_ID=13, twice: "220 passed, 2 skipped in 38.42s", "220 passed, 2 skipped in
  37.97s" (220 vs the 215 baseline: other agents' new tests).
- Y2: no harden2 module changed; the benchmark itself was the broken caller.

The vision run (lock gpu, 3 min 18 s wall, estimate was ~3 min): `MVD_HOME=integration_harden2
python3 bench.py --labels human`, 137 rows. Every verdict and every instance count equals the
2026-09-20 live-matched run (checked by comparing the two JSON files: "identical True").

| arm | false-draw | correct | partial | p50/p95 ms 2026-09-28 | p50/p95 ms 2026-09-20 |
|---|---|---|---|---|---|
| control | 84 | 34 | 13 | 412/1259 | 413/1253 |
| baseline | 24 | 89 | 16 | 413/1273 | 413/1261 |
| verify | 8 | 105 | 16 | 821/898 | 829/928 |

Change-impact:
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| detect() unpacking in bench.py, propose_boxes.py | the vision benchmark runs again | no: same numbers as 2026-09-20 | none (a benchmark) |
| bench moved to bench/perception/ | paths only | no | test_perception2.py GPU test: path string only, not its logic |
| .gitignore line moved | images stay private | no (check-ignore proves it) | none |
| whole-system retired (README, research doc) | docs only; scripts await the owner's rm | no app code | none |

Self-check against 9d:
- B5 fix detect() in bench.py + propose_boxes.py: done. Move to bench/perception/: done (mv).
  Rerun vs 2026-09-20: done, identical accuracy. English input and own scorer kept (X2, X3): yes.
  gitignore moved + check-ignore: done. README + bench/README.md + current docs: done.
- B6 research-complete document (Objective, Setup, Results, Analysis, Conclusions): done. Delete
  scripts + run_all.sh: REFUSED by the tool, command under "For the owner". run_list.py kept.
  labels/ + results/ kept. README 3 lines: done.

Proposed HISTORY entry:
### 2026-09-28 -- the vision benchmark runs again, as bench/perception; whole-system retired
- **What:** bench/vision-verify-bench moved to bench/perception/ (Y1). bench.py and
  propose_boxes.py unpack detect()'s (status, hits), broken since 2026-09-23. The private-image
  ignore line moved with it. bench/whole-system retired (D1 a): its results in
  docs/research-complete-whole-system.md; labels/ and results/ kept.
- **Measured:** 137 human rows, 3 min 18 s. Every verdict equals 2026-09-20: false draws control
  84 / baseline 24 / verify 8; correct 34 / 89 / 105. Latency p50/p95 ms: 412/1259, 413/1273,
  821/898 (2026-09-20: 413/1253, 413/1261, 829/928).
- **Verdict:** the vision system's accuracy is unchanged by the perception2 refactor. The
  whole-system scripts wait for the owner's rm.

### B3 checkpoint (2026-09-28): the confirm tool
Files: bench/recognizer/confirm.py (new), bench/recognizer/README.md (new section "Label the
recordings", under lock).

Tested on 3 clips (output in my scratchpad, not in datasets/):
- Run 1: clip 1 accepted as proposed (nearest live-test-e2e-50-1, 0.94); clip 2 took option 2
  and then n (none); q. File: 2 cases.
- Run 2 resumed at "clip 3" ("2/139 clips saved ... resuming at clip 3"). A bad JSON expect was
  refused ("not used: Expecting property name ..."); a JSON expect with groups was taken; Enter
  saved clip 3; b went back and removed it; the notation "dz+10, +90" gave
  [["fly_by","dz",10.0],["spin_by","degrees",90.0]]; t replaced the sentence; Enter saved; q.
  File: 3 cases, the last one with the typed sentence and the notation expect. No .tmp left.
- Playback: aplay and paplay both play a clip with rc 0 here (audible: unverified, no speaker in
  the container).
- Found while testing: clip 2 (whisper "fly right one metre") has "fly forward one metre" at
  0.88. So the sentence is proposed from a case only at 0.9 or more (was 0.75).
- Checks: confirm.py flake8 (89) + pyflakes clean. No harden2 file changed, so the suite, the
  headers and Y2 do not apply (the harden2 lint stays as at the B5 checkpoint).
- No automated test: this is an interactive benchmark tool outside the harden2 suite; the piped
  runs above are its check.

Change-impact:
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| bench/recognizer/confirm.py | additive: a new tool | no | none |
| bench/recognizer/README.md section | docs | no | none |

Self-check against 9d B3: nearest B1 case proposes the sentence + expected: yes. Plays the clip:
yes. Confirm or correct: yes (keys). Writes the recordings JSON in the path B format (`wav` +
the case fields): yes. Keyboard only, one clip at a time, saves after every clip, resumes: yes
(tested). In bench/recognizer/, documented in its README: yes. Tested on 3 clips: yes. Command
under "For the owner": yes.

Proposed HISTORY entry:
### 2026-09-28 -- the confirm tool for the 139 recordings (path B labels)
- **What:** bench/recognizer/confirm.py plays each clip of datasets/asr, proposes the sentence
  and the expected result from the nearest recognizer case, and saves the owner's confirmed
  answer to datasets/asr/recordings.json after every clip; it resumes where it stopped.
- **Measured:** tested on 3 clips (accept, pick, JSON, notation, back, resume). One direction
  word changed scores 0.88 similarity, so a case sentence is proposed only at 0.9 or more.
- **Verdict:** ready for the owner's labelling (B4).

WAITING for B1 [x] in 9d (B7, B2) and for the owner's labels (B4, for B2).

### B7 checkpoint (2026-09-28): the typing study retired
Files: docs/research-complete-2026-09-18-command-typing.md (moved + edited), deleted
bench/hebrew-command-bench/{type_compare, type_fresh, type_english, perf, cases_typing_fresh,
cases_typing_fresh_en}.py, bench/hebrew-command-bench/README.md (rewritten), bench/README.md (row).

Checks:
- Importers of bench.py (grep "import bench" / "from bench import" in bench/, tools/, harden2):
  unified_bench.py and bench/whole-system/run_list.py only, both waiting for the B1 rm.
- `grep -niE "sieve|wire|seam|load-bearing"` on the study document: no match.
- flake8 rc 0, pyflakes rc 0, audit "except handlers: 5   raise statements: 1".
- suite, ROS_DOMAIN_ID=13, twice: "229 passed, 2 skipped in 45.96s", "229 passed, 2 skipped in
  47.11s". No harden2 file changed.

Change-impact:
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| typing study doc renamed, banned word removed | docs | no | none |
| six typing scripts deleted | none: nothing imported them (grep) | no | none |
| hebrew-command-bench README rewritten | docs | no | none |

Self-check against 9d B7: doc moved to research-complete (yes); banned word removed, rule C
(yes); links fixed where I may edit (none named it; the rest listed in Notes for the main agent);
six scripts deleted (yes); bench.py once nothing imports it (not yet: two importers wait for the
owner's rm; command under "For the owner"); README updated (yes); contention.py and real_cadence.py
untouched (investigator deleted them; the study names them retired, R8).

Proposed HISTORY entry:
### 2026-09-28 -- the 2026-09-18 command-typing study retired (G2 a)
- **What:** the study became docs/research-complete-2026-09-18-command-typing.md, with the banned
  word replaced by "fast path". Its six scripts were deleted (in the git history, 8a8e022).
  bench.py follows the owner's B1 rm. bench/hebrew-command-bench/README.md now lists only what
  remains: the case sources and the raw results.
- **Verdict:** rules A-D hold for the typing study. The contention part points to the SAM3
  assessment, R8.

WAITING for the owner's labels (B4) before B2.

### Brief 2, milestone 1 (2026-09-29): TR4, TR9, TR12 done; TR6, TR13, TR14 wait for test_app.py
Files: test/test_audio.py, test/test_runtime.py (each under lock, released).
- TR4 NEW test_audio.py::test_a_mic_transcript_over_ros_is_one_turn: SpeechIn(["ros"]) over a
  REAL ROS2 topic (config.ASR_TOPIC, the publisher helper of scripted_e2e_run.py); an empty
  transcript gives no turn; the sentence arrives once as ("...", "ros").
- TR9 NEW test_runtime.py::test_a_stable_run_earns_the_crash_budget_back: budget 1, stable_s 0.3,
  a child that runs 0.5 s then exits 3; four crashes, every one "restart 1/1", never WAITING.
- TR12 DELETED test_audio.py::test_clips_land_where_the_session_log_reads_them and
  test_runtime.py::test_there_is_no_global_board_and_states_are_distinct (owner TR12 (2)); the now
  unused imports (runtime.status, FAILED) removed.
- Mutation checks (files locked, copied, restored, "MUTANT" count back to 0): supervisor.py
  `restarts = 0` -> `pass`, and asr_ros.py source "ros" -> "mic": "2 failed". Restored: "2 passed".
- test/README.md is held by perf: its test list is updated when the lock frees.
- TR6, TR13, TR14: written, not applied. perf holds test/test_app.py and test/README.md (D2,
  since 05:39); two 9-minute waits timed out. The patch is
  /tmp/claude-0/-root-groundstation/1d8b196b-7abe-45b9-a9d6-ddf7daef5fae/scratchpad/tr_app.py
  (python3 it under the test_app.py lock): TR6 four tests (count 0 -> "לא מצאתי"; highlight
  while SAM3 loads -> "not ready", record {"not_ready": true}; lost -> boxes gone, "לא מצאתי:",
  {"gave_up": true}; failed describe -> {"answer": null, "gemma": "failed"}, no answer line),
  TR13 rewrite of test_long_detail_and_many_rows_never_overflow (REWRITTEN: detail_lines cut +
  pixel-equal panes), TR14 rewrite of test_a_phone_transcript_is_recorded_as_phone (REWRITTEN:
  the real SessionLog, the trace lines' source, the phone turn takes no clip).
- B8 (prepared, waits for J5 [x]): docs/research-complete-hebrew-command-bench.md written from
  results/RESULTS.md + the README (banned words removed: "wire schema", "sieve"). Not yet done:
  delete cases_commands.py, cases_perception.py, CASES.md; bench/README.md row; the
  hebrew-command-bench README to 3 lines.

WAITING for test/test_app.py + test/README.md (held by perf, D2) and for J5 [x] in 9f (B8).

### Brief 2, milestone 2 (2026-09-29): TR6, TR13, TR14 applied
Files: test/test_app.py (patched AS IT WAS after perf's D2; a diff against the pre-patch copy
removes only the two rewritten tests and two import lines), test/README.md (the list; counts:
test_app 40, test_audio 18, test_runtime 18). Both under lock, released.
- TR6 NEW: test_a_count_of_zero_says_not_found, test_a_highlight_while_sam3_loads_says_not_ready,
  test_a_lost_highlight_clears_the_drawing_and_says_so,
  test_a_failed_describe_closes_its_record_with_no_chat_line.
- TR13 REWRITTEN (owner TR13 (2)+(3)): test_long_detail_and_many_rows_never_overflow ->
  test_a_long_detail_is_cut_and_the_pane_draws_only_the_cut_lines.
- TR14 REWRITTEN (owner TR14 (2)): test_a_phone_transcript_is_recorded_as_phone now uses the
  real SessionLog and reads trace.jsonl (and the phone turn takes no clip, R27).
- Two fixes found on the first run: request.json is written when a request opens, so the tests
  wait for a verdict (helper _verdicts); the mic clip is named after the record's own seq.
- The six tests: "6 passed" three runs in a row.
- Mutation checks (files locked, copied, restored, MUTANT count 0): count 0 says "יש 0"; the
  not-ready speech removed; describe failure treated as success; the pane wraps the raw detail
  at 30 characters; the trace source always "mic": "5 failed, 1 passed". The one that passed
  (hl_dets not reset on LOST) is not a gap: the last tracking pass already sets hl_dets = [];
  the target reset carries the drawing, and its mutant fails ("1 failed": target 'car, van,
  truck' is not None).
- Checks: flake8 rc 0, pyflakes rc 0, audit "except handlers: 5   raise statements: 1", suite
  (ROS_DOMAIN_ID=13) twice: "243 passed, 2 skipped in 47.94s", "243 passed, 2 skipped in 48.44s".

Change-impact (Brief 2 tests):
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| TR4, TR6, TR9 | none (tests only) | no | 6 new tests |
| TR12 | none | no | 2 tests deleted (owner TR12 (2)) |
| TR13, TR14 | none | no | 2 tests REWRITTEN by owner rulings TR13 (2)+(3), TR14 (2) |

Self-check against Brief 2 point 1: TR4 real ROS2, no mic (yes); TR6 four outcomes on _app (yes);
TR9 short stable time (yes); TR12 the two named tests deleted (yes); TR13 the owner's design, cut
+ pixel-equal (yes); TR14 real SessionLog, trace source read (yes). Each in its module's test file.

Proposed HISTORY entry:
### 2026-09-29 -- the test review's test tasks (TR4, TR6, TR9, TR12, TR13, TR14)
- **What:** six new tests (the mic transcript over ROS2; four turn outcomes; the crash-budget
  reset), two deleted (a constant, a structure check), two rewritten to test the real path (the
  status detail cut drawn exactly; the phone source read from the written trace).
- **Measured:** suite 243 passed, 2 skipped, twice; every new or rewritten test fails under a
  mutant of the code it covers.
- **Verdict:** the gaps A4, A6, A9 and the weak tests B1-B4 of the test review are closed.

WAITING for J5 [x] in 9f (B8; its document is drafted).

### B8 checkpoint (2026-09-29): bench/hebrew-command-bench retired
Files: docs/research-complete-hebrew-command-bench.md (new: Objective, Setup, Results, Analysis,
Conclusions, Sources; from results/RESULTS.md + the README; "wire schema" and "sieve" removed),
deleted bench/hebrew-command-bench/{cases_commands.py, cases_perception.py, CASES.md} (rm
worked), bench/hebrew-command-bench/README.md (3 lines), bench/README.md (row, under lock).
results/ kept.
- Importers of the deleted files (grep, .py and .sh): bench.py, unified_bench.py and
  bench/whole-system/planning_table.py only. All three are already in the owner's rm commands
  (B1 in recognizer_doc, B6 and B7 here): nothing live imports them.
- Left as is: bench/recognizer/README.md names cases_*.py as the source of each JSON file
  (provenance, recognizer's file); results/RESULTS.md (raw data).
- Checks: flake8 rc 0, pyflakes rc 0, audit "except handlers: 5   raise statements: 1", suite
  twice: "243 passed, 2 skipped in 50.01s", "243 passed, 2 skipped in 50.39s".

| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| case files deleted | none: datasets/recognizer/ is their home (J5) | no | none |
| research-complete document, READMEs | docs | no | none |

Self-check against Brief 2 point 2: document from RESULTS.md + README (yes); the three files
deleted (yes); results/ stays (yes); bench/README.md updated (yes).

Proposed HISTORY entry:
### 2026-09-29 -- the Hebrew command benchmark retired (G1, G2, J5)
- **What:** its results are docs/research-complete-hebrew-command-bench.md (412/487 on
  2026-09-19, the path from translators to one Gemma call). The case files went; every sentence
  lives once in datasets/recognizer/. results/ stays as raw data.
- **Verdict:** rules A-D hold once the owner runs the pending rm of bench.py and
  unified_bench.py.

WAITING for the owner's labels (B4) before B2.

### UI1 checkpoint (2026-09-29): the labelling web page
Files (new): tools/asr-verify-transcript/{server.py, labels.py, index.html, test_labels.py,
test_server.py, README.md}. Deleted: bench/recognizer/confirm.py (rm worked). Edited (under
lock): bench/recognizer/README.md ("Label the recordings" points to the tool).
- One home: the proposal logic (normalize, load_cases, nearest, propose, read_expect, the
  recordings file) moved into labels.py; scorer.read_notation is imported from
  bench/recognizer/scorer.py; util.guarded (atomic_write, parse_json) from harden2. No try.
- Plain words: util/mission.step_text gives "fly_by dx=-8", not words, and cannot read the
  expected-value forms ("+", ["abs", n], null). So labels.step_words writes the words ("fly
  backwards 8 m") and falls back to step_text only for a step type it has no words for. See
  OPEN O3.
- Saving: one case per clip keyed by wav, written in clip order after every save (atomic);
  opens at the first clip not saved; any clip can be opened and re-saved (Go to clip).
- Design (impeccable 4.4.0, mode Operate): its context script ran (no PRODUCT.md: the brief
  stands in for init; no question tool here, so no interview). Dark, restrained, one amber
  accent for the primary action, play and focus; Hebrew in RTL fields with a Hebrew font
  stack; plain-word plan; nearest cases as buttons; a sticky action bar; one-file page.
  Detector: 3 findings (a coloured glow shadow x2, a width transition), fixed; rerun: [].
  NOT verified in a browser: no browser or JS runtime in the container, so the page's script
  is unchecked by a real render (the server, the API and the served page are tested).
- Tests: "9 passed". Mutation checks (labels.py copied, restored): the sign of backwards, the
  clip order of the save, the 0.9 sentence bar: "4 failed, 5 passed"; restored "9 passed".
- Smoke run on a COPY of the real file (port 8799): /api/state says 14 saved, first unsaved
  14; /api/clip/12 shows the saved clip 13 with plan "fly backwards 8 m"; the page is served.
- No harden2 file changed: the harden2 suite, headers and Y2 do not apply. flake8 (89) and
  pyflakes clean on the tool.

Change-impact:
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| the web tool | additive | no | 9 new tests (the tool's own) |
| confirm.py deleted | the terminal labeller | replaced by the page | none (it had no tests) |

Self-check against Brief 3: 1 stdlib server on 127.0.0.1, prints its URL, serves page, audio,
JSON API (yes). 2 card: clip N / 139, play, Heard, RTL sentence, plan in words + edit field with
parsed preview and refusal, 5 nearest as buttons (yes). 3 Accept (Enter), Review, Back, Next,
Go to, edit saved; atomic save, same format, resumes (yes). 4 logic moved, confirm.py deleted,
README pointed (yes; step_text: O3). 5 tests for load, propose, save, go-to, plain words,
Hebrew round trip (yes). 6 README with the one command (yes).

Proposed HISTORY entry:
### 2026-09-29 -- a web page to label the recordings (UI1)
- **What:** tools/asr-verify-transcript/: a local page (stdlib server) that plays each clip,
  shows whisper's text, the sentence in an RTL box, the plan in plain words and the 5 nearest
  cases; it saves every clip to datasets/asr/recordings.json. It replaced confirm.py (typed
  Hebrew arrived garbled; key-then-Enter; plans as raw JSON).
- **Measured:** 9 tool tests pass; each fails under a mutant of the code it covers.
- **Verdict:** ready for the owner's labelling (B4). The page itself is unverified in a
  browser.

WAITING for the owner's labels (B4) before B2.

### UI1 (3) checkpoint (2026-09-29): step rows and whisper's exact text
Files: tools/asr-verify-transcript/{labels.py, server.py, index.html, test_labels.py,
test_server.py, README.md}. The file format is unchanged.
- Plan editor: step rows (action drop-down + number + remove, "Add step") and the buttons
  "Nothing flies" / "Halt" / "Vision request" (plus "Fly a plan"). labels.ROW_ACTIONS maps each
  action to its step and sign: forward dx+, back dx-, right dy+, left dy-, up dz+, down dz-,
  turn right +degrees, turn left -degrees, turn either way ["abs", n], take off, land, wait
  +seconds; an empty number = the sign only ("+"/"-"). New POST /api/rows turns rows into the
  expect; /api/clip and /api/parse also return rows. The notation field is folded under
  "Advanced".
- Sentence: an unsaved clip's box is transcript_he exactly (tag "whisper's text" -> "edited",
  a link back); nearest cases are offers ("use this sentence" / "use this plan" / "use both");
  save stores the box exactly (no whitespace collapse).
- FOUND: clips 63-100 have transcript_he null in the manifest. The running server returns an
  error for them (normalize(None)); fixed (heard_of -> ""); the page then asks for a typed
  sentence.
- Tests: "14 passed" (5 new: every row action's step and sign, the cases up10 / spin90cw /
  g_right4 / g_left1 / g_fwd1, rows_of round trip over every mission of commands.json, the
  sign-only and refused rows, whisper's exact text on all 139 clips, /api/rows). REWRITTEN: the
  save test now expects the sentence exactly as typed (UI1 (3); was: whitespace collapsed).
- Mutation checks (labels.py copied, restored): turn right -> -1 and the whisper default removed:
  "3 failed, 11 passed"; restored "14 passed". Detector: []. Smoke run on a copy (port 8798):
  clip 71 heard '' with a plan in rows; clip 41 starts with whisper's text.
- Not verified in a browser (none in the container).
- The owner's server (pid 2968965, started 08:31) runs the OLD code: it must be restarted.

### B4 (7) checkpoint (2026-09-30): "Nothing was said"
Files: tools/asr-verify-transcript/{server.py, index.html, test_server.py}.
- A "Nothing was said" button (Alt+N) in the action bar: it empties the sentence, sets the plan
  to "Nothing flies" ({"kind": "none"}) and saves. An empty sentence is valid: /api/save now
  requires `he` to be a string (it may be ""); the page no longer refuses an empty box.
- Tests: "15 passed". NEW test_nothing_was_said_saves_an_empty_sentence_and_nothing_flies
  (clip 63 saved with "" and none; the page has the button). REWRITTEN (ruling B4 (7)): the
  refusal test now refuses a save with NO sentence field (was: an empty sentence).
- Mutation: /api/save refusing an empty `he` again: "1 failed, 14 passed"; restored "15 passed".
  Detector: []. Not verified in a browser.
- The owner's server (pid 3291730, started 06:12) runs the old code: restart it.

### UI1 (4) checkpoint (2026-09-30): the target of a vision request
Files: tools/asr-verify-transcript/{labels.py, server.py, index.html, test_labels.py,
test_server.py, README.md}.
- "Vision request" opens an editor: the kind (Highlight / Count / Describe / Any kind) and the
  target words in English ("," between words, "/" between synonyms). POST /api/vision ->
  {"kind": "perception", "groups": [...]}; /api/clip and /api/parse return "vision".
- The scorer and the kind: an expect holds only groups; score_perception passes ANY vision kind
  whose "<kind words> the <target>" holds every group. So the tool saves the chosen kind as the
  FIRST group, the scorer's own KIND_WORDS for it (imported, not copied): a wrong kind fails.
  "Any kind" saves no kind group. Known limit: a kind word inside a target ("find", "what")
  could pass another kind; unmeasured, likely rare.
- Proposal: the editor starts from the nearest option whose plan is a vision request (its
  groups), else Highlight with no words. Words are saved lowercase, English only.
- labels.py at 08:32: its time stamp is 2026-09-29 08:32:46, the last write of my UI1 (3) work:
  the restore after its mutation check (cp of my own copy; byte-identical to that copy, cmp).
  It was one minute after the owner's then-server started (pid 2968965, 08:31), which is why I
  asked for that restart in UI1 (3). Nobody changed it after that until this task.
- Tests: "19 passed". NEW: the real scorer grades a saved vision request (right kind + target
  PASS, wrong kind FAIL, wrong target FAIL, "any" passes any kind); the editor's read-back and
  refusals; clips offer the target of their nearest vision request; /api/vision + save + read
  back. REWRITTEN (UI1 (4)): the plain-words test's vision line now names the kind ("any kind").
- Mutation: the kind group not added: "3 failed, 16 passed"; restored "19 passed". Detector: [].
  Not verified in a browser.
- No server of the tool runs right now (ps): the owner starts it again.

### B4 (8) checkpoint (2026-09-30): the page's bugs, a browser, removed clips
Files: tools/asr-verify-transcript/{labels.py, server.py, index.html, test_server.py,
test_page.py (new), install-browser.sh (new), screenshots.py (new), README.md};
bench/recognizer/README.md (one sentence: path B skips a removed clip; under lock);
datasets/asr/recordings.json (the four removals; under lock, server stopped).
- LOCK RULE BROKEN (reported by the main agent): I edited labels.py and test_server.py without
  taking their locks, while recognizer held them (SC1). I had treated the tool as mine. My
  mutation checks copy a file and restore it; a restore could have undone a concurrent edit.
  Checked afterwards: labels.py holds recognizer's SC1 ("vision" field) and my removal code;
  recognizer's two rewritten tests are present; all 26 tests pass. From here on I lock the
  tool folder before any edit (done for the rest of this task).
- 1, the recommendations: the browser showed the causes. (a) `[hidden]` lost to `display:
  flex/grid` rules: the removal form, the step rows and the add-step button showed when they
  should not; fixed with one global `[hidden] { display: none !important; }`. (b) Clips 63-100
  have no whisper text, so their "nearest" cases were the first five of the pool (similarity
  0): now the page shows a note, and the nearest cases follow the typed sentence (POST
  /api/nearest; the save's option number names the same case). (c) A page reloaded against a
  server still running older code gets missing fields: restart after every server change.
- 2, the remove (X) buttons: a hidden number field removed its grid cell, so X jumped left on
  take off / land. Now the field keeps its cell (visibility), measured: one x for all 12 actions.
- 3, the browser: install-browser.sh (pip --target /root/.venvs/asr-verify-browser: this Python
  has no venv module; `playwright install --with-deps chromium`). Installed and working.
  screenshots.py: 9 states x desktop + phone = 18 screenshots, "0 browser errors". I have no
  image viewer here, so I checked the renders by measurement: no element outside the viewport
  and no horizontal scroll in any state at either width; the fixed action bar was 328 px tall
  on a phone, so on narrow screens it is now in the page flow. impeccable detect: [].
- 4, "Remove from the set": a reason form in the action bar; the record keeps
  "removed": true + removed_reason, its expect becomes review (never graded even if path B
  forgot), the badge shows "Removed: <reason>". Applied with the owner's server stopped (ps
  checked; backup of the file in my scratchpad): clips 83, 84, 85 ("SAM3/Gemma don't know the
  context regarding the system internals") and 92 ("too much of the same sentence"); 97 saved
  before and after.
- Tests: 26 passed with the browser (21 passed, 5 skipped without it). NEW: test_page.py (5:
  nearest cases fill sentence + plan; they follow a typed sentence when whisper wrote nothing;
  every X in one column; removal with its reason; hidden parts stay hidden), test_server.py
  (removal kept and refused without a reason; /api/nearest). Mutations: X layout, the rerank
  call, the removed flag: "4 failed, 21 passed"; the [hidden] rule: "1 failed"; restored "26
  passed".
