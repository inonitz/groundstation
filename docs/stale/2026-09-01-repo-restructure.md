# Repo restructure -- monorepo layout (2026-09-01)

Owner-directed restructure, executed by the agent under an explicit owner override of the
run-no-git-writes rule, granted 2026-09-01 for this restructure only. The repo-destruction
rule (no force-push family, ever) and the drone-safety rules were and are untouched by that
override. Decision inputs: the churn heatmap (`2026-09-01-repo-churn-heatmap.md`) and the
owner's monorepo ruling -- each sub-project owns its `source/`, `include/`, `test/`.

## The layout

- `projects/integration` -- the FROZEN field-tested MVD fallback. Only path strings were
  updated so it still runs from its new home; logic untouched.
- `projects/integration_notify` -- notify-demo fork.
- `projects/integration_tts` -- TTS fork, the going-forward base.
- `projects/integration_harden` -- the interview-sprint fork (copied from integration_tts;
  renamed from the earlier `integration_sprint`). Gains `test/` with the router tests.
- `projects/llm_to_action` -- the C++ stack: `source/` (as before, `include/` split is
  post-sprint), `test/lib` (sim engine), `test/sitl` (consolidated suite), `test/sitl-legacy`
  (old tree, deleted after one clean `--all` sweep).
- `projects/slam` -- C++ VSLAM work, `source/` only.
- `tools/` -- `dji_mock/` (shared mock API server), `devenv/` (Dockerfile + devenv scripts +
  `install-runtime-deps.sh`), `prewarm_llama.sh`, `preflight.sh`.
- `archive/` -- revivable dead code: `tello/`, `slam-tests/`, `llm_cv_scene/`, `llm_cv_track/`.
- `docs/` -- `active/` (live working docs) · `runbooks/` (how to run things) · `specs/`
  (durable designs) · `research/` · `stale/` (superseded; git history is the real archive).
- Deleted outright (spent one-offs; git history keeps them): `scripts/sandbox` (now
  `run.sh --free`), `run_fmu_mock.sh`, `mix_noisebed.py`, `yolo-quality/`, the two build.sh
  stubs, the `colors` scenario (depended on archived slam code), run_all's six phantom
  scenarios, `dependencies/` (symlink shim; CMake + sim_core now point at `assets/` directly).

## SITL consolidation

20 scenario dirs + sandbox + run_all.sh became `test/sitl/{run.sh, scenarios.conf, verdicts/,
SCENARIOS.md}`. Verdict logic ported verbatim; config gained honest verdict-quality labels
(verified / digest / unverified) and completion modes. Headless runs auto-set
`PX4_PARAM_NAV_DLL_ACT=0` (the GCS preflight waiver run_all never set -- headless sweeps
before this likely never armed).

## Gates run (2026-09-01)

- Router tests: 11/11 pass against `integration_harden` (pytest).
- C++ dji backend: configure + build green after the CMake repoints (fresh
  `llm_to_action_fmu_dji`, 43s incremental).
- Headless SITL hover through the new runner: launches end to end from the new paths
  (worlds resolved from `assets/gz_world`, FMU + camera + PX4 up). First run hit the known
  GCS arm-refusal (fixed in the runner, see above); the re-run PASSED: armed, flew the
  forward leg, HOVER held with no reversal -- `run.sh --verdict hover` returned PASS.
- `tools/preflight.sh` PASS after `install-runtime-deps.sh` (found aiohttp eaten by a
  container rebuild; TTS binaries still absent -- C5c install script still owed).

## Known warts / follow-ups

- `sim_core.sh` prints a pre-existing `line 131: 1: command not found` (quoting inside
  CMD_PX4); cosmetic, PX4 launches fine. Fix during the post-sprint rewrite.
- px4/tello C++ backends not rebuilt (only dji gate run); first px4 build will just take longer.
- `projects/slam` C++ test comments still mention old paths (comments only).
- `include/` split for the C++ projects: post-sprint, with the rewrite.
- `sitl-legacy` deletion pending one clean `--all` sweep.
- NOTES.md untouched by owner ruling.
