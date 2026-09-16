# Manager handoff — written 2026-09-02 night, for the next session (revised MVD / integration_harden)

Read order for a fresh agent: this file -> docs/active/2026-09-02-state-and-next.md ->
docs/NOTES.md (2026-09-02 section) -> the two component READMEs. CLAUDE.md and memory bind you;
this file explains WHY they say what they say.

## 1. Who you are and how the owner works

You are the manager agent on a 1.5-week interview sprint (interview #2 is the one that counts).
The owner is a senior engineer who audits every reply against their numbered points. Hard-earned
rules, each one paid for in this session:
- Answer EVERY numbered point, by number. Never fuse points. Never skip one silently.
- Recommendations are not decisions. Anything unruled stays OPEN and is listed as such.
- No unverified numbers, ever. Label estimates "unverified". The owner catches fabrication.
- Decisions go into repo docs in the same turn they are made. Chat dies at compaction; docs do not.
- Background output goes to files; chat gets short summaries and FULL tables (never abbreviated
  tables — an abbreviated table next to a full artifact reads as deleted data; that mistake cost trust).
- Lead with disagreement when you have it. The owner explicitly wants a critical pair programmer.
- The owner says "Bruh" when you deserve it. Recover by fixing, not apologizing.

## 2. Output style and writing

- Output style: Plain English (Simplified Technical English), set in ~/.claude/settings.json.
  Short sentences. One idea each. No metaphors, no drama words, no invented vocabulary.
- Terminology discipline: one name per thing, forever. This session fixed: the RECOGNIZER is the
  whole Hebrew pipeline; "the sieve" is only its deterministic stages; "lookup" is dead. When you
  coin a term mid-session it WILL leak into docs and confuse the owner — define once, reuse.
- Result docs: Objective / Setup / Results / Analysis / Conclusions. READMEs: 3-line intro +
  section table + current state only; history goes to results/HISTORY.md. Full rules now in
  docs/writing-style.md. Never append-as-you-go; update in place.

## 3. Safety and process rails (absolute)

- NEVER send arm/takeoff/motor commands to a real drone. Mock (127.0.0.1) only. Human runs
  everything armed. The emergency word is sacred: stage-0 stays greedy by ruling.
- Git: the human owns ALL writes. Never git add -A (it once swept the owner's in-progress CMake
  edits into a commit — incident dcf4a25). You SUGGEST commit blocks; they run them.
- No integration of a component until the owner declares it closed. The Recognizer earned
  integration only after the full 370-sentence measurement.
- Tool lifetime: one-off scripts die after use; superseded lanes get deleted (git history keeps
  them). This repo hates archives of living code.
- Script every install; the devenv wipes ad-hoc installs. AND: only mounted paths survive
  rebuilds — /root/models/{asr,vlm,vision,translate} are mounts; anything else dies. The
  translate models were lost once to this; the install script now refuses non-mounted targets.
- llama-server stderr goes to a log, never DEVNULL — DEVNULL hid a missing-model error for hours.

## 4. Architecture (the system you are building)

Chain: ASR => RECOGNIZER => VLM/LLM => REST API (MSDK server on the phone).
- RECOGNIZER (projects/integration_harden/recognizer/): Hebrew in; {mission | planner English |
  VLM English | spoken rejection} out. Six stages; each exists because a measured failure
  demanded it: digits because עשרים became "ten"; inline English because כתום always became
  "red" and DictaLM copies Latin through; the bypass because 45% of commands are deterministic;
  guards because DictaLM hallucinates numbers and echoes its examples; route() because the
  Recognizer's job is deciding where text goes (movement verb beats perception clause).
  The translator is an INJECTED callable — the component owns no models.
- PERCEPTION (projects/integration_harden/perception/): engine.py = injected-model logic
  (relative-confidence gate, mask hygiene, VLM-box fallback, VLM presence gate — the gate exists
  because open-vocab detectors ground absent phrases onto salient objects). detectors.py owns
  OmDet+Eyes; vlm_client.py owns the Qwen client with testable parse_reply.
- Single-home rule: components live ONLY in integration_harden; the bench imports them in place.
- Remaining unclustered top-level: control (router/commands/dji_wire), audio (ears/phone_ears/
  voice), video (camera_stream/video_doctor/video_watchdog), glue (scene_omdet, config, run
  scripts). Clustering is roadmapped; do NOT do it without a live smoke available.
- Measured GPU topology (8 GiB laptop): Qwen3-VL 3.8 + OmDet 0.9 + SAM2.1 0.7 + wav2vec2-ASR 0.1
  = 5.5 GiB, 2 GiB headroom. Translators run on CPU (DictaLM p50 199 ms). TranslateGemma cannot
  co-reside; deferred to the future E2E ASR system.

## 5. Measurement method (why the numbers are trustworthy)

- Temp 0; determinism proven (10 identical requests -> 1 output); each case runs once; case
  count is the confidence lever. Wilson 95% + exact McNemar for pairs; latency percentiles as
  columns (p25..max). One model on GPU at a time. Estimate duration BEFORE every run.
- Controls always: perfect-English control isolates the planner; reference-scoring control
  calibrates the scorer (it caught nothing only because references must satisfy their own
  groups — bench.py --audit enforces this).
- The development loop is measure -> attribute failures -> amend rules -> re-measure. Every
  sieve rule carries positives AND adversarial negatives; zero false fires is the ship gate.
  E2E accuracy is the only headline metric — token-level scores are diagnostics.
- After ANY refactor, re-run the full measurement and compare counts. This caught a truthiness
  bug (empty mission [] scored as invalid) and four number-parser defects that code review missed.
- Keyword scoring cannot see relation inversion; the dump file review is mandatory for that class.

## 6. Current measured state (2026-09-02 night)

370 sentences, complete Recognizer + planner: emergency 6/6, std-190 98% (planner ceiling,
p50 171 ms, 79 answered by bypass at 0 ms), verbose-54 85% (ceiling; residue planner-side),
perception-100 58% (DictaLM; entity drops at depth>=3 are the unfixable-by-lookup residue),
military-20 55% (out of scope). ALL 301/364. Tests 26/26, both self-tests clean.

## 7. Rulings ledger (owner, all standing)

Revised planner prompt ADOPTED. Model split NOT adopted (VRAM); tgemma deferred to E2E ASR
system. Emergency filter = stage 0 INSIDE the Recognizer, greedy. Routing = the Recognizer's
decision. Unresolved number guard = REJECT + read back what was recognized. TTS inside the
Recognizer = TODO. Direct-Hebrew planning parked (VLM flies anyway). ASR work deferred until
Recognizer alpha. Components single-home. No integration until declared closed. Trace recorder
= the owner's database ask: JSONL per utterance, traces/ gitignored, audio never in git.

## 8. Next objectives (the owner's stated direction: revised MVD in integration_harden)

1. Live desk-loop smoke of the extracted perception package (code checks pass; live video never run).
2. Go-live wiring of the Recognizer: the one-liner in its README + run_dicta_server.sh.
3. Recognizer residue: chain-initial takeoff rewrite; planner "a second after that" delay-shot.
4. Then the ROADMAP tail: clustering, ASR round (gates: 2 scripted installs + team recordings
   per tools/bench/model-cpu-or-gpu/RECORDING-SPEC.md), TTS/backlog D.

## 9. Known agent failure modes this session (do not repeat)

Append-only docs until they rotted; invented vocabulary leaking into docs; abbreviated tables
read as data loss; lasagna code from string-patching one file all day (write files clean or
rewrite them; constants top, main() bottom, intent comments only); claiming a fix worked without
re-measuring (the clockwise-shot claim was wrong); measuring models in a vacuum when the owner
wanted the full pipeline; forgetting the active output style. Every recovery came from the same
move: measure, admit, fix, re-verify.
