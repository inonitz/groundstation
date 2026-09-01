# Demo-Day run-of-show — Thu 2026-08-27

The one page for demo day. Main show = the MVD (voice -> drone + smart CV). llm_to_action is a
bonus bench segment (section 8). The assistant PREPARES; the human runs every armed/real command.

Absolute paths from `/root/groundstation`. Phone IP is the WiFi gateway — DERIVE it, never hardcode
(the `10.222.215.92` in old docs is stale).

---

## 0. Timeline
- **10:00–12:00 on-site:** setup, kill-switch drill (MANDATORY), F2 latency capture, full dry-run.
- **~16:00:** the demo.

## 1. What we show, in order
1. **MVD main demo** — speak a verb -> the drone flies; ask a question -> smart CV understands the scene.
2. **llm_to_action bench** (section 8) — the C++ "destination" engine, on the mock. Optional/bonus.

## 2. Power-on order (do NOT skip a step)
1. Laptop up; PulseAudio + display alive.
2. Drone ON, RC ON, phone ON + hotspot, laptop joined to the hotspot.
3. Phone: **API Server toggle ON** (foreground the app — Android suspends it backgrounded).
4. Derive the phone IP and verify the whole chain BEFORE launching:
   ```bash
   GW=$(ip route | awk '/^default/{print $3; exit}'); echo "phone=$GW"
   curl -s "http://$GW:8080/status/" | head -c 200; echo     # want aircraft JSON, not 503
   python3 scripts/test/dji_mock/probe_video.py "$GW" 5600 5  # want VIDEO LIVE
   ```
   503 = chain down (RC↔phone USB / aircraft off / MSDK not activated). Fix before proceeding.
5. Launch the MVD (HUMAN runs `real`; it prompts `ARMED`):
   ```bash
   PHONE_IP=$GW bash source/integration/run_mvd.sh dji real
   ```
   Press **H** to talk. Ctrl-C = full shutdown.

## 3. Kill-switch drill — MANDATORY before ANY arm (kill-switch-verification.md)
Props OFF, aircraft clamped/held in open space, NOT on a table. Run A/B/C once, record it.
1. **Power button hold 3–5 s** = the hardware net. Must stop motors < 5 s. Non-negotiable.
2. **API Server toggle OFF** = drops our virtual-stick authority. Must stop < 2 s.
3. **DJI CSC** (both sticks bottom-inner) — may be overridden while our stick is active; record which.
Software halt (not a substitute): say **"stop"** -> `POST /c/fly [{"type":"delay","seconds":0}]`.

## 4. The verb script (choreography) — mvd-voice-command-table.md
**Indoor-reliable (no VPS lock needed):** `takeoff` · `spin` · `up` / `down` · `wave` · `land`.
Emergency at any time: **"stop"** (halt, keeps our control) or **"manual"** (hand back to RC pilot).
**Outdoor-only (needs GPS/VPS):** `forward`/`back`/`left`/`right` · `follow` · `look at me` · `come home`.
**Known-broken, skip on stage:** gimbal (`look up/down/forward`) — broken BACKEND-side; `fly_by` works.
Length guard: BASIC verbs fire only on ≤ 4 words. Emergency/manual/resume ignore length.

## 5. The intelligence (the differentiator) — perception
Any non-verb / > 4 words -> Qwen-VL + OmDet/SAM2 on the laptop. **No drone motion.** Answer splits:
LONG on screen (`Scene:`), SHORT spoken (phone `/tts` + laptop espeak).
Stage lines: **"what do you see"**, **"how many windows"**, **"highlight the red backpack"**.

## 6. Fallbacks (rehearse each once)
- **Video stalls** -> `video_watchdog` auto-reconnects gst. If not, relaunch with `webcam` video.
- **Laptop ASR flaky** -> use phone ASR (`POST :8080/input`) or the phone mic path.
- **Indoor, drone refuses lateral/vertical** -> VPS can't lock (physics, not a fault). Fall back to
  yaw/spin/vertical/wave + the perception showcase. Say so plainly — it reads as competence.
- **:8080 / :5600 drop mid-demo** -> Android suspended the API Server. Foreground the app, re-toggle ON.
- **Anything scary** -> kill-switch section 3, power button first.

## 7. F2 latency capture (on-site, props off / tethered) — the scored < 1 s number
```bash
# HUMAN runs; drone secured. Fills command->action p50/p95:
build/release/shared/dji/bin/dji_latency_probe "$GW" 8080 30 8
```
Record p50/p95 into dji-bringup-runbook.md Task C. This is the top UNPROVEN scored item.

## 8. llm_to_action bench segment (bonus) — [DEMO MODE: A / B — pending]
The C++ "destination" engine, run on the MOCK (no aircraft). Proven today: scenario control loop
(takeoff -> climb -> GO closed-loop, 20 Hz, ONNX perception loaded).
```bash
pip install aiohttp   # once
source /opt/ros/jazzy/setup.bash
BIN=build/release/shared/dji/bin
ONNX=build/release/shared/dji/_deps/onnxruntime/onnxruntime-linux-x64-1.20.1/lib
export LD_LIBRARY_PATH="$BIN:$ONNX:$LD_LIBRARY_PATH"
python3 scripts/test/dji_mock/mock_apiserver.py 127.0.0.1 8080 &
"$BIN/llm_to_action_fmu_dji" "" --scenario-orbit    # or -hover / -follow / -rotate
```
- **Mode A** (scripted): the above. Shows the real-time engine executing a multi-step plan.
- **Mode B** (live LLM plan): add llama-server + a spoken objective -> "language to flight plan."
  UNVERIFIED — verify before committing to show it.
Talk track: "this is our production C++ flight engine — the same one, on the bench, planning and
executing autonomously. The voice demo you just saw is the deterministic-safety layer on top."
