# Session handoff — 2026-08-19 (05:30, end of a long day)

Big session, many rabbit holes. This is the honest ledger: done / WIP / not-done, specs made, what to
commit, and tomorrow's focus with time estimates. Context: **Thursday 2026-08-20 is a tech-credibility
GATE assessment** (not Demo Day ~08-28). Bar = the system is SMART: live scene understanding via ASR +
strong CV, **flight is cut for Thursday**. See `docs/active/thursday...`/memory `thursday-assessment-gate`.

---

## 1. DONE and working (verified live by you)
- **`source/llm_cv_scene/` — the Thursday demo module (NEW).** Standalone Python/OpenCV app.
  - Voice (ASR) -> Qwen3-VL-4B describes the scene -> chat pane. **This core loop WORKS** (you talked
    to it, got real descriptions).
  - Architecture: worker-thread perception (native-res video stays smooth), ChatGPT-style chat pane +
    live legend, ASCII sanitize, `SCENE_RECORD=out.mp4`, swappable input (webcam / file / GStreamer
    for the drone later), vendor-neutral device (`resolve_device`: CUDA/ROCm/CPU).
  - `run_demo.sh` = one command, 4 tmux panes (vlm | keys | asr | app) with cleanup-on-exit + pane
    logging. `run_llama_server.sh` (Vulkan, `-dev Vulkan0`, LD_LIBRARY_PATH fix).
- **Docker/build baked (NEW/edited).** `scripts/Dockerfile` step 1.6 bakes torch+ultralytics
  (`PIP_BREAK_SYSTEM_PACKAGES`, `TORCH_INDEX` arg, numpy<2 + opencv<4.12 pins). `scripts/build-devenv.sh`
  (NEW) auto-picks backend per host GPU: **NVIDIA->CUDA, AMD->ROCm, else CPU**.
- **Git remotes fixed.** `groundstation` origin was wrongly -> `claude-context`; now correct:
  project=`inonitz/groundstation` (**PUBLIC** — see git section), sessions=`inonitz/claude-context`.

## 2. WIP — coded this session, NOT yet rebuilt/retested by you
- **ASR ring-buffer wrap fix (`source/llm_to_action/asr/asr_node.cpp`).** THE cause of the intermittent
  EMPTY/truncated transcripts: consumer did one contiguous `acquire_read` and flushed the rest, dropping
  audio past the ring wrap (positional -> "pattern you couldn't place"). Now loops to drain the whole
  utterance. **Needs a rebuild + retest.** (~5 min rebuild; verify: every toggle-off transcribes the
  full sentence, no `""`.)
- **ASR press-to-toggle (`asr_node.hpp`).** H = record ON, H again = OFF+transcribe (was hold-PTT).
  Built; toggle worked live, but the wrap fix landed after -> retest together.

