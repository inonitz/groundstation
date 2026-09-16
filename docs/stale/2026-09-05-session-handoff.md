# Session handoff — live-test agent (groundstation-05), 2026-09-05
> **Doc owner:** groundstation-05  (ref 55e80f)  — role: **live-test agent** for the integration_harden desk test / judges demo. Reach via SendMessage to `groundstation-05`; manager is `groundstation-3c`.

Author: groundstation-05. For: groundstation-3c (manager) and the owner. This document is
exhaustive by owner instruction: it omits nothing, so the manager can decide what is relevant.
House registers: Objective/Setup/Results/Analysis. No git writes were made; commit blocks are
listed for the owner to run.

## 1. Objective this session

Bootstrap `projects/integration_harden/` into a runnable desk test, support the owner's live
testing, and build a passive audio+transcription dataset recorder. Also move ASR to Hebrew and
change the push-to-talk key. The e2e chain: mic -> Hebrew Whisper ASR -> Recognizer ->
command/perception -> JSON on the REST wire -> MOCK server, with real drone video via gstreamer_rx.

## 2. Finished and verified

- **Mock records every REST command.** `tools/dji_mock/mock_apiserver.py` logs method, path, and
  full JSON body of `/c/fly`, `/c/takeoff`, `/c/land`, `/c/stop` to console and to `MOCK_CMD_LOG`
  (default `${TMPDIR:-/tmp}/mock_commands.log`). Response shapes byte-identical; the 204 silent
  mode unchanged. Verified live on a localhost port: `fly()` still returns `mission_len`, so the
  body survives the log read.
- **Hebrew ASR quantized.** `q5_k_m` is NOT a whisper.cpp ftype (verified; the tool errors and
  leaves a corrupt partial). Owner ruled q5_k + q4_k + q4_0. All three produced from the fp16
  source with `tools/desk-test/quantize_hebrew_asr.sh`: q5_k 547.4 MB, q4_k 452.0 MB, q4_0 452.0 MB
  (q4_k and q4_0 tie at 4.5 bits/weight; they differ in quality, not size). Desk-test default is
  `ggml-model-q5_k.bin`. A FLEURS-style inference/accuracy benchmark is deferred (owner).
- **run_mvd.sh switched to Hebrew ASR.** `--backend=whisper-whisper --language=he`, model default
  `ggml-model-q5_k.bin`. Backend, language, model, and capture device are env-overridable, so
  English is restored without editing the file. `--fa/--threads/--gid` kept.
- **Desk-test harness** in `tools/desk-test/`: `preflight.sh`, `up.sh`, `down.sh`, `status.sh`,
  `show_session.py`, `quantize_hebrew_asr.sh`. `up.sh` runs `run_mvd.sh` under a detached pty so its
  `tmux attach` does not block and its EXIT-trap cleanup does not fire. One timestamped log dir per
  run; `latest` symlink. Preflight and teardown port-free logic verified; the full boot was
  exercised live by the owner.
- **Phone IP handling.** The phone IP changed to 10.200.2.63 (WiFi gateway). Root trap: the box has
  TWO default routes (a USB-ethernet NIC at 192.168.1.1 plus WiFi), and the naive "first default
  route" picks the wired one. `up.sh`/`preflight.sh` now derive the phone IP from the WIRELESS
  interface only. `run_mvd.sh` still uses the naive form, so launch via `up.sh` or pass PHONE_IP.
  Memory `phone-ip-is-wifi-gateway` updated.
- **Preflight phone check** uses `GET /status/` on :8080, not ping (the phone drops ICMP). It also
  distinguishes "server up but drone/API not ready" (HTTP 503) from "not answering".
- **Mock JSON is visible on screen.** New tmux window `mock` (index 7) tails `mock_commands.log`
  live. Baked into `up.sh`.

## 3. Finished, needs an app restart to activate (verified in isolation, not yet seen live)

- **Hebrew + English chat overlay.** OpenCV's Hershey font is ASCII-only, so `scene_omdet.py` now
  draws Hebrew with DejaVuSans + `python-bidi` (correct RTL) and shows the DictaLM English
  translation, labeled You:/En:/Scene:. The English is captured by wrapping the injected translator
  inside scene_omdet, so the benchmarked Recognizer is untouched. `python-bidi` added to
  `tools/devenv/install-runtime-deps.sh` and the Dockerfile, and installed on the box. Render path
  and the real `_draw_conv` were unit-tested; the live look is unconfirmed until a restart.
