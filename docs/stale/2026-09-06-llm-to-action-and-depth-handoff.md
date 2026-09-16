# Session handoff — llm_to_action demo polish + depth-model study (2026-09-06)

**Author / ownership:** groundstation-13 [8501ec]. Spawned as the **llm_to_action presentation
agent** (make projects/llm_to_action presentable for the judges). Scope expanded, owner-directed, to:
(a) demo polish, (b) a control-loop code-smell catalog, (c) a full monocular-depth benchmark study.
This doc is the single source of truth for continuing after a context compaction.

## 0. Owner rulings this session (2026-09-05 / 06)
- Demo polish PRIMARY, code cleanup BOUNDED. Do not start the fmu_node.hpp refactor.
- **fmu_node.hpp is intentionally "vibecoded"/throwaway — owner does not care about that code's quality.**
- Depth: benchmark EVERYTHING; cheap exploration de-risks the owner's expensive decisions.
- **DECIDED: move to Qwen3-VL-4B, fix its issues, then "call it a day" IF the UI looks sensible and
  describes what is impressive.** Meeting is probably TODAY (2026-09-06).
- Do NOT report to the session manager ("Fable"/groundstation-3c) unless hard/whole-repo issue.
- Owner is a critical pair programmer: push back on scope creep / misalignment, no sycophancy.

## 0.5 EXECUTED 2026-09-06 (this turn) — 4B swap + auto-land fix DONE + verified
- **Auto-land guard APPLIED** (fmu_node.hpp:2244): APPROACH auto-land fires only when the task queue
  is empty. Multi-step plans no longer land at the first approach. Compiles (build exit 0). NOT yet
  run in full SITL -- verified by code reasoning only.
- **4B swap APPLIED** (sim_core.sh:170-171): default VLM model -> Qwen3-VL-4B Q4_K_M; env override
  (VLM_MODEL / VLM_MMPROJ) still falls back to 2B.
- **4B VERIFIED standalone** (RTX 5070 Laptop, 8 GB, Vulkan): loads with mmproj, VRAM 4097/8151 MiB,
  text 0.078 s, vision 1.06 s (320x240 frame), accurate description. Fits with ~4 GB headroom.
- **UI assessed sensible** (dashboard.html): 2x2 diagnostics -- annotated camera, depth, flight HUD,
  VLM objective+plan+reasoning. Meets the owner's gate. Not gold-plated.
- **Full record + the single commit block: report section 8** (supersedes the report section 7 block).
- Tuning note (not applied): sim_core.sh lacks `--image-min-tokens 1024` (grounding precision only).
- STILL UNVERIFIED BY AGENT: full multi-step VLM flight end-to-end in Gazebo. Owner runs
  rubicon_orbit on the workstation GUI to confirm.

## 1. FINISHED (all UNCOMMITTED — working tree only; commit block in the report §7)
Demo polish (verified in headless Gazebo SITL, `follow` scenario PASS x3):
- **serve.py bridge port-leak FIXED (demo-critical).** rclpy.init() swallowed SIGINT+SIGTERM so the
  HTTP bridge never exited and held port 8088 -> a 2nd demo run could not rebind -> blank dashboard.
  Added own signal handlers + join the spin thread on shutdown. Exits clean, port freed, no C++ abort.
- Stale run paths fixed: dashboard README (`scripts/dashboard/*` did not exist), serve.py/assess.py/
  mock_data.py docstrings; mock_data.py pointed at a non-existent `smoke.py` (it IS the publisher).
- sim_core.sh CMD_PX4: a comment with backticks lived INSIDE the double-quoted string -> `${HEADLESS:-0}`
  ran as a command -> `1: command not found` on every headless bring-up. Moved comment out. Byte-identical launch.
