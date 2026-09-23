# Thermo-nuclear code-quality review — integration_harden2 (2026-09-21)

Static, read-only review of every `.py` file under
`/root/groundstation/projects/integration_harden2` (55 files, `__pycache__` skipped).
Judged against `docs/guidelines.md`, `CLAUDE.md`, and the house exception rule
(no exceptions in our own code; `die()` on a fatal invariant; `try/except` only to
wrap a third-party call and convert it to a status). The priority dimension is
exception/try-except misuse. Nothing was modified.

Overall the core is strong. `recognizer/recognizer.py`, `perception/engine.py`,
`audio/tts_io.py`, `control/router.py`, and the `perception2` pure helpers are
model files: pure logic, guard clauses, small units, no swallowed exceptions,
extensive WHY-comments. The findings concentrate in the `mvd.py` orchestrator,
a few stale/dead artifacts left by the harden2 restructure, and one real
concurrency gap around the shared SAM3 backend.

## Summary

| Severity | Count |
|---|---|
| Blocker | 1 |
| Major | 11 |
| Minor | 40 |
| **Total** | **52** |

| File | Blocker | Major | Minor |
|---|---|---|---|
| mvd.py | 1 | 3 | 5 |
| perception2/sam3_backend.py | 0 | 1 | 2 |
| control/dji_wire.py | 0 | 1 | 2 |
| recognizer/pipeline.py | 0 | 1 | 2 |
| perception2/concept.py | 0 | 1 | 1 |
| video/video_watchdog.py | 0 | 1 | 0 |
| show_session.py | 0 | 1 (shared) | 1 |
| score_session.py | 0 | 1 (shared) | 1 |
| test/capture_golden_config.py | 0 | 1 | 0 |
| test/live_mock_smoke.py | 0 | 1 | 0 |
| perception/vlm_client.py | 0 | 0 | 2 |
| session_log.py | 0 | 0 | 3 |
| audio/phone_asr.py | 0 | 0 | 3 |
| recognizer/llama.py | 0 | 0 | 2 |
| perception2/verify.py | 0 | 0 | 2 |
| control/kill.py | 0 | 0 | 2 |
| video/camera_stream.py | 0 | 0 | 2 |
| overlay.py | 0 | 0 | 1 |
| config/defaults.py | 0 | 0 | 1 |
| recognizer/recognizer.py | 0 | 0 | 1 |
| recognizer/trace.py | 0 | 0 | 1 |
| perception/detectors.py | 0 | 0 | 1 |
| perception2/counting.py | 0 | 0 | 1 |
| recognizer/prompts.py | 0 | 0 | 1 |
| cam_list.py | 0 | 0 | 1 |
| test/ (stale env vars) | 0 | 0 | 1 |

(The `show_session.py`/`score_session.py` structural defect is one shared
finding counted once in the totals.)

---

## mvd.py

- **Blocker** — `mvd.py:457` (`setup_drone_router`, the `except Exception as e:` at the
  end). One broad catch wraps the entire construction of the drone assembly: `DjiWire.from_env`,
  the `record_fly`/`record_halt` wrappers, `Pipeline`, `Router`, and `KillSwitch`. This both
  violates the house rule (it catches OUR own code, not a third-party call) and is
  safety-relevant: a bug or partial failure anywhere in the kill-switch or router wiring is
  swallowed and the drone router is silently disabled, or worse left half-wired (router built,
  kill switch not). Fix: build each piece explicitly, let our own invariant failures reach
  `die()`, and reserve any narrow `try` for the one genuinely reachable third-party failure
  (the wire host being unreachable at connect time, if that even raises here).

- **Major** — `mvd.py:226-231` (`_handle_drone`). `try: res = self.router.handle(text)` wraps
  our own `Router.handle` in a broad `except Exception`. Router code should not raise; if it can,
  fix the router, do not catch it here. Keep a `try` only around the actual wire HTTP call, which
  already returns status codes. Fix: remove the broad catch; if the wire POST can raise, convert
  it to a status at `DjiWire` and check the code.

- **Major** — `mvd.py:329-331` (`_gate_thread`). Lines 329-330 compute `present, px` from the
  VLM box, then line 331 unconditionally sets `px = None` with the comment that Gemma boxes are
  never drawn. The degenerate-box check on 329-330 and every earlier assignment to `px` are dead:
  `px` is always `None` from here on. Fix: delete the `px` plumbing in this thread (the
  `presence_gate` box path and 329-330) so the reader is not tracking a value that cannot survive.

