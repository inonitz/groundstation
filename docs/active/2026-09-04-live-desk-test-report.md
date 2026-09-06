# Live desk test — preparation report (2026-09-04)

Author: groundstation-05 (live-test agent). For: the owner, and groundstation-3c (manager).
Status: five tasks prepared. Task 2 (quantization) executed after the owner ruled the types on
2026-09-04. The owner runs the boot scripts; the agent booted no stack.

## 1. Objective

Prepare `projects/integration_harden/` so the owner can boot it on his desk. The chain under test:
microphone -> Hebrew Whisper ASR -> Recognizer -> command or perception -> JSON on the REST wire
-> MOCK ApiServer that prints what it received. Real drone video arrives over `gstreamer_rx`.
Control goes to the mock, so a powered drone on the desk cannot be moved by our software.

## 2. Setup

- Branch `feature-hardening-mvd`. Ground state was taken as given from the manager's 14:50 check.
- The agent's container lacks the phone, a drone, ROS video, and (originally) `aiohttp`.
- The agent verified: syntax of every changed file, the mock's logging on a localhost port, the
  preflight logic, and the teardown port-free logic. The agent could NOT boot the full stack.
- `aiohttp 3.14.3` was pip-installed in the agent container only, to run the mock smoke test.
  This does not touch the owner's box, where `aiohttp` is baked into the devenv image.

## 3. Results

### 3.1 Task 1 — mock prints what it receives (DONE, verified)

File changed: `tools/dji_mock/mock_apiserver.py` (+34 / -3). A `log_cmd()` helper records each
REST command to the console and to a file. It is called in `/c/takeoff`, `/c/land`, `/c/stop`,
`/c/fly`. The log path is `MOCK_CMD_LOG`, default `${TMPDIR:-/tmp}/mock_commands.log`.

Smoke test on `127.0.0.1:8085` (localhost only, no drone, no phone):

| Verb | Response body (unchanged) | Log line written |
|---|---|---|
| `/c/takeoff` | `{"ok": true, "status": "takeoff"}` | `[mock-cmd] ... POST /c/takeoff` |
| `/c/fly` | `{"ok": true, "status": "starting mission", "mission_len": 2}` | `[mock-cmd] ... POST /c/fly {"mission":[...]}` |
| `/c/land` | `{"ok": true, "status": "landed"}` | `[mock-cmd] ... POST /c/land` |
| `/c/stop` | `{"ok": true, "status": "stopped"}` | `[mock-cmd] ... POST /c/stop` |

- The `fly()` response still reports `mission_len: 2`. The logger reads the body, but aiohttp
  caches the read, so `fly()`'s own `req.json()` still sees the body. Response shape unchanged.
- In `MOCK_SILENT_VERBS=1` mode, `/c/takeoff` still returns HTTP 204 with no body, and the
  command is still logged. The 204 behaviour did not change.
- Routes, the state integrator, the status endpoints, and the sticks WebSocket logging: untouched.

### 3.2 Task 2 — quantize Hebrew ASR (DONE — owner ruled q5_k/q4_k/q4_0 on 2026-09-04)

The `whisper.cpp` quantize tool does NOT accept the type string `q5_k_m`. This is verified.

Evidence — the tool's own accepted-type list (`whisper-quantize` with no args):

| Accepted type | q2_k | q3_k | q4_0 | q4_1 | q4_k | q5_0 | q5_1 | q5_k | q6_k | q8_0 |
|---|---|---|---|---|---|---|---|---|---|---|
| ftype id | 10 | 11 | 2 | 3 | 12 | 8 | 9 | 13 | 14 | 7 |

Passing `q5_k_m` against the real source model produced:

    ggml_parse_ftype: unknown ftype 'q5_k_m'
    ggml_common_quantize_0: invalid model type -1
    whisper_model_quantize: failed to quantize model
    exit code 1  (and a corrupt 596 KB partial file was left behind)

- `q5_k_m` / `q5_k_s` are llama.cpp mixture policies. whisper.cpp has no S/M selection.
- The 5-bit k-quant for Whisper is spelled `q5_k` (ftype 13). That is the direct equivalent.
- Per the brief, the agent STOPPED and did NOT substitute. No model was produced.

