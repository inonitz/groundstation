# MVD integration plan — 4-tier command router (2026-08-24)

Same-day sprint. One human, ~8 hours to build and test. This is the executable checklist.
Read `CLAUDE.md` first. It overrides everything here, especially the drone-safety rules.

## Safety banner (non-negotiable)

- The assistant/agent NEVER sends arm/takeoff/land/stick/velocity/motor commands to the real drone.
  The agent prepares the command. The HUMAN runs it.
- Real phone IP is `10.222.215.92:8080`. The agent NEVER targets it with a control tool.
- All agent-run control testing hits the mock at `127.0.0.1:8080` only.
- Steps that can spin motors are marked **[HUMAN-ONLY / real]** or **[agent OK / mock]**.
- Indoors the drone refuses horizontal and vertical sticks (VPS cannot lock). Yaw and slow
  vertical only. This is expected, not a bug.

---

## Manager's independent recommendation (read before you start)

You asked for a 4-tier flight router. I am building it. But I disagree with making the
*flying* router today's primary goal, and I am saying so per the house rules.

- **OBJECTIVE:** ship a voice + perception + drone demo that passes the technical-credibility gate.
- **ROI:** the committed MVD (locked 2026-08-22) is voice -> Python perception -> answer on the
  live drone video. That path is nearly done. It is the graded threshold. It does not fly the drone.
- **KILL-SHOT:** a router that flies the drone is the *stretch* "physical llm_to_action" path. The
  roadmap marks it "only if the core holds, decided with the Android dev." Building it before the
  perception MVD is tested end-to-end is scope creep, and it adds the whole drone-safety risk surface
  under an 8-hour clock.

So this plan is phased. **Phase 0 secures the committed perception MVD.** The router is built on top,
in Python, and every motion tier is gated and human-only. If time runs short you still ship Phase 0,
which is the thing you are actually graded on.

---

## Current-state map (what exists vs what is missing)

Verified by direct repo scan on branch `feature-llm-smart-scene`, 2026-08-24.

- **Transcript source works.** C++ ROS2 node `source/llm_to_action/asr/asr_node.cpp`
  (`llm_to_action_asr_server`, Parakeet, `--language=en`). Push-to-talk on the H key. Publishes
  `std_msgs/String` on `/asr_server/transcribe`. The bus is already multi-subscriber.
- **Transcript entry seam works.** `source/llm_cv_scene/ears.py` (`class Ears`) subscribes to that
  topic and fires an `on_text(text)` callback. Any new consumer just subscribes to the same topic.
- **Perception works, but emits NO drone command.** `llm_cv_scene` (safety-net) and `llm_cv_track`
  (star, OmDet-Turbo) both terminate at on-screen overlay + TTS. There is no verb output anywhere in
  Python. This is the core gap for any motion tier.
- **Tier-1 regex ALREADY EXISTS on the phone app — this is the reuse source.** Android app
  `/root/DJI-android-sdk-v5-recon-swarm/.../res/values/strings.xml` (lines 526-570) holds the full
  pipe-delimited command regex vocabulary; `com/kcg/dr/voice/SpeechResolving.kt`
  (`class RegexCommandResolver`) matches it case-insensitive, first match wins. The app already has a
  3-way parser concept: Flash=regex / Deep-Think=LLM / Ground-Station. Port the regex strings to the
  Python router; do not reimplement from scratch.
- **A second (dead) keyword map exists in C++.** `asr_node.cpp:64 parse_msg_for_drone_topics` is
  fully commented out. Same verb families. Use it only to cross-check the strings.xml set.
- **The C++ string->verb map exists and is tested.** `fmu/command_id.hpp` `commandIdFromAction()`
  (enum TAKEOFF/LAND/STOP/GO/ROTATE/ORBIT/...), unit-tested by `fmu/test/fmu_translate_test.cpp`.
