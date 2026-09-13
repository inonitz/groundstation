# Test evidence — Hebrew command work, 2026-09-01

Every test run for the Hebrew-input work (the A-work commit + the pipeline comparison), with
environment, inputs, and actual outcomes. Raw model outputs: `2026-09-01-qwen-direct-hebrew-raw.json`
(direct HE/EN bench) and `2026-09-01-results.json` (six-pipeline matrix) in this directory.

## 1. Router unit tests — pytest, 13/13 PASS
Command: `python3 -m pytest -q projects/integration_harden/test/test_router.py`
Environment: python 3.12, no network, `_StubWire` records wire calls. 11 tests inherited from the
tts fork (import retargeted to `integration_harden`), 2 new Hebrew tests.
| test | asserts |
|---|---|
| test_basic_verbs | 9 verb phrases map to canonical verbs (takeoff/land/go_*/spin) |
| test_back_up_is_backward_not_up | "back up" -> go_backward (the historical collision) |
| test_tiers | stop/abort/freeze/kill -> EMERGENCY; manual -> OVERRIDE; resume -> RESUME |
| test_complex_and_length_guard | questions -> COMPLEX; "is the drone going to land soon" must NOT land |
| test_override_mode_gating | manual swallows verbs; resume restores dispatch |
| test_emergency_beats_manual | e-stop fires while in manual |
| test_spin_uses_native_spinby | "spin around" -> SpinBy(360), never a yaw nudge |
| test_expanded_verbs | track/follow/scan/search/come_home wire methods; "come back" -> come_home |
| test_stop_does_not_latch_manual | stop is one-shot; mode stays auto; next verb flies |
| test_v3_mappings | gimbal pitches, wave greetings, scan INWARDS/OUTWARDS, directionals->fly_by, stop->halt NOT /c/stop |
| test_unknown_move_guard | "go dance" -> no-op feedback, NOTHING on the wire |
| test_hebrew_emergency_tiers (new) | 7 Hebrew stop forms -> EMERGENCY; ידני/אני בשליטה -> OVERRIDE; המשך/אוטומטי -> RESUME; emergency fires inside a long Hebrew sentence |
| test_hebrew_emergency_dispatch (new) | "עצור" -> halt() on the wire; "מה אתה רואה עכשיו" -> COMPLEX, no wire call |

## 2. PhoneEars live desk loop — 2 runs, second PASS
Throwaway harness (not committed), real sockets on loopback, real `PhoneEars` instance.
- RUN 1 (port 18099): REST POST /input {"text":"עצור"} -> 200 {"ok":true}; raw TCP JSON line
  "טוס קדימה חמישה מטרים"; then TCP "עצור" again 0.4s later expecting dedup.
  RESULT: assertion FAILED — received ['עצור','טוס קדימה חמישה מטרים','עצור']. Diagnosis: dedup
  compares only the LAST text (by design — the app double-sends the same command back-to-back);
  my interleaved sequence was a wrong expectation, not a code bug.
- RUN 2 (port 18098): the app's real pattern — same text via REST then TCP back-to-back, twice
  with different texts. RESULT: PASS — received exactly ['עצור','טוס קדימה חמישה מטרים'];
  REST + TCP channels live (validating the TCP phantom-arg fix), duplicate swallowed, UTF-8 intact.
  Post-PASS the harness crashed at interpreter shutdown (exit 134, daemon-thread stdout lock) —
  teardown artifact of the throwaway script; the MVD process never exits this way.

## 3. Qwen3-VL-4B direct HE vs EN — EN 12/12, HE 5/12
llama-server (Vulkan, Q4_K_M, temp 0, max_tokens 300), whitelist planner system prompt,
12 paired cases. Full outputs in the raw JSON. Hebrew failures, exactly:
| case | HE input meaning | HE result |
|---|---|---|
| up10 | go up 10m | `takeoff` (wrong verb) |
| spin90cw | rotate 90 cw | `degrees: 80` (misread תשעים) |
| takeoff | המראה | `[]` (read as non-movement) |
| combo3 | up10+spin90+fwd5 | z lost, degrees 30 (steps mangled) |
| combo_tl | takeoff+up5+wait3+land | invalid JSON (truncated/malformed) |
| back2left3 | back2 then left3 | fused into one action, y sign wrong |
| down3 | descend 3m | `fly_by x:+3` (wrong axis AND sign) |
EN side: all 12 correct including both combos; open-ended "square" produced a 4-leg square.

## 4. Six-pipeline matrix — 72 planner calls + translations
`run_bench.py`, same scorer everywhere. One incident: nllb OOM'd on the 7.5GiB GPU
(Qwen 3.7G + DictaLM 1.5G resident) -> CPU fallback added, latency labeled accordingly.
| pipeline | ok | median e2e | failures |
|---|---|---|---|
| qwen-en | 12/12 | 246ms | — |
| opus->qwen | 10/12 | 263ms | המראה->"The Mirror", נחת->"Marine" (isolated single words) |
| nllb->qwen (CPU) | 9/12 | 1825ms | המראה->"The mirror"; combo_tl mangled; ccw45 sign lost |
| dicta->qwen | 8/12 | 338ms | המראה->"The show"; נחת->"You have landed."; combo_tl mangled; back2left3 verbs reordered |
| qwen-he | 5/12 | 346ms | as section 3 |
| dicta-he direct | 2/12 | 286ms | 6 invalid JSON (incl. answering the question itself), 2 wrong-z, wrong-len |

## Not tested anywhere above
Real phone, real aircraft (human-only, always), phone-side Hebrew locale behavior, and the
C++ build after the CMake changes that were swept into the A commit (not part of this work).