- **Major** — `mvd.py:190-191` (`__call__` finally block). `en = rec.get("english")` reads a key
  the record never has: `SessionLog.begin()` writes `heard_he`/`he2`/`target_en`, never `english`
  (a leftover from the retired translator). So `if en:` on 164 never fires and the "En" chat line
  is dead. `show_session.py:32` reads the same non-existent key. Fix: read `he2` (or delete the
  branch, since harden2 is Hebrew-direct and has no English line).

- **Minor** — Dense one-liner cluster: multiple statements chained with `;` or inline after a
  colon at `mvd.py:88, 91, 151, 229, 233, 238, 244, 259, 314, 316, 335, 351-352`. The house rule
  bans dense one-liners and semicolon-chained statements. Fix: one statement per line.

- **Minor** — `mvd.py:30-33`. `try: from audio.ros2_asr import Ears ... except Exception: _HAVE_EARS = False`
  is a silent import guard that degrades. ROS2 mic ASR is genuinely optional here (phone ASR is
  the primary channel), so this is defensible, but the catch is `Exception`-wide and swallows an
  import bug in `Ears` itself. Fix: narrow to `ImportError`/`ModuleNotFoundError`.

- **Minor** — `mvd.py:276-277`. `try: self.voice.say(...) / except Exception: pass` silently
  swallows a voice failure with no log. `say()` wraps third-party TTS so the boundary is allowed,
  but the total silence hides a broken voice. Fix: log the exception.

- **Minor** — Dead whitespace: large blank-line runs (roughly `mvd.py:44-50`, `365-369`, and the
  seven blank lines before `from fatal import die`). These are restructure leftovers. Fix: collapse.

- **Minor** — `mvd.py` is 671 lines mixing perception dispatch, drone wiring, display loop,
  session logging, and `TextHandler` with six thread bodies. Under the 1000-line trip wire but a
  decomposition candidate: `TextHandler` plus its thread bodies is a natural module. Fix: consider
  splitting the text-handler/threads out of the entry point.

## perception2/sam3_backend.py

- **Major** — Concurrency: one `Sam3Backend` instance (`OM["det"]`) is called from three threads
  — the display `worker` (via `engine.highlight_step` -> `detect` + `mask_for_box`), `_gate_thread`,
  and `_count_thread` (both via `ENGINE["e"].detect`) — with no lock. `detect()` at
  `sam3_backend.py:114` resets `self._cache = {}` then repopulates it, and `mask_for_box()` reads
  it; two concurrent `detect()` calls race on `_cache` (and on the `last`/`OM` closure state in
  `mvd.build_highlight`), so `mask_for_box` can return a mask from a different frame or phrase, and
  two concurrent CUDA forwards run on one model. The `SAM3_PERIOD` throttle only de-dupes the
  worker's own repeats; it does not serialize across threads. Fix: guard the backend with a
  `threading.Lock` around `detect`+`mask_for_box` as one critical section, or route all SAM3 calls
  through the single `worker` thread.

- **Minor** — `sam3_backend.py:58` the `compile` constructor parameter shadows the Python builtin
  `compile`. Fix: rename to `use_compile`.

- **Minor** — Dense semicolon lines at `sam3_backend.py:27-28, 32, 48`. Fix: one statement per line.

## control/dji_wire.py

- **Major** — `dji_wire.py:33`. The non-loopback safety guard does `raise RuntimeError(...)`. This
  is our own fatal invariant (a real-drone host without `allow_real`), which the house rule says
  must go through `die()` with a loud crash, not an exception. Worse, it is constructed inside
  `mvd.setup_drone_router`'s broad catch (Blocker above), so a real-host misconfiguration is
  swallowed and the router is silently disabled instead of crashing loudly. Fix: call
  `die("refusing non-loopback host ... real-drone commands are HUMAN-run only")`.

- **Minor** — `dji_wire.py:59-60` and `92-93`. The generic `except Exception as e: print(...); raise`
  re-raises network errors while the `HTTPError` branch converts to `return e.code`. The third-party
  boundary is handled two different ways. Fix: convert both to a status code (or let both propagate)
  so callers see one contract.

