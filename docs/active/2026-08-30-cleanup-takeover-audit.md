# Cleanup & Takeover Audit (Rev 2, 2026-08-30)

Purpose: every open, broken, or contradicted point across the project, so the owner can take the
codebase back. Rev 2 folds in the owner's full review: condensed items are split (one idea per item,
per docs/writing-style.md), every owner question is answered inline, and decisions are recorded.
IDs are stable; sub-IDs (R1a...) split former bundles. Reply `C2=P0, A16=drop` style to prioritize.
(rec) marks a recommendation, never a decision.

---

## S. Session ledger — owner decisions recorded

- **S1** — notify fork: owner tests tomorrow morning (webcam commands in `2026-08-27-run-guide.md`).
- **S2** — Laptop TTS: verified audible on the demo laptop. C5's wipe applies to fresh envs only.
- **S3** — rotate verb rides the DJI mobile-SDK path (`integration_tts` -> `spin_by`), not the FMU.
- **S4** — `.claude` sync perms: fixed in another session (mostly). Residual: next host `./sync.sh` must pass without sudo.
- **S5** — Pitch screenshots: taken, owner satisfied.
- **S6** — captureid: override-ability suffices. No stability expectations.
- **S7** — Emergency ASR: "kind of" covered by the MVD Python regex; must be properly handled inside the FMU (A22).
- **S8** — Vosk is dead. Hebrew = whisper-large-v3-turbo plan (H1).
- **S9** — Dynamic IP discovery + exoskeletons comms: demo-verified, both directions.
- **S10** — Fork merge deferred until the win. Interim rule: `integration/` is FROZEN; changes land in forks only.
- **S11** — Git: 4 commits landed on `feature-llm-smart-scene`. Still pending: push, merge to master, `checkout -b feature-cleanup-reorg`.
- **S12** — Root `NOTE.md`: owner keeps until its live points are addressed, then deletes (D6).
- **S13** — Process: owner marks priorities on this audit -> reorg spec (owner-approved) -> moves on `feature-cleanup-reorg`.
- **S14** — **Working agreement (new): the OWNER writes the C++.** The takeover's whole point is the owner developing with their own brain again — rewrite / refactor / hybrid read-refactor-repeat. The agent explains current behavior, prepares maps and sketches, and reviews diffs. It does not write `llm_to_action` code. Recorded in agent memory.
- **S15** — POC scope for the interviews: demonstrate BOTH the perception engine AND `llm_to_action`.
- **S16** — **Tello platform: DEPRECATED (owner).** It cannot hold VPS in feature-poor environments and offers no testing capability going forward. Backend code stays in-tree, frozen; scripts get archived (P6). DJI V5 MSDK REST is the platform.
- **S17** — CURVE verb: owner leans DELETE — the VLMs we run cannot plan curved paths, and the future is Behaviour Trees (A16).
- **S18** — Dead wire methods (R9): verdict deferred until the owner talks to the other dev.
- **S19** — Anonymization scrub: owner accepts the current state (shallow scrub; deep git-history digging is a tolerated risk). C6 CLOSED.
- **S20** — Phone strip partially executed: Play Store, Google STT/TTS, USB permissions removed. GMS/GSF status unknown -> C3 residual.
- **S21** — Repo-destruction rule added to `CLAUDE.md` (2026-08-30): the assistant may never run or script any operation that can destroy or rewrite the repo or its remote. Owner's 0% requirement.
- **S22** — Documentation duty: any new feature (rotate, captureid default, TTS envs) must land with its docs, in the same change.

---

## C. Critical

