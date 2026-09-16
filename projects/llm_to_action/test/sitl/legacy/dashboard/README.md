# dashboard — headless SITL + live dashboard (self-assessing)

Brings up the `moving_person` FOLLOW demo with **Gazebo headless** (no GUI window)
and `FMU_OBSERVABILITY=1`, starts the dashboard bridge, and runs an assessor that
writes a PASS/FAIL verdict for the whole pipeline. Watch the demo in a browser
instead of a Gazebo window.

```bash
cd projects/llm_to_action/test/sitl-legacy/dashboard
./run.sh                                # demo: holds ~30 min, assesses once
HEADLESS_TIMEOUT_SECONDS=150 ./run.sh   # short self-test
DASH_PORT=9000 ./run.sh                 # pick the dashboard port
```

Open **http://localhost:8088** while it runs.

Outputs land in `./logs_<timestamp>/`:
- `verdict.txt` — PASS/FAIL with evidence (rates, width, HUD, website checks)
- `fmu.log` — FMU stdout: `[FMU_HUD]`, camera rx, perception, VLM, errors
- `dashboard.log` — bridge: subscription rates, requests, stream open/close
- `assess.log`, `sim.log` — assessor + stack bring-up output

The stack (PX4, gz, FMU, VLM) is a child process with its own cleanup trap; the
wrapper only owns the dashboard bridge. Needs PX4 built, gz, the ONNX vision +
Qwen VLM models, and MicroXRCEAgent.
