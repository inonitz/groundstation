# Thermo-nuclear review — rest of repo (2026-09-17)

Scope: the project code OUTSIDE `logs/`, `build/`, `projects/` — i.e. `tools/`, `bench/` (live
harnesses), and the root build glue. Method: 2 parallel read-only agents, thermo-nuclear standards,
static analysis + grep only (nothing run). Detail: `scratchpad/thermo-{tools,bench}.md`.

EXCLUDED, with reason (stated so you can override):
- `archive/` (5186 code files) — vendored third-party (ggml, depth-anything.cpp, a Python venv) +
  dead forks; purged at freeze. Reviewing it is meaningless.
- `docs/stale/` — stale, deleted at freeze. `docs/private/` — private.
- Retired bench campaigns (`depth-sota-bench`, `hebrew_asr`, `model-cpu-or-gpu`, `yolo26-depth-bench`)
  — archival; result docs kept, scripts not deep-reviewed.

No file-size (1000-line) violations in scope.

---

## Headline: the same two migrations broke bench tooling too

The translator retirement and the `tools/bench -> bench` restructure were applied to the app but
NOT finished in `bench/`. Several whole-system bench scripts are now **broken**, not merely messy —
they ImportError / read a retired JSON schema / glob an old path that no longer exists. They are
unused day-to-day (the live harness is `unified_bench.py`), which is why the breakage went unnoticed.

- `bench/whole-system/run_list.py:31` — `from bench import make_translator, plan`; both deleted in
  the 2026-09-12 retirement. Hard ImportError.
- `bench/whole-system/run_all.sh:22,29,32` — drives removed bench.py flags
  (`--translator/--perfect-en/--planner/--direct-he`); bench.py now takes only `--audit/--cases`.
  3 of 5 default lanes are dead.
- `bench/hebrew-command-bench/compare_runs.py:14` — reads the retired schema
  (`d["recognized"]`/`payload`/`translator`); unified_bench writes `rows`/`obj`/`verdicts` -> KeyError.
- `bench/whole-system/planning_table.py:26` — expects 3 retired stacks
  (`*-recognizer-{gemma4-direct,hymt2,dicta}`); unified_bench writes one `*-unified-gemma4.json` ->
  SystemExit.
- Stale `tools/bench/` path in 5 files (vlm_compare.py:18, sam3_alone.py:13, vision_chain.py:11,
  overlays.py:11, planning_table.py:6): the restructure moved `tools/bench -> bench` (verified
  absent), so globs return empty -> `cv2.imread(None)` / ImportError.

NOTE: these are the SAME two bug classes I squashed inside `integration_harden2` (stale `tools/bench`
paths + translator-retirement dead code). They persist in `bench/` because that sweep was scoped to
the frozen tree. `bench/` needs its own pass.

---

## Duplication (code-judo targets)

- **SAM3 `detect()` copy-pasted 4x** — measure.py, run_indepth.py, run_suite.py, run_web.py hand-roll
  raw-transformers SAM3, while `perception2.Sam3Backend` is the single home already used by
  quant_bench/sam3_alone/vision_chain/overlays. A "one component, one home" violation with a ready fix.
- **`build.ps1` is a drifted twin of `build.sh`** — hand-maintained second arg-parser that already
  lost the `dji` backend and the live MVD target. Dev runs in the Linux container. Delete it (~110
  lines, a second source of truth, and a correctness bug gone).
- **Two WS-RTT probes** — `ws_latency.py` (drags in the `websockets` dep) vs `measure_ws_rtt.py`
  (pure stdlib) measure the same hop. Delete ws_latency; add a server echo mode to measure_ws_rtt.
- **DJI-probe scaffolding copy-pasted** — `measure_telemetry.py:14-38 == measure_ws_rtt.py:19-43`
  (identical `preflight()`+`HINTS`), and `pct()` reimplemented 6x with DIVERGENT index math
  (power_profile.py:120 is off-by-one vs the rest). Extract one `_djiprobe.py`.
- **mock_apiserver.py** — quick_takeoff/quick_land duplicate takeoff/land bodies; `batteryPct -= 0`
  is dead code posing as drain; json-or-None try/except copy-pasted 5x.