## 3. NOT done — the real gap the demo still has
- **Highlight is broken for anything non-canonical.** Root cause CONFIRMED (imgsz 1280 didn't help):
  **YOLOE-26 is a bounded-vocab detector** — it cannot find esoteric/small/described objects (your mic,
  the medallion, "the person with the black hat" -> it boxed only the hat). No knob fixes this.
- **Highlight currently BYPASSES Qwen3-VL** (regex -> YOLOE). It SHOULD route through the VLM to resolve
  the referent. This is the core of the rebuild below.
- SAM2 only *segments a given box* — it never *detects*; its size is irrelevant to finding objects.

## 4. THE next big task (planned, not started) — Grounding rebuild  [est. 3-5 h]
Rebuild the highlight backend in `source/llm_cv_scene/`:
1. **Research 2026 SOTA open-vocab grounding** (Grounding DINO 1.6 / **DINO-X** / MM-Grounding-DINO /
   T-Rex2 / anything newer). Pick best for esoteric+small+described, runs locally, no CUDA lock-in. [~45m]
2. **Route "highlight X" through Qwen3-VL** to resolve the referent ("person with the black hat" ->
   `person`), then ground with that model, then **SAM2** mask (Grounded-SAM style). [~2-3h]
3. Keep YOLOE-26 only as fast always-on background. [trivial]
4. New dep done no-CUDA + baked in Dockerfile; touch `eyes.py`, `vlm.py`, `config.py`, `requirements.txt`.
   [~30m]
(Do this next session with fresh context — flagged at 16% today.)

## 5. Flight / SITL work — DEFERRED (off Thursday's path, do after the gate)
Coded + build-verified earlier, but **your Gazebo tests found real bugs I did NOT fix** (we pivoted):
- **approach-real still drives through the car** — root cause found: monocular depth flip-flops
  3.5<->7m, travel budget over-reads. [fix est. 2-3h] Reddit note confirmed: fix = temporal-consistent +
  metric depth, or brake on looming not absolute depth.
- **follow** sinks / yaw issues (vUp unguarded). [~1h]
- **obstacle-stop** uses an injected fake obstacle, not a real one in the world. [~1-2h]
- **queue-overflow-airborne** filter FAIL (stale grep; behavior is actually correct). [~15m]
- Done+passing already: cross, hover, rotate, orbit (control), approach-impact, battery-rth/landnow,
  interrupt-storm (mechanism), override (no bug), queue-overflow.

## 6. Specs / docs created this session
- `docs/active/spec-dji-endtoend-bringup.md` (NEW) — drone bring-up: `.apk` on phone, Linux backend over
  WiFi, video (H.264/TCP), latency table; **+ workstation-vs-laptop parallelization split**.
- `docs/active/2026-08-19-session-handoff.md` (this file).
- Memory: `thursday-assessment-gate.md`. NOTES.md: llm_cv_scene + depth-is-structural bullets.
- DJI-backend agent got a copy-paste briefing (in chat) pointing at the specs.
- Verified the Gemini "BT+LLM vs VLA" numbers = **mostly fabricated/misattributed** — do NOT cite to judges.

## 7. Git — what to commit (remotes now correct)
Working tree is large (flight work + docs reorg deps->assets + DJI files + llm_cv_scene + ASR). Options:
- **Fast:** one checkpoint commit of everything, or
- **Clean:** group — (a) `llm_cv_scene` module, (b) ASR toggle+wrap fix, (c) Dockerfile+build-devenv.sh,
  (d) DJI specs, (e) flight/SITL + scenario renames, (f) docs reorg + NOTES.
Suggested standalone messages:
- `asr: read full utterance across ring-buffer wrap + press-to-toggle recording`
- `llm_cv_scene: standalone voice->CV+VLM scene demo (Thursday gate)`
- `build: bake ML deps in Dockerfile + build-devenv.sh auto-picks torch backend per GPU`
**BEFORE pushing:** (1) **`inonitz/groundstation` is PUBLIC** — it will expose the MOD/strategy/DJI docs.
Decide: `gh repo edit inonitz/groundstation --visibility private`, or scrub docs. (2) Delete the stray
branch pushed to the private sessions repo: `git -C /root/.claude push origin --delete feature-llm-driver`.
Do NOT commit `panes.log` (scratch) or `bench_out/` (private ASR).

## 8. TOMORROW on the laptop — focus + estimates
**Track A — drone comms (field, needs hardware)** — DJI-backend agent + you, per `spec-dji-endtoend-bringup.md`:
- Phase 0-1: MSDK app key + build/run the `.apk` LAN-only (tunnel OFF), `curl /status/` over WiFi. [~1-1.5h]
- Phase 2: telemetry + tethered takeoff/land via `DjiBackend`. [~1h]
- Phase 3: video H.264/TCP -> GStreamer decode; record codec/res/fps. [~1h, may block on app author]
- Phase 5: end-to-end latency table (command->action, video, telemetry, WiFi). [~45m]
**Track B — demo fix-ups (workstation, with me)**:
- Rebuild + retest the **ASR wrap fix** (quick, unblocks voice). [~15m]
- **Grounding rebuild** (section 4) — the demo's real gap. [3-5h]
- Optional: point the drone stream into `llm_cv_scene` once video works (Phase 6). [~30m]

Rule of thumb: mock/code/decode = workstation now; real phone/drone/WiFi = laptop/field.
