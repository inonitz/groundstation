# Live desk test — session brief for the live-test agent (2026-09-04)

Author: groundstation-3c (manager). Executor: groundstation-05 (live-test agent).
Owner ruling date: 2026-09-04. This document stands alone. Read it in full before acting.

## 1. Objective

Bootstrap `projects/integration_harden/` into a system that actually runs on the owner's desk.

The chain under test, in order:

    owner's microphone -> Hebrew Whisper ASR -> Recognizer -> command or perception
      -> JSON on the REST wire -> MOCK ApiServer (which prints what it received)

At the same time, real drone video arrives over `gstreamer_rx` from the phone MSDK server.
Video is one-way. A powered drone on the desk is safe, because control goes to the mock.

This is the first end-to-end boot of the wired app. It is the gate before any real flight.

## 2. Roles — these are hard, and owner-ruled

- The AGENT writes and adapts scripts. The agent does not boot the stack.
- The OWNER runs every script. He speaks the Hebrew into the microphone.
- The agent never runs the app, the mock, `run_mvd.sh`, or any control tool.
- All logs collect to files. The owner may ask the agent to read a log mid-session and diagnose.
- The scripts must work without the agent present. They must be seamless.
- The agent runs NO git writes. Prepare a commit block in house style; the owner runs it.

## 3. Safety rails — absolute, from CLAUDE.md

- Control target for the desk test is the MOCK at `127.0.0.1:8079`. Never a phone IP for CONTROL.
- The phone IP IS used for VIDEO only (`gstreamer_rx --dji <PHONE_IP>`). That is one-way and safe.
- Never run `run_mvd.sh` with the `real` argument. That is a human-only path.
- Never run `dji_latency_probe` or `dji_backend_mock_test` against anything but `127.0.0.1`.
- The drone will be POWERED on the desk to stream video. Our software cannot spin its motors,
  because control goes to the mock. Do not send any control command yourself regardless.
- Do not weaken, bypass, or "temporarily" relax any of the above to make a test pass.

## 4. Ground state — verified by the manager on 2026-09-04, about 14:50

- Tree clean. Branch `feature-hardening-mvd`.
- `python3 -m pytest projects/integration_harden/test/ -q` -> 32 passed.
- `python3 tools/bench/hebrew-command-bench/bench.py --audit` -> CLEAN.
- GPU free: 110 MiB of 8151 MiB, zero compute processes.
- Ports 18090, 18091, 8079, 8080 all free. No tmux session exists.
- Binaries built and present in `/root/groundstation/build/release/shared/dji/bin`:
  `llm_to_action_asr_server`, `llm_to_action_keyboard_hook`, `llm_to_action_gstreamer_rx`.
- Webcam devices present: `/dev/video0`, `/dev/video1`.

## 5. Verified technical facts — do not re-derive these

The manager read the code and confirmed each one. Treat them as given.

| # | Fact | Evidence |
|---|---|---|
| 1 | `PhoneEars` starts by default and injects text straight into `on_text`. It binds `MVD_PHONE_ASR_PORT`, default 8080. A `POST /input` with `{"text":"..."}` injects a transcript. Identical text inside 1.5 s is deduped. | `scene_omdet.py:299`, `audio/phone_asr.py` |
| 2 | Mock control is `127.0.0.1:8079`. `PhoneEars` owns 8080. They do not clash. | `run_mvd.sh` |
| 3 | The ASR binary supports `--backend=whisper-whisper` with `-l/--language` and `-m/--model`. Backends offered: `whisper-whisper`, `whisper-parakeet`, `sherpaonnx-parakeet`, `sherpaonnx-whisper`. | `llm_to_action_asr_server --help` |
| 4 | `run_mvd.sh` line 162 hardcodes `--backend=whisper-parakeet --language=en`. This cannot transcribe Hebrew. | `run_mvd.sh:162` |
| 5 | `EMERGENCY_RE` is BILINGUAL: `stop\|emergency\|abort\|halt\|freeze\|mayday\|kill\|cut` plus `עצור\|עצרי\|עצרו\|תעצור\|תעצרי\|תעצרו\|סטופ\|חירום`. The emergency stop survives the ASR language switch. | `recognizer/recognizer.py:43` |
| 6 | The router's basic-verb table is ENGLISH-keyed. With Hebrew ASR those verbs never fire, so every non-emergency utterance goes COMPLEX into the Recognizer. This is the intended architecture. DO NOT "fix" it. | `control/commands.py` |
| 7 | The mock's `fly()` reads the `/c/fly` body and discards it. It returns only a step count. `takeoff`, `land` and `stop` print nothing. Only the sticks WebSocket logs. | `tools/dji_mock/mock_apiserver.py:145` |
| 8 | Latency instrumentation today is one total `ms` per utterance, Recognizer only. It does not split translate, plan, wire or perception time, and records nothing for ASR. | `recognizer/trace.py`, `recognizer/pipeline.py:83` |
| 9 | `run_mvd.sh` ends in `tmux attach`, which blocks the caller. | `run_mvd.sh` |
| 10 | `scene_omdet` opens an OpenCV window and needs a display. The owner has one. Nothing runs headless. | `scene_omdet.py` |

