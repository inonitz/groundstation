# Agent 2 — Live dashboard (lean) + 320×240 downscale

**Date: 2026-08-11** · Deadline: Wed evening 2026-08-12.

**Mission**: a lean browser dashboard — camera + depth + detection boxes + HUD tiles + VLM reasoning —
that does NOT hurt system performance mid-test/flight/demo. Communication MUST stay lean.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + LOCKS + commit rules),
then `CLAUDE.md`, `docs/code-guidelines.md`, `docs/writing-style.md`. Study:
`docs/active/2026-08-10-a2-dashboard-mockup.html` (the visual target); `fmu_node.hpp`
`publishAnnotatedFrame` (`1260-1266`) + `publishDepthColormap` (`1270-1281`) + HUD assembly
(`1329-1345`) + `callLlamaServer` (`~1871`); `perception_runtime.hpp` seg/depth loops; the
`mb_observability` gate wiring (`fmu_node.hpp:280-316`).

**Your place in the plan**: presentation wow + a live debug tool. Independent — start now. Boxes are
already baked into the annotated image, so v1 just shows that image (no vector-box plumbing).

## Build

- **FMU downscale (lean transport, C++)**: in `publishAnnotatedFrame` and `publishDepthColormap`, add
  `cv::resize(..., cv::Size{320,240}, cv::INTER_AREA)` before `toImageMsg()`. Throttle to ~10 fps with
  `m_lastAnnUs`/`m_lastDepthUs` guards mirroring `kHudThrottleUs` (`fmu_node_base.hpp:100`). Keep it
  ALL under the existing `mb_observability` gate — OFF must stay zero-cost (this is what protects
  takeoff). Add `m_lastVlmText` cache + an obs-gated `/fmu/vlm_text` `std_msgs/String` set in
  `callLlamaServer` (the HUD only carries `busy/idle` today).
- **Bridge** `scripts/dashboard/serve.py` (new, no lock): an `rclpy` node + stdlib
  `ThreadingHTTPServer`. Subscribe `/fmu/perception/annotated`, `/fmu/perception/depth` (JPEG-encode
  via `cv_bridge`+`cv2`), `/fmu/hud`, `/fmu/vlm_text`. Serve `dashboard.html`, one MJPEG
  `multipart/x-mixed-replace` endpoint per image, and `/events` SSE for HUD + VLM log. **Zero pip deps**
  — websockets/rosbridge/foxglove are NOT installed; do not add them. Single process, cheap.
- **Browser** `scripts/dashboard/dashboard.html` (new): adapt the mockup — replace its `setInterval`
  self-sim with `new EventSource('/events')` + two `<img>` MJPEG panels.

## Constraint (hard)

Measure that dashboard ON does NOT break takeoff and keeps total app RSS < 8 GiB (we hit this
regression before — full 1280×720 publishing starved the VLM). Prefer FMU-side resize over shipping
full frames. If you must choose, leanness wins over prettiness.

## Tests (with the human)

`FMU_OBSERVABILITY=1` SITL run + `python3 scripts/dashboard/serve.py`; open `http://localhost:<port>`;
confirm camera + depth + boxes + HUD + VLM update live with FMU CPU low; re-run a takeoff to confirm no
regression and RSS < 8 GiB.

## Locks (docs/LOCKS.md)

`fmu_node.hpp`, `fmu_node_base.hpp` — short holds; Agents 0 and 1 also edit `fmu_node.hpp`. New
`scripts/dashboard/*` files are yours alone.

## Constraints

Concise intentful code. No git writes — suggest `agent2: dashboard bridge + downscale`. Prose per
`docs/writing-style.md`.

## Report
_(append findings / blockers / decisions below)_
