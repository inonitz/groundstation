# vlm test

Full VLM-driven run (Qwen3-VL): the planner issues the verbs, no canned plan.

- **Canned plan flag:** `(none — VLM-driven)`
- **World:** `default_car`   **Spawn:** `0,7,3`
- **Filter:** milestone digest (VLM wake/plan, GO, APPROACH) — no PASS/FAIL.

## Run
```
cd scripts/test/vlm
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- Needs the model at /root/models/vlm and a Vulkan device (extra llama-server pane).
- `VLM wake` -> `VLM plan received` -> the FMU executes the planned GO/APPROACH verbs.
- Behavior is prompt-dependent; watch whether the plan is sane and it lands.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
