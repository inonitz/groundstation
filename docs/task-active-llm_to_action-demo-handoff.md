# llm_to_action VLM-demo handoff (2026-09-10)

> **Status (2026-09-12, owner-ruled): PARKED behind integration_harden2 -- not an immediate pickup.**
> integration_harden2 is the active Minimum-Viable-Demo successor. llm_to_action resumes later: re-evaluate its
> state, settle the general architecture, then write real code and measure a fine-tuned human-built system.
> Fusion path: bring harden2's perception in -- likely rewritten to C++/C for the embedded compute box -- and
> fuse the two. It "kind-of works" (planner is fine; the drone approaches but hits the car on monocular depth),
> so it waits. When showing llm_to_action becomes urgent, spruce it as a POC. The finding and status below stand.


Author / ownership: groundstation-13 [8501ec] (llm_to_action presentation agent). This hands the
paused llm_to_action demo work to the next subagent. Demo-day slides took priority; this is where the
flight work stopped and what remains.

## 1. Objective
Ship a working multi-step VLM flight demo: a typed or spoken objective, the VLM plans it, the drone
flies it. The planner is not the blocker. World-grounding — the monocular depth — is the blocker.

## 2. The one finding that matters
The drone hits the car. Qwen3-VL-4B plans the full mission correctly (takeoff, approach, move back,
orbit, land). The approach then fails. The loom guard at `fmu_node.hpp:826` interrupts when a
detection's bounding box fills more than `kBoundaryLoomFillFrac` = 0.28 of the frame. As the drone
nears the car, the car fills the frame, so the guard fires. It cannot tell the target from an
obstacle. The root cause is monocular depth that is unreliable close up.

## 3. Done — all UNCOMMITTED (working tree only)
- 4B swap: `test/lib/sim_core.sh` default VLM model is now Qwen3-VL-4B Q4_K_M. `VLM_MODEL`/`VLM_MMPROJ`
  still override, falling back to 2B. Verified standalone (RTX 5070 Laptop, Vulkan): loads with mmproj,
  VRAM 4097 / 8151 MiB, text 0.078 s, vision 1.06 s on a 320x240 frame. Fits with ~4 GB headroom.
- Auto-land guard: `source/fmu/fmu_node.hpp:2244`. The APPROACH auto-land fires only when the task
  queue is empty. Multi-step missions no longer land at the first approach. Compiles (build exit 0).
- Dashboard VLM demo: `source/dashboard/run_vlm_dashboard_demo.sh`. Runs the `vlm` scenario (a typed
  multi-step objective, no microphone) headless through the dashboard. This is how to demo without ASR.
- Dashboard bridge fix: `source/dashboard/serve.py` installs SIGINT/SIGTERM handlers and joins the
  spin thread, fixing the port-8088 leak across runs.
- Reports: `docs/active/2026-09-05-llm-to-action-report.md` sections 8 (4B verify), 9 (the vlm run +
  the car collision), 10 (the deterministic sweep).

## 4. Verified / measured
- The `vlm` scenario, run headless: completed takeoff_ok, orbit_ok, land_ok. 4B planned the whole
  mission. The approach did NOT complete (the loom storm). First 4B plan took ~7 s (640x640 frame +
  17302-char prompt).
- Deterministic sweep (`test/sitl/run.sh --all`, VLM scenarios skipped): 8 PASS, 3 FAIL. The 3 fails
  (rotate, search, queue-overflow-airborne) were the LAST three. Cause: no odometry — posENU stayed
  (0,0,0), so PX4 never armed. This is container degradation across a long sequential sweep, not a
  code regression. The scenarios pass when run fresh.
- QGroundControl is never needed. `PX4_PARAM_NAV_DLL_ACT=0` waives the GCS arm-check (proven in
  PX4 `commander/HealthAndArmingChecks/checks/rcAndDataLinkCheck.cpp:81`: gcs_connection_required =
  NAV_DLL_ACT > 0).