Owner ruling 2026-09-04: produce `q5_k`, `q4_k`, and `q4_0`. The agent ran all three from the one
fp16 source (`ggml-model.bin`, 1549.3 MB) with `tools/desk-test/quantize_hebrew_asr.sh`. All three
exited 0. The desk-test default is `ggml-model-q5_k.bin`, which now exists, so the model blocker
is cleared. `q4_k` and `q4_0` are the same size (both pack 4.5 bits/weight); they differ in
quality, not size. An inference-time and accuracy benchmark (perhaps FLEURS) is planned later.

Produced set:

| File | Size (bytes) | ftype |
|---|---|---|
| `ggml-model-q4_0.bin` | 473,992,235 (452.0 MB) | 2 (q4_0) |
| `ggml-model-q4_k.bin` | 473,992,235 (452.0 MB) | 12 (q4_K) |
| `ggml-model-q5_k.bin` | 574,041,195 (547.4 MB) | 13 (q5_K) |

Existing Hebrew quants on disk, for size comparison:

| File | Size |
|---|---|
| `ggml-model-q4_0.bin` | 452.0 MB |
| `ggml-model-q5_1.bin` | 595.2 MB |
| `ggml-model-q8_0.bin` | 833.7 MB |
| `ggml-model.bin` (fp16) | 1549.3 MB |

### 3.3 Task 3 — switch the app to Hebrew ASR (DONE)

File changed: `projects/integration_harden/run_mvd.sh` (+9 / -2), line 162 region.

- The ASR line now uses `--backend=$ASR_BACKEND --language=$ASR_LANGUAGE --model=$ASR_MODEL`.
- Defaults: `ASR_BACKEND=whisper-whisper`, `ASR_LANGUAGE=he`,
  `ASR_MODEL_PATH=/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q5_k.bin`.
- `--fa`, `--threads=1`, `--gid=0`, `--captureid` are unchanged, as required.
- English is restored WITHOUT editing the file:
  `ASR_BACKEND=whisper-parakeet ASR_LANGUAGE=en ASR_MODEL_PATH=<parakeet .bin> bash run_mvd.sh ...`
- `bash -n` passes. The default model file does not exist until Task 2 runs; preflight blocks on it.

### 3.4 Task 4 — desk-test scripts (DONE; boot path unverified)

New directory `tools/desk-test/`, five scripts. `bash -n` passes on all.

| Script | Purpose | Verified |
|---|---|---|
| `preflight.sh` | Fail loudly if a port, binary, model, tool, phone, or display is missing. Starts nothing. | Ran here; logic correct |
| `up.sh` | Preflight, start the mock, launch `run_mvd.sh dji mock` detached, mirror each pane to a log. | Syntax only |
| `down.sh` | Kill named processes, kill the `mvd` session, free ports 18090/18091/8079/8080/5600. | Port-free logic verified |
| `status.sh` | Read the run logs and print a compact status for diagnosis. | Syntax only |
| `quantize_hebrew_asr.sh` | The Task 2 quantize step, parametrized on type. | Not run (Task 2 blocked) |

- Logs collect under `${TMPDIR:-/tmp}/desk-test/<timestamp>/`, with `latest` pointing at the newest.
  One file per component: `mock.log`, `mock_commands.log`, `mvd_app.log`, `mvd_dicta.log`,
  `vlm.log`, `asr.log`, `gst.log`, `dog.log`.
- `up.sh` runs `run_mvd.sh` under a detached `script` pseudo-terminal. `run_mvd.sh` ends in
  `tmux attach`, which blocks and whose EXIT trap kills the session. The pty holds the attach open,
  so the session lives and `up.sh` returns. This pty mechanism is the one runtime assumption the
  agent could not test without a full boot.
- Preflight checks the phone is reachable (`ping`). Actual frame arrival cannot exist before
  `gstreamer_rx` starts, so `status.sh` confirms frames AFTER boot. This split is deliberate.

## 4. Analysis

1. `q5_k_m` is not a whisper.cpp ftype. The tool fails on it and leaves a corrupt partial file.
   A naive script would leave that 596 KB file looking plausible next to the real quants.
