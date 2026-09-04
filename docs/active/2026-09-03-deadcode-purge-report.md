# Dead-code purge — projects/integration_harden (Tier 1 + real bugs)

## Objective

Execute the Tier-1 deletions and the four real-bug fixes from `docs/active/nuclear-code-review.md`.
Every deletion was gated on an independent zero-caller grep across `projects/integration_harden`
and `tools/`. A symbol with a live caller was skipped, not deleted.

## Setup

Branch `feature-hardening-mvd`. Scope limited to seven files under `projects/integration_harden`.
`recognizer/`, `tools/bench/`, and `test/test_recognizer.py` were edited concurrently by another
agent and were not touched here. Greps were call-shaped (`\.name(`, `config.NAME`) because the
plain word-boundary form matched docstrings and unrelated identifiers.

## Results

| # | Item | Action | Lines (+/-) | Zero-caller evidence |
|---|---|---|---|---|
| 1 | `Grounder`, `YoloeHighlighter`, `Eyes._init_highlighter/set_target/highlight` | deleted | +6/-144 | `SCENE_HL_BACKEND` is pinned to `"vlm"` at `scene_omdet.py:15`, so the branch is unreachable. `.set_target(` and `.highlight(` have zero callers outside `detectors.py`. `Eyes.background`/`mask_for_box` kept (`scene_omdet.py:74,167`). |
| 2 | `nudge()`, `_stream_sticks()`, `STREAM_HZ` | deleted | see #3 | `.nudge(` and `._stream_sticks(` return zero hits outside `dji_wire.py`. `aiohttp` was NOT removed from any install script — see Analysis 1. |
| 3 | `fly_to`, `fly_circle`, `fly_square`, `look_at`, `delay`, `report_status`, `REPORT_METRICS`, `fly_to_gps`, `look_at_gps`, `tts`, `key`, `status_sub` | deleted | +6/-95 (whole file) | Each `.name(` grep returns 0 outside `dji_wire.py`. Every verb `router.py` calls is kept: `takeoff`, `land`, `stop`, `halt`, `fly_mission`, `spin_by`, `fly_by`, `gimbal_pitch`, `scan_ground`, `go_home_to_user`, `follow_me`, `track_me`, `wave`. |
| 3a | `DjiWire.status()` | **SKIPPED** | 0 | Zero method callers, but `GET /status/` has three hand-rolled consumers (`test/live_mock_smoke.py:31`, `video/video_doctor.py:47`, `tools/dji_mock/measure_telemetry.py:12`) and CLAUDE.md classifies it as the SAFE read-only lane. Deleting the only typed accessor for a live endpoint deepens the duplication instead of removing it. Four lines. Overrule in one line if you disagree. |
| 3b | `DEFAULT_SPEED_MPS`, `DEFAULT_YAW_DEG_S`, `DEFAULT_NUDGE_S` | **SKIPPED** | 0 | Live caller: `control/router.py:44` uses all three as `Router.__init__` defaults, imported at `router.py:17,21`. `router.py` is out of scope. Deleting them broke every test; restored with a comment naming the real consumer. |
| 4 | `_scale_objects`, `analyze`, `ground`, `SYSTEM_ANALYZE` | deleted | +0/-84 | Zero hits for each outside `vlm_client.py`. `ask`/`parse_reply` are the only live entrypoints. |
| 5 | `WIN_NAME`, `RECORD`, `PERF`, `DETECT_HZ`, `HIGHLIGHT_HZ` | deleted | +7/-35 (whole file) | Zero `config.NAME` readers repo-wide. |
| 5a | `OPENVOCAB_MODEL`, `CONF_HL`, `GROUNDER_REPO`, `GND_BOX_THR`, `GND_TEXT_THR`, `GND_TOPK`, `WARMUP`, `HIGHLIGHT_BACKEND`, `VLM_COORD_SCALE`, `VLM_MAX_OBJECTS` | deleted | included above | Each was read only by code deleted in items 1 and 4; zero readers afterwards. |
| 5b | Stale LLMDet/YOLOE lineage comments | rewritten | included above | The eyes header and the `COL_YOLOE_HL` comment now describe the live OmDet + VLM-gate + SAM2 design. `COL_YOLOE_HL` keeps its name because renaming it would touch out-of-scope `scene_omdet.py:112,302`. |
| 5c | `COL_VLM_BOX`, `COL_TEXT` | **SKIPPED** | 0 | Zero readers, but they are two rows of the four-source overlay colour table. Deleting half a table is worse than keeping it, and they were not on the review's list. |
| 6 | `TTS_BACKEND` default `"both"` -> `"phone"` | fixed | +3/-2 | Changed in both places: `config.py` env default and the `Voice.__init__` fallback. `"both"` still works when asked for explicitly; the docstring now states that it speaks every answer twice. |
| 7 | `video_watchdog` respawning `--dji None` | fixed | +7/-2 | `respawn_gst()` now prints a loud `NO WIFI GATEWAY` banner and returns `None` without respawning; the caller only prints the reconnect line when an IP came back. |
| 8 | VLM-box fallback skipped mask hygiene | fixed | +2/-12 | The fallback box now goes through `self.apply_masks(frame, [fallback], use_sam)`, the same call the primary path uses. Garbage-mask drop, box tightening, and the `BOX_MAX_FRAC` check now apply to both paths. |
| 9 | `detectors.py` docstring/path mismatch | fixed | included in #1 | The docstring named `/root/models/omdet-turbo-swin-tiny`; `LOCAL` is `/root/models/vision/omdet-turbo-swin-tiny`. The docstring now refers to `LOCAL` instead of repeating the path. |