- **Minor** — `dji_wire.py:122-125`. `_loc2` and `_loc3` are defined but unused anywhere in the
  repo. Dead code. Fix: delete.

## recognizer/pipeline.py

- **Major** — `pipeline.py:19-22`. `try: from perception2.lexicon import fix_target / except Exception:`
  defines a no-op stub. The lexicon is our own HE->EN correction net (the safety net under Gemma's
  `target_en`); silently stubbing it out on any import error degrades a correctness feature with no
  signal. The house rule says a missing required dependency calls `die()` with the fix line. Fix:
  if it is required, `die()`; if truly optional, narrow to `ImportError` and log that the net is off.

- **Minor** — `pipeline.py:24-33`. The package-vs-flat dual import block (`try: from .llama ... except
  ImportError: from llama ...`) duplicates the import list to support running flat from inside the
  package. Convenience debt. Fix: pick one import style (the package path, since consumers put the
  root on `sys.path`).

- **Minor** — Dense `; action = ...` one-liners at `pipeline.py:90, 96, 104, 111, 121, 123, 125, 127`.
  Fix: one statement per line.

## perception2/concept.py

- **Major** — Dead subsystem. `extract_concepts`, `make_vlm_asker`, `load_learned`, `save_learned`,
  `_LEARNED`, `_parse_vlm`, `_norm`, and `CONCEPT_PROMPT` (about 100 lines) form a VLM-based concept
  extractor with a learned cache. Nothing in the live path calls them: `mvd` and `verify` use only
  `phrase_concepts` (the pure offline path). They are exercised only by this file's own `selftest`.
  This is maintained-but-unused weight (YAGNI). Fix: either wire the VLM extractor into the highlight
  path if it is meant to be used, or delete it and keep the offline `phrase_concepts`.

- **Minor** — `concept.py:123` and `132`. `json.load(open(path))` / `json.dump(_LEARNED, open(path,"w"))`
  leak the file handle. Fix: use `with open(...)`.

## video/video_watchdog.py

- **Major** — No `if __name__ == "__main__":` guard. The `with FrameCounter(...) as fc:` block and
  the monitoring `while` loop run at module import (`video_watchdog.py:32-57`). Any import of this
  module — a test collector, a tooling scan — starts the watchdog and blocks. Fix: wrap the runtime
  in `def main(): ...` under a `__main__` guard.

## show_session.py and score_session.py

- **Major (shared)** — In both files the `_u()` helper and other statements appear at lines 1-8,
  BEFORE the `#!/usr/bin/env python3` shebang (line 9) and the triple-quoted docstring (line 10).
  A shebang only works on line 1, so it is inert; a docstring must be the first statement, so the
  string at line 10 is a dead literal, not `__doc__`. `_u()` is also copy-pasted identically across
  the two files. Fix: move the shebang to line 1 and the docstring directly under it, and extract
  the shared `_u()` into one helper both import.

- **Minor** — `score_session.py` is extremely dense: every function is packed into semicolon-chained
  one-liners (`score_session.py:19, 28-30, 43-49, 52-67, 69-83`). `show_session.py` is milder but
  similar. These are diagnostic utilities, not the live path, but they are the worst readability
  offenders in the tree. Fix: expand the judge/parse functions to one statement per line.

- **Minor** — Stale reads: `score_session.py:16` reads `MVD_HOME`, an env var deleted in the
  restructure (per `config/constants.py`); `show_session.py:32` reads the non-existent `english`
  record key. Fix: drop `MVD_HOME`; read `he2`.

## test/capture_golden_config.py

- **Major** — Retired-but-present dead file. `test/test_config_golden.py:1-4` states the golden
  master was retired 2026-09-18 and "capture_golden_config.py and golden_config.json are retired
  with it," yet the file is still in the tree. It references deleted env vars (`MVD_DRONE`,
  `MVD_PLANNER`, `MVD_TRANSLATOR`, `SCENE_SAM2`, `MVD_XLATE_PORT`) and config attrs that no longer
  exist (`SAM2_WEIGHTS`, `TTS_MODEL`, `TTS_PIPER_BIN`, `TTS_SR`), and its `# L162`-style line
  citations point at a `mvd.py` layout that has changed. Fix: delete the file (owner runs the git
  removal).

