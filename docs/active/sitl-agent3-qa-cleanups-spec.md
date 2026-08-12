# Agent 3 — QA / cleanups / roadmap

**Date: 2026-08-11** · Deadline: Wed evening 2026-08-12.

**Mission**: verification tasks and roadmap curation — no big features. Later, verify SLAM changes
don't break the PX4 path.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + LOCKS + commit rules),
then `CLAUDE.md`, `docs/code-guidelines.md`, `docs/writing-style.md`. Study: `fmu_node_base.hpp:82-83`
(YOLO model paths), `perception_runtime.hpp` (seg/depth), `px4_backend.cpp` (the FLIGHT→FAULT fix +
`fmu_node.hpp:638` lost-flight guard), `docs/ROADMAP.md`.

**Your place in the plan**: independent for the QA items; the PX4-SLAM safety check waits on Agent 5.

## Do

1. **YOLO image-quality test** (static scene): measure how detection/classification quality degrades as
   image quality drops, and 384 vs 480, fp32 vs INT4 (`/root/models/vision/` has the variants; current
   is `yolo26n-seg-384.onnx` / `yolo26n-depth-384.onnx`). Note: 384 is baked into the ONNX model — you
   swap by changing the two path constants at `fmu_node_base.hpp:82-83`. **Verdict**: if a smaller INT4
   384/480 model degrades quality materially, do NOT adopt it. Report a numbers table.
2. **P1 disarm verify** (no code — fix already in `px4_backend.cpp`): run a SITL flight, inject
   `commander disarm --force` in the PX4 console mid-flight, capture the logs, confirm
   FLIGHT→FAULT→reconcile STANDBY→task abort. Hand the logs to the manager/human to verify.
3. **ROADMAP notes** (`docs/ROADMAP.md` — lock it): schedule (a) the **prompt-trim** (the GBNF now
   enforces JSON shape / thought-first / verb enum / takeoff-first, so the OUTPUT-FORMAT block + the
   dynamic-prompt "MUST start with takeoff" line are redundant — but it only speeds the first plan, so
   it is not urgent); (b) the **rotate/drift** item, reframed: the airframe drifts in space, so rotation
   testing is blocked on SLAM stabilization (Agent 5), not a yaw fix.
4. **Later** (after Agent 5 lands SLAM): verify the SLAM/odometry changes don't break the PX4/SITL path
   (run a normal SITL VLM mission, confirm takeoff/approach/orbit still pass).

## Locks

`docs/ROADMAP.md`, `docs/NOTES.md` (short holds). Your test scripts are yours alone.

## Constraints

No git writes — suggest `agent3: <item>`. Prose per `docs/writing-style.md`.

## Report
_(append findings / the YOLO numbers table / P1 logs summary below)_

### 3. ROADMAP notes (2026-08-11, agent3) -- DONE

- `docs/ROADMAP.md` 3.9 added -- prompt-trim, `[DEFER, low-urgency]`: the GBNF grammar
  (`buildPlanGrammar`, `llamaclient.hpp:111`) already enforces JSON shape / thought-first /
  verb-enum / takeoff-first, so the OUTPUT FORMAT block (`llm_base.hpp:132`) and the dynamic
  "MUST start with takeoff" line (`fmu_node.hpp:1787`) are redundant. Only speeds the first
  plan; keep the thought's 3-part content guidance when trimming.
- `docs/ROADMAP.md` 1.1.2 -- rotate/drift reframed as `[GATE Agent-5 SLAM]`, not a yaw fix:
  the airframe drifts through space during a turn, so a rotation test can't separate a
  yaw-law error from positional drift until SLAM stabilizes the pose. The once-seen ROTATE
  hang stays a separate open item.
- Locks: acquired + released `docs/ROADMAP.md`; `docs/NOTES.md` short hold, no duplicate
  content added there for these two (ROADMAP cross-refs it).

### 1. YOLO image-quality test (2026-08-11, agent3) -- DONE

**Headline: the `.int4` file is not quantized. It is the fp32 model under a
misleading name.** So there is no INT4 model to adopt or reject. The only real
small model is `.int8`, and it degrades quality materially -- do not ship it.
Keep the current fp32-384 seg + depth.

**Evidence the `.int4` file is fp32:**

| seg file | bytes | weight dtypes | quant ops |
|---|---|---|---|
| `yolo26n-seg.onnx` (fp32 base) | 12,056,176 | FLOAT only | none |
| `yolo26n-seg.int4.onnx` | 12,056,240 | FLOAT only | none |
| `yolo26n-seg.int8.onnx` | 4,158,530 | 234x INT8 | 102x DynamicQuantizeLinear |

