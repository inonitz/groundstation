# Ponytail review (ultra) — consolidated, both phases (2026-09-17)

What this is: an independent over-engineering audit (ponytail `ultra`: deletion before addition),
run as a second pass to corroborate the thermo-nuclear review and surface cuts it missed.
Over-engineering ONLY, not correctness. Static analysis + grep call-graph; NOTHING was run.
Tags: delete (dead/speculative), yagni (abstraction with one impl), stdlib (reinvented std lib),
native (dep doing the platform's job), shrink (same logic, fewer lines).
Source detail: `scratchpad/ponytail-{harden2-logic,harden2-runtime,tools-bench}.md`.

CONFIDENCE: these are grep/static findings, high but not runtime-proven. The one place I personally
verified against source is the `_nums_en` dispute (see correction). Every deletion must pass the 66
tests + the 410/487 unified_bench before it is trusted.

================================================================================
# PHASE 1 — integration_harden2
================================================================================

## 1a. Logic core (recognizer, perception x2, control, config)
Ranked biggest cut first:

- delete  perception2/engine.py — dead; near-verbatim duplicate of live perception/engine.py (33/~200
  lines differ); not imported. 189 lines. [perception2/engine.py:1-189]
- delete  perception2/detectors.py — dead; OmDet-Turbo + Eyes + lazy SAM2; the ONLY remaining
  OmDetTurbo + ultralytics.SAM load paths in the runtime; not imported. 124 lines. [perception2/detectors.py:1-124]
- delete  perception2/vlm_client.py — dead; near-verbatim duplicate of live perception/vlm_client.py
  (18/~120 differ); not imported. 116 lines. [perception2/vlm_client.py:1-116]
- delete  perception2/chain_demo.py — dead AND broken: imports build_engine/parse_highlight not
  exported by perception2/__init__ -> ImportError on run. 65 lines. [perception2/chain_demo.py:10,33]
- delete  recognizer stage 5 (EN_RULES + apply_en) — English rewrites, zero callers. ~40 lines. [recognizer.py ~505-560]
- delete  recognizer stage 4b (ANSWER_RE, ANSWER_POSITIVES/NEGATIVES, answer_mode) — zero callers. ~30 lines. [recognizer.py ~468-498]
- delete  recognizer stage 4 EN reconciliation (check_numbers, patch_number, _resolve_numbers) — no
  caller on the direct path (numbers_vs_mission runs instead). ~34 lines. [recognizer.py:423-465]
- delete  recognizer stage 6 routing (PERCEPTION_RE, MOVEMENT_RE, route()) — Gemma "kind" +
  commands.classify route now; route() has an __init__ export but zero call sites. ~20 lines. [recognizer.py ~565-590]
- delete  recognizer check_colors + COLORS table — no caller. ~20 lines. [recognizer.py ~500-518]
- yagni   config.py redundant adapter — docstring claims "single import surface" but mvd.py:20 imports
  config_constants/_defaults directly for 11 symbols while ALSO using config.X; mostly 1:1 remaps +
  aliases. ~50 lines. [config.py:1-65]
- delete  config wire_target()+video_input()+CONTROL — dead in the live app (mvd uses
  DjiWire.from_env; these feed only test_config_golden.py + capture_golden_config.py). ~14 lines. [config_defaults.py:56-79]
- delete  declared-but-hardcoded ports — only LLAMA_SERVER_PORT is read in Python; VIDEO_TCP_PORT(5600),
  PHONE_ASR_PORT, MOCK/REAL_WIRE_PORT are ceremonial (hardcoded literals or test-only). [config_constants.py:19-23]
- native  two gateway-discovery impls: _default_route_ip() (subprocess `ip route`) vs default_gateway()
  (/proc/net/route). Collapse to one. ~15 lines. [config_defaults.py:11-19 & 106-121]
- shrink  duplicate number-token predicate: recognizer _number_token vs inner is_number of _nums_he. ~8 lines. [recognizer.py ~215 & ~372]
- shrink  in-module selftests duplicated by pytest (perception2/engine.py ~55-line selftest tests DEAD
  code; sam3_backend._smoke). [perception2/engine.py:130-189; sam3_backend.py _smoke]
- shrink  recognizer/pipeline.py dual import dance (try .llama / except flat llama, twice) — speculative;
  every consumer already puts root on sys.path. ~8 lines. [recognizer/pipeline.py:24-32]

Sub-net (logic core): ~780 lines (perception2 494 + recognizer dead ~180 + config ~68 + dedup ~40).

## 1b. Runtime / IO (mvd, overlay, audio, video, session, launchers)
Ranked biggest cut first:

- delete  run_mvd.sh entirely — 170-line subset-duplicate of run.sh (which docs call its replacement;
  run.sh adds down/status/preflight/score/show + log pipe-pane). -170. [run_mvd.sh:1-170]
- delete  run_router.py entirely — dead harness; documents a nonexistent module path, its perception
  handler always raises then no-ops; mvd wires Router+Pipeline directly and never imports it. -55. [run_router.py:1-55]
- delete  video/video_doctor.py — 62-line layer diagnostic NOT wired into any launcher; `run.sh status`
  already reports phone-gate/gst/frames. -62. [video/video_doctor.py:1-62]
- delete  OmDet dead render scaffolding — build_highlight raises unless seg=="sam3", so the SCENE_SEG
  fork [mvd.py:64], the `else` branches [mvd.py:273,331], the OM name-dict threaded as constant "SAM3"
  through render_chat/HUD/_model_lines, and the "omdet" map entry [overlay.py:134] are all unreachable.
- delete  _hl_debug + _last_hl_dbg — 14-line throttled box-coverage printer in the worker hot path;
  stale "what OmDet returns" docstring. -14. [mvd.py:97-110]
- shrink  env-knob galaxy — ~11 os.environ.get("SCENE_*", str(_K.X)) wrappers over constants nobody
  sets + a 6-line safety-valve essay; use _K.*/_D.* directly. ~-12. [mvd.py:64-77]
- shrink  tts_io Voice — the threaded queue + drain + subprocess-terminate is redundant for the default
  phone backend (phone flushes its own queue); the `both` mode is speculative/unused. Gate queue/kill
  to local-only; drop `both`. ~-18. [tts_io.py]
- delete  --keep-llama + we_started_llama pgrep dance — launchers own llama-server in a tmux pane and
  tear it down; mvd's kill is redundant, the flag speculative. -5. [mvd.py:385,397,553-554]
- shrink  session_log atomic durability — temp+fsync+rename on EVERY per-pass JSON + EVERY JPEG into a
  gitignored disposable dir; keep atomicity for trace.jsonl only. ~-8. [session_log.py]
- shrink  _u() legacy-layout probe duplicated in show_session.py AND score_session.py (probe
  trace.jsonl -> asr/utterances -> utterances; only trace.jsonl exists post-2026-09-12); show_session
  also prints a dead r.get("english"). ~-8.
- shrink  OM/ENGINE dict-as-mutable-box singletons [mvd.py:78-79] — collapse to plain globals. ~-3.
- shrink  _resolve_phone_host regex re-parse of host= from SCENE_INPUT — phone IP is already
  default_gateway(); drop the fragile branch. ~-4. [tts_io.py:24-31]

Sub-net (runtime/IO): ~420-450 lines (whole-file deletes run_mvd 170 + run_router 55 + video_doctor 62
= 287; in-file ~130-160).

## Corroboration of the thermo review (Phase 1)
- OmDet dead scaffolding — CONFIRMED. overlay string round-trip — CONFIRMED. TTS triplication (+ dead
  espeak re-check) — CONFIRMED. run_mvd.sh duplicate, run_router.py dead — CONFIRMED.
- perception2 half-fold — CONFIRMED and stronger (494 dead lines; engine/vlm_client are near-verbatim
  v1 duplicates; chain_demo crashes on import).
- config split / hardcoded ports / dead wire_target+CONTROL — CONFIRMED and worse (mvd.py:20 bypasses
  the config.py adapter and imports the raw files too).

## CORRECTION (verified against source) — the one dispute
Thermo said "delete `_nums_en`/`EN_NUM`, repoint is_shot_echo to `_nums_he`." RETRACTED as unsafe.
Proven: `_nums_en` is LIVE — pipeline.py:107 (handle_direct, the live path) calls is_shot_echo, which
calls `_nums_en` at pipeline.py:49. handle_direct passes he2 (Hebrew), so `_nums_en` always returns []
— live-but-inert. Deleting/repointing changes is_shot_echo's result. KEEP `_nums_en`/`EN_NUM`.
Therefore recognizer genuinely-dead ~= 180 lines (stages 4b/5/6 + stage-4 EN reconciliation +
check_colors + the selftest lines testing them), NOT ~260.

## Phase-1 net removable (static estimate): ~1,200 lines
logic core ~780 + runtime/IO ~420-450. No whole top-level dependency drops (live perception/ v1 mirrors
the dead perception2 imports; SAM3 + YOLO26 keep torch/transformers/ultralytics).

================================================================================
# PHASE 2 — tools/ + live bench/ (archive/, docs/stale/, retired campaigns excluded)
================================================================================

Ranked biggest cut first:

- delete  build.ps1 — 92-line Windows twin, drifted (backend set px4,tello,all MISSING dji), Linux-only project. [build.ps1:1]
- delete  ws_latency.py — superseded by measure_ws_rtt.py (real /c/ws/echo, stdlib, zero deps); sole `websockets` importer. [tools/dji_mock/ws_latency.py:1]
- delete  plot_latency.py — 77-line matplotlib one-off, hardcodes a "2026-08-22" run title; sole matplotlib user. [tools/dji_mock/plot_latency.py:1]
- delete  compare_runs.py — reads the retired translator A/B schema (recognized/translator). [bench/hebrew-command-bench/compare_runs.py:1]
- delete/rewrite  planning_table.py — 2/3 stacks retired; globs JSON unified_bench never emits; stale tools/bench path. [bench/whole-system/planning_table.py:7]
- yagni   install-translation-models.sh — translated path retired 2026-09-12 (unified_bench = Gemma
  direct-Hebrew); the opus/nllb/madlad/translategemma fetches are dead. OWNER-CONFIRM. [tools/devenv/install-translation-models.sh:1]
- delete  run_all.sh dead lanes — replay/bench/perfect/gemma lanes call retired bench.py flags. [bench/whole-system/run_all.sh:19-37]
- native  SAM3 detect() x4 -> perception2.Sam3Backend.detect() (already takes precision=/compile=). [sam3-mask-bench/{run_suite,run_web,run_indepth,measure}.py]
- native  preflight()+HINTS byte-identical x2 -> one djiprobe module. [tools/dji_mock/measure_telemetry.py:14, measure_ws_rtt.py:18]
- stdlib  pct() x5 -> one stats.pct; fixes the power_profile off-by-one (:118 uses int(q/100*len(s)) vs
  canonical int(round(q/100*(len(s)-1))) -> p95 idx 95 vs 94). [tools/power_profile.py:118 + 4 others]
- stdlib  box-IoU x3 -> one helper. [whole-system/vlm_compare.py:89, vision_chain.py:14, sam3-mask-bench/compare_engines.py:65]
- yagni   build.sh debug_perf + release_perf — identical cmake to debug/release, only a renamed out dir. [build.sh:59,68]
- delete  mock battery placeholder `STATE["batteryPct"] -= 0` (does nothing). [tools/dji_mock/mock_apiserver.py:104-106]
- shrink  stale tools/bench path in 6 files -> one shared `bench/` path constant. [run_list.py:25, planning_table.py:7, vlm_compare.py:16, sam3_alone.py:12, vision_chain.py:11, overlays.py:11]
- shrink  prewarm_llama.sh PIL heredoc -> static tiny-PNG base64 const. [tools/prewarm_llama.sh:16-22]
- shrink  watch_503.sh stale default IP 10.222.215.92 -> derive from route. [tools/dji_mock/watch_503.sh:5]
- shrink  run_web.py + run_suite.py dated one-off overlay gens over the same set; consolidate. [sam3-mask-bench]

## Corroboration of the thermo review (Phase 2)
All five thermo claims CONFIRMED: build.ps1 twin, ws_latency dup, copy-pasted DJI probe scaffolding
(corrected: preflight/HINTS in measure_telemetry + measure_ws_rtt, NOT power_profile; pct off-by-one
at :118 not :120), SAM3 detect x4, and the broken bench scripts (stale path in 6 files, not 5).

## Phase-2 net removable (static estimate): ~500-560 lines
Whole-file deletes build.ps1 92 + ws_latency 105 + plot_latency 77 + compare_runs 56 = 330; retired
trims ~107; dedup ~67; small ~16. Deps removable: websockets, matplotlib; if the translated path is
confirmed retired: sentencepiece + 5 translation-model downloads.

================================================================================
# GRAND TOTAL (static estimate): ~1,700-1,780 removable lines
Phase 1 ~1,200 + Phase 2 ~500-560. Corrects my earlier chat figure of ~1,200-1,340, which wrongly used
only the Phase-1 logic sub-scope. All figures are static; the `_nums_en` case shows why each cut is
gated by the 66 tests + the 410/487 bench.