Net for the seven files in scope: **+31 / −374**. File sizes after: `detectors.py` 268 -> 124,
`dji_wire.py` 246 -> 157, `vlm_client.py` 200 -> 116, `config.py` 116 -> 88.

## Verification

| Check | Outcome |
|---|---|
| `python3 -m py_compile` on all seven touched files | OK |
| `python3 -m pytest projects/integration_harden/test/ -q` | **26 passed**, no shrink |
| `python3 projects/integration_harden/perception/engine.py` | self-test CLEAN |
| `python3 integration_harden/test/live_mock_smoke.py` (from `projects/`) | LIVE MOCK SMOKE PASSED |
| `python3 -c "import scene_omdet"` (from `integration_harden/`) | scene_omdet import OK |
| `python3 tools/bench/hebrew-command-bench/bench.py --audit` | audit CLEAN |

No test needed adapting. No test referenced a deleted symbol: `test_router.py:43,73` defines
`nudge` on its own fake wire and asserts the router never calls it, which stays a valid regression
guard against re-introducing a stick lane.

## Analysis

1. The review's claim that deleting `nudge()` removes the `aiohttp` dependency is **wrong**.
   `tools/dji_mock/mock_apiserver.py` imports `aiohttp` and serves the whole mock on it
   (`web.get("/status/", ...)` at line 190). `aiohttp` was left in every install script and
   Dockerfile. Deleting it would break `live_mock_smoke.py`, which is a required gate.
2. Two of the review's Tier-1 items were not actually dead. The three `DEFAULT_*` constants have a
   live consumer in `router.py`, and `status()` is the typed home for an endpoint with three
   consumers. Both were caught by grep before merge, not by the review.
3. `scene_omdet.py:15` still sets `SCENE_HL_BACKEND=vlm`, which is now an orphan env default since
   `config.HIGHLIGHT_BACKEND` is gone. It is inert. Removing it is a one-line follow-up, left to
   whoever owns `scene_omdet.py` next, since that file is being edited concurrently.
4. The engine fix in item 8 is a behaviour change, not just a refactor: a near-full-frame VLM
   fallback box with a garbage mask is now dropped instead of drawn. That is the intent of the
   review finding. The self-test's fallback case still passes because its box is 9% of the frame.
5. Item 2 removes one of the two motor-command paths on a safety-critical client. `/c/ws/sticks`
   is no longer reachable from Python; every flight verb now goes through `POST /c/fly`.

## Changed files

- `projects/integration_harden/perception/detectors.py`
- `projects/integration_harden/perception/vlm_client.py`
- `projects/integration_harden/perception/engine.py`
- `projects/integration_harden/control/dji_wire.py`
- `projects/integration_harden/config.py`
- `projects/integration_harden/audio/tts_io.py`
- `projects/integration_harden/video/video_watchdog.py`