2. `q5_k` (ftype 13) is the whisper.cpp 5-bit k-quant and the direct equivalent of the intent.
   This is a recommendation, not a decision. The owner rules the type; the agent did not choose.
3. The mock change is additive. Every response shape and the 204 path are byte-identical.
4. The Hebrew switch is env-overridable, so a language flip needs no file edit and no second copy.
5. COMPLEX text runs synchronously on the ASR callback thread (translate + plan + wire). A long
   plan blocks the next utterance. This is read from the code, not measured. Label it unverified.
6. Real DictaLM says "Ascend ten meters", not "go up 10 meters". Whether the Qwen planner maps
   "Ascend N" to a correct `fly_by` dz is untested and is the most likely failure at the desk.

## 5. Test plan — the owner executes this

Prerequisite: rule on the ASR quant type, then produce the model.

    # 0. produce the Hebrew ASR model (after ruling; q5_k is the whisper.cpp equivalent of q5_k_m)
    bash /root/groundstation/tools/desk-test/quantize_hebrew_asr.sh q5_k

Boot (drone powered on the desk for VIDEO; control goes to the mock):

    # 1. preflight, then bring the whole test up (non-blocking)
    PHONE_IP=10.200.2.63 bash /root/groundstation/tools/desk-test/up.sh   # phone IP = WiFi gateway; up.sh auto-derives it too
    # 2. attach to watch the panes
    tmux attach -t mvd
    # 3. confirm both model servers are LISTEN before the first Hebrew word
    ss -tln | grep -E ':(18090|18091) '
    # 4. compact status any time (the agent can read this on request)
    bash /root/groundstation/tools/desk-test/status.sh
    # 5. tear down when finished
    bash /root/groundstation/tools/desk-test/down.sh

The first DictaLM call is slow on CPU. That is not an error.

Hebrew sentences, one per outcome kind, spoken into the microphone:

| Kind | Sentence | Expected |
|---|---|---|
| mission (bypass, no model) | עלה עשרה מטרים | `POST /c/fly` with a mission, printed by the mock |
| command (translate + planner) | טוס קדימה חמישה מטרים ואז הסתובב תשעים מעלות | a planned mission on the wire |
| perception (VLM) | מה אתה רואה עכשיו? | a VLM answer in the chat pane, no flight |
| emergency (router tier 4) | עצור | `POST /c/fly [{delay:0}]` (`wire.halt()`), NOT `/c/stop` |
| number-heavy (reject watch) | תעלה לי בעדינות עשרים מעלות ועוד שלושים | a normal plan, or a reject `לא הבנתי, שמעתי:` |

What the test must prove:

1. The `dicta` pane is healthy and 18091 is LISTEN.
2. A Hebrew movement command produces a mission on the mock. Capture the body verbatim from
   `mock_commands.log`.
3. A Hebrew see-question produces a VLM answer and does not fly.
4. `עצור` reaches `wire.halt()` (a `[{delay:0}]` fly body), not `/c/stop`.
5. The real-model chain works end to end: DictaLM translate -> Qwen plan -> mission. This has zero
   automated coverage today. It is the single most important point.
6. Record whether the Qwen planner maps DictaLM's "Ascend N" to a correct `fly_by` dz.
7. The boot printed "MVD drone router ON", not "drone router DISABLED". `status.sh` reports this.
8. Record what the ASR heard versus what was said, for every sentence (from `asr.log`).

Also record, unverified unless measured: roughly how long `on_text` blocks during a plan.

## 6. Conclusions and open items

- DONE and verified: Task 1 (mock logging), Task 3 (Hebrew ASR switch), Task 4 script logic where
  testable, the teardown port-free logic.
- DONE: Task 2. Owner ruled q5_k/q4_k/q4_0 (2026-09-04); all three produced from the fp16 source.
  `q5_k_m` remains unsupported by whisper.cpp; `q5_k` is its equivalent and is the desk-test default.
- UNVERIFIED (needs the owner's boot): the full `up.sh` boot, the `script` pty mechanism, live
  Hebrew ASR accuracy, and the DictaLM -> Qwen -> mission chain (test points 5 and 6).
- No git write was made. A commit block follows for the owner.