- **The real router exists only in C++, and the C++ engine is not built.** `fmu/fmu_node.hpp:410
  handleAsrCommand` implements emergency LAND, emergency STOP/HOLD, and an operator override topic.
  It needs the full ROS2/C++ FMU + DjiBackend build, which is unverified and out of scope today.
  Treat it as the reference design, not the thing you run.
- **Control wire is frozen and mocked.** Android `ApiServer.kt` exposes `GET /status/`,
  `WS /c/ws/sticks` (`{vx,vy,vz,yaw}` body-frame m/s), `POST /c/takeoff|land|stop|fly`, `POST /tts`.
  `POST /c/stop` = `stop(emergency=true)` = `relinquishControl()` (the software kill). Mock at
  `scripts/test/dji_mock/mock_apiserver.py`. Python can POST/stream this wire directly, so the router
  needs no C++ engine at all.

Tier readiness summary:

| Tier | Exists | Missing |
|------|--------|---------|
| 1 basic -> regex -> verb | strings.xml regex + RegexCommandResolver (app) | Python port + verb dispatch to the wire |
| 2 complex -> perception -> verb | perception (answer/highlight) | target -> verb bridge; for MVD, answer is enough |
| 3 user override | C++ override topic + app take/relinquish (unbuilt on Linux) | Python override flag that stops stick streaming |
| 4 emergency fast-path | `POST /c/stop` (relinquish), `POST /c/land` | Python fast-path caller, checked first |

---

## Merge decision: llm_cv_scene + llm_cv_track

**Do NOT merge today. It is a distraction.** One-line reason: `llm_cv_track` already *imports*
`llm_cv_scene` (config, vlm, eyes, ears), so ~60-70% is already shared and a refactor buys zero
demo function under the clock.

What to do instead: pick `scene_omdet.py` as the single demo app. It is the star path (OmDet-Turbo
open-vocab, follows the object) and it reuses the frozen scene modules. Keep `llm_cv_scene/app.py`
as the untouched safety-net backup. The only genuinely distinct code is the highlight detector
(already pluggable via `SCENE_HL_BACKEND`) and `follow.py`'s tracker (parked). Fold OmDet in as a
registered backend on Tue/Wed hardening, not today.

---

## Architecture — the router (Python, thin, on top of what works)

Build one new module: `source/llm_to_action/router/` (Python). It subscribes to the transcript bus,
classifies, and acts on the frozen wire. No C++ build. No LLM in the motion path.

```
/asr_server/transcribe (Parakeet, H-to-talk)
        |
     ears.py on_text(text)
        |
   router.dispatch(text)          <-- new
        |
   +----+------------------------------------------------+
   | Tier 4 EMERGENCY  (checked FIRST, always)           |  regex stop/halt/land/abort
   |   -> POST /c/stop  or  POST /c/land                 |  [HUMAN-ONLY / real] [agent OK / mock]
   +-----------------------------------------------------+
   | Tier 3 OVERRIDE   (flag check)                      |  manual flag set -> router streams
   |   -> stop streaming sticks; RC/human has authority  |  nothing; drone holds, RC flies
   +-----------------------------------------------------+
   | Tier 1 BASIC      (regex keyword map)               |  takeoff/land/go */rotate *
   |   -> deterministic verb -> wire                     |  [HUMAN-ONLY / real] [agent OK / mock]
   +-----------------------------------------------------+
   | Tier 2 COMPLEX    (everything else)                 |  -> existing perception (scene_omdet)
   |   -> VLM answer / highlight (MVD)                   |  answer via /tts; motion is stretch only
   +-----------------------------------------------------+
```

Router rules that must hold:

- **Order is fixed: emergency, override, basic, complex.** Emergency is evaluated before anything
  parses, so "stop"/"land" is never delayed by VLM latency.
- **The VLM never drives motion.** Tier 2 for the MVD produces an answer or a highlight only. Any
  motion from a target is deterministic and bounded, and is stretch work, not MVD.
- **Motion goes to the wire, not through the C++ engine.** `POST /c/takeoff|land|stop` for discrete
  verbs; `WS /c/ws/sticks` streaming `{vx,vy,vz,yaw}` at ~15-18 Hz for go/rotate. Stream is also the
  keepalive; stop sending and the drone hover-brakes.