The `.int4` file is the same size as fp32 (delta 64 bytes of metadata), carries
zero integer weights, and has no quantization nodes. Its inference is
bit-identical to fp32 to 3 decimals on every image and every degradation level
(see table). ONNX has no native 4-bit weight type this build's ORT would run, so
"int4" here bought nothing: same size, same speed, same output. The `.int8` file
is the only genuine quantization (roughly one-third the size, real dynamic-int8
weights).

**Seg quality -- primary-object confidence (n = total dets > 0.25):**

`person` (fills a 960x540 frame -- the hat-follow target):

| input | fp32-384 | fp32-480 | int4@384 | int4@480 | int8@384 |
|---|---|---|---|---|---|
| orig  | 0.905 | 0.913 | 0.905 | 0.913 | 0.888 |
| jpg25 | 0.906 | 0.917 | 0.906 | 0.917 | 0.871 |
| jpg10 | 0.903 | 0.907 | 0.903 | 0.907 | 0.871 |
| ds320 | 0.908 | 0.912 | 0.908 | 0.912 | 0.875 |

`dog` COCO photo (302x329 -- a small, distant-like target, the sensitive case):

| input | fp32-384 | fp32-480 | int4@384 | int4@480 | int8@384 |
|---|---|---|---|---|---|
| orig  | 0.948 | 0.924 | 0.948 | 0.924 | 0.945 |
| jpg50 | 0.927 | 0.876 | 0.927 | 0.876 | 0.899 |
| jpg25 | 0.745 | 0.851 | 0.745 | 0.851 | 0.489 (2 dets) |
| jpg10 | lost  | lost  | lost  | lost  | lost |
| ds320 | 0.947 | 0.923 | 0.947 | 0.923 | 0.941 |

**Depth -- median output on `person_std`, orig input:**

| variant | median depth | note |
|---|---|---|
| fp32-384 | 1.137 | baseline |
| fp32-480 | 1.162 | ~2% higher |
| int4@384 | 1.137 | identical to fp32 (same non-quantized file) |
| int8@384 | 1.783 | +57%, output is broken |

**Reading the numbers:**

- **fp32 vs int8.** Seg int8 costs a small but real confidence drop on the easy
  person case (0.905 -> 0.888). On the hard compressed case it collapses:
  dog at jpg25 falls 0.745 -> 0.489 and spawns a spurious second detection.
  Depth int8 is unusable -- median 1.78 vs a true ~1.14, a 57% error. This
  matches ROADMAP 4.1.5 ("int8 dynamic ... do not ship it"); it loads and runs
  in ORT but is unfit.
- **384 vs 480.** Marginal. 480 adds ~+0.01 confidence on the large person and
  is more robust on the small dog under heavy JPEG (0.851 vs 0.745 at jpg25).
  384 actually scores higher on the small dog at low compression. 384 is baked,
  faster, and already solid for the demo target, so there is no reason to switch.
- **Image-quality degradation.** The person target -- what the demo follows --
  holds ~0.90 confidence through JPEG q10 and through the 320x240 downscale
  roundtrip (the lean-dashboard path). Compression only bites small/distant
  objects: the dog survives to q50, wobbles at q25, and is lost at q10.

**Verdict:** keep fp32-384 for both seg and depth. Do not adopt `.int4` (it is
fp32, no gain) or `.int8` (materially worse seg, broken depth). The demo's
person-follow detection is safe under the dashboard's downscale + MJPEG
compression; small/far detections are the only quality risk from a compressed
feed. Harness + methodology: `scripts/test/yolo-quality/`.

*Aside (not blocking): rename or delete `yolo26n-seg.int4.onnx` /
`yolo26n-depth.int4.onnx`. The name asserts a 4-bit model that does not exist,
and `fmu_node_base.hpp:82-83` or a future benchmark could pick it up expecting a
speedup that is not there.*

### 2. P1 disarm verify (2026-08-11, agent3) -- VERIFIED (PASS)

**Status: PASS. Ran a canned-orbit SITL flight with QGroundControl connected, injected
`commander disarm -f` mid-orbit, and captured the full reconcile signature in order. The
fix works: an in-flight disarm is caught, surfaced as FAULT, and the FMU stops, reconciles
to STANDBY, and aborts the task instead of streaming velocity to a dead drone.**