- **Passive session recorder (the dataset).** `scene_omdet.SessionLog` writes
  `projects/integration_harden/sessions/session-<date>-<host>/` (gitignored): `utterances.jsonl`
  (dataset), `utterances.log` (readable), `meta.json`. Per utterance: timestamp, heard Hebrew,
  English translation, routed kind/action, and the mission put on the wire. Hooked at `on_text`, so
  it captures EVERY utterance including emergency (which bypasses the Recognizer's own trace).
  Reader: `tools/desk-test/show_session.py latest`. Unit-tested (command + emergency records).

## 4. Work in progress (C++, owner-written; agent prepared/reviewed)

- **Audio-clip capture in the ASR node.** The owner added `--record` and `--recordDir` flags and a
  WavWriter clip save in the consumer thread. Agent-prepared and reviewed:
  - Clip name in one snprintf, no `std::to_string`, single heap allocation (a reserved string).
    Buffer sized `name[96]` to satisfy `-Wformat-truncation` (the analyzer assumes full-width int
    per `%d`, ~94 bytes worst case; real strings are ~42).
  - Filename is `audio_<index>_<YYYY-mm-dd_HH-MM-SS>.wav`, unique via an atomic index.
  - **CLI parser refactor (the important fix).** argv was being parsed by two cxxopts parsers (the
    sttserv backend parser and the node's), and cxxopts throws on unknown options, so the node died
    on every launch. Resolved WITHOUT touching the sttserv library: the node parser calls
    `allow_unrecognised_options()`, reads `--record/--recordDir`, and passes `result.unmatched()`
    (the backend's own flags, plus `--help`) to `parse_commandline_args`. `--help` therefore reaches
    sttserv, which prints its own help. Verified with the repo's cxxopts: unmatched() preserves the
    backend flags intact and in order; `--help` passes through.
  - `keyCodeToString` link error root-caused: the definition lived only in the keyboard executable,
    so the ASR target had the declaration but not the symbol. Owner fixed it by making
    `keyCodeToString` `inline` in `key_codes.hpp` (header-only), per the file's own TODO note.
  - Static check of the final files: constructor/destructor correct, node-then-backend parse order
    correct, lifetimes correct (the passthrough string vector outlives the backend parse), capture/
    playback ids read from the backend args. It compiled and linked in the owner's build (only the
    now-fixed truncation warning). Re-run the build to confirm the warning is gone with `name[96]`.
- **Bundling audio + metadata in one session folder (NOT wired yet).** Design agreed: one session
  folder holds the WAV clips (C++) and utterances.jsonl/.log/meta.json (Python). Coordinate the
  folder via a shared env (e.g. MVD_SESSION_DIR) set once by `up.sh` and passed to both processes;
  the ASR node's `--recordDir` points at it (or a clips/ subfolder). Coupling each clip to its
  record: push-to-talk is sequential and both stamp wall-clock time, so Nth clip = Nth utterance;
  exact coupling would need the ASR node to emit the clip filename with the transcription. The
  Python side (SessionLog into a shared folder + record the clip filename) is not yet written; the
  C++ record folder wiring is the owner's.

## 5. F5 keybinding (done, owner C++)

Push-to-talk moved from H to F5. Two files: `keyboard/keyboard_node.hpp` binds `KeyCodeEnum::F5`
(the hook only forwards bound keys), and `asr/asr_node.hpp` uses a `kPushToTalkKeyBind` constexpr
and logs the key name via `keyCodeToString`. Verified live: `asr.log` shows `[KEY] F5 -> recording
ON`. The stale "press H" wording is fixed (now prints the key name twice via `%s`).

## 6. Live-test findings (transcription quality, 2026-09-05)

Measured from the owner's spoken tests and the recognizer trace `traces/session-20260905-121829.jsonl`:

| Said (Hebrew) | ASR heard | Wire mission | Verdict |
|---|---|---|---|
| עלה עשרה מטרים | correct | fly_by dz +10 | correct |
| רד חמישה מטרים | correct | fly_by dz -5 | correct |
| טוס קדימה שלושה מטרים | correct (digit 3) | fly_by dx +3 | correct |
| טוס אחורה שני מטרים | "to סחורה שתי מטרים" | none | ASR failure |
| הסתובב 90 מעלות ימינה | correct | Turn right 90 (planned) | correct |
| תמריא, תעלה ל-20, תסתובב 360, ותנחת | correct | 4-step mission (planned) | correct |

Analysis:
1. Simple commands with variables transcribe and mission correctly (up/down/forward/turn, and a
   full multi-step chain). This is the core capability and it works.
2. "backward" is the fragile word: אחורה is misheard as סחורה (merchandise), and טוס as "to". No
   mission fires (correctly, since it is not a direction). This is an ASR error, not a planner error.
3. ASR sometimes returns empty transcripts. The device is correct (the M4 mic, the system default;
   device 1 was a monitor loopback and was wrong). Empty results are audio level or push-to-talk
   timing, not a wrong device and not a hang.

## 7. Known open / not integrated / not tested

- E2E with the phone is blocked for ~1.5 hours (no phone available; owner).
- The overlay and the session recorder need one app restart to activate; verified in isolation only.
- Audio-clip bundling into the session folder is not wired (section 4).
- TTS targets the wrong IP: `integration_harden/audio/tts_io.py` resolves the phone via
  `config.default_gateway()`, which hits the same two-default-route trap and picks 192.168.1.1. No
  actual /tts POST was observed, so "spoken replies fail" is unverified. Fix ready but not applied
  (set SCENE_TTS_HOST to the phone, or follow MVD_WIRE_HOST like integration_tts does). Owner asked
  a question here; not ruled.
- The console/terminal Hebrew reversal is the terminal emulator (no bidi); not fixable from the app.
- SAM3 / perception2 not wired into scene_omdet (separate lane).
- `run_mvd.sh` still uses the naive PHONE_IP derivation (up.sh/preflight fixed).

## 8. Files changed

Agent (Python, scripts, docs):
- tools/dji_mock/mock_apiserver.py
- projects/integration_harden/run_mvd.sh, scene_omdet.py, config.py
- tools/desk-test/{preflight,up,down,status,show_session,quantize_hebrew_asr}.sh (new dir)
- tools/devenv/install-runtime-deps.sh, tools/devenv/Dockerfile (python-bidi)
- docs/active/2026-09-04-live-desk-test-report.md, docs/NOTES.md
- memory: phone-ip-is-wifi-gateway

Owner (C++):
- projects/llm_to_action/source/keyboard/keyboard_node.hpp (F5 binding)
- projects/llm_to_action/source/keyboard/key_codes.hpp (inline keyCodeToString)
- projects/llm_to_action/source/asr/asr_node.hpp, asr_node.cpp (F5, --record/--recordDir, parser
  refactor, clip capture)

## 9. Git status

Nothing committed (owner owns git). Suggested commits, in the owner's house style, were handed over
for: the desk-test harness + mock logging + Hebrew ASR switch + quant; the Hebrew/English overlay;
the session recorder + reader. The C++ (keybinding, record flags, parser refactor, inline) is the
owner's to commit.

## 10. Owner message relayed to the manager

The owner said: there is no phone available to test the system end to end for the next hour and a
half. The owner wants to spawn another subagent to handle `llm_to_action` and make it presentable
for the meeting with the judges.

## 11. Addendum (2026-09-05, later — owner follow-up)

- **q6_k added.** Quantized `ggml-model-q6_k.bin` (648.9 MB) to complete the ladder
  (q4_0 452 / q4_k 452 / q5_k 547 / q6_k 649 / q8_0 874 / fp16 1549 MB). q6_k is near-fp16 quality.
  Do NOT declare a final pick until the accuracy/latency benchmark runs; VRAM and latency are the
  trade against quality. `quantize_hebrew_asr.sh` is kept as the scripted, repeatable regenerator
  (the container/models can be wiped on rebuild; the script is provenance + one-command redo).
- **Dynamic phone-IP integrated into the program (one home).** `config.default_gateway()` now
  prefers the WIRELESS interface's default route (mirrors the /sys/class/net/<iface>/wireless
  one-liner), falling back to the first default route. This fixes the phone-IP source for `tts_io`,
  `video_doctor`, and `video_watchdog` at once — the TTS wrong-IP issue is resolved at the source,
  not per-caller. It returns the phone only when the laptop is on the phone hotspot; with the phone
  offline it returns whatever WiFi wlp4s0 is on (currently 192.168.1.1). Needs the phone to verify
  end to end.
- **ASR language is NOT being forced (likely root cause of the "to" Latin token).** whisper.cpp
  auto-detects (and logs "auto-detected language") only when `params.language` is null/empty/"auto"
  (whisper.cpp:6833). The asr.log prints "auto-detected language: he" on every utterance, so the
  language arriving at whisper is empty — Hebrew is NOT forced, even though the backend sets it from
  `--language` and run_mvd passes `--language=he`. Auto-detect usually returns he (p~1.0) but can slip
  a Latin token per segment, which is how טוס became "to". Fix: ensure `--language=he` actually
  reaches the whisper backend (confirm the node's unmatched() passthrough preserves it, and add a
  one-line startup log of the resolved language / call print_arguments), so detection is off and
  Hebrew is forced. Then retest. The "to" is whisper's output, not the Recognizer regex — a
  Recognizer rewrite is the wrong layer and is benchmarked (needs the recognizer-bench skill,
  measured evidence, and a zero-false-fire gate), so it is on hold behind the ASR-forcing fix.
- **Audio-clip capture status.** The C++ code is written and compiles. Left to do: (1) test — record
  real clips and verify the WAVs are valid; (2) integrate — pass `--record`/`--recordDir` from
  run_mvd/up.sh and point the record folder at the session folder; (3) bundle — the Python
  SessionLog writes into that same shared session folder and records each clip's filename. Item 3
  was not started because it needed the C++ capture (now done) plus the shared-folder coordination;
  it is unblocked and phone-free.

## 12. Recheck additions (details missed in the first pass)

- **YOLO background detector was re-downloading; now pinned (run_mvd.sh).** On the first live boot,
  ultralytics downloaded `yolo26n-seg.pt` from GitHub every run because `config.BG_SEG_MODEL`
  defaulted to a bare filename and run_mvd did not pin it. The HF offline flags do not cover
  ultralytics (it fetches from GitHub), so on the internet-less phone hotspot this fetch would fail
  and perception would not start. Fix: run_mvd's APP_LAUNCH now exports
  `SCENE_BG=/root/models/vision/yolo26n-seg.pt` (the file already existed there), next to the
  existing `SCENE_SAM2` pin. The stray copy the run left in the repo dir was removed. Only that 6.4 MB
  model was fetching — Qwen, DictaLM, SAM2, and Whisper all load from disk.
- **Capture device: forced device 1 was wrong; now the system default (run_mvd.sh).** `--captureid=1`
  selected "Monitor of M4" (a silent loopback). run_mvd now omits `--captureid` unless `ASR_CAPTUREID`
  is set, so the ASR uses the system default input, which is the real MOTU M4 mic. The ASR startup
  log enumerates devices and confirms "Picked ... Capture: M4 Analog Surround 4.0".
- **Full run_mvd.sh change set this session:** (1) Hebrew ASR backend/language/model (env-overridable),
  (2) capture device -> system default unless ASR_CAPTUREID set, (3) `SCENE_BG` pinned to the local
  YOLO weight. All three are in the one file.

## 13. REST API full sync (2026-09-05) — against /root/DJI-android-sdk-v5-recon-swarm

Read all 9 commits from the last 5 days (author ExoSkeleton). Client-facing changes and our updates:

- **`POST /c/fly` takes a bare JSON array of Actions** (commit "better action list request parsing"),
  not `{"mission":[...]}`; response is `{"ok":true,"actions":[...]}`. FIXED in the clients:
  `integration_harden/control/dji_wire.py`, `integration_notify/dji_wire.py`, `integration_tts/dji_wire.py`
  now send `list(actions)`. `projects/integration/` is FROZEN and still sends the wrapper — flagged,
  not touched (owner rules changes to the frozen demo).
- **Action DTO schema verified** against `com/kcg/dr/api/dto/actions/*.kt`: discriminator key `type`;
  SerialNames and fields match our client for every action we send (fly_by dx/dy/dz/velocity,
  spin_by degrees, delay seconds, takeoff, land, gimbal_pitch angle, home maxVelocity, scan_ground
  height/radius/velocity/facing/clockwise, follow_me cruiseHeight/followDistance/maxVelocity,
  track_me fovTolerance, wave count). No field renames — only the array wrapper changed.
- **Discrete verbs now return bodies:** `/c/takeoff`→`{"ok":true,"status":"taking off"}`,
  `/c/land`→`"landing"`, `/c/stop`→`"stop"`. Our client only checks HTTP status, so no client change needed.
- **New endpoints** (mock now mirrors all): `POST /tts`, `POST /key`, `GET /`, `GET /c/`,
  `POST /c/flyTo`, `POST /c/lookAt`, `GET /c/(wave|hi|hey|hello)`, `POST /c/stream/start|stop` +
  `GET /c/stream/status`, quick `GET /takeoff|/fly|/land`, and WS `/c/ws/echo|gimbal|telemetry`
  (plus the existing `/c/ws/sticks`). Status endpoints wrapped in `{"ok":true,...}`.
- **503 gating:** the real server returns 503 when RC/aircraft/product/controller not connected
  (the live 503 seen earlier). The mock stays a healthy connected stand-in — not simulated.
- **Telemetry serializers** (Velocity3D / LocationCoordinate3D / 2D) changed structurally in the
  refactor. The mock keeps velocity3D/position3D as the sim's local `{x,y,z}` on purpose (useful for
  dead-reckoning); the real position3D is GPS `{latitude,longitude,altitude}`. The MVD does not parse
  telemetry, so this does not affect the desk test. The C++ DjiBackend (which does parse it) is a
  separate owner-owned track; it does not POST /c/fly, so the mission change does not touch it.
