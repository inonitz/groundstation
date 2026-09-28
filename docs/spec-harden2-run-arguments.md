# harden2: how to run, measure and test it (every command, setting and flag)

Current state, read from the code on 2026-09-26: run.sh, config/defaults.py, config/constants.py,
app/feed.py, log/, test/. When the code changes, update this file in the same change.
config/ is the one home of every value: only config/defaults.py reads the environment.

| section | what it covers |
|---|---|
| 1. Run | run.sh commands: start, stop, status, preflight |
| 2. Settings | every environment setting the app reads, with its default |
| 3. Keys | the global keys and the window keys |
| 4. Measure | the timings, the scripted run, the reports |
| 5. Test | the test suite and its opt-in flags |

## 1. Run

All commands use `bash /root/groundstation/projects/integration_harden2/run.sh <command>`.

| command | what it does |
|---|---|
| `up [VIDEO] [CONTROL]` | Runs the preflight, then starts the app in the tmux session `mvd`. Default: `up webcam mock`. |
| `down` | Stops the app, every process it started, and frees the ports. |
| `status [run_dir]` | Shows the ports, the tmux panes, the last transcripts and mock commands, the cameras. |
| `preflight [webcam\|dji]` | Checks only; starts nothing. Ports free, system/deps.py (packages, programs, model files), one ggml version, tools, DISPLAY, cameras or the phone. |
| `show [session]` | Prints a session's turns (log/show.py). Default: the newest session. |
| `score [list.md] [session]` | Judges a session against a live-test list; writes REPORT.md into the session (log/score.py). |
| `perf [session]` | p50 / p95 / max per stage from the session's perf.jsonl (log/perf_report.py). |

