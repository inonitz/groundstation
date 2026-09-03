# Structure pass — projects/integration_harden (review items 8, 10, 11, 12, 15)

## Objective

Execute the Tier-3/4 structural items from `docs/active/nuclear-code-review.md`, then close the pass:
verify what landed, finish what a stopped mid-run had left, and prove every gate. Behaviour-preserving
throughout: no verb, threshold, or wire call changed. `recognizer/`, `tools/bench/`, and
`test/test_recognizer.py` were untouched.

## Setup

Branch `feature-hardening-mvd`, on top of the 2026-09-03 dead-code purge. Every claim of deadness was
re-verified by grep before deletion. The config value surface was snapshotted before and after its
rewrite and proven byte-identical. No test needed adapting.

## Results (final)

| # | Item | Action | Notes and evidence |
|---|---|---|---|
| 8 | `scene_omdet.on_text` megafunction | decomposed | Became a module-level `TextHandler(router, voice)` whose `__call__` is a 14-line dispatch over `_handle_drone/_handle_clear/_handle_highlight/_handle_ask`; the two inline thread bodies became `_gate_thread`/`_ask_thread`. Every branch body is byte-for-byte the old logic. |
| 8a | `scene_omdet.py` orphan env default | deleted | `os.environ.setdefault("SCENE_HL_BACKEND", "vlm")` had no reader left after `config.HIGHLIGHT_BACKEND` was removed. |
| 10 | config.py god-bag | **kept as ONE file, rewritten for navigation** | An interrupted attempt had split config into `config_pkg/` (7 files) behind no facade -- nothing imported it, so it was orphaned. Decision (owner, 2026-09-03): keep a single `config.py`, made as navigable as the split -- a table-of-contents header and seven uniform, searchable section banners (VLM / eyes / ears / camera / colours / TTS / resolvers). `config_pkg/` was deleted. The 29-constant surface and all defaults are unchanged; a pre/post value snapshot proved them identical, and `default_gateway()`/`resolve_device()` return the same values. |
| 10a | `COL_VLM_BOX`, `COL_TEXT` | deleted | Zero readers repo-wide (re-verified). The colour legend draws three overlay sources, not four; the comment was corrected. |
| 11 | Gateway resolution duplicated 3x | one helper | `config.default_gateway()` is the single home; returns `None` with no default route (callers must handle it). `tts_io._resolve_phone_host` keeps its override chain and ends in `default_gateway() or ""`; `video_doctor` and `video_watchdog` import it. |
| 11a | Hardcoded `"camera/stream"` | imports `TOPIC` | `video_doctor` and `video_watchdog` import `TOPIC` from `video.camera_stream`; the live-source check uses `camera_stream.ROS_SOURCES`. |
| 12 | Three rclpy frame-count subscriptions | shared `FrameCounter` | `FrameCounter(topic, node_name)` context manager owns the node, its own executor, and the spin thread; both consumers use it. |
| 12a | Core-dump-on-teardown fix | extracted | `_teardown(spin, executor, node)` does join-before-`destroy_node` in one place; `CameraStream.release()` delegates to it. |
| 15 | `control/router.py` dead import fallback | deleted | Every import site is a package import; `control/__init__.py` exists so the relative branch always wins. Both import styles are exercised by the passing suite. |
| b | `run_mvd.sh` watchdog launch | now `-m` | The `dji` watchdog window runs `cd $HERE && python3 -m video.video_watchdog` (was a loose-file `python3 .../video_watchdog.py`). `video_watchdog` runs its monitor at module top level, so `-m` is the correct launch. |
| c | `video_doctor` docstring | documents `-m` | Header shows `cd .../integration_harden && python3 -m video.video_doctor`; verified accurate. |
| d | integration_harden README | matches reality | The webcam-check line now reads `cd .../integration_harden && python3 -m video.camera_stream 0`, the invocation the module documents (was a loose-file path). |
| 15b | `camera_stream.py` self-test path shim | removed | The old `sys.path` insert is gone; only an explanatory comment remains, and `-m video.camera_stream 0` is the documented self-test (verified: 18 real webcam frames in 3 s). |

The app launch itself (`scene_omdet.py`) still runs as `python3 scene_omdet.py`; converting it to `-m`
was not in scope and is left as-is.

## Verification (all green, re-run at closure)

| Check | Outcome |
|---|---|
| `py_compile` config.py; `bash -n` run_mvd.sh | OK |
| `import config` / `import scene_omdet` | OK (config: 33 public names, 29 constants) |
| config value snapshot, pre vs post rewrite | IDENTICAL |
| `pytest projects/integration_harden/test/ -q` | 26 passed |
| `perception/engine.py` self-test | CLEAN |
| `recognizer/recognizer.py` self-test | CLEAN |
| `tools/bench/hebrew-command-bench/bench.py --audit` | CLEAN |
| `live_mock_smoke.py` from `projects/` (mock only) | PASSED |
| `python3 -m video.camera_stream 0` | 18 webcam frames, 1280x720 |

## Analysis

1. **The config stayed one file, and was made to read like the split.** The split into `config_pkg/`
   was real work but never wired in -- an orphan. For a 119-line config with ~29 settings, a single
   file with a table-of-contents and uniform section banners gives the same "jump to concern"
   navigation without a re-export layer that would add a hop to every value trace. The one file is
   authoritative; `config_pkg/` is deleted.
2. `video_watchdog` and `video_doctor` carry the house-rule `sys.path` insert so `video.camera_stream`
   has exactly one module identity; that is what makes the shared helper safe to import from a script,
   not a shim.
3. `video_doctor` gained a `NO DEFAULT ROUTE` verdict, the same root cause as the `--dji None` bug:
   a `None` gateway must never be printed or passed as a literal.
4. `TextHandler` holds `router`/`voice` as fields; shared frame and chat state stays in the module-level
   `S`, so locking is unchanged.

## Changed files

- `projects/integration_harden/scene_omdet.py`
- `projects/integration_harden/config.py`  (rewritten header + banners; values unchanged)
- `projects/integration_harden/config_pkg/`  (created by the interrupted split, now REMOVED)
- `projects/integration_harden/audio/tts_io.py`
- `projects/integration_harden/video/camera_stream.py`
- `projects/integration_harden/video/video_doctor.py`
- `projects/integration_harden/video/video_watchdog.py`
- `projects/integration_harden/control/router.py`
- `projects/integration_harden/run_mvd.sh`  (watchdog launched via `-m`)
- `projects/integration_harden/README.md`  (webcam check via `-m`)
