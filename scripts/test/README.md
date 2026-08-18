# SITL feature tests

One folder per feature. Each is self-contained: `cd` in, run the sim, watch it,
filter the logs, write what you saw, hand the folder's `README.md` back.

## Layout
```
scripts/test/
  lib/sim_core.sh     # shared launch engine (sourced by every run.sh) -- single source of truth
  <feature>/
    run.sh            # sets this feature's knobs, then `source ../lib/sim_core.sh`
    filter.sh         # captures panes -> captured_panes_log.txt + digest + PASS/FAIL
    README.md         # expected behavior + a slot for your observations
```

## Workflow
```
cd scripts/test/<feature>
./run.sh                 # terminal 1: sim comes up; watch the drone
./filter.sh              # terminal 2 (after it lands): prints the digest
# write your observations into README.md, then hand README.md back
```

## Add a new feature
Copy any `<feature>/` folder, then in its `run.sh` set `FMU_OBJECTIVE`,
`FMU_SCENARIO_FLAG`, `WORLD_NAME`, `SPAWN_POSE` (see `lib/sim_core.sh` header for all
knobs, incl. `LAUNCH_VLM=1` and `DRAIN_BATTERY=1`). Point `filter.sh` at the right
mode (`rotate` or `land`). No engine code to copy — that lives once in `lib/sim_core.sh`.

Note: the old monolithic `scripts/simenv_llm.sh` has been removed. Its launch logic now
lives once in `lib/sim_core.sh`, which every `run.sh` sources.
