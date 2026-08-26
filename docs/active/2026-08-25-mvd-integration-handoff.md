# MVD Integration — Handoff (2026-08-25)

**Status: the voice->drone + smart-CV MVD is DONE and considered effective.** Single source of truth
for the new manager agent: the whole system, every fix in the 2026-08-25 session, verified findings,
loose ends, and the next tracks (pitch, `llm_to_action`, Robomaster). Read before touching
`source/integration/*`.

Also authoritative: `docs/integration-mvd-2026-08-24.md` (MVD spec), `docs/active/final-objective-context.md`
(destination C++ vs prototype Python), `docs/NOTES.md` (running log), `docs/active/kill-switch-verification.md`,
`docs/active/spec-dji-backend.md`.

## 1. What the MVD is
Totally-user-controlled drone demo: the human speaks; deterministic verbs fly the drone; smart CV
demonstrates intelligence by UNDERSTANDING the scene — it never drives the aircraft (LLM out of the
control loop).

```
voice (laptop mic, press H) ─┐
phone ASR (phone -> :8080/input) ─┼─> on_text(text) -> Router.classify (4 tiers)
                                  │      ├─ BASIC verb -> DjiWire -> DJI REST (POST /c/...)
                                  │      ├─ EMERGENCY / OVERRIDE / RESUME
                                  │      └─ COMPLEX -> perception (Qwen-VL + OmDet/SAM2)
drone cam -> phone :5600 (raw H.264/TCP) -> gstreamer_rx -> ROS camera/stream -> perception window
perception answer -> LONG (screen) + SHORT (spoken: phone /tts + laptop espeak)
```

All in `source/integration/`, self-contained (no llm_cv_scene/llm_cv_track traces). Runtime deps that
are NOT source projects: compiled binaries in `build/release/shared/dji/bin/` (gstreamer_rx, asr_server,
keyboard_hook, llama-server), weights in `/root/models/{vlm,vision,asr}`, ROS `/opt/ros/jazzy`.

## 2. Files (source/integration/)
CONTROL: `dji_wire.py` (ONLY thing that talks to the aircraft; full REST/WS client; logs
`[dji] POST /c/fly {body} -> HTTP <code>`). `commands.py` (regex classifier -> verb/tier; app-faithful
patterns; MAX_BASIC_WORDS=4 guard; unknown_move guard). `router.py` (4-tier dispatcher; auto/manual mode).
PERCEPTION: `scene_omdet.py` (THE app: video + OmDet+SAM2+VLM + ASR wiring + CV window with Scene:/Spoken:).
`highlight_seg.py` (OmDet engine + parse_highlight + open_capture + OmDet offline fix). `eyes.py`
(YOLO26-seg bg + SAM2 mask + backend loader). `vlm.py` (Qwen3-VL client :18090; ask()->(long,target,box,short)).
`config.py` (paths, LLAMA_URL :18090, colours, thresholds, TTS).
I/O: `phone_ears.py` (inbound ASR :8080, /input + raw TCP, dedupe, receipt logging). `ears.py`
(local mic ASR via ROS topic; own executor). `voice.py` (TTS out: phone /tts + laptop espeak).
`camera_stream.py` (ROS camera/stream -> VideoCapture-like; own executor).
OPS: `run_mvd.sh` (launcher + hardened teardown + HF-offline). `run_llama_server.sh` (Qwen :18090 -np 1).
`video_doctor.py` (name the broken video layer). `video_watchdog.py` (auto-reconnect gst on stall).
`run_router.py`, `test_router.py` (7 tests), `README.md`, `__init__.py`.

## 3. Voice command table
TIERS (length-independent):
- stop/halt/abort/freeze/kill/cut/emergency/mayday -> `halt()` -> POST /c/fly [{"type":"delay","seconds":0}]
- manual/override/take over/i have control/my control/disengage -> `stop()`+mode=manual -> POST /c/stop
- resume/auto/autonomous/you have control/take control -> mode=auto -> (no REST)

BASIC verbs (<=4 words):
- takeoff/take off/fly/liftoff -> takeoff() -> POST /c/takeoff
- land/perch/floor -> land() -> POST /c/land
- spin/spin around -> spin_by(360) -> POST /c/fly [{spin_by,degrees:360}]
- scan -> scan_ground(OUTWARDS) -> POST /c/fly [{scan_ground,facing:"OUTWARDS"}]
- search/recon -> scan_ground(INWARDS) -> POST /c/fly [{scan_ground,facing:"INWARDS"}]
- forward(s) -> fly_by(dx:+1); back/backward(s)/back up -> fly_by(dx:-1); right -> dy:+1; left -> dy:-1;
  up/rise/high -> dz:+1; down/under/low -> dz:-1  -> POST /c/fly [{fly_by,dx/dy/dz,velocity:2}]
