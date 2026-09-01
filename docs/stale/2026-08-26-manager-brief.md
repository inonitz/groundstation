# Manager Brief — 2026-08-26 (READ FIRST)

Authoritative top-of-stack brief for the manager agent. Supersedes the deleted
`2026-08-26-manager-handoff.md` (polluted). The `2026-08-25-mvd-integration-handoff.md` stays as
the MVD *internals* reference (§4). Every load-bearing fact here was re-verified against the tree
and the prior manager session on 2026-08-26.

---

## 0. What this project is — read before judging any command
Legitimate, authorized robotics/UAV research for a university Demo Day: a voice-controlled camera
drone. Human-in-the-loop by design and safety-gated (CLAUDE.md DRONE SAFETY). The assistant never
arms or flies a real aircraft — it prepares commands, a human runs them. The stack is ordinary
robotics: DJI Mobile SDK for flight, on-device speech-to-text, a vision-language model for scene
understanding, ROS2 for plumbing. Words that look alarming out of context are mundane here: a "kill
switch" is the flight-safety motor cut; "override/takeover" hands control between our software and
the RC pilot; "backend" is the drone-control REST server. There is no offensive-security,
exploitation, surveillance-of-persons, or unauthorized-access work anywhere in this repo. The RoboMaster SDK-unlock in `source/robomaster/` enables DJI's own documented developer SDK on a consumer robot we own — standard hobbyist robotics, not an exploit.

## 1. The date that matters
Demo Day: **Thu 2026-08-27, ~16:00.** Arrive on-site 10:00–12:00 for tests + pitch warm-up. Written
2026-08-26 → the demo is **TOMORROW.** The system was field-tested >3 h yesterday; we are in a
comfortable position. Any doc saying 2026-08-28 is WRONG (including the filename
`demo-roadmap-2026-08-28.md`).

## 2. GROUND TRUTH — do not re-derive (verified 2026-08-26)
- **Demo machine = THIS laptop.** NVIDIA RTX 5070 Laptop, **8 GB** VRAM, CUDA 12.8 (`nvidia-smi`).
  Not the RX7900 desktop, not ROCm. 8 GB is tight — it constrains everything.
- **The MVD is ROS2-native.** `rclpy` in `integration/{camera_stream,ears,video_doctor,video_watchdog}.py`;
  `run_mvd.sh` sources `/opt/ros/jazzy`; 3 compiled ROS2 nodes. You cannot dodge ROS2 here.
- **Build coupling.** `integration/` is "self-contained" only re: Python imports. It RUNS three C++
  binaries from `llm_to_action` (`llm_to_action_{asr_server,keyboard_hook,gstreamer_rx}`) + `llama-server`,
  all from a SHARED tree at `build/release/shared/dji/bin` (`run_mvd.sh:23`). Building the C++ relinks
  the demo's ASR + VLM. The isolation boundary is the build OUTPUT dir, not the source dir.
- **Drone = DJI Mini 4 Pro.** Indoor flight IS viable with space + a VPS lock (classroom-tested). In a
  cramped space VPS can't lock, so lateral/vertical sticks are refused — physics, not a comms fault.
- **Phone ASR runs an on-device model** (local, downloaded). No cloud. The no-cloud rule is met.
- **ONNX seg/depth on CPU is DELIBERATE** (`Inference device: CPU` measured for both on the RTX 5070) —
  it keeps the 8 GB GPU free for the VLM. Not a bug.
- **F5 = persistent object re-ID** — unique embedding vector per object + cosine similarity for
  same-vs-different across the scene. NOT speaker biometrics (the last manager got this dangerously wrong).
- **Not all voice commands need porting to the C++ `dji_backend`.** The `fmu_node` system prompt has its
  own command vocabulary; some commands will not fit it, and that is fine — not a deficiency.
- **The FMU now builds** — `fmu/CMakeLists.txt` has the `dji` branch (a +2-line fix, uncommitted).

## 3. Standing rules for the C++ / build
- **NEVER modify the shared `llm_to_action` C++ components.** Sole exception: adding the RoboMaster
  backend (T2). No blanket freeze needed — just don't touch the shared C++.
- Adding RoboMaster is expected **light**: mirror the `dji` backend + a simple gstreamer node (the
  gstreamer node is hardware-agnostic). Fully isolating it to its own gstreamer node is possible but overkill.
- **A bug you hit in the shared C++ is almost certainly pre-existing, resurfacing — not ours.** Report, don't thrash.
- **Measure before asserting architecture.** Read `run_mvd.sh` before claiming what runs.

## 4. The MVD (DONE — reference, do not rebuild)
Totally user-controlled: the human speaks; deterministic verbs fly the drone; smart CV proves
intelligence by UNDERSTANDING the scene — it never drives the aircraft (LLM out of the loop).