- **C1 — Repo protection. RESOLVED by rule, backup optional.** Ground truth: `origin = github.com/inonitz/groundstation` exists — a remote copy IS off-machine. The Aug-28 backup-script saga is therefore a convenience, not a gap. The owner's actual requirement — 0% chance of the agent nuking the remote — is now a hard CLAUDE.md rule (S21). Optional (rec): one `git clone --mirror` to a second disk before mass file moves, for same-day rollback comfort.
- **C2 — Kill-switch A/B/C drill — what it is and why it outranks "override".** The three kills, surest first: (1) aircraft POWER BUTTON 3-5 s — hardware cut, always works; (2) phone API Server toggle OFF — drops OUR virtual-stick authority, motors fall to RC/failsafe; (3) DJI CSC stick combo — may be OVERRIDDEN while our virtual stick is active. The drill: Test A proves the power button stops motors <5 s (the net). Test B proves the API toggle drops authority <2 s. Test C characterizes CSC under our authority — stop or overridden, either is fine as long as it is KNOWN. Why this beats "override control back to the user": voice-"manual"/RC override requires our software to cooperate. The kills are for when our software IS the problem — and while virtual stick is live, the RC may not be able to save you. That is what Test C measures. A and B are pass/fail gates; C is knowledge. Never recorded through two live events. (rec: P0 before any interview flight; props off, airframe clamped, per the doc's preconditions.)
- **C3 — Phone strip: probably NOT yet enough.** Removed (S20): `com.android.vending` (Play), `com.google.android.tts` (STT/TTS + its en-US model), USB perms. The nuke list has two more that matter MOST: `com.google.android.gms` (Play Services — the background telemetry surface) and `com.google.android.gsf`. Also outstanding: `settings delete secure voice_recognition_service` + reboot. Verify in one line: `adb shell pm list packages | grep -iE "google|vending|gms"` -> expect empty. If gms/gsf are gone already, C3 closes.
- **C4 — drone_config default divergence: agent-caused DRY violation (owner is right).** The agent copied the VALUE (80.0f) instead of referencing the constexpr. Fix (owner applies): make every `DroneConfig` default reference its constant — `f32 approachSpeedDefault = kApproachSpeedDefault;` — so divergence becomes impossible, plus a `static_assert`-style startup check while both exist. One small patch; do before any tuning session.
- **C5 — Fresh clone is model-dead: known, must be un-forgettable.** Owner confirms awareness: weights (`*.pt`), VLM ggufs, OmDet, SAM2, TTS voices are external and gitignored — a clone cannot run. Requirement is durable documentation + tooling, not tracking weights:
  - **C5a** — C7 onboarding doc gets a "models & assets" section: every required file, its path, its source.
  - **C5b** — a `bootstrap`/preflight script that lists exactly what is missing (extend the existing `integration_notify/bootstrap.sh` pattern repo-wide).
  - **C5c** — TTS install scripted (piper + voice + espeak-ng + aplay); today it is a silent no-op when absent.
  - **C5d** — root `README.md` quickstart rewritten (all 5 lines currently invoke the deleted `simenv_llm.sh`; build.sh usage shows 3 args, takes 4).
- **C6 — CLOSED** per S19.
- **C7 — The takeover itself (owner: only the tip of the iceberg was captured).** Reframed: the deliverable is not a document — it is the owner back in the driver's seat, rewriting with their own brain. What the agent owes that loop: (a) the working agreement S14, in force now; (b) the onboarding doc (clone -> build -> run + C5a models + safety rules + D4 reading order); (c) per-verb behavior maps as each rewrite slice starts; (d) this audit as the defect ledger. Everything else in this file is graded by one question: does it make the owner's read-refactor-repeat loop faster?

---

## A. llm_to_action cleanup (owner writes; agent maps and reviews)

### A-I. Structure
- **A1 — step<Verb> extraction: idea confirmed.** Yes — each action becomes fully self-contained: its 20 Hz law in one named method, later its parse/activate/name too (A2). The pattern exists (`stepHover`, `fmu_node.cpp:114-125`); Appendix A sketches ROTATE. Per S14 the OWNER writes every slice; the agent delivers a per-verb behavior map (inputs, members touched, exit conditions) before each one and reviews the diff after.
- **A2 — the six-table problem, plainly.** To add or change ONE verb today you must edit SIX separate places that all switch on the same enum: `cmdName` (command_id.hpp:52 — verb->string), `commandIdFromAction` (command_id.hpp:35 — VLM string->id), `translateToBaseCommands` (fmu_node.hpp:2555 — JSON->Cmd struct), `activateTask` (fmu_node.hpp:1951 — state init, 270 lines), the `controlLoop` if-chain (fmu_node.hpp:839 — the tick law), and `hudTask` (fmu_node.hpp:1654 — display). Nothing checks they agree. Proof it bites: CURVE exists in five of the six and is missing from `commandIdFromAction` — so it is silently dropped (A16). Fix: one unit per verb owning all six pieces; five tables become dispatch over units.
- **A3 — helpers to scoped utility headers: agreed, with the owner's constraint.** Functions stay `inline` in headers like `fmu_geometry.hpp`; split a header when it grows too long. (spec-fmu-cleanup Task G calls this the single biggest lever.)
- **A4 — units -> metres: concrete scope (was too vague).** The codebase mixes centimetres and metres. Where the cm lives: `kManualTeleopVelCmS` (fmu_node_base.hpp:48), several Cmd struct fields, the Tello wire (takes cm), and scattered `/100.0f` `*100.0f` conversions in `translateToBaseCommands` + control laws. Intention: metres everywhere internally; convert ONLY at the Tello wire boundary — and with Tello deprecated (S16) that boundary is frozen anyway. Must be atomic per field (config + struct + conversion sites in one commit), else half-converted values fly the drone wrong. Practical route: convert each verb's fields during that verb's rewrite slice.
- **A5a — test hooks + demo control hacks out of the loop.** The fault-injection members (`m_floodArmed`, `m_obstacleArmed`, `m_batForce*`) and the demo hacks (HARDCODED SAFE ORBIT fmu_node.hpp:1238, auto-land-after-approach) get replaced during each verb's rewrite, not before.
- **A5b — hardcoded absolute paths in C++ [owner: ASAP].** Compiled-in `/root/groundstation/...`: `kVlmPromptLogDir` (fmu_node_base.hpp:102), slam defaults (slam2.hpp:71-72), the vision-model path block in fmu_node_base.hpp. Fix: env override with a runtime-derived default, or DroneConfig keys. Small, standalone, safe to do first.

### A-II. Constants
- **A6 — "won't the rewrite shrink this?" — answered.** Mostly yes: dead constants (~20) vanish, duplicates (~10) merge, and per-verb extraction moves each verb's constants next to its law, killing the mega-cluster's bulk. What you would be missing: the ~100 genuinely-tuned gains and thresholds do not disappear under any rewrite — they can only be relocated. Each needs a HOME (constexpr vs DroneConfig) and a PROVENANCE tag (SITL-swept vs "first guess" — the file marks which). Count drops maybe a third; the tuning debt survives and should be triaged during the rewrite, verb by verb.
- **A7 — inline magic numbers:** fold each into its verb during extraction. Delete the second search-preset table (fmu_node.hpp:2201-2205) that shadows `kSearchSizePresets`.
- **A8 — duplicate PX4 constants: see A13** (the duplicate set lives in the dead node; deleting it is the fix).
- **A9 — write-only config keys** (`searchLaneLengthM/SpacingM`): delete the keys, or wire the lawnmower params when SEARCH is rewritten.
- **A10 — `DRONE_CONFIG` default path is dead** (`config/tello.yaml`; profiles live in `assets/`). Fix alongside R1a.
- **A11 — ground truth stands:** runtime config exists since 2026-08-10; the scheduled doc is stale (D1).

### A-III. Dead code
- **A12 — SPSC queues + slam1: keep the hardening, drop the twins.** Owner is right that these were hardened — so keep ONE: the two SPSC files are near-identical twins (`fmu/spsc_bounded_queue.hpp`, `gstreamer_gz_udp_tx/spsc_ringbuffer.hpp`); move the survivor to `util/`, delete the other (git history keeps both). `slam1.hpp` is superseded by slam2 -> archive with the Tello/SLAM material (P6), don't delete.
- **A13 — "source of the duplicates," explained.** `llm_to_action_offboard_mode` is an early standalone node, superseded by `px4_backend` inside the FMU. It declares its OWN copies of the four PX4 topic strings and the sysIDs — that copy-set is the A8 duplication, and the two copies have drifted (`vehicle_status_v4` vs `_v1`; which is correct is UNVERIFIED — check against the px4_msgs version in the build). Owner said "sync them": deleting the dead node syncs them by leaving one definition. If the node is kept for some reason, both must include one shared header instead.
- **A14 — dead functions/members: plausibly unfinished-rewrite leftovers (owner suspicion shared).** `pushOrbitRange`/`medianOrbitRange` belong to the pre-"hardcoded orbit" vision path; the dead FOLLOW-sweep constants to a retracted recovery. Suggested rule: delete each verb's dead remnants IN that verb's rewrite slice (history preserves them). Exception worth doing now: `asr_node.cpp:64-140` — a 74-line fully commented-out function body plus its dead mutex — pure noise, delete.
- **A15 — misleading comments: suggestion (owner asked).** Fix each stale comment in the same commit as its verb's extraction. Do two now, they actively lie: fmu_node.hpp:118-120 ("no control-law yet" — three laws exist) and fmu_node_base.hpp:94 ("zero getenv" — there are four). For the FOLLOW contradiction (:1199-1214): keep the retraction, delete the sweep description and its five dead constants.

### A-IV. Half-built / traps
- **A16 — CURVE (and `re-assess`): owner leans delete — agree.** (rec) Remove both from the system prompt (`llm_base.hpp:56-59, :137`) and delete their structs/ctors during the rewrite. Rationale matches the owner's: the 2-4B VLMs cannot plan curve geometry, replanning belongs to the future Behaviour Trees, and today both verbs are silent traps (taught to the model, dropped by the parser with no log). Cheapest safe interim: delete the two prompt sections — 10 minutes, kills the trap without touching C++ logic.
- **A17 — `stop` no-op: "how necessary?" — it is a trap, not a feature.** The prompt advertises `stop`; a VLM can emit it mid-flight expecting motion arrest; nothing happens. Two exits: implement `stepStop` (zero-velocity setpoint + clear queue — ~5 lines, safety-positive) or remove it from the prompt vocabulary. (rec: implement; a stop verb that stops is worth having.) Leaving it as-is is the one wrong option.
- **A18 — ReID seam: groundwork acknowledged, completion deferred** to the perception fold-in (P9), where the notify fork's OSNet work supplies the embedding producer.
- **A19 — Tello zero-XY odometry: folded into S16.** This defect is WHY the platform is a dead-end (cannot hold position where features are sparse). Backend frozen, no fix planned.
- **A20 — aliases: adopt during rewrite.** fmu_node.hpp converts its 11 raw declarations as verbs move; fix slam's diverging local alias names; replace `<bits/chrono.h>` with `<chrono>`; add a `CallbackGroupPtr` alias.
- **A21 — "why missing from CMakeLists if used?" — answered.** Header-only files compile via `#include` regardless; the CMake source list only affects IDE indexing, installs, and file-set tracking. So the build never broke — it is an oversight. Fix: add `fmu_helpers/plan_parse/drone_config.hpp` to the list. The four slam tests are the real gap (no build-system entry at all, raw g++ in a script) -> archive them with Tello (P6) or give them a target.
- **A22 — confirmed open:** approach-real HITS the car (monocular range lock); search 160deg post-DETECT retest; interrupt-storm + override retest; `od.yaw` 0->1.57 handoff suspect; latency e2e benchmark (mic-release -> first setpoint) never built; ASR tests missing — per S7, emergency ASR ("land"/"stop", override) needs a proper FMU-side path + tests, not just the MVD regex.

---

## B. Perception

- **B1 — eval harness: "how reliable, against what?" — answered.** It replays CAPTURED frames (your real demo/flight footage — the actual distribution that broke) against your real prompt set, deterministically. You hand-mark ~50-100 frames once (target present/absent, rough box). Metrics per model/config: grounding hit-rate on present targets, false-fire rate on ABSENT targets (the hallucination axis), JSON-validity rate, latency. What it gives you: regressions caught before a demo, and apples-to-apples model comparisons on YOUR data. What it cannot give: proof of live robustness (lighting drift, motion blur beyond the captured set). It is a regression net, not a certifier — and it is the interview-friendly artifact.
- **B2 — 4B-at-Q4 box-accuracy experiment: confirmed, runs inside B1.**
- **B3 — NE-approach root cause (`bboxToEnuAnchor` back-projection): confirmed open.**
- **B4 — "which folder?" — the MVD family, precisely:** `source/integration/scene_omdet.py:15` + `highlight_seg.py:16` force `SCENE_HL_BACKEND=vlm`; identical lines in `integration_notify` and `integration_tts`; the unreachable grounder/yoloe branches live in all four `eyes.py`/`config.py` copies (incl. `llm_cv_scene`). Decision: delete the dead branches or restore the choice. (rec: delete in the forks; `llm_cv_scene` keeps them as the historical playground.)
- **B5 — LLMDet questions: honest status.** Why still carried: nobody removed the Dockerfile bake after the demotion — oversight, not intent. Your research questions — do bigger grounding models (LLMDet-large, MM-GDINO-large, newer DINO-X-class) beat OmDet on absent-target hallucination, at what VRAM, with what tradeoffs — are UNMEASURED here. Published numbers we hold are recall-flavored (LLMDet-large LVIS APr 44.7 vs MM-GDINO 34.2) and say nothing about false-fires on absent targets. This is exactly a B1 experiment: add a "grounder-candidates" mode to the harness and let it answer with your frames. Per the owner (not waste if useful for testing): KEEP the baked weights until that experiment concludes, then decide.
- **B6 — VLM hallucination gate on the FMU side (NOTES:2018): confirmed open.**
- **B7 — LLMDet history: recorded; agent memory corrected.**

## H. Hebrew ASR
- **H1 — plan confirmed:** whisper-large-v3-turbo safetensors + VAD silence gate; quantize q4/q5/q6/q8 (or ONNX); benchmark vs Parakeet on the same recordings.
- **H2 — captureid: closed** (override suffices).
- **H3 — documentation duty (S22):** rotate, `ASR_CAPTUREID`, and the TTS env knobs get documented in the run guide + command table as part of R8/D7.

---

## R. Repo & scripts hygiene

- **R1a — `config/` -> `assets/` path cluster.** 9 references point at a `config/` dir that never existed post-move; the files live in `assets/`. Includes the compiled slam defaults (slam2.hpp:71) and `DRONE_CONFIG` default (A10). Fix the callers.
- **R1b — the `dependencies/` symlinks: why they exist, and the proper fix.** History: `dependencies/` was once a git submodule (CMakeLists fossils at :30/:97/:98 and Dockerfile:125 prove it). Assets later moved to `assets/`, but `sim_core.sh` and the slam headers kept the old paths. During the 08-27 demo crunch the agent restored those paths with 11 symlinks instead of editing the callers — a deliberate band-aid under time pressure, never promoted to a fix. It is also incomplete: 7 assets (orb_vocab.fbow, both stella configs, tello.yaml, rviz/foxglove layouts) were never linked, which is why every SLAM script still dies. Proper fix: repoint the 2 live consumers (`sim_core.sh:39,45`; slam2.hpp compiled default) at `assets/`, then delete `dependencies/` entirely (R2).
- **R1c — `scripts/dashboard/` moved** to `source/llm_to_action/dashboard/`; 6 callers never updated (the SITL `dashboard/` scenario is fully dead). Fix the 6 paths.
- **R1d — pre-SITL-move stale headers** (~15 files: `cd scripts/test/<x>` comments, old dir names). Mostly comments/READMEs; fix opportunistically, or delete with the Tello archive where applicable.
- **R1e — tello/slam build trees** (`build/release/shared/tello`, `build/release/slam`) were never configured; 3 referenced binaries unbuildable. Resolved by S16: archive, don't fix.
- **R2 — merge `dependencies/` into `assets/`:** after R1b, delete the directory + the submodule fossils (Dockerfile:125, CMakeLists:30/97/98 comments). Result: one asset root, zero symlinks.
- **R3a — `.gitignore`: delete the verbatim duplicate block** (lines 55-58 repeat 51-54).
- **R3b — delete `scripts/test/SITL/rubicon_orbit/`'s directory ignore** (both copies): it hides a live scenario dir; the bag-hoarding intent is already covered by `scripts/test/SITL/**/bag_*/`.
- **R3c — delete dead patterns:** `.vs/`, `*.sln`, `*.vcxproj*`, `imgui.ini`, `m2.zip`, `*.apk`, `_exo_transfer/`, `venv`, `test_img*`, `dji_mock/out/`, `frame*.png` — none match anything anymore.
- **R3d — collapse subsumed patterns:** `*/slam_check.log` (under `*.log`), `Makefile`/`*.ninja` lines (under `build/`), `captured_panes_log.txt` (under the nested test .gitignore), `.vscode/compile_commands` (dir never exists; keep `compile_commands.json`).
- **R3e — `*.pt` policy:** keep weights ignored; the answer to fresh-clone death is C5b's bootstrap + C5a docs, not tracking binaries.
- **R4 — test drift, confirmed.** Fix `run_all.sh`: remove the 6 phantom scenarios, correct the "8 filters" comment (it is 4), delete the dead `lib` guard. Then the real gap: 10 of 23 scenarios produce no verdict — write `filter.sh` for the 6 that lack one, or mark them unverifiable explicitly.
- **R5 — duplication, explained (owner: "don't understand").** The same file exists in multiple places; a fix applied to one silently misses the others. The instances: `test_router.py` x4 (and the `scripts/test/router/` copy has ALREADY diverged — 92 vs 73 lines — proving the failure mode); `run_llama_server.sh` x4; `video_watchdog.py` x3; `video_doctor.py` x3 (orphan — nothing imports it); `config.py` x4 near-identical; `yolo26n-seg.pt` x2 real copies (12.8 MB, integration + llm_cv_track). Consequence: every bugfix is N edits until the fork merge (P1) collects them. Interim mitigation is S10 (integration/ frozen).
- **R6 — `llm_cv_track`: owner says make it self-contained — proposal.** It is PARKED (its own README) and 7 of its files import from `llm_cv_scene` by absolute path; its `follow.py`/`track.py` need a weight file that does not exist. (rec) Archive it with P2 until track-verb planning resumes; if you want it runnable instead, vendor the 7 referenced files into it (one `cp` + path fix).
- **R7 — fork situation, plainly (owner: "don't understand the dilemma").** There is no dilemma anymore — there is a rule. Three folders are copies of one app; 13 files are byte-identical. The risk while they coexist is drift (R5). Your S10 decision resolves it: `integration/` frozen as the proven fallback, all changes land in forks, merge happens after the win — and the merge will be near-mechanical because the forks changed disjoint files (notify: scene_omdet/vlm; tts: commands/config/router/voice).
- **R8 — rotate verb debt: confirmed.** Write the parse+dispatch tests in `test_router.py` (harness exists — it already tests `spin`); document the phrases in `mvd-voice-command-table.md` + the fork README; one mock-then-live sign verification; add the exact `POST /c/fly` JSON bodies (`fly_by`/`spin_by`/`scan_ground`/`gimbal_pitch`) beside the verb table.
- **R9 — dead wire methods: DEFERRED (S18)** until the owner talks to the other dev. No culling before that conversation.
- **R10a — `mix_noisebed.py`:** purpose recorded per owner — mixes combat noise into ASR recordings to find each model's accuracy cutoff. One-time bench, keep; move to the one-off home (R10g) with a purpose header.
- **R10b — `stella_vslam_viz.rviz`:** SLAM-integration era; archive with the Tello/SLAM material (P6).
- **R10c — `scripts/build.ps1`:** per owner, rewrite as `build-devenv.ps1` mirroring `build-devenv.sh` (auto torch-index etc.); then delete the stale `scripts/build.sh`+`build.ps1` pair (they also name-collide with the root build scripts).
- **R10d — `ws_latency.py` vs `measure_ws_rtt.py`:** overlapping measurements; pick one, note the survivor in the dji_mock README.
- **R10e — `dji_check.sh` hardcodes NIC `wlp2s0`:** derive from `ip route` like everything else.
- **R10f — stray `captured_panes_log.txt` in 4 scenario dirs:** delete (ignored anyway).
- **R10g — structural rule (owner's point, generalized):** one-time-check scripts were used and cast away with no home. Create `scripts/oneoff/` (or `scripts/archive/`); every one-shot script lands there with a date + purpose line at the top. Propose as a code-guidelines addition.
- **R11 — renames, confirmed:** `gstreamer_udp_cam_rx` -> `gstreamer_cam_rx`; canned-approach-rig cluster -> `synthetic*`.
- **R12 — hardcoded `/root/groundstation`, explained (owner: "don't understand").** ~25 scripts write the repo's absolute container path into themselves. Consequence: clone the repo anywhere else — your host machine, a git worktree, a differently-named dir — and every one of them breaks, silently pointing at a path that isn't there. Fix pattern already in the repo: derive the root from the script's own location (`ROOT="$(cd "$(dirname "$0")/../.." && pwd)"`; `test_router.py:10` does the Python equivalent). Mechanical sweep during the reorg. The 3 compiled-in C++ paths are A5b.

---

## D. Docs (redone per owner notes)

- **D1 — move to `stale/`, one line each, with reason:**
  - S1 jailbreak guide + runbook + t1-t2 map — robomaster deleted, S1 never bought.
  - 2026-08-26 manager-brief + session-postmortem — single-event docs, event past.
  - 2026-08-27 demo-runbook + morning-checklist — same.
  - fmu-node-split-map — describes a file layout that no longer exists (wrong LOC, class, symbols).
  - spec-dji-backend, spec-dji-endtoend-bringup, spec-dji-websocket-protocol, dji-apiserver-review — delivered or superseded by the bringup runbook + latency results.
  - exoskeletons-android-studio-handoff — superseded by the graphene build runbook.
  - scheduled/runtime-drone-config — implemented (A11); file it stale, tick ROADMAP 9.14.
  - root-level system-architecture.md + -slides.md + project_overview.md — Tello/Humble era.
  - integration-mvd-2026-08-24.md — sprint checklist, shipped.
  - LOCKS.md — multi-agent protocol for sessions that no longer exist (P7).
- **D2a — rewrite `docs/README.md`:** it indexes `closed/` and `specs/` (don't exist) and misses `stale/`. Make it the real map: active / stale / scheduled + the D4 reading order.
- **D2b — rewrite root `README.md`** (C5d).
- **D2c — fix the spec-vs-tasklist naming contradiction:** the tasklist and the tree win (`step<Verb>`, not `servo*`); correct spec-fmu-cleanup.
- **D2d — fix NOTES.md's yaw self-contradiction:** :2443 says unconfirmed; :2355 resolved it (CW+, `kDjiYawRateSign=-1`). Correct :2443.
- **D2e — unify the mock port story:** 8079 = mock, 8080 = real phone (handoff:108 is right); fix demo-runbook:79.
- **D2f — one machine-roles statement:** three docs each call a different machine "this box" (RTX 5070 laptop / RX 7900 GRE workstation). State once in final-objective-context: workstation = dev + heavy VLM; laptop = demo box.
- **D2g — rename `stale/demo-roadmap-2026-08-28.md`** (misdated filename, flagged twice, never fixed).
- **D2h — kill-switch doc:** replace the stale literal IP with the derive-the-gateway line; record the C2 drill results in its table when run.
- **D2i — grapheneos doc:** update with C3's partial execution; move to `scheduled/` until the GMS/GSF check closes it.
- **D3 — NOTES.md: keep the monolith (owner), fix the lying claims in place:** :577 (simenv re-gate — script deleted), :2443 (yaw, = D2d), :2522 (robomaster field kit — deleted), :1581 (config/ path — assets/), :2329 (stale link to a moved doc).
- **D4 — takeover reading order (the keep-set, sequenced):** 1) final-objective-context 2) ARCHITECTURE.md (post-D5) 3) 2026-08-25-mvd-integration-handoff 4) mvd-voice-command-table 5) 2026-08-27-run-guide 6) fmu-cleanup-tasklist + spec-fmu-cleanup 7) dji-bringup-runbook + latency-2026-08-22/ 8) kill-switch-verification 9) asr-noise-robustness 10) NOTES.md as the searchable log. Plus code-guidelines + writing-style.
- **D5a — ARCHITECTURE: replace the RTMP->MediaMTX video diagrams** with raw H.264 TCP :5600 (the shipped path).
- **D5b — ARCHITECTURE/ROADMAP: fix the `-c 65536` / 12 GiB VRAM claims** (shipping value is 8192).
- **D5c — ARCHITECTURE + system docs: ASR->FMU is BUILT** (fmu_node.hpp:279/384/405), not "PROPOSED".
- **D5d — ROADMAP: the SITL matrix names pre-rename dirs** (rotate-land, boundary, flood...) — sync to the real tree.
- **D5e — ROADMAP: fix the date block** ("Demo Day ~08-28, today 08-20").
- **D6 — root `NOTE.md`:** keep until its live points are addressed (tech-stack blurb + high-level diagram, owner-verified), then owner deletes. The expired points (presentation prep, pre-demo SITL scenarios) can go now.
- **D7 — codify S22:** a feature lands with its documentation, same change. Propose one line in code-guidelines.