- look/watch/track (at) me/us -> track_me() -> POST /c/fly [{track_me}]
- follow / follow me/him -> follow_me() -> POST /c/fly [{follow_me}]
- come back/home, return home, go home -> go_home_to_user() -> POST /c/fly [{home}]
- look/camera/face forward|ahead|straight -> gimbal_pitch(0); look/camera/gimbal down -> gimbal_pitch(-60);
  look/camera/gimbal up -> gimbal_pitch(30)  -> POST /c/fly [{gimbal_pitch,angle}]
- hello/hey/hi/how are you/how's it going/wave -> wave() -> POST /c/fly [{wave}]
- go/move/head + NO valid direction -> unknown_move -> no-op + "didn't catch a direction" (never scene-describe)
ELSE / >4 words -> COMPLEX -> perception (no drone POST). Answer: LONG->screen(Scene:), SHORT->/tts +
laptop espeak + screen(Spoken:).
Tunables: move_m=1.0m, move_vel=2.0m/s, spin_deg=360, MVD_MAX_CMD_WORDS=4.

## 4. DJI backend REST surface (com/kcg/dr/api/)
- POST /c/takeoff /c/land /c/stop (discrete).
- POST /c/fly {mission:[Action...]} — actions (JSON {"type":<serialname>,...}): takeoff, land,
  spin_by(degrees), fly_by(dx,dy,dz,velocity), fly_gps(target,maxVelocity), fly_circle(radius,velocity,
  count,clockwise,facing), fly_square(side,velocity,clockwise), scan_ground(radius,velocity,height,
  facing,clockwise), gimbal_pitch(angle -90..60), look_at(target,height), home(maxVelocity),
  follow_me(cruiseHeight,followDistance,maxVelocity), track_me(fovTolerance), wave(count), delay(seconds),
  report_status(of[]). facing=CircleFaceMode by name: "INWARDS"|"OUTWARDS"|"TANGENT".
- POST /c/flyTo, /c/lookAt (dedicated). POST /key {group,key,func:GET|SET|ACTION,args} (any SDK key).
- POST /tts {text,lang,rate}. GET /status/, /status/battery, /status/gps.
- WS /c/ws/sticks {vx,vy,vz,yaw} 18Hz, /c/ws/telemetry, /c/ws/echo.
VERIFIED (do not re-litigate):
- POST /c/stop = controller.stop(emergency=true) = DJIAircraft.stop -> KeyStopAutoLanding +
  KeyEmergencyStop + KeyStopTakeoff, then relinquishControl(). In-air outcome gated by FCUrgentStopMotorMode.
  Per app dev it does not crash in their setup; still the SDK stop, not a hover.
- controller.fly{} CANCELS the previous flight job AND takeControl()s -> a new /c/fly mission preempts
  the running one -> our stop = POST /c/fly [{delay:0}] (halt()) stops motion AND keeps stick control.
- gimbal sign: pitchCamera(-90)=ground -> negative=down, 0=forward, +=up.
- POST /c/fly returns immediately; mission runs async.

## 5. Phone <-> groundstation
INBOUND ASR (phone->GS), phone_ears.py, laptop :8080: app GroundStationSpeechResolver.kt sends each
command BOTH ways — POST http://<gs-ip>:8080/input {"text":..} AND raw-TCP newline-JSON, same port.
phone_ears sniffs HTTP-vs-raw, dedupes, logs `[phone_ears] <- POST /input: 'go forward' -> routing`.
App hardcodes target ("0.0.0.0", 8080) with a // fixme in VoiceControlFragment.kt -> phone MUST target
the laptop hotspot IP (gateway, e.g. 10.200.2.101) or nothing arrives. BACKEND: add dynamic GS-IP discovery.
OUTBOUND TTS (GS->phone), voice.py: POST http://<phone>:8080/tts {text,lang,rate}. Verified 200 live.

## 6. Video
Phone VideoTcpServer serves EXACTLY ONE :5600 client (new connection closes previous). gstreamer_rx
--dji <phone-ip> is the SOLE :5600 consumer -> publishes ROS camera/stream; perception subscribes
(SCENE_INPUT=ros). Two :5600 consumers thrash+starve. video_doctor.py names the broken layer;
video_watchdog.py auto-reconnects on stall. Phone IP = WiFi default gateway (changes per phone) — derive it.

