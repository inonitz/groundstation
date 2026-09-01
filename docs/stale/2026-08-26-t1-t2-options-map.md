# T1 / T2 options map — 2026-08-26 (for the human to sequence)

Breadth + measurements, no recommendation. Demo is TOMORROW (Thu 2026-08-27 ~16:00). Every
"MEASURED" line below was run on this laptop today against the mock (127.0.0.1 only, per CLAUDE.md).

---

## T1 — the llm_to_action C++ FMU flying (headline win)

### Status: PROVEN on the mock, end-to-end. Nothing to build.
- `llm_to_action_fmu_dji` (3.6M) and `dji_backend_mock_test` are ALREADY built in
  `build/release/shared/dji/bin`. The +2-line CMake `dji` branch is in place.
- **MEASURED — DjiBackend soak vs mock:** PASS. 250 commands, 0 send-fails, takeoff code=0,
  land code=0, telemetry fresh 9/9 (max age 63 ms), odometry model tracked the sticks.
- **MEASURED — full FMU node, `--scenario-hover` vs mock:** ran the whole engine. WS-connected,
  loaded ONNX seg+depth on CPU (by design), FMU active @ 20 Hz, executed TAKEOFF -> climb to
  2.12 m -> GO-forward 0.30 m/s closed-loop, mock odometry tracked cmdVel, 227 stick frames
  streamed. The C++ engine flies the mock drone with no LLM in the loop.

### Cheapest live path to a DEMO
1. Scenario mode skips the VLM. So the mock demo needs NO llama-server. Verbs are scripted JSON
   (`--scenario-hover`, `--scenario-rotate`, `--scenario-orbit`, `--scenario-follow`, etc; ~19 flags).
2. The run recipe that works (found by measuring — no wrapper script exists yet):
   ```
   pip install aiohttp                 # mock dep; was MISSING on this box, now installed
   source /opt/ros/jazzy/setup.bash
   BIN=build/release/shared/dji/bin
   ONNX=build/release/shared/dji/_deps/onnxruntime/onnxruntime-linux-x64-1.20.1/lib
   export LD_LIBRARY_PATH="$BIN:$ONNX:$LD_LIBRARY_PATH"
   python3 scripts/test/dji_mock/mock_apiserver.py 127.0.0.1 8080 &   # mock on 8080
   "$BIN/llm_to_action_fmu_dji" "" --scenario-hover                    # the engine
   ```

### Gaps (small, all non-code)
- No launch wrapper for the standalone FMU. `run_mvd.sh` launches the MVD, not the bare FMU.
  A ~15-line `run_fmu.sh` (the block above) would make it one command. Not written yet — your call.
- Runtime deps that bit today and will bite on any fresh shell: `aiohttp` (mock) and the
  onnxruntime lib dir on `LD_LIBRARY_PATH`. Both fixed here; confirm on the demo laptop.

### Real-drone step (HUMAN-ONLY — I do not run this)
- `dji-bringup-runbook.md` Tasks B/C are the real-link path: `dji_backend_mock_test <PHONE_IP> <PORT>`
  soak, then `dji_latency_probe <PHONE_IP> <PORT> 30 8` for the scored command->action number.
- The FMU against a real drone is the same binary with host/port retargeted off the mock default.
  Aircraft SECURED, props off/tethered, kill = phone toggle / power button. You arm, not me.
- Open scored item F2 (command->action < 1 s) is still UNPROVEN on the real link; the probe fills it.

---

## T2 — RoboMaster as a second backend (headline win, time-sensitive TODAY)

### Status: offline-ready for the trip. Blocked on hardware (unit ~2 h out) + one unknown.
- **Offline assets present on disk:** `source/robomaster/` has the probes (`s1_probe.py`,
  `s1_video.py`, `s1_text.py` — stdlib only) AND the collabnix unlock repo fully cloned
  (`root.py_s1`, `upload.sh`, `s1_sdk_hack.zip`, the root PDF). No internet needed at the seller.
- **The one decisive test:** on the robot's Wi-Fi, `python3 s1_probe.py` (-> 192.168.2.1:40923).
  `*** SDK MODE ENABLED ***` = turnkey, buy it. `CONNECT FAILED` = locked, needs the unlock.

### The two gates BEFORE money (from FIELD_CHECKLIST)
1. **Platform gate:** S1 has NO official SDK; EP / EP Core ship with it ON. If it is an EP, the
   whole firmware question evaporates.
2. **Firmware trap (S1 only):** the unlock rides a Lab/Python sandbox escape DJI patched in later
   firmware. "Do NOT update." **The exact safe-vs-blocked version is UNVERIFIED in our docs.**
   On-site: read the version off the app, ask update history. Never-updated = safe. Latest + no
   downgrade file = walk away.

### Cheapest live path to a DEMO (once a usable unit is in hand)
- The S1 streams raw H.264 on TCP 40921 — same shape as the drone feed. Point
  `SCENE_INPUT="tcpclientsrc host=192.168.2.1 port=40921 ! h264parse ! ..."` straight into
  `scene_omdet.py` (video-in only, ~1 h per the README). This proves "same brain, different
  platform" with ZERO shared-C++ changes.
- The clean route (point `llm_to_action_gstreamer_rx` at 40921, publish `camera/stream`) is the
  only place the standing rule allows touching shared C++ — and even that is a host/port change.

### Gaps
- `adb` is NOT on PATH on this box. The probe doesn't need it; the *unlock* (step 3, `adb shell`)
  does. If the unit is stock, install adb on the demo laptop before the unlock.
- **OPEN — the exact safe S1 firmware version.** Our docs punt it to on-site reading. I can try to
  web-source it now if you want a number in hand before the seller. Say the word.