- run_sitl_demo.sh docstring: FMU log is at test/sitl/runs/<scn>/captured_panes_log.txt, NOT logs_*/fmu.log.
- NEW projects/llm_to_action/README.md (top-level; node graph, build, run, dashboard).
- Report: docs/active/2026-09-05-llm-to-action-report.md.
Build: a fresh checkout has NO FMU binary. Built via `./build.sh release shared px4 configure|build`
(-> build/release/shared/px4/bin/llm_to_action_fmu_px4 etc.). Binaries are currently present.
Changed files (uncommitted): projects/llm_to_action/source/dashboard/{README.md,serve.py,assess.py,
mock_data.py,run_sitl_demo.sh}, projects/llm_to_action/test/lib/sim_core.sh; untracked:
projects/llm_to_action/README.md, docs/active/2026-09-05-*.md.

## 2. Control-loop code-smell catalog
Doc: docs/active/2026-09-05-fmu-control-loop-smell-catalog.md. controlLoop = fmu_node.hpp:591-1494.
- TEST-ONLY hooks (set only in fmu_node.cpp runTestScenario; checks sit inside controlLoop): flood
  (681), forced battery (691), synthetic obstacle (769), canned-rig flag (913), forced-impact (485).
- REAL-flight hardcodes (deliberate workarounds for schizo depth + flaky detection + weak planner):
  - APPROACH bbox-anchor (setup 2052-2067; law 913,918-950): VLM bbox -> world ENU anchor -> fly by
    odometry, inject synthetic detection. m_approachBboxRig set LIVE at 2063.
  - ORBIT hardcoded fixed circle (1238-1264): orbits a point kOrbitFixedRadiusM ahead of the drone,
    NOT the target; altitude floored kOrbitFixedAltM=4m. Code comment: depth-seeded orbit "flung the
    drone into terrain".
  - Auto-land after APPROACH (2239-2246): auto-enqueues LAND to cover a weak planner. Gated by a plan field (2532).
- The bbox-anchor reuses the canned TEST rig's state/names (m_cannedApproachTargetEnu, updateCannedApproachRig,
  injectSynthetic) -> real vs test indistinguishable by name (cosmetic).

## 3. vlm pre-flight (2026-09-06) — DEMO-BREAKER FOUND
Ran `test/sitl/run.sh vlm` headless (Qwen3-VL-2B). Objective: takeoff, approach car, move 2m back, orbit
15s, land. Actual: takeoff OK -> VLM planned (real Qwen thoughts) -> APPROACH car (bbox-anchor, car@62%)
-> approach_ok -> **"APPROACH finished -> auto-land" -> LAND -> "Mission complete; VLM planning halted"**.
It SKIPPED move-back + orbit. A GO(move back 2m) fired AFTER the mission halted (ordering bug).
=> The auto-land-after-approach hack ENDS any multi-step mission at the first approach. Multi-step
autonomous flight (approach->orbit->land) does NOT work as-is. Approach+land missions and `follow` DO work.
Log: projects/llm_to_action/test/sitl/runs/vlm/captured_panes_log.txt.

## 4. Depth benchmark study (for POST-meeting perception decision)
Master table: tools/bench/depth-sota-bench/DEPTH-BENCHMARKS.md (COMPLETE, all axes). yolo tables:
tools/bench/yolo26-depth-bench/{results.md,results_ladder.md,results_torch.md}.
Machine: RTX 5070 Laptop (Vulkan; NO CUDA toolkit, no nvcc) + 16-core CPU. Key numbers (p50 ms):
- Current prod: yolo26n-depth-384 ONNX CPU-2t = 44ms/22.5Hz. ONNX is CPU-ONLY build (no CUDA provider).
  int8 fails (no CPU ConvInteger kernel); int4 no speedup. This model is the "schizo" one to replace.
- **depth-anything.cpp (ggml DA3, the C++ INTEGRATION path = same stack as VLM llama.cpp + ASR whisper.cpp):**
  metric-large q8_0 (428MB) = 176ms Vulkan / 1237ms CPU-16t. base rel q8_0 = 494ms CPU. On Vulkan every
  ViT-L ~176-191ms (compute-bound; quant only changes load/size). q8_0 = CPU sweet spot. Bit-exact vs PyTorch DA3.