## 6. Task 1 — make the mock print what it receives

File: `/root/groundstation/tools/dji_mock/mock_apiserver.py`

The owner's requirement: the mock intercepts the REST commands and outputs them to console and file.
Today it does not. That is gap (a).

- Log every received REST command: timestamp, method, path, and the FULL JSON body.
- Write to the console AND to a file.
- The file path comes from an environment variable, default `${TMPDIR:-/tmp}/mock_commands.log`.
- Cover `/c/fly`, `/c/takeoff`, `/c/land`, `/c/stop`. The sticks WebSocket already logs; leave it.
- Keep every response shape byte-identical. The `SILENT_VERBS` 204 behaviour must not change.
- Do not change the routes, the state integrator, or the status endpoints.

Constraint: the mock must remain a faithful stand-in for the phone app. Logging is additive only.

## 7. Task 2 — quantize the Hebrew ASR model to q5_k_m

OWNER RULING, 2026-09-04: quantize `whisper-large-v3-turbo` to `q5_k_m`.

- Source: `/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model.bin` (fp16, 1549.3 MB).
- Target type: `q5_k_m`.
- FIRST, verify that the `whisper.cpp` quantize tool accepts a `q5_k_m` type for Whisper models.
  This is UNVERIFIED. A `q4_k` Whisper GGUF exists on disk
  (`/root/models/asr/xviers-whisper-large-v3-turbo-gguf/whisper-large-v3-turbo-q4_k.gguf`),
  so k-quants exist for Whisper, but the tool's accepted type list is not confirmed.
- If `q5_k_m` is NOT supported, STOP and report to the manager. Do not silently substitute `q5_1`.
- Report the exact command used and the resulting file size.
- SCRIPT the whole thing. The dev container wipes ad-hoc installs on rebuild.
- Write the output next to the other quantizations, under
  `/root/models/asr/ivrit_ai/whisper-large-v3-turbo/`.

Existing sizes, for comparison in your report:

| File | Size |
|---|---|
| `ggml-model-q4_0.bin` | 452.0 MB |
| `ggml-model-q5_1.bin` | 595.2 MB |
| `ggml-model-q8_0.bin` | 833.7 MB |
| `ggml-model.bin` (fp16) | 1549.3 MB |

## 8. Task 3 — switch the app to Hebrew ASR

File: `/root/groundstation/projects/integration_harden/run_mvd.sh`, line 162. This is gap (b).

- Switch to `--backend=whisper-whisper --language=he`.
- Use the `q5_k_m` model produced by Task 2.
- Make backend, language and model path overridable by environment variable, so English can be
  restored without editing the file.
- Keep `--fa`, `--threads`, `--gid` and `--captureid` as they are.
- This is a production launcher, so the change lands in this file, in place.

## 9. Task 4 — the desk-test scripts

Location: `/root/groundstation/tools/desk-test/` — a NEW directory.
OWNER RULING: do NOT put these in `integration_harden`. Do not clutter that folder.

The owner runs these. He should not have to think. Requirements:

