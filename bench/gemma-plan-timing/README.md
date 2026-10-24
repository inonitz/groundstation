# gemma-plan-timing

This benchmark splits the time of one Gemma plan request into the server's own work and
the time around it. It exists because one app run showed a plan of 735 ms in the app
against 371 ms in llama-server's log, and nobody knew where the rest went (owner KI2,
2026-10-01).

| section | content |
|---|---|
| Method | what is measured and how |
| Run | the commands, start to finish |
| Results | the current scorecard |

## Method
- The app's Gemma client records each request's own time. Since 2026-10-01 it also records
  llama-server's own times from the reply: prompt_ms, predicted_ms and their token counts.
- "outside" = our time minus the server's prompt and generation time.
- Every plan goes through the app's real path: gemma.client.Gemma and Recognizer.plan().
- Gemma starts the way the app starts it, warm-up included (bench/recognizer start_gemma).
- Phase "first": the first plan after each of RESTARTS fresh starts and the app's warm-up plan.
- Phase "warm": PLANS plans on the warm server; the GPU is free.
- Phase "sam3": the same plans while a thread in the same process runs SAM3 without a
  pause. The app shares one process and one GPU the same way. A pause-free loop is a worst case.
- The sentences alternate between datasets/recognizer/commands.json and perception.json.

## Run
```
bash /root/groundstation/tools/lock.sh run main gpu -- python3 /root/groundstation/bench/gemma-plan-timing/plan_timing.py
```
Options: `--restarts 5`, `--plans 60`, `--no-sam3`. It takes a few minutes (estimate).
Results: results/<date-time>.json (every request) and results/<date-time>.md (the table).

## Results
Scorecard, 2026-10-01-0722 (results/2026-10-01-0722.md). Times in ms, p50 / p90 / max.

| phase | plans | ours | server | outside |
|---|---|---|---|---|
| first (after a start and the warm-up) | 5 | 549 / 584 / 584 | 512 / 548 / 548 | 37 / 38 / 38 |
| warm | 60 | 525 / 736 / 1207 | 489 / 699 / 1169 | 38 / 39 / 41 |
| sam3 (1.63 SAM3 passes/s) | 60 | 1401 / 2073 / 3223 | 1362 / 2034 / 3183 | 39 / 42 / 45 |

- The time outside the server is about 40 ms. One plan of 250 (both runs) took 497.7 ms outside it.
- SAM3 without a pause makes Gemma's own work 2.8 times slower.
- 2026-10-01-0715 ran the "first" phase without the warm-up: 1546 ms p50. Superseded for that row only.