- The SITL verdicts are FMU self-report (they parse the FMU's own log), NOT world ground truth. A
  "pass" means the control law converged by its own sensors, not that the drone reached the right
  place. The car's true pose is (6, 7, 0.3); the FMU's depth over-read it as 7.24 m.

## 5. WIP / open
- The loom-vs-approach conflict is not fixed. It is owner-gated because the loom guard is a
  collision-safety backstop; do not weaken it without the owner's OK.
- The orbit is a hardcoded fixed circle (`fmu_node.hpp:1233`), not centered on the object, because
  depth cannot localize the object.

## 6. What is left — the roadmap
1. Adopt metric depth. DA3 metric via depth-anything.cpp is the C++ path; the depth study is done
   (see section 8). This is the enabler for everything below.
2. Fix the loom guard to exclude the approach target's own bbox during an active APPROACH, so the
   approach completes. Owner must approve (safety guard).
3. Replace the fixed-circle orbit with a real object-centered orbit. Needs metric depth.
4. Build a ground-truth verdict: capture the true drone trajectory, compare to the object's true pose,
   so success is measured, not eyeballed.
5. Post-meeting: the perception Path A/B decision, then delete the depth-workaround hacks.

## 7. Commit block (the owner runs git; do not stage or commit)
```bash
cd /root/groundstation
git add projects/llm_to_action/source/fmu/fmu_node.hpp \
        projects/llm_to_action/test/lib/sim_core.sh \
        projects/llm_to_action/source/dashboard/serve.py \
        projects/llm_to_action/source/dashboard/run_vlm_dashboard_demo.sh \
        projects/llm_to_action/README.md \
        docs/active/2026-09-05-llm-to-action-report.md \
        docs/active/2026-09-10-llm-to-action-demo-handoff.md
git commit -m "feat(llm_to_action): 4B VLM swap + multi-step auto-land guard + dashboard VLM demo

- sim_core.sh: default VLM model -> Qwen3-VL-4B Q4_K_M (env override falls back to 2B). Verified
  standalone: VRAM 4097/8151 MiB, text 0.078 s, vision 1.06 s.
- fmu_node.hpp: APPROACH auto-land only when the task queue is empty; multi-step missions no longer
  land at the first approach.
- run_vlm_dashboard_demo.sh: typed multi-step vlm scenario through the dashboard, headless, no mic.
- serve.py: SIGINT/SIGTERM handlers + spin-thread join (port-8088 leak).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

## 8. Pointers
- Full detail: `docs/active/2026-09-05-llm-to-action-report.md` sections 8-10.
- Depth study: `docs/active/2026-09-06-llm-to-action-and-depth-handoff.md` and
  `tools/bench/yolo26-depth-bench`, `tools/bench/depth-sota-bench`.
- Control-loop smell catalog: `docs/active/2026-09-05-fmu-control-loop-smell-catalog.md`.

## 9. Runbook — reproduce the demo
- Build the FMU: `./build.sh release shared px4 build`
- Multi-step VLM demo (typed objective, headless, dashboard):
  `cd /root/groundstation/projects/llm_to_action/source/dashboard && HEADLESS_TIMEOUT_SECONDS=420 DASH_PORT=8088 ./run_vlm_dashboard_demo.sh`
  Watch at http://localhost:8088. The script header shows the 2B fallback env vars.
- Deterministic sweep: `cd /root/groundstation/projects/llm_to_action/test/sitl && SKIP_HIGH_VRAM=1 ./run.sh --all`
- 4B model on disk: `/root/models/vlm/Qwen3-VL-4B-Instruct/` (Q4_K_M + mmproj-BF16).

## 10. Standing gotchas + owner rulings (do not relearn these)
- `fmu_node.hpp` is intentionally vibecoded. The owner does not want it refactored. Fix the one bug, no more.
- The loom guard is a collision-safety backstop. Do NOT weaken it without the owner's explicit OK.
- SITL arming needs NO QGroundControl. `PX4_PARAM_NAV_DLL_ACT=0` waives the check. Do not add QGC.
- A long sequential SITL sweep degrades: the last runs lose odometry and never arm. Run a flaky scenario fresh, one at a time, to judge it.
- The SITL verdicts are FMU self-report, not ground truth. Do not claim "works" from a green verdict alone.
- 4B is a decided owner ruling. It plans well but costs ~7 s per plan on a 640x640 frame.
- The owner is a critical pair programmer. Push back, no sycophancy, hard numbers only, address every point by its number.
- The human owns all git. You run no git writes. Prepare the commit block; the human runs it.
- Retests use `VIDEO=webcam SCENE_TTS=off` (owner ruling 2026-09-08). Phone or drone only for final footage.
- Use the `rtk` wrappers for reads, greps, and git, per CLAUDE.md.