- **Indoors: only yaw and slow vertical produce motion.** Map go-forward/back/left/right to a no-op
  or a spoken "blocked indoors" when VPS is not locked. Do not fight the drone.

Basic-verb regex source (port from the app `strings.xml`, the intended vocabulary):

```
stop     = stop|halt|quit|end
takeoff  = takeoff|take off|fly|liftoff
land     = land|landing|ground|down|perch|floor
go_up    = (go )?(up|rise|high)
go_down  = (go )?(down|under|low)
go_forward = (go )?forward
go_backward= (go )?(back(ward)?)
go_left  = (go )?left(ward(s)?)?
go_right = (go )?right(ward(s)?)?
spin     = spin|((spin|look) around)         # yaw
```

Emergency set (checked first, superset of stop + land families above): stop, halt, freeze, hold,
hover, land, abort, emergency, mayday, come down, get down, descend.

---

## The 8-hour checklist (ordered, each item small and testable)

### Phase 0 — secure the committed perception MVD (hours 0-2.5). Ship this no matter what.

0.1 Pre-warm and smoke-test `scene_omdet.py` on webcam. `bash source/llm_cv_track/run_scene_omdet.sh`
    (use `ASR_CAPTUREID=5` for the C920 mic). Confirm the window opens, background boxes draw, and
    H-to-talk transcripts arrive. Test: say "highlight the <object>" and "what do you see". [agent OK]

0.2 Bring up the drone video into perception. Prefer the rx_node ROS topic path over OpenCV capture.
    Fallback is drone RTMP (`run_scene_omdet.sh rtmp`) or `SCENE_INPUT=tcpclientsrc host=<phone>
    port=5600 ...`. Test: live drone frames render. **[HUMAN-ONLY: drone powered / secured for any
    real link]** Decode is read-only, but the aircraft must be on.

0.3 Confirm voice-out. `voice.py` POSTs the VLM answer to the phone `POST /tts`. Test the mock first
    (agent), then the real phone (human). Test: ask a question, hear the answer.

0.4 Full loop test: voice question -> perception answer -> spoken reply, on live drone video.
    **This is the graded MVD. If you ship only this, you passed the threshold.**

### Phase 1 — router skeleton + emergency + override, mock only (hours 2.5-4.5)

1.1 Create `source/llm_to_action/router/router.py`. Subscribe to `/asr_server/transcribe` (reuse an
    `Ears`-style subscriber). Add a `WireClient` that POSTs `/c/takeoff|land|stop` and opens
    `WS /c/ws/sticks`. Host is config, default `127.0.0.1:8080`. Test: `python3 router.py` connects
    to the mock and logs each transcript. [agent OK / mock]

1.2 Implement Tier 4 emergency FIRST. Regex the emergency set. On match, POST `/c/stop` (hold) or
    `/c/land`. Test on the mock: "stop" -> mock logs `/c/stop`; "land" -> mock logs `/c/land`.
    Confirm it fires before any other tier. [agent OK / mock]

1.3 Implement Tier 3 override. A shared boolean flag (keyboard toggle, or a ROS Bool topic mirroring
    the C++ `kFmuOverrideTopic`). When set, the router stops streaming sticks and ignores basic-verb
    motion; emergency still works. Test: toggle on, send "go up", confirm no sticks streamed. [agent OK / mock]

1.4 Run the whole skeleton against the mock.
    `python3 scripts/test/dji_mock/mock_apiserver.py 0.0.0.0 8080`, then drive the router with voice
    or piped text. Confirm emergency + override behave. [agent OK / mock]

### Phase 2 — Tier 1 basic verbs, mock only (hours 4.5-6)

2.1 Port the basic-verb regex from `strings.xml` into `router.py`. Discrete verbs (takeoff/land) ->
    POST; go/rotate -> a short bounded `{vx,vy,vz,yaw}` stick burst on `WS /c/ws/sticks`, then zero.
    Clamp velocity (`<= 2.0 m/s`) and yaw. [agent OK / mock]