---

## P. Parked / deferred (one per line)

- **P1 — fork merge:** after the win. POC scope until then: show BOTH the perception engine and `llm_to_action` (S15).
- **P2 — track-verb planning** (`llm_cv_track` fold-in): parked by owner Aug-28; R6 archives the folder meanwhile.
- **P3 — battery-RTH energy subsystem:** far future; 4 dependencies missing.
- **P4 — AGPL escape:** YOLO26 + SAM2 + BoT-SORT are Ultralytics/AGPL; matters only on public/product release.
- **P5 — OctoMap / A* / tf2 anchor:** far-future nav stack.
- **P6 — Tello archive (S16):** move `scripts/tello/` + the slam-tello tests + R10b's rviz to the archive home; backend code stays in-tree, frozen.
- **P7 — LOCKS.md:** retire (D1).
- **P8 — depth-models survey note:** write during the B-track, or drop — owner call.
- **P9 — perception -> llm_to_action fold-in scoping:** after the reorg; shaped by S14 (owner writes) and S17 (BT future).
- **P10 — exoskeletons app-side items:** foreground-service + battery-opt exemption (backgrounding kills :8080/:5600), gimbal, /key confirm, takeoff/land response bodies, committed local.properties — bundle into the R9/S18 other-dev conversation.
- **P11 — the reorg spec itself:** owner priorities on this audit -> spec (target layout + move plan + path fixes, owner-approved) -> execution on `feature-cleanup-reorg`.