- **Vulkan bug (root-caused): DA3 *relative* models (base+large) SEGFAULT on the Vulkan forward** (no
  GGML_ASSERT). DA3 *metric* and all DA2 run fine on Vulkan. -> relative-on-GPU must use DA2, or run DA3 rel on CPU.
- PyTorch SOTA reference (Path B, would need a Python service): DA3-small GPU 38.5ms, DA3-mono-large GPU
  95.3ms; Depth Pro GPU 1086ms@1536 (CPU impractical); Metric3D GPU small 182ms/large 1207ms (CPU FAILS,
  code pins cuda device). Depth Pro loads from apple/DepthPro-**hf** (not apple/DepthPro).
- Assets: tools/bench/depth-sota-bench/{depth-anything.cpp (cloned+built CPU + Vulkan), gguf/ (DA3+DA2
  gguf, incl. my quantized DA3 metric-large q8_0/q4_k via `da3-cli quantize`), models/ (yolo pt)}.
  Isolated venv-less deps via pip --target ./libs (onnxruntime) + system pip (torch/da3/mmengine).
- ARCHITECTURE FORK (open, post-meeting): Path A C++/ggml drop-in (depth-anything.cpp) vs Path B Python
  perception service. Quality is UNMEASURED (needs ground-truth; Gazebo can give GT depth).

## 5. THE ORBIT-vs-DEPTH point (owner asked; important)
Real target-tracking orbit is impossible with bad depth: you cannot place the orbit center on the true
target in 3D. That is WHY the fixed-circle hack exists. For the DEMO the fixed circle looks fine; the
actual blocker is the auto-land gate cutting the mission before the orbit runs. Real orbit needs reliable
METRIC depth (DA3 metric via depth-anything.cpp) -> then center on the true target. Same root cause as the
bbox-anchor + ORBIT + approach hacks: schizo depth. Fixing depth (post-meeting) is what removes all of them.

## 6. UNFINISHED / OPEN / next steps
- [ ] Move to Qwen3-VL-4B in the loop (owner-decided). Config default is 2B
      (/root/models/vlm/Qwen3-VL-2B-Instruct/*Q4_K_M.gguf); 4B is on disk
      (/root/models/vlm/Qwen3-VL-4B-Instruct/*, use Q4_K_M per owner). Known 4B issues: NOTES.md
      "VLM plan-execution bugs" (~L930), max_tokens truncation, parse failures, target-loss on FOLLOW.
- [ ] Fix auto-land gate so multi-step missions (approach->orbit->land) don't land early (fmu_node.hpp
      ~2239-2246 + gate field ~2532). Behaviour-touching -> Gazebo-verify. Owner ok with vibecoded fmu.
- [ ] Make the dashboard/UI "look sensible and describe what's impressive" (owner's ship gate).
- [ ] COMMIT the demo fixes (bridge leak esp.) — commit block in report §7.
- [ ] POST-meeting: pick perception Path A/B; adopt a real depth model; then delete the depth hacks.
- [ ] Quality benchmark of depth models (mAP/AbsRel) never done — needs ground truth (Gazebo GT depth).

## 7. Skimmed / not-fully-addressed talking points
- The dashboard shows an idle VLM panel with `follow` (VLM off); a VLM scenario populates it. Exact
  "dashboard + vlm scenario" launch command was never finalized (run_sitl_demo.sh is hardcoded to follow).
- Python vision-service (Path B) mirroring PerceptionRuntime's async loop: agreed viable, not decided.
- More threads for the depth estimator: measured (yolo + ggml thread sweeps) — helps sub-linearly.
- `rubicon` scenario (approach+land, no orbit) as a safe demo: NOT verified.