- VIDEO: `webcam` (/dev/video<WEBCAM_DEV>), `dji` (the phone's video through gstreamer and ROS2),
  `rtmp` (rtsp://127.0.0.1:8554/live; needs an RTSP server there, which nothing here starts;
  untested since harden2).
- CONTROL: `mock` (the mock phone app at 127.0.0.1:8079) or `real` (the phone at PHONE_IP:8080).
  `real` is HUMAN-ONLY: run.sh asks you to type ARMED. The assistant runs only `mock`.
- The app itself: `python3 -m app.main [--source S]` from the harden2 folder. run.sh adds the
  settings, the tmux panes and the session folder. Without `--source`, config derives it from VIDEO.
- Each run writes a session folder under logs/sessions/: trace.jsonl, perf.jsonl, perception/,
  asr_clips/, and one proc-<name>.log per process.

## 2. Settings (environment; config/defaults.py)

Run context:

| setting | default | meaning |
|---|---|---|
| VIDEO | webcam | webcam, dji or rtmp (see section 1) |
| CONTROL | mock | mock or real (real = HUMAN-ONLY) |
| WEBCAM_DEV | 0 | the camera index: 0 = lid camera, 2 = C920 on this machine |
| PHONE_IP | the default route's gateway | the phone (it is the hotspot gateway; it changes per hotspot session) |
| ASR_SOURCES | ros,phone | speech in: ros = the laptop mic through our ASR server; phone = the phone app's speech |
| TTS_OUTPUTS | phone | speech out: phone (the phone app's /tts), laptop (offline phonikud), phone,laptop (both), "" (silent) |
| RECORD | 1 | 0 = do not record the audio clips |
| MVD_SESSION_DIR | logs/sessions/session-<time>-<host> | the session folder (run.sh sets it) |
| SCRIPT | (unset) | run.sh only: `default` or a script file starts the scripted run (section 4); mock only |

Perception (normally left alone):

| setting | default | meaning |
|---|---|---|
| SCENE_SEG | sam3 | the vision backend (the only one) |
| SCENE_GATE | sam3 | the highlight presence gate: sam3, either, vlm |
| SCENE_VERIFY | on | split and verify a related-noun phrase ("the man next to the car") |
| SCENE_HL_REL | 0.65 | relative confidence gate; lower (0.45) for crowded scenes |
| SCENE_SAM3_PERIOD | 1.0 | minimum seconds between SAM3 passes of one highlight |
| SCENE_HL_GIVEUP | 8.0 | seconds without a hit before a highlight is LOST |
| SCENE_COUNT_FRAMES | 3 | frames per count (the median is said) |
| SCENE_COUNT_GAP | 0.3 | seconds between count frames |
| SCENE_MIN_BOX_FRAC | 0.001 | boxes smaller than this part of the frame are dropped |
| SCENE_HL_TOPK | 128 | boxes SAM3 returns per query |
| SCENE_HL_MAX | 128 | boxes drawn per frame |
| SCENE_DETECT_FLOOR | 0.12 | SAM3 query threshold |
| SCENE_HL_CONF | 0.3 | minimum confidence to draw a box |
| SCENE_DEVICE | auto | torch device override (cuda, cpu, ...) |

Video, speech and launch internals:

| setting | default | meaning |
|---|---|---|
| SCENE_OPEN_TIMEOUT | 180 | seconds to open the video source before the app dies |
| WATCHDOG_STALL_SEC | 6 | dji video: no new frame this long -> RECOVERING and a gstreamer restart |
| WATCHDOG_RETRY_SEC | 15 | dji video: the restart repeats this often while stalled |
| ASR_MODEL_PATH | ivrit-ai whisper-large-v3-turbo q5_k | the ASR model file |
| ASR_BACKEND / ASR_LANGUAGE / ASR_CAPTUREID | whisper-whisper / he / the default mic | the ASR server's arguments |
| SCENE_ASR_TOPIC | /asr_server/transcribe | the ROS2 topic transcripts arrive on |
| MVD_PHONE_ASR_PORT | 8080 | the port the phone sends its speech to |
| PULSE_SERVER | unix:/tmp/pulse-socket | the host sound server the ASR server records from |
| SCENE_TMUX_SESSION | "" | set by run.sh: quitting the app then closes the tmux session |
| DISPLAY | (run.sh: :0) | the X display the app window opens on |

Fixed in config/constants.py, not settings: the ports, the model paths (Gemma, SAM3, phonikud), the
program paths (build/release/shared/dji/bin), the key codes, SAM3_PRECISION = nf4.

## 3. Keys

Global keys come from the keyboard hook over ROS2 (/keyboard/in/raw) and act from ANY window.
Only function keys act (owner 2026-09-23); every letter does nothing, because letters are typed in
other windows.

| key | action |
|---|---|
| F5 | push-to-talk (the ASR server binds it); its release starts the ASR timing |
| F4 | kill toggle: manual (transmit off, /c/stop, the RC flies) or auto again |
| F2 | clear the highlight |
| F1 | quit the app |

Window keys act only while the app window has the focus: q or Esc quit, c clear the highlight,
t masks on/off, [ ] or the mouse wheel scroll the chat, x clear the chat. All key codes live
in config/constants.py (KILL_/QUIT_/CLEAR_KEY_CODE, WINDOW_*_KEY(S)).

## 4. Measure

- Every run records its timings in <session>/perf.jsonl (log/perf.py); there is no switch. Stages:
  asr (F5 release to transcript, mic only), turn, gemma, sam3 (wait + forward), highlight_gate,
  count, describe, say, frame (per second: fps; read / draw / show mean and max; worst_frame_ms,
  the longest gap between two frames), gpu (per second).
- Its cost (measured 2026-09-27): 0.65 ms per record, about 2 records per second; the GPU sampler
  takes 23 ms per second on its own thread.
- `run.sh perf [session]` prints p50 / p95 / max per stage, and the seconds under 10 fps.
- The scripted run gives every measured run the same input:
  `SCRIPT=default bash /root/groundstation/projects/integration_harden2/run.sh up webcam mock`.
  app/feed.py waits for Gemma plus 20 s, then publishes each line of the script on the ASR topic,
  as if spoken. `default` = app/perf_script.txt; any file works: one sentence per line,
  `wait N` pauses N seconds, `#` starts a comment. It dies unless CONTROL=mock.
- `run.sh score [list.md] [session]` judges a session's missions against a live-test list
  (default list: datasets/e2e/live-test-e2e-50.md).
- A measurement result goes into docs/HISTORY.md (Why / Setup / Result / Verdict / Where), newest last.

## 5. Test

From /root/groundstation/projects/integration_harden2, with ROS2 sourced
(`source /opt/ros/jazzy/setup.bash`):

| command | what runs | time |
|---|---|---|
| `python3 -m pytest test/ -q` | every test; the models are stand-ins; real sockets, ROS2, HTTP, subprocesses | ~40 s |
| `HARDEN2_GPU_TESTS=1 python3 -m pytest test/test_perception2.py -q -k real_sam3` | the real SAM3 on the GPU | ~1 min |
| `HARDEN2_APP_TEST=1 python3 -m pytest test/test_app.py -q -k whole_app` | the whole-app test (below) | 40 s warm, more cold |

The whole-app test (test_app.py, `test_the_whole_app_over_ros`) starts the real app
(`python3 -m app.main`) with every process it starts: Gemma, SAM3, the ASR server, the keyboard
hook, the mock. It sends speech on the ASR topic and keys on the keyboard topic, as the C++ nodes
do. It checks three questions (describe, count, a mission to the mock), F4 on (/c/stop, the next
mission refused) and off, Gemma killed with SIGKILL and recovered, then F1 quits with exit code 0
and no process left. It needs the GPU, a webcam and the mic stack, and CONTROL is always the mock.
- `HARDEN2_APP_TEST_SCREEN=1`: the window opens on your display (DISPLAY, default :0).
- Without it: on a virtual screen (Xvfb :97, installed by tools/devenv/install-runtime-deps.sh).
- It refuses to start while another app or Gemma server runs (`run.sh down` first).

Before a report: `python3 -m flake8 --isolated --select=E30,E501,E70,E731 --max-line-length=89`
and `python3 -m pyflakes` clean; the suite twice; `python3 tools/audit_exceptions.py
projects/integration_harden2` from the repo root (5 handlers); no new folder under logs/.