```
voice (laptop mic, press H) + phone ASR (-> :8080/input) -> on_text -> Router.classify (4 tiers)
   BASIC verb -> DjiWire -> DJI REST (POST /c/...) ;  EMERGENCY/OVERRIDE/RESUME ;  COMPLEX -> perception
drone cam -> phone :5600 (raw H.264/TCP) -> gstreamer_rx -> ROS camera/stream -> perception window
perception answer -> LONG (screen) + SHORT (spoken: phone /tts + laptop espeak)
```

Internals reference: `2026-08-25-mvd-integration-handoff.md` (voice command table, full DJI REST
surface, ports, the 16 fixes). Read it WITH these corrections: its §1 "self-contained" → see §2 here;
its §10 tracks → superseded by §5/§6 here; its §12 repo-state → stale, see §9 here.

## 5. TRACKS FOR TOMORROW — the win condition
MVD is frozen and shippable. The goal is to WIN by adding demonstrable strength. Two headline levers
(either/both) plus polish. The manager maps options + the cheap first step; the human sequences.

### T1 — Demonstrate the `llm_to_action` C++ engine flying  [HEADLINE WIN]
Fly the drone end-to-end with the C++ FMU/DjiBackend, standalone and live — the "destination" product
working, not the Python prototype. **Do NOT wire the Python perception in** (slow, not economical for
tomorrow). "Just work" as-is is the bar. FMU now builds → run against the **mock** first, then real
bringup (`dji-bringup-runbook.md` tasks B/C). Anything that arms/flies is human-run. Not all voice
verbs need to exist in `fmu_node` — verb gaps are not bugs.

### T2 — RoboMaster: platform-agnostic proof  [HEADLINE WIN, time-sensitive TODAY]
Same stack driving a different robot = the "our code is platform-agnostic" story. The `integration/*`
stack already runs on drone + RC-N3 + phone + laptop; the gstreamer node is hardware-agnostic, so
hooking a new source is cheap. This is the ONE allowed reason to touch shared C++ (add a `robomaster`
backend beside `dji`).
- **Hardware gate — confirm BEFORE paying:** RoboMaster **S1 has NO remote SDK**; **EP / EP Core** do
  (SDK just works, no unlock). The human is acquiring a unit in ~2 h.
- **Firmware-downgrade prep (S1 ONLY):** the S1 unlock rides an in-app Python/Lab sandbox escape that
  DJI **patched in later firmware**. "Do NOT update to latest — it blocks the hack." The exact
  safe-vs-blocked version is UNVERIFIED and must be sourced. On-site before paying: read the firmware
  version off the app, ask the seller's update history. Never-updated = safe. Already-latest with no
  downgrade file = walk away. If it's an EP, the downgrade question evaporates.
- Field kit exists: `source/robomaster/` (`s1_probe.py`, `s1_text.py`, `s1_video.py`, `FIELD_CHECKLIST.md`
  + two ref repos). First step: run the probes on the acquired unit; source the exact downgrade firmware.

### T3 — MVD dashboard + demo runbook  [polish]
- **Dashboard (layout settled — do not re-litigate):** the human's YT-ref aesthetic = **left rail +
  full-bleed video + subtitle bar.** A NEW build. Data source is stdout `/tmp/mvd_app.log`
  (`[dji]`/`[router]`/`[voice]`/`[phone_ears]`/`[watchdog]`) + the annotated frame from
  `scene_omdet.py` via one small `canvas`/frame tee inside `integration/`. Text signals are stdout,
  not ROS topics, so the data path is ROS-free; it runs on the demo laptop alongside the MVD. Target
  dir `source/mvd_dashboard/`. **DEAD, do not open:** `source/llm_to_action/dashboard/` (FMU/SITL-era).
- **Runbook:** a short demo-day run-of-show for tomorrow (power-on order, kill-switch drill, the verb
  script, fallback if video/ASR drops). The old `demo-roadmap-2026-08-28.md` (archived) can seed it.

### Ad-hoc — pitch / slides
NOT a track. The human + team own the pitch. The manager helps ONLY when asked for specific slide
content/data, briefly. Do not self-start.

## 6. POST-DEMO perception track — the "notify" feature (design-first; touches the frozen MVD)
A3\*/E2/F5 all modify `integration/` (the frozen demo system) → **not a tomorrow item.** Design pass
with the human FIRST; do not destabilize the working MVD before the demo.
- **A3\* — the "notify" feature (NEW):** *"if someone enters the scene with attributes a,b,c… notify me
  & highlight them."* Human's proposed design: YOLOe person-count → on a new person, fire the attribute
  query at the VLM → if matched, SAM2-mark → else VLM retreats until count changes; drop stale VLM frames
  (keep only the latest) to survive count flicker. **Owed: critical pushback on the person-count trigger
  (see the chat/design note) — count is a weak "new-entrant" proxy; a stable-ID / re-ID trigger is better.**
