# bench/recognizer: the recognizer benchmark

It measures the recognizer "as a function of the backend" (owner, 2026-09-27): each sentence goes
through `Recognizer.route()`, the app's own decide step with its guards, and one scorer grades the
decision. route() sends nothing, so no drone, phone or camera is needed; only the planner backend
(Gemma on the GPU) runs.

| section | content |
|---|---|
| Why it exists | what it measures and what it replaced |
| Run it | from start to finish |
| The cases | the JSON files and the expected results |
| The scorer | what counts as right |
| Label the recordings | the web page that labels the 139 clips (path B) |
| Results | the current scorecard |

## Why it exists
- The recognizer decides what a sentence means: a mission, a vision request, a halt or a reject.
  This benchmark grades that decision per sentence, with the number guard and the echo guard in
  place, as the app runs them.
- It replaced two copies of the recognizer's routing (bench/hebrew-command-bench/unified_bench.py
  and bench/whole-system/run_list.py) and a second scorer (log/score.py). A copy of the routing
  hid the guards (2026-09-26); now the benchmark calls route() itself.
- Two input paths (owner, U2.2): path A (sentences, built) and path B (recordings: whisper's text
  first, then path A; task B2, not built).

## Run it
Gemma needs the GPU: take the lock first when other agents run.
```
/root/groundstation/tools/lock.sh acquire <name> gpu
python3 /root/groundstation/bench/recognizer/accuracy.py
/root/groundstation/tools/lock.sh release <name> gpu
```
- No argument: every topical file (below), each sentence once. A file argument runs only that
  file (a topical file or a live list):
  `python3 /root/groundstation/bench/recognizer/accuracy.py /root/groundstation/datasets/recognizer/numbers.json`
- `--list NAME` runs one live list, in its order:
  `python3 /root/groundstation/bench/recognizer/accuracy.py --list live-test-50`
- `--print NAME` prints one live list in order, to read aloud in a live test; no Gemma, no GPU:
  `python3 /root/groundstation/bench/recognizer/accuracy.py --print live-test-50`
- The script starts Gemma the way the app does (the supervisor, gemma.server.process) on port
  18091, and stops it at the end. Start-up takes ~15-60 s.
- `--port P` measures another backend: any llama-server already up on port P.
- `--thinking` starts Gemma with thinking on. `--first N` runs the first N cases of each file.
  `--tag T` names the results.
- Output: a table on the screen; bench/recognizer/results/<date>-<tag>.json (every case: the
  decision, the verdict and the reason) and .md (the table).

## The cases
Every sentence has one home (owner J5, 2026-09-29): the topical file of its kind, in
/root/groundstation/datasets/recognizer/. The expected values were converted as they were
(owner V3); where two copies disagreed, an exact result beat "review" or "open", and the
topical file's keyword groups won.

| topical file | cases | source |
|---|---|---|
| commands.json | 267 | bench/hebrew-command-bench/cases_commands.py CASES, + 15 sentences only the live lists held |
| verbose.json | 63 | cases_commands.py VERBOSE_CASES (generated once) |
| emergency.json | 13 | cases_commands.py EMERGENCY_CASES, + one live-list sentence |
| perception.json | 141 | cases_perception.py PERC100, + 3 live-list sentences |
| military.json | 21 | cases_perception.py SLANG20 |
| numbers.json | 40 | task A2: fractions and the seven front letters |
| ALL | 545 | |

A live list is the order a person speaks in a live test. It holds case names only:

| live list | names | the old spoken list |
|---|---|---|
| live-test-50.json | 54 | live-test-50.md, with its 4 unnumbered bonus lines at the end |
| live-test-75.json | 75 | live-test-75.md |
| live-test-e2e-50.json | 50 | live-test-e2e-50.md |
| live-test-subset.json | 26 | live-test-subset.md |

A topical file: `{"set": ..., "source": ..., "cases": [...]}`. A case: `name` (unique across
every file), `he` (the sentence), `expect`; optional `en`, `note` (a live list's expected
text), `depth`, `class`, `draft` (an expected result the owner has not confirmed; the scorer
ignores it). A live list: `{"list": ..., "source": ..., "cases": [case names]}`. A recordings
file (path B, datasets/asr/recordings.json) adds `wav`, a path relative to /root/groundstation;
a clip the owner took out of the set has `"removed": true` and `removed_reason`, its expect is
review, and path B skips it (owner B4 (8)).

`expect.kind`:
- `mission` + `steps`: exactly these steps, in order. A step is `[type, key, value]` in the phone
  app's names (fly_by dx / dy / dz, spin_by degrees, delay seconds). `key` null: no value
  checked. `value`: a number, null (any), "+" or "-" (the sign), or ["abs", n] (the magnitude).
- `mission` + `alternatives` (instead of `steps`): a list of accepted step lists; a plan that
  matches any one passes.