**Captured signature (SITL, 2026-08-11 14:50Z, `captured_panes_log.txt`):**
```
14:50:19  [PX4_BACKEND_DEBUG] OFFBOARD+ARM CONFIRMED at setpoints=102
14:50:24  [FMU_NODE_DEBUG] ORBIT activated target=car speed=0.30 angle=6.28 dir=ccw
14:50:27  [inject] firing 'commander disarm -f' -> pane %1        (mid-orbit)
14:50:27  [PX4_BACKEND_DEBUG] unexpected disarm while airborne (arm=1) -> IOState FLIGHT->FAULT.
14:50:27  [FMU_NODE_DEBUG] backend left FLIGHT (io=3) while FMU airborne -> stop, reconcile STANDBY, abort task.
14:50:27  [FMU_NODE_DEBUG] task complete status=backend_lost_flight total=2
14:50:28  [FMU_NODE_DEBUG] LANDING->STANDBY altENU=-0.03 (force_disarm)
```
`io=3`=FAULT, `arm=1`=disarmed; reconcile landed ~1s after the disarm. The orbit was cut
short mid-circle (disarm at :27, only ~3s into a ~68s sweep), confirmed visually in QGC by
the operator. Two prerequisites made this pass where earlier headless runs stalled:
QGroundControl was running (supplies the GCS link PX4 needs to arm), and the injector was
fixed to target the PX4 pxh pane by its stable pane-id (an earlier run typed the disarm
into the wrong tmux pane after `select-layout tiled` renumbered pane indices, so the drone
flew a full uninterrupted orbit).

**Fix code (confirmed present + now exercised):**


- `px4_backend.cpp:135-146` -- once `m_ioState==FLIGHT`, if arming telemetry != ARMED,
  store `IOState::FAULT` (blocks auto re-takeoff).
- `fmu_node.hpp:638` lost-flight guard -- when `FlightState==FLIGHT` and
  `backend->state() != FLIGHT`: zero velocity, reconcile to STANDBY,
  `completeCurrent("backend_lost_flight")`, halt mission. Placed after the LANDING/TAKEOFF
  early-returns so a normal land can't false-trip it.

**Expected signature (what a good run must show, in order):**
```
[PX4_BACKEND_DEBUG] OFFBOARD+ARM CONFIRMED at setpoints=...
[PX4_BACKEND_DEBUG] unexpected disarm while airborne (arm=...) -> IOState FLIGHT->FAULT.
[FMU_NODE_DEBUG] backend left FLIGHT (io=...) while FMU airborne -> stop, reconcile STANDBY, abort task.
completeCurrent("backend_lost_flight")
```

**Earlier headless stalls (pre-QGC), for the record:** the FMU booted, loaded seg+depth, entered TAKEOFF,
and streamed the +2 m/s climb setpoint -- but PX4 never armed. Telemetry read
`io=1 nav=14 arm=1 altENU~0.07` steady for minutes: OFFBOARD accepted, ARM refused,
gz physics running (altitude noise, not climb). FLIGHT is gated on `arm==ARMED`, so it
never confirmed and the disarm guard could not be exercised. Arming-permissive params
did not help.

**Root cause (from the PX4 pxh console):**
```
WARN [health_and_arming_checks] Preflight Fail: No connection to the GCS
WARN [commander] Arming denied: Resolve system health failures first
```
`rcAndDataLinkCheck.cpp:81` gates this on `NAV_DLL_ACT > 0` -- when set, a GCS (or RC)
link is REQUIRED to arm. This build defaults it > 0. Operator-attended runs pass because
QGroundControl supplies that link; a headless run has none, so arming is blocked. This is
a headless-harness gap, not a bug in the reconcile fix.

**Harness fix applied (untested by me):** `disarm-verify/run.sh` now exports
`PX4_PARAM_NAV_DLL_ACT=0` to waive the data-link-loss action so a headless run can arm.
Flag for the team: any *other* headless SITL that must arm (A1 `run_all.sh`) likely needs
the same waiver or a live GCS -- the green test matrix was operator-attended.

**Documented for the team:** the QGC-required-to-arm gotcha is now recorded loudly --
`docs/NOTES.md` top banner ("RUN QGROUNDCONTROL BEFORE ANY SITL SIM"), a runtime warning
printed at every launch in `scripts/test/lib/sim_core.sh`, and the header of
`disarm-verify/run.sh`. QGC is the intended path; `NAV_DLL_ACT=0` is the headless fallback.

**To reproduce (operator):**
1. Ensure NO Tello work is live -- this scenario runs the gz GstCameraPlugin (TX) + the
   gstreamer RX node, which bind the Tello UDP ports (11111 / 8889 / 8890). It hogs them.
2. `cd scripts/test/SITL/disarm-verify && ./run.sh` (headless, now with the NAV_DLL_ACT
   waiver), OR run attended with QGC connected. Once "OFFBOARD+ARM CONFIRMED" prints, the
   built-in injector fires `commander disarm -f` (PX4's in-flight force-disarm; the spec's
   "--force" maps to the `-f` magic-21196 override).
3. `./filter.sh` prints the ordered signature above. Hand that log to the human.

**Caveats:**
- I stopped mid-verify because the running SITL was hogging the Tello UDP ports and
  blocking the Tello agents.
- Agent 1 rebuilt `release/shared/px4` at 11:54-11:57, so the on-disk FMU binary is now
  their FOLLOW build. The reconcile fix is committed (5f935e0) so it is in that binary too,
  but for a clean baseline verify, run against the committed source with no unrelated WIP.