## test/live_mock_smoke.py

- **Major** — Broken against the current router. This live smoke asserts `r.handle("take off")`,
  `"go forward"`, `"go up"`, `"land"` reach the wire and flip mock telemetry (`live_mock_smoke.py:55-76`).
  But harden2 retired the English BASIC verb tier (`control/commands.py`): those phrases now classify
  as `Tier.COMPLEX` and go to the `on_complex` perception stub, never to the wire. So
  `status()["aircraft"]["isFlying"] is True` after "take off" can no longer hold, and the manual-mode
  check `assert r.handle("go forward").dispatched is False` is also wrong, because COMPLEX always
  returns `dispatched=True` (the router does not gate). The test is stale and would fail. Fix: rewrite
  it to drive the mock through the harden2 path (safety tiers + a `Pipeline` mission), or retire it.

## perception/vlm_client.py

- **Minor** — `vlm_client.py:1` places `import os` before the module docstring (lines 2-6), so the
  triple-quoted string is a dead literal, not `__doc__`, and `os` is then imported a second time at
  line 7. Fix: move the docstring to line 1 and drop the duplicate import.

- **Minor** — `vlm_client.py:88-89`. `ask()`'s docstring promises a 3-tuple
  `(answer, target, box)` but the function returns a 4-tuple `(long, target, box, short)`. Fix:
  correct the docstring.

## session_log.py

- **Minor** — Broad `except Exception` around our own file I/O at `session_log.py:70, 108, 125, 148,
  164, 180`. This is a defensible best-effort-logger pattern (a logging failure must not crash a live
  drone session, and stdlib I/O is the throwing party), but `70-71` swallows the meta.json write with
  a bare `pass` and no log at all. Fix: at minimum log every swallowed logging failure.

- **Minor** — File-handle leaks: `session_log.py:175` `json.load(open(rp))`. Fix: `with open(...)`.

- **Minor** — Dense `print(...); return None` one-liners on the except lines (`session_log.py:108,
  126, 149, 165, 181`). Fix: split.

## audio/phone_asr.py

- **Minor** — `phone_asr.py:55-58`. `try: self._on_text(text) / except Exception` wraps our own
  `TextHandler.__call__`. Catching our code violates the rule; it is boundary-justified (a network
  thread must not die on a downstream bug) and at least logs, so it is minor, but the right fix is
  to make `on_text` not raise and drop the catch.

- **Minor** — `phone_asr.py:60-97`. `_handle` is a ~40-line method with a hand-rolled HTTP header
  parse loop nested inside the sniff branch. Fix: extract the HTTP request parse into a helper.

- **Minor** — `phone_asr.py:100-101`. `try: writer.close() / except Exception: pass` dense one-liner.
  Fix: split across lines.

## recognizer/llama.py

- **Minor** — File-handle leaks: `llama.py:48` `open(LOG_PATH, "ab", ...)` is never closed, and
  `llama.py:54` `open(LOG_PATH, "rb").read()` leaks. Fix: `with`.

- **Minor** — `llama.py:59-65`. `__exit__` catches `Exception` around `proc.wait(timeout=15)`; the
  only expected throw is `subprocess.TimeoutExpired`. Fix: catch the specific type.

## perception2/verify.py

- **Minor** — Dense semicolon lines at `verify.py:70, 80, 91, 124` and inline `if c == ...: return`
  one-liners at `verify.py:132-134, 142`. Fix: one statement per line.

- **Minor** — `verify.py:121` imports `cv2, numpy` inside `region_is_color`, which runs per related
  hit. Python caches the import so the cost is small, but the module-level home is cleaner. Fix:
  hoist the imports to module scope (they are already hard deps of the file).

## control/kill.py

- **Minor** — `kill.py:43` (`self.killed = True; self.kills += 1`) and `kill.py:54-55` (inline
  `if/else`) are dense one-liners. Fix: split.

- **Minor** — `killed`/`refused` are mutated from the key-handler thread (`toggle`) and read from
  the pipeline/worker threads (`_guard`) with no lock. Benign under the GIL for a single bool, but
  it is a lock-free shared flag on the safety path. Fix: document the GIL assumption, or use a small
  lock. (The `setattr` monkeypatch of wire methods is intentional defence-in-depth and is fine.)