- Mock rewritten (`tools/dji_mock/mock_apiserver.py`) and smoke-tested against every endpoint;
  command logging preserved.

## 14. ASR language fix (point 1): make backendArgs a member

`whisper` reads `full_params.language` per utterance (whisper.cpp:6978); the pointer must stay valid.
`backendArgs` is a constructor local, so make it a class member so it outlives the backend. Then
`--language=he` forces Hebrew (no more per-utterance auto-detect, no string duplication). C++, owner-applied.

## 15. Sync ledger (2026-09-05) — everything checked against the Kotlin API

| Component | Path | Synced? | Note |
|---|---|---|---|
| MVD client | integration_harden/control/dji_wire.py | YES | /c/fly bare array |
| Notify fork | integration_notify/dji_wire.py | YES | /c/fly bare array |
| TTS fork | integration_tts/dji_wire.py | YES | /c/fly bare array |
| Frozen demo | integration/dji_wire.py | YES | /c/fly bare array — owner-authorized freeze exception (must work as fallback) |
| Mock server | tools/dji_mock/mock_apiserver.py | YES | full endpoint + response mirror, smoke-tested |
| Action schema | (verified vs dto/actions/*.kt) | YES | type + fields unchanged; only the wrapper changed |
| C++ DjiBackend | llm_to_action/source/dji_backend/* | DEFERRED | no /c/fly; /status serializer parse to resync at llm_to_action integration |

## 16. FULL SESSION STATE — read FIRST after compaction (2026-09-05 ~23:40)

### Verified WORKING live (desk test: laptop-mic F5, mock control 127.0.0.1:8079, phone video)
- Missions: `/c/fly` bare arrays, all HTTP 200 — fly_by dz+10 / dz-5 / dx+3, spin_by 90, halt `[{delay:0}]`.
- Whisper language forced: clean Hebrew, NO auto-detect spam, no "to" garbage. Fix lives in the pulled
  sttserv `backend_whisper.cpp` (WhisperBackendState owns `std::string language`; verified in tree).
- Audio dataset: `clips/*.wav` + `utterances.jsonl` bundled in the session folder; recording ON by
  default in up.sh (DESK_TEST_RECORD=0 disables).
- ASR speed: cold first utterance ~3860 ms (Vulkan shader compile), then ~300 ms each. beam_size=4
  (faster than the old 8). The "dramatic slowness" was the cold start, NOT beam_size.

### FIXED this session (all in tree; most need only an app restart, not a rebuild)
- Overlay blank Hebrew = `python-bidi` missing in the app's ROS python -> installed into it now, and
  in tools/devenv/{install-runtime-deps.sh,Dockerfile}. Render code is correct. Restart -> Hebrew shows.
- config.default_gateway() -> wireless-iface only, returns None if no wifi (no wired fallback).
- All four dji_wire clients send the bare `/c/fly` array (integration_harden, integration_notify,
  integration_tts, AND frozen integration -- owner-authorized freeze exception).
- tools/dji_mock/mock_apiserver.py rewritten to mirror the current ApiServer.kt (all endpoints,
  response shapes, WS echo/gimbal/telemetry, /tts, /key, flyTo/lookAt/stream, quick GETs). Logging kept.
- scene_omdet.py: Hebrew(RTL)+English overlay (DejaVuSans+bidi), SessionLog recorder (heard/english/
  kind/action/mission), translator + wire wrappers. config.py: HE_FONT_PATH/SIZE.
- run_mvd.sh: Hebrew ASR (whisper-whisper/he, env-overridable), capture-device -> system default,
  SCENE_BG pinned (no ultralytics re-download), ASR --record/--recordDir, MVD_SESSION_DIR forward.
- tools/desk-test/: up/down/status/preflight/show_session/quantize_hebrew_asr. up.sh = detached pty
  (non-blocking), session folder, mock JSON in tmux window 7, wireless PHONE_IP.
- ASR quants produced: q4_0/q4_k/q5_k(default)/q6_k under /root/models/asr/ivrit_ai/whisper-large-v3-turbo/.

### OPEN findings / not bugs
- **En: line empty for mission-BYPASS commands** (עלה/רד/טוס): the recognizer bypass builds the fly_by
  mission WITHOUT calling DictaLM translate, so there is no English. LLM-planned commands (הסתובב) and
  questions/rejects DO show English. NOT a bug. For the overlay, show the mission/action for bypass so
  there is always feedback (see showcase plan below).
- ASR pane buries each transcript under ~12 lines of whisper_print_timings (asr_node.cpp:288) + bursts
  after each GPU encode -> looks frozen. Cosmetic. Gate/remove print_timings for a clean pane (C++).
- COMPLEX runs SYNCHRONOUSLY on the ASR callback thread; command latency = DictaLM+Qwen planner blocks.
- One ASR empty transcript (1/8) = a miss (clip saved). DictaLM sometimes answers instead of
  translating (האם אתה קולט -> "Yes, I hear you") = known residue.

### C++ (owner-written; status)
- backendArgs is still a ctor local -- NO LONGER an issue (backend owns the language string). No action.
- m_backend.create() re-added by owner. F5 keybinding works. keyCodeToString inlined (owner).
- DEFERRED: DjiBackend /status telemetry parse must resync to new Velocity3D/LocationCoordinate
  serializers WHEN llm_to_action is integrated (dji_backend does NOT POST /c/fly, unaffected now).
- OPTIONAL demo polish: gate print_timings for a clean ASR pane.

### Overlay full-chain showcase (#2) -- IMPLEMENTED 2026-09-06 (scene_omdet)
Owner wants to gauge failures from the OpenCV window alone. Data is already in SessionLog. Plan: per
utterance render a block: `You: <he>` / `En: <english or "(direct)">` / `kind: <mission|command|
perception|reject|emergency>` / `wire: <mission json or action>` / `-> HTTP <status>`. Implement by
appending these roles to S.chat in scene_omdet (bypass -> show the mission as the gloss). Discuss layout.

### KEY PATHS
- App: projects/integration_harden/{scene_omdet.py,config.py,run_mvd.sh,control/dji_wire.py,recognizer/*}
- Mock: tools/dji_mock/mock_apiserver.py ; Desk test: tools/desk-test/*.sh
- Dataset: projects/integration_harden/sessions/session-<ts>-<host>/{utterances.jsonl,utterances.log,meta.json,clips/*.wav}
- Run logs (ephemeral): /tmp/desk-test/<ts>/{mock,mvd_app,mvd_dicta,asr,gst,dog}.log + latest symlink
- Kotlin API truth: /root/DJI-android-sdk-v5-recon-swarm/SampleCode-V5/.../com/kcg/dr/api/server/ApiServer.kt + dto/actions/*.kt
- Docs: docs/active/2026-09-05-session-handoff.md (THIS), 2026-09-04-live-desk-test-report.md ; rulings in docs/NOTES.md

### RESUME CHECKLIST (post-compaction)
1. If container was rebuilt: `bash /root/groundstation/tools/devenv/install-runtime-deps.sh` (bidi + others).
2. Phone on hotspot, API Server ON. `bash /root/groundstation/tools/desk-test/up.sh` (auto phone IP, records dataset, mock JSON in window 7).
3. Overlay now shows Hebrew. Review a session: `python3 /root/groundstation/tools/desk-test/show_session.py latest`.
4. GIT: nothing committed all session; owner runs ALL git. Commit blocks are in this doc / chat history.
5. Next work items: implement the full-chain overlay (#2); optional print_timings gate; DjiBackend telemetry resync at integration time.

## 17. Ownership + final updates (2026-09-06)

- **This document's author/owner:** groundstation-05, messaging ref **55e80f**, role = **live-test
  agent** (bootstrap integration_harden into a runnable desk test for the judges demo). Reach via
  `SendMessage` to `groundstation-05`. Manager = `groundstation-3c`.
- **Overlay full chain IMPLEMENTED** (scene_omdet.py, this session): per utterance the OpenCV chat now
  shows `You: <he>` / `En: <english or (direct)>` / `kind: <..>` / `Cmd List:` then a vector
  `{ 0  <type k=v>  1  ... }` / `-> <action>`. Renamed "Wire" -> "Cmd List" (owner). Multi-line command
  arrays render one command per line inside braces. New chat roles: `meta` (plain indented line),
  `cmd` (indexed command line). Translator no longer double-appends `En` to the chat. NEEDS AN APP
  RESTART to see; py_compile clean; not yet seen live.
- **Triple-check done:** reviewed the whole session against §§1-16 + NOTES. Nothing else material is
  missing. Git is fully UNCOMMITTED — the owner runs ALL git; the changed-file list is in §16 "FIXED".
- **Resource note:** GPU freed (down.sh). Owner is benchmarking SOTA monocular depth estimators —
  the agent must NOT run heavy GPU/CPU work until the owner says so.

## 18. FINAL STATE v2 — post day-2 live test (2026-09-06). READ WITH §16-17.
**Doc owner: groundstation-05 (ref 55e80f) — the live-test agent** (integration_harden desk test / judges demo). Manager = groundstation-3c. NEW commit attribution from here on: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

### Since §17
- Owner COMMITTED all §1-17 work (the 4 commit blocks). Judge reviews architecture today; I wrote the
  manager's diagram-task prompt (sync-first reading list, federate low-level to lane agents, system
  inventory) — owner was reviewing it; send-status UNKNOWN. My offer to draw my lane's low-level
  diagram: OPEN, never green-lit.
- **up.sh silent death FIXED:** phone_ip_wifi() returned non-zero when no wireless default route ->
  `set -e` killed up.sh at the PHONE_IP assignment with no output. Both up.sh + preflight.sh now
  `return 0` on the empty case (empty IP -> preflight fails LOUDLY instead).
- **24-case live subset** saved to tools/desk-test/live-test-subset.md (was chat-only). Owner ran
  roughly half informally on day-2; a formally SCORED pass is still OPEN.

### Day-2 live findings (session-2026-09-06 ~18:xx + pane-capture-180640/, both under sessions/)
1. **Hebrew reversed = DOUBLE-bidi. FIXED.** App PIL has Raqm (native bidi in ImageDraw.text); our
   get_display() pre-reversal double-reversed. scene_omdet now detects `_RAQM` and passes the raw
   logical string when Raqm is present (get_display only as no-Raqm fallback).
2. **Overlay block re-formatted. FIXED.** Aligned label column `En|Kind|Cmds|Action` with indexed cmd
   lines; overlay font default -> DejaVuSansMono (Hebrew glyphs verified) so columns truly align.
3. **"complex->perception" was a recorder artifact. FIXED.** Router labels every COMPLEX res.action
   with that constant; recorder now wraps pipe.handle to record the pipeline's REAL action string
   (router label = fallback only). The phone "narration" on some commands = the REJECT path speaking
   "לא הבנתי, שמעתי:..." (by design); root causes of those rejects: DictaLM answering instead of
   translating (incl. the owner's prompt-injection tests, answered in Hebrew) + ASR-garbled numbers.
4. **EMERGENCY_RE gap. OPEN, bench-gated:** תפסיק הכל / תפסיק שליטה not matched -> no halt. Adding
   תפסיק requires the recognizer-bench skill + measured zero-false-fire pass.
5. **Phone TTS 503 = the app's connection gate. OPEN, owner to rule:** ALL routes incl /tts gated on
   RC/aircraft/product connection; drone eco -> 503 -> silence (early posts 200, later all 503).
   Options: (a) exempt /tts app-side (Kotlin dev) or (b) tts_io local espeak/piper fallback on 5xx
   (beware old "both = double-speak" trap; espeak may not be installed).
6. Positives: land-trap question did NOT land (guard held); ASR-typo הסתורב still planned 90 correctly;
   backward WORKED inside chains post-language-fix (single-backward confirm still pending).

### UNCOMMITTED since the owner's commits (new commit block)
Files: projects/integration_harden/scene_omdet.py (raqm fix, aligned block, real-action recorder),
projects/integration_harden/config.py (mono font default), tools/desk-test/up.sh + preflight.sh
(set-e fix), tools/desk-test/live-test-subset.md (new), docs/NOTES.md, docs/active/2026-09-05-session-handoff.md.
```
cd /root/groundstation
git add projects/integration_harden/scene_omdet.py projects/integration_harden/config.py \
        tools/desk-test/ docs/NOTES.md docs/active/2026-09-05-session-handoff.md
git commit -m "fix(desk-test): Raqm double-bidi, aligned overlay block, real action in recorder, up.sh set-e death

PIL+Raqm applies bidi natively -> skip get_display when raqm present (Hebrew was double-reversed) | overlay -> aligned En|Kind|Cmds|Action column, font -> DejaVuSansMono | SessionLog records pipe.handle's real action (router's constant complex->perception label demoted to fallback) | phone_ip_wifi return 0 on no-wireless (set -e killed up.sh silently) | live-test-subset.md (24 bench-drawn cases) | NOTES: double-bidi, TTS-503 gate, recorder artifact, EMERGENCY_RE gap

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Skimmed / unresolved talking points (so nothing is lost)
- ggml language-pointer curiosity: found issue #2998 (danbev, strdup workaround, no documented
  rationale for keeping the pointer); deeper dig offered, not pursued.
- ASR pane noise (gate print_timings, asr_node.cpp:288) — optional C++ polish, open.
- My lane's architecture diagram for the judge — offered, not green-lit.
- Formal scored run of the 24-case subset — open.
- SOTA monocular depth benches (tools/bench/depth-sota-bench, yolo26-depth-bench) = OWNER's lane,
  untracked, not mine; share the GPU politely.

### NEXT BOOT CHECKLIST (all Python fixes -> restart only, no rebuild)
1. up.sh (on the phone hotspot). 2. Verify: Hebrew direction CORRECT (raqm fix), aligned block, real
Action values. 3. Run tools/desk-test/live-test-subset.md and score via show_session.py. 4. Owner
rulings pending: TTS-503 remedy (a/b), EMERGENCY_RE תפסיק addition (bench-gated).

### Standing owner rules for this agent (triple-check addition — do not violate post-compaction)
- MINIMIZE SendMessage to the manager (groundstation-3c): the owner relays between agents himself;
  message the manager ONLY when the owner explicitly directs it.
- The owner runs ALL git writes and every boot/mock/control script; the agent diagnoses from logs and
  runs down.sh only when the owner says so. Owner writes C++; agent writes MVD Python.
- Owner is human at the desk: put review files in the workspace with a clickable path, no SendUserFile.
- GPU/CPU: do not run heavy work while the owner benchmarks (depth lane) unless told.