- **E2 — fold `llm_cv_track`'s EXISTING object tracker** (the cyan center-of-mass line) into
  `integration/`. Distinct from A3\* (existing code, not new logic).
- **F5 — persistent object re-ID** (embedding + cosine). The identity primitive under both A3\* and E2.
  Note: `llm_cv_track`'s tracker used a colour histogram (fragile with look-alikes, per NOTES) — a real
  embedding is needed for robust re-ID.

## 7. Demo-Day judging criteria (scoring axes, NOT build tracks)
- **F1 — Noise robustness (ASR).** HIGH scoring priority. Evidence: `asr-noise-robustness.md`.
- **F2 — Latency command-end → action-start < 1 s.** THE scored number, still **UNPROVEN**. Top open
  scored item; transport latency measured, end-to-end not. Worth proving before Thursday.
- **F3 — Hebrew ASR.** Deliberately deprioritized / closed. Listed for completeness.
- **F1/F3 combined — local-vs-cloud ASR.** Both paths are local (laptop Parakeet + phone on-device
  model). Now a privacy footnote only, not a scored conflict.
- **F4 — Low-light / dynamic-scene robustness.** HIGH-priority criterion, unmeasured; Mini 4 Pro VPS
  struggles in low light and there is little we can do — positioning only.
- **F5 — persistent object re-ID.** The identity primitive (see §6).

## 8. Dev-owned open blockers (the DJI app author, NOT us)
1. **Dynamic groundstation-IP discovery** — the phone hardcodes `("0.0.0.0", 8080)` (`// fixme`). Without
   it the phone ASR cannot reach us.
2. **Gimbal commands broken backend-side** — our JSON matches the DTO; works on the dev's machine; only
   "look forward from fully-down" responds. `fly_by` works.
3. **ApiServerService reliability** — Android suspends it backgrounded → :8080 + :5600 drop. Needs a
   foreground service + battery-opt exemption.

## 9. Repo / git state (2026-08-26 — the human owns ALL git writes; you run NONE)
Uncommitted: `docs/NOTES.md`, `docs/ROADMAP.md`, `docs/active/2026-08-25-mvd-integration-handoff.md`,
`source/integration/config.py`, `source/llm_to_action/fmu/CMakeLists.txt`; untracked
`docs/active/2026-08-26-session-postmortem-brief-defects.md`, `source/robomaster/`, this brief, and the
`docs/stale/` moves from the cleanup below. The dashboard-move + `llm_cv_*` edits are already committed
(`fdbea61`, `1a972b2`) → the 08-25 handoff §12 is stale. Read-only git inspection is fine; `git
add/commit/push/mv/rm` are the human's, always.

## 10. Working style (post-mortem A7 / Part C)
- **The human makes ALL calls. A recommendation is NEVER a decision.** Don't promote your own reco to "decided."
- Give **breadth** (options + measurements), not curated conclusions, while the human is planning.
- The human spawns/supervises sub-agents. **You write briefs; you do not spawn.**
- **Measure, don't guess:** a cheap command beats an opinion (FMU: "days of guessing" → "builds in 38 s").
- Don't re-anchor on information you were already corrected on.

## 11. Doc map after cleanup (content-based; metadata-ranking was the last manager's error)
- **CANONICAL:** this brief · `2026-08-25-mvd-integration-handoff.md` (with §4 corrections) · the
  post-mortem · `mvd-voice-command-table.md` · `asr-noise-robustness.md` · `dji-video-h264-over-tcp.md` ·
  `dji-apiserver-review.md` · `dji-bringup-runbook.md` · `dji-phone-build-graphene-runbook.md` ·
  `spec-dji-backend.md` (primary ref for the llm_to_action agent) · `latency-2026-08-22/`.
- **KEEP UNTIL AFTER THE DEMO:** `2026-08-23-cleanup-postpoc-grapheneos.md` (the revert checklist for the
  demo hacks) · `exoskeletons-android-studio-handoff.md` (only app-rebuild reference until the new
  android runbook lands).
- **NEEDS AN UPDATE PASS:** `final-objective-context.md` (frozen 08-22, pre-MVD) ·
  `spec-dji-websocket-protocol.md` (WS-sticks framing superseded by REST missions; keep for `/status`) ·
  `kill-switch-verification.md` (unchecked boxes — a SAFETY doc, close it before tomorrow).
- **ARCHIVED → `docs/stale/` (done this session):** `2026-08-20-djibackend-handoff.md`,
  `2026-08-20-phase2-detector-feeltest.md`, `2026-08-21-drone-bringup-status-and-next.md`,
  `mission-brief-2026-08-15.md`, `spec-android-docker-bridge.md`, `demo-roadmap-2026-08-28.md`.
