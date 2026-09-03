# Thermo-nuclear code-quality review — projects/integration_harden

Scope: the MVD restructure on branch feature-hardening-mvd. 28 Python files, 3,613 lines. No file
exceeds 1,000 lines (largest: recognizer.py at 535), so the file-size blocker does not apply. The
findings below are ranked by structural impact. [VERIFIED] = checked against the real lines this
session. [reported] = high-conviction module-reviewer finding, not personally line-verified.

Headline: about 290 lines (~8%) are dead code that should be deleted outright, and one
safety-relevant control signal is passed as a substring inside a debug-flag list. Fix those two
classes first; the rest is decomposition.

## Tier 1 — delete dead complexity (the biggest, safest wins)

1. [VERIFIED] Dead highlighter backend in perception. `SCENE_HL_BACKEND` is hardcoded to "vlm"
   (config.py:101, scene_omdet.py:15), so the yoloe/grounder path is unreachable. Delete
   `Grounder` + `YoloeHighlighter` and `Eyes._init_highlighter/set_target/highlight`
   (detectors.py:76-147, 159-262). Eyes collapses to `background()` + `mask_for_box()`.
   ~130 lines removed; detectors.py 262 -> ~90.

2. [VERIFIED] Dead WS velocity-stick lane in the drone client. `nudge()` + `_stream_sticks()`
   (dji_wire.py:91-107) have zero production callers; test_router.py:73 asserts nudge is never
   used; native SpinBy/FlyBy replaced it. Deleting it removes ~20 lines AND the entire `aiohttp`
   dependency. Safety bonus: one fewer motor-command path on a safety-critical client.

3. [VERIFIED] ~12 unused DjiWire methods (dji_wire.py: status:86, fly_to:157, fly_circle:162,
   fly_square:168, look_at:180, and fly_to_gps/look_at_gps/tts/key/status_sub/delay/report_status
   in 205-232). Grep shows zero callers. ~60 lines of speculative surface, no tests, each an extra
   way to arm a drone. Keep only the verbs the router actually calls; the rest are data, not methods.

4. [reported] Dead VLM entrypoints (vlm_client.py:119-200: `_scale_objects`, `analyze`, `ground`,
   `SYSTEM_ANALYZE`). No callers; `_scale_objects` duplicates the live `engine.scale_vlm_box`
   (engine.py:44). Only `ask`/`parse_reply` are live. ~80 lines removed.

5. [reported] Dead config knobs (config.py: WIN_NAME/RECORD/PERF/DETECT_HZ/HIGHLIGHT_HZ, zero
   readers) plus stale LLMDet/YOLOE lineage comments that contradict the live OmDet+VLM decision.

## Tier 2 — one structural regression to fix now