1. One script brings the whole desk test up: the mock, then the app with `dji` video and `mock`
   control. It must not leave him staring at a blocked terminal (see fact 9).
2. All logs collect into one timestamped directory, one file per component: mock, app, dicta,
   vlm, asr, gstreamer.
3. One script tears everything down cleanly and frees every port.
4. One script reads the collected logs and prints a compact status, so the agent can diagnose from
   it when the owner asks.
5. Absolute paths everywhere. No `cd`-relative assumptions.
6. Preflight checks before boot: ports free, models present, binaries present, drone video arriving.
   Fail loudly and early with a clear message, rather than half-starting.

Reuse what already exists in `run_mvd.sh` rather than rewriting it. The point of this exercise is
to bootstrap `integration_harden` into reality, not to build a parallel system.

## 10. Task 5 — the test plan the owner will execute

Step 1, at the desk: real drone video, mock control.

Both model servers must be up before the first Hebrew utterance: Qwen3-VL on 18090, DictaLM on
18091. Confirm with `ss -tln`. The first DictaLM call is slow on CPU. That is not an error.

Hebrew sentences, one per outcome kind:

| Kind | Sentence | Expected |
|---|---|---|
| mission (bypass, no model) | `עלה עשרה מטרים` | `POST /c/fly` with a mission, printed by the mock |
| command (translate + planner) | `טוס קדימה חמישה מטרים ואז הסתובב תשעים מעלות` | a planned mission on the wire |
| perception (VLM) | `מה אתה רואה עכשיו?` | a VLM answer in the chat pane, no flight |
| emergency (router tier 4) | `עצור` | `wire.halt()` = `POST /c/fly [{delay:0}]`, NOT `/c/stop` |
| number-heavy (reject watch) | `תעלה לי בעדינות עשרים מעלות ועוד שלושים` | plans normally, or rejects with `לא הבנתי, שמעתי:` |

What this test must prove. These are the reasons it exists.

1. The `dicta` pane is healthy and 18091 is LISTEN.
2. A Hebrew movement command produces a mission on the mock. Capture the body verbatim.
3. A Hebrew see-question produces a VLM answer, and does not fly.
4. `עצור` reaches `wire.halt()`.
5. The real-model chain works: DictaLM translate -> Qwen plan -> mission. This has ZERO automated
   coverage today. The wiring tests use fakes. This is the single most important point.
6. Real DictaLM returns "Ascend ten meters", not "go up 10 meters". Record whether the Qwen planner
   maps "Ascend N" to a correct `fly_by` dz. This is untested and is the most likely failure.
7. `main()` really built the Pipeline. If it printed "drone router DISABLED", say so plainly.
   `test_scene_wiring` does not import `main()`, so a live boot is the only check on it.
8. Hebrew ASR accuracy at the desk: record what the ASR heard versus what the owner said.

Also record, for later: roughly how long `on_text` blocks during a plan. COMPLEX now runs
synchronously on the ASR callback thread. Label any number you did not measure as unverified.

## 11. Out of scope — do not do these

- Step 2 (outdoors, real control). That is the owner's, later, and human-only.
- Step 3 (latency and per-component performance). DEFERRED by owner ruling, undefined on purpose.
  Do not build instrumentation for it now.
- Wiring `perception2/` (SAM3) into the app. Separate lane, not yours.
- Changing the router's English basic-verb table. See fact 6. It is correct as it stands.
- Any git write.

## 12. Reporting

- Write the full report to `/root/groundstation/docs/active/2026-09-04-live-desk-test-report.md`.
- House register per `docs/writing-style.md`: Objective, Setup, Results as neutral tables with every
  column, numbered Analysis, then Conclusions and open items. It must stand alone.
- Send the manager a SHORT summary only: pass or fail per numbered point, plus blockers.
- Never paste bulk output into chat. Put it in files.

## 13. Cost discipline — read this

The manager runs on an expensive model, and every message to it costs a full turn of the owner's
budget. The owner is conserving.

- Do not message the manager for anything answerable from this brief or from the repo.
- Send ONE message when the work is done.
- Send ONE message if you are blocked for more than 20 minutes, or if `q5_k_m` is unsupported.
- Otherwise, work from this document.
