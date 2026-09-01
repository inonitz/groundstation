# test/sitl -- consolidated SITL suite

One runner + one config replace the old 20 per-scenario directories, `scripts/sandbox`, and
`run_all.sh`.

```bash
./run.sh --list                          # scenarios + verdict quality + world + tags
./run.sh hover                           # attended tmux run of one scenario
./run.sh --free "explore the area"       # free-form VLM-driven run (the old sandbox)
./run.sh --verdict hover                 # PASS/FAIL from the last run's captured log
./run.sh --all                           # headless sweep of every verified scenario
SKIP_HIGH_VRAM=1 ./run.sh --all          # skip the ~12GiB LAUNCH_VLM scenarios
```

- `scenarios.conf` -- the scenario table (knobs, completion mode, verdict quality, tags).
- `verdicts/<name>.sh` -- per-scenario PASS/FAIL logic, ported verbatim from the old filter.sh
  files. `digest`-quality verdicts only print milestones (always exit 0) -- eyeball those attended.
- `runs/<name>/` -- per-run workdir; the FMU log lands there (gitignored).
- `SCENARIOS.md` -- what each scenario proves, concatenated from the old per-scenario READMEs.
- Engine: `../lib/sim_core.sh` (unchanged launch logic; roots derived, worlds from
  `assets/gz_world/`). Headless runs auto-waive the PX4 GCS preflight check
  (`PX4_PARAM_NAV_DLL_ACT=0`).
- `../sitl-legacy/` -- the old tree, kept until this suite has survived one full `--all` sweep;
  then it gets deleted.