6. [VERIFIED] Routing is a stringly-typed control signal hidden in a debug list.
   recognizer.py:441 does `flags.append(f"route:{route(he)}")`; pipeline.py:70 recovers it with
   `elif "route:perception" in flags`. The `flags` list mixes debug breadcrumbs ("number-flag",
   "number-patched") with a load-bearing routing decision. Any drift in that string silently falls
   through to the `else` branch, which calls `plan_fn` -> `fly_mission` (the flight path). A
   perception query mis-tagged becomes a flight plan. Judo: make route a first-class element of the
   recognize() return (e.g. the tuple's kind already is a tagged union — extend it), and dispatch on
   it in pipeline.py. Delete the substring match.

## Tier 3 — missed simplifications (code-judo) and spaghetti

7. [reported] Hebrew numbers are decoded by two divergent parsers: `hebnum_to_digits`
   (recognizer.py:119-167, positional composer) and `_nums_he` (:270-300, naive summer over a
   separate `HEB_NUM` dict at :258). Two tables, two value conventions. Latent bug: `_nums_he` has
   no hundreds-composition, so a word-residue >= 300 sums wrong. Judo: delete the summer, reuse
   `hebnum_to_digits` in stage 4. Removes a whole parser and a class of number bugs.

8. [reported] `scene_omdet.on_text` is a 60-line orchestration megafunction (scene_omdet.py:191-250)
   fusing drone dispatch, clear, presence-gate, and ask, with two thread bodies nested inline. The
   "thin glue" intent held in `worker()` but broke here. Extract a dispatch plus named
   `_handle_*`/`_gate_thread`/`_ask_thread`; on_text drops to ~10 lines.

9. [VERIFIED] `recognize()` inlines a 3-level number-guard retry ladder (recognizer.py:444-460).
   Extract `_resolve_numbers(...)` so the entry point reads as a flat stage sequence.

10. [reported] config.py is an untyped ~50-global god-bag mixing VLM/detector/ASR/camera/colour/TTS,
    imported by every layer. Split by concern or make a typed config object; today any module can
    reach any knob.

11. [reported] Gateway/host resolution is duplicated 3x (tts_io.py:24-38, video_doctor.py:8-13,
    video_watchdog.py:14-21 — the last two byte-identical) and the "camera/stream" topic is
    hardcoded despite `camera_stream.TOPIC`. Extract one `default_gateway()` helper; import TOPIC.

12. [reported] Three separate rclpy frame-count subscriptions (camera_stream.py:24-83,
    video_doctor.py:28-42, video_watchdog.py:33-60) repeat the same boilerplate in three lifecycle
    styles; the core-dump-on-teardown fix lives in only one. Extract a shared `FrameCounter`
    context manager — this also propagates the crash fix everywhere.

## Tier 4 — abstraction / evidence-discipline

13. [reported] The `Rule` class carries positives+negatives, but only HE_RULES/EN_RULES use it.
    inline_english, add_missing_verb, bypass, and the two `route` regexes are ad-hoc regex with
    evidence scattered as asserts. The safety-relevant routing regexes have the least structured
    evidence. Bring them under `Rule` (or an equivalent) so the selftest guards them too.

14. [reported] Hebrew word-boundary + prefix idiom `(?<![range])[prefixes]{0,2}...(?![range])` is
    re-derived ~7x (recognizer.py:158,194-200,212,288,355,402,407) and drifting. Add a canonical
    `he_word()` builder + an `HE` range constant.

15. [reported] The flat->clustered move did not finish: dual import shims remain (router.py:14-21
    try/except; camera_stream.py:112 sys.path). Commit to `python3 -m` package imports and delete
    the shims.

## Real bugs found (separate from quality)

- [VERIFIED] TTS default double-speak. `Voice` defaults `TTS_BACKEND` to "both" (tts_io.py:39), so
  when a phone and espeak are both present every answer is spoken twice. Pick one default, or make
  "both" deliberate.
- [VERIFIED] video_watchdog respawns with a literal "None". If `gateway()` fails it returns None and
  the command becomes `--dji None` (video_watchdog.py:23-27). Guard the None before respawning.
- [reported] The VLM-box fallback in engine.py:118-124 skips the garbage-mask check that the primary
  path at :89-94 performs. Route the fallback box through `apply_masks` so both share the check.
- [reported] OmDet docstring/path mismatch (detectors.py:19 vs 20). Minor.

## What is already good (keep)

- The Recognizer's injected-translate boundary, the tagged-union return, and the Rule-with-evidence
  idea are sound. The perception engine is genuinely pure (imports only re/numpy, faked in selftest)
  and `worker()` really is one engine call. CameraStream's cv2-compatible adapter and the
  per-consumer SingleThreadedExecutor (a documented core-dump fix) are both good.

## Approval verdict

Not approvable as-is, on two grounds: the stringly-typed routing signal (Tier 2, #6) is a
structural regression on a safety path, and ~290 lines of dead code (Tier 1) should not merge.
Neither is hard to fix. The dead-code deletions are pure subtraction; the routing fix is a small
type change. After those, the Tier 3 decompositions are worth doing but are not blockers.