## video/camera_stream.py

- **Minor** — `camera_stream.py:73-78` and `122-127`. The spin loops `try: ... except Exception: pass`
  swallow every rclpy spin error silently, so a dead frame thread leaves no trace. Fix: log before
  swallowing. (The import-guard-then-`die()`-at-use pattern at 14-20/54/105 is a good pattern, not a
  finding.)

- **Minor** — `camera_stream.py:129-135`. `_cb` catches our own `numpy` reshape in a broad `except`
  and drops the frame. A malformed ROS message is the realistic cause, so converting to a dropped
  frame is reasonable, but the catch is `Exception`-wide. Fix: narrow to `(ValueError, TypeError)`.

## overlay.py

- **Minor** — `overlay.py:21-22`. `_ttf` is a dense one-liner (`try: return ... / except Exception:
  return fb`). The PIL boundary is fine; split the lines. (The top-level PIL/bidi import guard that
  degrades to ASCII Hershey text is documented and acceptable.)

## config/defaults.py

- **Minor** — `defaults.py:1`. The docstring says "DRAFT (2026-09-10 ...), not yet wired into the
  app," but the file IS wired: `config/__init__.py` imports it as the live default source. Stale.
  Fix: update the docstring.

## recognizer/recognizer.py

- **Minor** — `recognizer.py:334`. `EN_NUM_REV = {v: k for k, v in EN_NUM.items()}` is unused
  anywhere. Dead. Fix: delete. (Otherwise this file is exemplary: pure, guard-claused, small
  helpers, every rewrite rule carries its own positives/negatives evidence.)

## recognizer/trace.py

- **Minor** — `trace.py:23-28`. `record()` opens and writes `trace.jsonl` with no guard, so a disk
  error raises into the caller — inconsistent with `session_log.py`, which treats the same class of
  write as best-effort. Pick one policy. Fix: match the session-log approach (log-and-continue) or
  document why the trace recorder is allowed to propagate.

## perception/detectors.py

- **Minor** — `detectors.py:35-36`. `except Exception as e: print("bg detect error:", e); return []`
  is a dense one-liner wrapping YOLO (third-party, so the catch is allowed). Fix: split the lines.

## perception2/counting.py

- **Minor** — `counting.py:35` `dup = True; break` dense one-liner. Otherwise clean and well-tested.
  Fix: split.

## recognizer/prompts.py

- **Minor** — `prompts.py:1-2` places `import json` / `import re` before the module docstring (lines
  3-10), making the docstring a dead literal (same defect as vlm_client.py). Fix: docstring first,
  imports after. (This file legitimately co-locates the bench prompts and the live UNIFIED_* prompts
  as the single home, which is fine.)

## cam_list.py

- **Minor** — Dense throughout (semicolon-chained statements at `cam_list.py:11, 13, 19, 23`; inline
  `if` at 33) and `open(f"{d}/name").read()` leaks a handle at line 13. It is a preflight utility, so
  low stakes, but it is dense. Fix: split statements; use `with`.

## test/ (stale environment variables)

- **Minor** — `test_pipeline_direct.py:2` sets `MVD_TRANSLATOR` and `test_scene_wiring.py:127` passes
  `MVD_HOME`/`MVD_TRANSLATOR` in the child env — all deleted in the restructure. Harmless (the code
  no longer reads them) but misleading. Fix: drop the dead env assignments.

---

## Notes on what is NOT a finding

- `raise SystemExit(1)` in the `__main__` selftests (`recognizer/recognizer.py`,
  `recognizer/selftest.py`, `perception/engine.py`, `perception2/concept.py`,
  `perception2/sam3_backend.py`) is idiomatic script-exit, not a swallowed app exception, and is fine.
- `fatal.die()` usage in `llama.py`, `tts_io.py`, `sam3_backend.py`, `mvd.build_highlight`, and
  `camera_stream.py` is exactly right: fatal invariants crash loudly with a fix line.
- The injected-callable `try/except` boundaries in `perception/engine.py` (around `detect`,
  `mask_for_box`, `vlm_ask`) correctly wrap third-party models and fail open by design.
- `audio/tts_io.py` is a clean implementation of the house SPSC mailbox idiom (one slot, lock,
  event, latest-wins) with correct `die()` on fatal TTS misconfig — no findings.
