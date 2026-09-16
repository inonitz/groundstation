# Full start-to-finish trace + HTML session replayer — workplan (2026-09-12)

Owner-approved design. Goal: every utterance and every SAM3/Gemma pass recorded model-agnostically to
disk, linked, and replayable. Raw frames + metadata (NO burned-in boxes); the replayer draws boxes so the
raw data stays reusable for A/B across architectures + fine-tuning.

## Session layout (final)
    session/
      asr_clips/utt_0003.wav                 # causal-claimed + renamed to the utterance seq (orphans kept)
      trace.jsonl                            # THE single e2e log, one line per utterance (retires utterances.jsonl)
      perception/
        0003-highlight-guitar/               # one dir per perception REQUEST (highlight | count | describe)
          request.json                       # seq, kind, target_en, he2, query, verdict, clip, timings
          pass_00000.jpg + pass_00000.json   # RAW frame + payload (one per FRESH SAM3 forward / Gemma VLM call)
          ...

## trace.jsonl fields (per utterance)
seq, ts, epoch, source, audio_clip, heard_he, he2, flags, kind, target_en, mission, vision_query,
perception_dir (or null), verdict, spoken, action, reject_reason,
timings { recognizer_ms, plan_ms, e2e_ms }.   ASR transcription ms stays in the C++ asr.log (no C++ change).

## Linking (owner-approved, no C++ change, no timestamp math)
CAUSAL CLAIM: the C++ node writes+closes the clip (asr_node.cpp 227-249) BEFORE publishing the transcript
(269). So on transcript arrival Python claims the NEWEST unclaimed .wav in asr_clips/, renames to
utt_<seq>.wav, records it. Monotonic by clip index; an index gap = a failed-transcription orphan -> flagged.

## Per-request / per-pass capture
- A PerceptionRecorder global owns the current request dir + pass index, seq SHARED with the utterance
  (SessionLog owns the seq).
- begin(seq, kind, target, he2, query, clip) on dispatch of highlight/count/describe -> makes the dir +
  request.json.
- save_pass(frame, payload, ms) on each FRESH SAM3 forward (build_highlight detect() fresh branch) and each
  Gemma VLM call (_ask_thread). Cached forwards do NOT save (no duplicate frames).
- end(verdict) updates request.json; a new begin() or a clear closes the previous request.
- Kinds that make a folder: highlight (continuous SAM3), count (SAM3), describe (Gemma VLM). mission / reject
  / emergency / clear make only a trace.jsonl line.

## Build order
1. DATA: SessionLog -> trace.jsonl + per-utterance seq + he2 capture; causal clip-claim + rename;
   PerceptionRecorder (begin/save_pass/end). Unit-tested offline with fakes.
2. HOOKS: wire begin/save_pass/end into mvd dispatch + build_highlight detect() fresh branch.
   Verified by the synchronous thread-driver dry-run (crash-free, files land, linked).
3. RETIRE utterances.jsonl: point show_session/score_session/score_live/gemma_asr at trace.jsonl.
4. HTML session replayer: loads a session dir, timeline of utterances, draws boxes from JSON over raw
   frames, audio playback, on-demand annotated-export. Standalone file.
5. LAST: opencv pane redesign (separate; Hebrew wrap + reject-reason + SAM3 score).

## Noted pre-existing issue (not fixing now)
count's median-of-3 is partly fake: COUNT_GAP (0.3s) < SAM3_PERIOD (1.0s), so frames 2-3 hit the detect()
rate-limit cache and reuse frame 1's dets. The per-pass capture will EXPOSE this (only 1 fresh forward
logged for a count). Flag for a later fix; out of scope for the trace work.

## STATUS 2026-09-12 (built, offline-verified)
- [x] DATA: SessionLog -> trace.jsonl (one line/utterance) + per-utterance seq; causal clip-claim (newest
      unclaimed .wav -> utt_<seq>.wav); PerceptionRecorder (begin_request/save_pass/end_request/det_payload).
- [x] HOOKS: begin_request at each dispatch (count/highlight/describe); one pass per FRESH SAM3 forward
      (build_highlight detect() hook) + Gemma-VLM pass in _ask_thread; end_request on absent/count-done/
      describe-done/clear/give-up/supersede.
- [x] he2 + flags + kind + target via an optional Pipeline observe() callback (mvd wires SESSION.set).
- [x] RETIRE utterances.jsonl -> the 5 reader tools read trace.jsonl (+ asr_clips fallbacks).
- [x] HTML session replayer: tools/session-replayer/replayer.html (directory picker, draws boxes from JSON
      over raw frames, audio, per-pass scrub/play, on-demand annotated export). Balanced/compiles; NOT yet
      browser-smoke-tested (no browser here) and NOT live-captured (needs a webcam run).
- Offline: 62 tests green; bench tag trace-build: 410/487, 0 changed cases (confirmed).
- [ ] LEFT: (2a) opencv pane redesign + its HTML mockup. Live webcam run to confirm capture + replayer end-to-end.