## Single highest-value code-judo (bench): one shared bench-support module
Own in one place: (a) ROOT + `bench/` paths + `image_set()`/`load_frame(1280)`; (b) SAM3 via
`Sam3Backend` only (deletes the 4 raw-transformers copies); (c) llama-server lifecycle +
`MODELS`/`PORT` re-exported from the component `llama` module (deletes vlm_compare.py's private
`start_server/stop_server/PORT=18090/MODELS` and the scattered `18090`/model-path literals that
duplicate the app wire config); (d) `iou`/`pct`/`draw_overlay`. Removes ~4 backend copies + a
duplicate server spinup + triplicated glob/resize, and centralizes the path so the `tools/bench`
breakage cannot recur.

## Other stale / hardcoded
- `watch_503.sh:4` hardcodes a stale phone IP `10.222.215.92`, violating the "derive from `ip route`,
  never hardcode" rule its siblings follow.
- `build.sh:66-79` — `debug_perf`/`release_perf` emit the same cmake config as `debug`/`release`, only
  renaming the output dir; wire real perf flags or drop them.

---

## The healthy model to copy
`bench/hebrew-command-bench` is the good structure: `bench.py` is thin shared infra importing the
component in place (no copies), `unified_bench.py` is the one harness, `cases_*.py` are pure data,
single non-duplicated scorers. The SAM3 and whole-system dirs lack exactly this and should converge
on it.

## Recommended actions (owner rules each)
1. Fix or delete the 5 broken whole-system scripts + the 3 dead run_all.sh lanes + the 5 stale
   `tools/bench` paths. These are the same migrations finished for bench/.
2. Build the shared bench-support module; delete the 4 SAM3 copies + vlm_compare private spinup.
3. Delete build.ps1; collapse the two WS probes; extract `_djiprobe.py` (fixes the pct off-by-one).
4. Fix watch_503.sh hardcoded IP; resolve build.sh perf flags.

Confidence: the broken-script findings are grep/import-graph verified (high). Nothing here was run.
No correctness bug found in the LIVE app path; these are dead/broken TOOLING and duplication.

---

# Ponytail cross-check (ultra) — 2026-09-17

Independent over-engineering audit (ultra: deletion-first). Confirmed all thermo findings, corrected
two facts, added new cuts. Detail: `scratchpad/ponytail-tools-bench.md`.

## Corroboration + fact corrections
- build.ps1 drifted twin — CONFIRMED (its backend set is `px4,tello,all`, missing `dji`).
- ws_latency.py duplicates measure_ws_rtt.py + is the sole `websockets` importer — CONFIRMED.
- copy-pasted DJI-probe scaffolding — CONFIRMED, corrected: identical `preflight()`+`HINTS` are in
  measure_telemetry.py + measure_ws_rtt.py (NOT power_profile.py); `pct()` copied 4-5x; the off-by-one
  is power_profile.py ~:118 (`int(q/100*len(s))` vs canonical `int(round(q/100*(len(s)-1)))`).
- SAM3 detect() copied 4x vs perception2.Sam3Backend — CONFIRMED.
- broken bench scripts from the two migrations — CONFIRMED, corrected: the stale `tools/bench` path
  is in 6 files (add run_list.py), not 5.

## New cuts ponytail added
- delete plot_latency.py (77 lines, sole matplotlib user; hardcodes a 2026-08-22 run title).
- yagni install-translation-models.sh — dead after the translator retirement (opus/nllb/madlad/
  translategemma fetches unused; ~40 lines + 5 downloads + the `sentencepiece` dep). Owner-confirm.
- yagni build.sh debug_perf/release_perf — identical cmake to debug/release, only a renamed out dir.
- stdlib: box-IoU reimplemented 3x (vlm_compare.py, vision_chain.py, compare_engines.py) — one helper.
- delete mock battery-drain placeholder (`batteryPct -= 0` does nothing).

## Consolidated removable estimate (tools + live bench)
~500-560 lines. Biggest deletes: ws_latency.py (~105), build.ps1 (~92), plot_latency.py (77),
compare_runs.py (56). Removable deps: `websockets`, `matplotlib`, and (if the translated path is
confirmed retired) `sentencepiece` + 5 translation-model downloads. STATIC estimate; verify before cutting.