2.2 Gate horizontal/vertical for indoors: if VPS not locked, respond "blocked indoors", do not
    stream. Yaw and slow vertical are allowed. [agent OK / mock]

2.3 **YAW UNITS — now confirmed, do not repeat the C++ bug.** The app's virtual stick is
    ANGULAR_VELOCITY in **deg/s** (agent-confirmed in `DJIVirtualStick.build()`). The C++ DjiBackend
    sends rad/s -> ~57x too slow. In the Python router, send yaw in **deg/s**. The SIGN (CW+ vs CCW+)
    is still unconfirmed; verify against the mock echo, and never command yaw on the real drone until
    the sign is settled. [agent OK / mock]

2.4 Full router test on the mock: emergency, override, all basic verbs, tier-2 fallthrough to
    perception. Confirm ordering + clamps. [agent OK / mock]

### Phase 3 — real-drone verification, HUMAN-ONLY (hours 6-7.5)

3.1 **Run the kill-switch verification first.** Follow `docs/active/kill-switch-verification.md` end
    to end. Tests A and B must pass before any armed command. Props off, airframe clamped in open
    space. **[HUMAN-ONLY / real]**

3.2 Point the router at the real phone (`10.222.215.92:8080`) and test safest verbs first: emergency
    stop, then yaw, then slow vertical. Skip horizontal indoors. The human runs every motor command.
    **[HUMAN-ONLY / real]**

3.3 Full voice demo dry-run: perception answer loop + a couple of bounded basic verbs, human at the
    kill. **[HUMAN-ONLY / real]**

### Phase 4 — buffer / hardening (hours 7.5-8)

Fix whatever broke. Write the demo script. Record a clean run.

---

## Time budget

| Block | Hours | Deliverable |
|-------|-------|-------------|
| Phase 0 | 0 - 2.5 | Committed perception MVD on live drone video (the graded threshold) |
| Phase 1 | 2.5 - 4.5 | Router skeleton + emergency + override, green on mock |
| Phase 2 | 4.5 - 6.0 | Tier-1 basic verbs, green on mock, yaw in deg/s |
| Phase 3 | 6.0 - 7.5 | Real-drone verification, human-run, kill-switch proven first |
| Phase 4 | 7.5 - 8.0 | Buffer, demo script, recording |

## MVD triage — what to cut if time runs short (in cut order)

1. **Cut first: real-drone flight (Phase 3).** Demo the router flying against the mock; show the
   perception MVD live on drone video. You keep the graded threshold.
2. **Cut next: Tier-1 basic motion verbs (Phase 2).** Keep emergency + override + perception.
3. **Cut next: Tier-3 override polish.** Emergency alone is the safety floor.
4. **Never cut: Phase 0.** The perception + voice loop on live drone video is the demo.

---

## Open questions the human must answer before building

1. **Is the drone flying today at all?** Phases 0.2 and 3 need a powered, secured aircraft and the
   phone on the hotspot. If not, real-drone work slips and you demo perception on recorded/webcam video.
2. **Video path: rx_node ROS topic or RTMP?** The roadmap says route through rx_node, not OpenCV. Is
   the rx_node -> perception frame path wired and tested, or do we fall back to RTMP today?
3. **Yaw SIGN on the real app.** Units are settled (deg/s). Sign (CW+ vs CCW+) is not. Read the app
   mapping or test empirically with the human at the kill. No yaw on the real drone until settled.
4. **Does this sprint override the locked "no autonomous flight" MVD decision?** The flying router is
   the stretch path the roadmap says to decide *with the Android dev*. Confirm that call was made, or
   hold at Phase 0.
5. **Where should the router live and how does it reach the wire?** This plan puts it in Python
   (`source/llm_to_action/router/`) talking straight to the ApiServer, bypassing the unbuilt C++
   engine. Confirm that is the intended shape, not a C++ FMU build.