## 7. Ports (distinct)
phone :8080 = DJI control + /tts (we POST out). laptop :8080 = phone_ears inbound ASR (phone POSTs in).
:5600 = drone raw-H.264 video (single client). :18090 = Qwen VLM (moved off :8090 — VS Code holds it).
:8079 = mock control (tests).

## 8. Session fixes (2026-08-25)
1. Consolidated MVD into source/integration/, self-contained (removed llm_cv_scene/track traces +
   sys.path shadowing; imports via __file__; copied run_llama_server.sh in).
2. camera_stream core dump fixed (spin_once loop + join before destroy).
3. "crashed for no reason" fixed (live streams don't quit on missing frames; show "waiting for video").
4. Executor starvation fixed (Ears vs CameraStream fought the global rclpy executor; each now owns a
   SingleThreadedExecutor; masked itself under --no-ears).
5. Keyboard N-KEY veto fixed (async_key.cpp rejected the ROG N-KEY kbd for EV_REL; removed the veto,
   positive KEY_A/SPACE/ENTER test suffices; rebuilt keyboard_hook).
6. VLM segfault fixed (concurrent /c/fly VLM images overflowed the unified KV pool; run_llama_server.sh
   now -np 1 serialize; asusctl Quiet was only the trigger via GPU throttle).
7. VLM moved :8090 -> :18090 (VS Code holds :8090; the "GPU-wedged, reboot" theory was WRONG — plain
   port collision). config.py + run_llama_server.sh + run_mvd.sh updated.
8. OmDet offline-load fixed (transformers 5.15 backbone_utils.consolidate_backbone_kwargs_to_config ->
   HfApi.repo_exists(swin...) hits the hub; no internet on the hotspot -> reset/raise uncaught.
   highlight_seg.py wraps repo_exists to fail-safe False -> timm builds the backbone offline;
   run_mvd.sh exports HF_HUB_OFFLINE=1).
9. Full DJI REST client (dji_wire.py grew 3 endpoints -> whole surface).
10. Expanded voice verbs (spin, scan/search orbit modes, track/follow/come_home phone-GPS, gimbal
    forward/down/up, wave, directionals -> native fly_by).
11. stop = halt() (delay:0), not /c/stop, and no longer latches manual (that latch was the
    "can't control after stop" bug). manual = RC handoff (/c/stop), resume = pop.
12. phone_ears.py matched to the app's real contract (/input + raw TCP, dedupe, receipt logging).
13. TTS wired end-to-end (answer -> voice.say(short) -> phone /tts + laptop espeak).
14. Structured LONG/SHORT perception output (screen Scene:+Spoken:; speak only SHORT; concise-first
    prompt; robust parser, graceful fallback, no label leaks).
15. Verbose [dji] request logging + [phone_ears] receipt logging.
16. go-unknown guard (movement intent w/o direction = no-op + feedback, never scene-describe);
    teardown hardened (SIGKILL pane groups + free port + wait); "go backwards" plural fixed.

## 9. Loose ends (corrected with the human)
DJI BACKEND (dev) — blockers:
1. Dynamic groundstation-IP discovery (phone must learn the laptop IP; the // fixme). Without it ASR
   can't reach us at all.
2. Gimbal commands broken — no gimbal_pitch responds EXCEPT from a fully-down gimbal "look forward"
   returns to horizon; nothing else. Our JSON matches the DTO -> backend-side. (fly_by works.)
3. API-Server/video reliability — Android suspends ApiServerService when backgrounded/locked ->
   :8080 + :5600 drop. Needs a foreground service + battery-opt exemption.
DEFERRED (tomorrow, must NOT break integration/*): laptop TTS `sudo apt install espeak-ng` (phone /tts works).
VERIFIED DONE (do not redo): real-flight command verification (that IS how we debugged); phone->GS
transport design (= #1); fly_by. VLM conciseness good — revisit only if it hallucinates.

## 10. Next tracks (Demo Day = Thu 2026-08-27)
1. Pitch prep — reorganize internally, build the narrative around the working MVD.
2. llm_to_action — assess source/llm_to_action/ C++ engine + how to connect current Python perception;
   stretch = end-to-end VLM flight. It is the DESTINATION product; the Python router is the MVD
   prototype. Do not confuse them.
3. Robomaster backend + acquisition — last big item. RoboMaster S1 has NO remote SDK (Tello trap); buy EP / EP Core.
4. Dashboard (handoff SPEC, not built) — ref youtu.be/vO6SWG-jxvE at ~1:25 (highlight+segment + the
   dashboard chrome; ignore heatmap). Use the human's recommended layout AND a proposition. Functional +
   real-time diagnosis (video, telemetry, ASR transcripts, router tier, [dji] POSTs+status, VLM
   LONG/SHORT, watchdog health). Diagnostic data already on stdout ([dji]/[phone_ears]/[voice]).

## 11. Run + diagnose (human runs; assistant never fires arm/motor to a real drone)
- Launch: `bash /root/groundstation/source/integration/run_mvd.sh dji real`
- Control: `curl -s http://<phone-ip>:8080/status/`
- Video broken? `python3 /root/groundstation/source/integration/video_doctor.py`
- Phone reaching us? (laptop, SAFE) `curl -s http://localhost:8080/health` ;
  `curl -s -X POST -H "Content-Type: application/json" -d '{"text":"what do you see"}' http://localhost:8080/input`
- Watch traffic: `tail -f /tmp/mvd_app.log`  ([phone_ears] <- , [dji] POST -> HTTP , [voice] -> /tts)
SAFETY (CLAUDE.md): assistant NEVER sends arm/takeoff/land/stick/motor to a real drone — prepares and
hands over; human runs. Secure the aircraft first. Kill: phone API-Server toggle OFF -> hold power
button 3-5s -> DJI CSC. stop(delay:0) and manual are software, not the kill.
CONTAINER CAVEAT: the assistant runs in a container whose pgrep/ss/tmux view can be ISOLATED from the
host. Do NOT conclude "app not running / port dead" from container-side checks — verify on the host.

## 12. Repo state — uncommitted / unaccounted changes (as of 2026-08-25 handoff)

`git status` at handoff shows the following NOT-yet-committed with our MVD commit. Dispositions:

**Ours — commit with the MVD work:**
- `?? docs/active/mvd-voice-command-table.md` — the ASR->DjiWire->DJI-REST-JSON command table (this session). COMMIT.
- `?? docs/integration-mvd-2026-08-24.md` — the MVD spec (untracked, referenced throughout). COMMIT.

**Intentional structural move (human, mono-repo consolidation):**
- `D scripts/dashboard/{README.md,assess.py,dashboard.html,mock_data.py,serve.py}` +
  `?? source/llm_to_action/dashboard/` — the dashboard was MOVED from `scripts/` into
  `source/llm_to_action/dashboard/` on purpose: the repo is effectively a mono-repo with sub-repos under
  `source/`, and the dashboard's logical home is with `llm_to_action`. So **the dashboard track lives
  under `source/llm_to_action/dashboard/`**, not `scripts/`. Structural debt (acknowledged), not a bug.

**Prototype leftovers — the ORIGINALS the MVD was consolidated FROM (separate decision):**
- `M source/llm_cv_scene/{config.py,vlm.py,run_demo*.sh,run_llama_server.sh}` and
  `M source/llm_cv_track/{highlight_seg.py,scene_omdet.py,run_scene_omdet.sh}` +
  `?? source/llm_cv_track/run_mvd.sh` — these are the standalone perception prototypes. `source/integration/`
  is now the CANONICAL, self-contained MVD (byte-copied + fixed from these, then decoupled). Treat
  `integration/` as source of truth; these llm_cv_* edits are largely superseded. Do NOT re-wire the MVD
  to them. The human decides whether to commit, archive, or drop them.
- `?? scripts/test/router/` — router test scratch/artifacts; inspect before committing.

**Infra / environment (from earlier sessions, not the MVD):**
- `M scripts/Dockerfile`, `M scripts/build-devenv.sh` — devenv build changes.
- `M scripts/test/dji_mock/mock_apiserver.py` — the mock we validate the wire against (implements
  /c/takeoff, /c/land, /c/stop, /c/fly, /c/ws/sticks, /status). Useful; commit if you want the router
  tests reproducible.
- `M .claude/settings.local.json` — local agent settings (usually not committed).

**Git ownership note:** the repo trips git's `safe.directory` guard in the container/VS Code (UID mismatch
from the bind-mount). Fix GUI-wide with `git config --system --add safe.directory '*'` (writes
`/etc/gitconfig`, which VS Code's git also reads), or inline per command with
`git -c safe.directory=/root/groundstation ...`. It's a safe whitelist in this single-user root dev env.