## G. Ground-truth corrections from this audit
- Runtime drone-config exists (A11). Yaw sign resolved CW+ 2026-08-21 (D2d). Dynamic-IP + exoskeletons comms demo-verified (S9). RoboMaster deletion clean. lookat/goto unused anywhere; no goto exists (R9). LLMDet memory corrected (B7). TTS wiped with the container -> C5c. `origin` remote verified present on GitHub (C1). Repo-destruction rule live in CLAUDE.md (S21). Working agreement recorded in agent memory (S14).

---

## Appendix A — step<Verb>() sketch (direction confirmed by owner; OWNER writes it)

Existing pattern, `stepHover` (fmu_node.cpp:114-125, decl fmu_node.hpp:586):

```cpp
// fmu_node.hpp (private:)
void stepHover(TickCtx& ctx);   // one 20 Hz control-law tick for HOVER

// fmu_node.cpp
void FlightManagementUnitNode::stepHover(TickCtx& ctx) {
    publishVelocitySetpoint({0,0,0}, 0.0f);   // behaviour-identical to the old inline branch
}
```

ROTATE next (current inline branch fmu_node.hpp:886-911, 26 lines):

```cpp
// BEFORE (controlLoop if-chain)
} else if (id == CommandID::ROTATE) {
    /* 26 lines: remaining rad from m_rotatePrevYaw, clamp yaw rate,
       publish setpoint, completeCurrent() at threshold */
}

// AFTER
} else if (id == CommandID::ROTATE) { stepRotate(ctx); }

// fmu_node.cpp — verbatim body move; touches the same members (m_rotateRemainingRad, m_rotatePrevYaw)
void FlightManagementUnitNode::stepRotate(TickCtx& ctx) { /* the same 26 lines */ }
```

`TickCtx` bundles only what verbs actually share (odometry snapshot, dt, depth stats); start with the
2-3 values each verb reads, grow it only as extraction demands — it exists to shrink the 64-local
preamble. Order (tasklist): HOVER done -> GO/ROTATE -> LAND/ORBIT/FOLLOW -> SEARCH/APPROACH last.
Each slice: build + Gazebo gate. The compounding win is A2: one `verbs/rotate.hpp` owning
parse + activate + step + name collapses the six hand-synced tables.