- `open`: any mission that flies.
- `none`: nothing may fly (a reject, an empty plan, a vision request or a halt passes).
- `emergency`: the fast path halts.
- `perception` + `groups` (+ `vision`): a highlight, count or describe whose "<kind words> the
  <target>" holds one synonym of every keyword group; `groups` [] grades the kind alone.
  `vision` (highlight, count or describe; owner SC1, 2026-09-30) names the one kind that
  passes; without it every vision kind passes. The perception cases, the military ones and 14
  recordings carry a drafted `vision` in their `draft` field until the owner's review.
- `review`: not graded; the live list gives no single expected result.

## The scorer
scorer.py, the one scorer of this benchmark (owner, U2.3 and X3):
- `score(expect, decision) -> (verdict, reason)`: PASS, FAIL or REVIEW. A Gemma failure is always
  a FAIL. Steps compare within 0.01.
- `read_notation(text) -> expect`: the live lists' notation ("dz+10, +90, takeoff, delay 3",
  "EMPTY", "halt", "VLM ..."). It reads a signed number without "deg" as a turn: that notation
  failed two right plans on 2026-09-26.
- Its tests: `python3 -m pytest -q /root/groundstation/bench/recognizer/test_scorer.py`.

## Label the recordings
The expected results of the 139 recorded clips (datasets/asr), the input of path B (owner, Z1 a),
are labelled with a web page: tools/asr-verify-transcript/ (owner UI1, 2026-09-29). It writes
datasets/asr/recordings.json in the recordings format above (`wav`, plus `file` and `case` of the
nearest case and a `note`), after every clip. The file sits next to the clips, so the default run
of accuracy.py does not grade it half-labelled. How to run it: tools/asr-verify-transcript/README.md.

## Results
Scorecard, 2026-09-29, gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf, thinking off: every sentence once
(J5). Source: results/2026-09-29-j5-one-home-gemma4.json.

| set | cases | PASS | FAIL | REVIEW |
|---|---|---|---|---|
| commands | 267 | 247 | 13 | 7 |
| emergency | 13 | 12 | 0 | 1 |
| military | 21 | 0 | 21 | 0 |
| numbers | 40 | 38 | 2 | 0 |
| perception | 141 | 102 | 36 | 3 |
| verbose | 63 | 59 | 4 | 0 |
| ALL | 545 | 458 | 76 | 11 |

route() per case: P50 532 ms, P95 1088 ms, max 2450 ms.

Against the run of 2026-09-28 (a2b, 729 cases with copies), each sentence now counts once. Two
verdicts changed, both by the J5 merge rule (an exact result beats "open"): square (a square of
2 m) now expects nothing to fly and passes; r_dis4 (fly right 2 m and tell me what you see) now
expects nothing to fly and fails, since Gemma flies the 2 m. The 19 sentences only the live
lists held: 8 PASS, 11 REVIEW. The expected results of the military set and of the open cases
are drafts for the owner (J1, J4); they do not count yet.

The runs of 2026-09-28, in order (results/):

| run | what changed | ALL PASS / FAIL / REVIEW | numbers |
|---|---|---|---|
| baseline-gemma4 | nothing (the recognizer before A2) | 592 / 94 / 43 | 29 / 40 |
| a2-numbers-gemma4 | A2, with stage 2 writing a prefixed number as digits ("ב-5") | 601 / 85 / 43 | 37 / 40 |
| a2b-numbers-gemma4 | A2, with stage 2 leaving prefixed number words to Gemma | 602 / 84 / 43 | 38 / 40 |

Analysis:
1. live-test-50: 32 PASS, 0 FAIL, 18 REVIEW. The run of 2026-09-26 (run_list.py) gave 30 / 2 / 18.
   The 2 lines it failed (21, 26) are right plans; the notation "+90" is now read.
2. commands, verbose, perception and emergency matched the scorecard of 2026-09-19
   (240/253, 59/63, 101/138, 12/12) before A2. commands now scores 254 cases: r_wait4 ("hold
   there for ten seconds", with the stop word) halts at the emergency stop. The old run left
   it out; this scorer counts a FAIL.
3. military: 0/21. The keyword groups grade a translation, and the recognizer routes these
   sentences instead; the set does not measure the recognizer. It is kept as converted (V3).
4. numbers, before A2: Gemma planned all 23 sentences with a front letter right, and the number
   guard read none of them, so any distance would have passed. On the fractions the guard
   rejected 9 right plans.
5. numbers, after A2: the guard reads all 40 sentences. 38 pass. The 2 FAILs are Gemma's, both
   on an eighth: one plan (2 and 8 instead of 2.125) is now rejected by the guard, the other
   Gemma rejects itself. Outside the numbers set, one case changed: l75_turn270 (three quarters
   of a turn) now passes.
6. Writing a prefixed number as digits for Gemma gained nothing and cost one case (two steps
   fused into one diagonal step), so stage 2 leaves those words as they are.
