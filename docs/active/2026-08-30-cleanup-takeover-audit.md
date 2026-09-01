# Takeover Tasklist & Audit (Rev 3, 2026-08-31)

Rev 3 implements the owner's C7 directive: the notes ledger is now a REFACTOR TASKLIST — what to
address, what is done, who does it, what to keep in mind. Detailed per-item evidence lives in Rev 2
of this file (git history, commit 3a395e9); IDs are unchanged so history lookups work.
Owner tags: **[OWNER]** = owner writes (all C++ per the working agreement), **[AGENT]** = agent
executes, owner reviews the diff and runs the git commands, **[PAIR]** = decision or physical action.
Status: `[x]` done, `[~]` partial/in progress, `[ ]` open.

---

## 0. SPRINT FREEZE (2026-09-01) — read before using this list
RESTRUCTURE NOTE (2026-09-01, same day): the owner overrode the freeze for a repo restructure
(monorepo `projects/` layout) executed before backlog A. Items it completed are flipped to `[x]`
below; the full record is `2026-09-01-repo-restructure.md`. Paths in older items may predate the
restructure — translate `source/` -> `projects/`, `scripts/test/` -> `projects/llm_to_action/test/`.
Change of plans: two more technical interviews inside ~1.5 weeks (see
`2026-09-01-interview-sprint-handoff.md`). This tasklist is FROZEN for the sprint except:
C3 (phone strip finish), S1/E (notify live test), and anything directly serving backlog A-E.
The working agreement is amended for the sprint: agent writes MVD Python again; C++ stays
owner-written. The refactor/takeover resumes AFTER the sprint, starting with G1 module verdicts.
The restructure remains a stated necessity - postponed, not cancelled.

## 1. THE TASKLIST

### Now / short-fuse
- `[x]` **[PAIR] C3 — phone strip DONE (verified 2026-09-01).** gms/gsf/vending/tts all absent from
  `pm list packages`. What remains is benign: GrapheneOS/Pixel resource overlays (no code),
  Pixel hardware glue (euicc/nfc/radio/camera services — removing risks breaking the device), and
  `app.grapheneos.gmscompat*` (GrapheneOS's own now-empty sandbox scaffolding, not Google code).
  No further removals. NOTE (owner): the GrapheneOS device is NOT used for demos — this strip has
  zero effect on the demo speech stack.
- `[x]` **[PAIR] C2 — kill drill A + B: PASSED** (owner, 2026-08-31; times unrecorded). `[ ]` Test C
  pending: with our virtual stick active, perform CSC and RECORD whether the motors stop or the stick
  authority overrides it. Either outcome passes — the point is knowing which. [AGENT] writes A/B PASS
  + C result into the kill-switch doc table.
- `[ ]` **[PAIR] S1 — notify fork webcam test** (owner, commands in the run guide).
- `[x]` **[AGENT] C1 — repo protection**: CLAUDE.md rule live; owner: no further action needed.
- `[x]` **[PAIR] S11 (DONE 2026-09-01) — merge to master + open `feature-cleanup-reorg`** (commands issued 2026-08-31).

### The rewrite (all [OWNER] — agent supplies a per-verb behavior map before each slice, reviews after)
Keep in mind, applying to every item: a refactor is imminent; agent code-notes below describe the
CURRENT tree so the owner knows what they are rewriting, not fixes for the agent to make.
- `[ ]` **A1 — step<Verb> extraction**, remaining 6 verbs. Order: GO/ROTATE -> LAND/ORBIT/FOLLOW ->
  SEARCH/APPROACH. Each slice: build + Gazebo gate. Pattern exists (`stepHover`).
- `[ ]` **A2 — collapse the six per-verb dispatch tables** into one unit per verb (do with A1; the
  six places are listed in Rev 2 A2).
- `[ ]` **A3 — helpers -> inline scoped headers** (`fmu_geometry.hpp` style; split when too long).
- `[ ]` **A4 — units -> metres**, converted per verb inside its slice; Tello wire boundary frozen.
- `[ ]` **C4 — DroneConfig defaults reference the constexprs** (kill the copied values; the 80-vs-120
  divergence is the proof it is needed).
- `[ ]` **A5b — compiled-in absolute paths out ASAP**: `kVlmPromptLogDir`, slam defaults, vision model
  paths -> env override or DroneConfig.
- `[ ]` **A6/A7/A9 — constants triage, per verb during its slice**: give each surviving constant a home
  (constexpr vs DroneConfig) and a provenance tag (SITL-swept vs first-guess); delete that verb's dead
  constants, inline magic numbers, and the shadow search-preset table; delete or wire the write-only keys.
- `[ ]` **A12/A13/A14 — dead-code sweep**: keep ONE hardened SPSC queue (move to `util/`), delete its
  twin; keep `slam2.hpp`, archive `slam1.hpp`; DELETE the `llm_to_action_offboard_mode` node (see
  answer Q3 below) after checking vehicle_status _v1-vs-_v4 against the px4_msgs in the build; delete
  the 74-line commented body in `asr_node.cpp`; per-verb dead members go with their verb's slice.
- `[ ]` **A16 — CURVE: out of the VLM vocabulary, KEPT as backend capability** (owner decision:
  usable for predefined patterns, e.g. a curved SEARCH sweep — just never VLM-emitted). Remove the
  two prompt sections; keep `CmdCurve` + wire an internal caller when a pattern needs it.
- `[ ]` **A17 — `stop`: REMOVE from the vocabulary** (owner decision: HOVER already achieves motion
  arrest). One nuance to decide during removal: `stop` implied "abandon the plan," hover holds then
  the queue continues — if abort-plan semantics are ever wanted, that is a new tiny verb, not stop.
  Emergency arrest remains the ASR tier's job.
- `[ ]` **A16b — `re-assess`: remove from the prompt** (replanning belongs to the BT future).
- `[ ]` **S7/A22a — proper FMU-side emergency-ASR path + tests** ("land"/"stop"/override injected via
  `/asr_server/transcribe`).
- `[ ]` **B6/A22b — FMU-side VLM presence gate** (see answer Q6): verify a planned target actually
  appears in frame before flying toward it — port of the MVD gate concept.
- `[ ]` **A15 — fix the two actively-lying comments now** (fmu_node.hpp:118-120; the zero-getenv
  claim); the rest die with their verbs.
- `[ ]` **A22c — open behavior defects to retest/fix during relevant slices**: approach-real range
  lock hits the car; search 160deg post-DETECT; interrupt-storm + override; od.yaw 0->1.57 suspect.
- `[ ]` **A20 — adopt util/base.hpp aliases as files are touched**; `<chrono>` not `<bits/chrono.h>`.
- `[ ]` **A21 — add the 3 missing headers to the CMake source list**; slam tests archived with Tello.

### Perception & ASR (research + tooling)
- `[ ]` **[PAIR] B1 — eval harness: time-cost decision pending.** Estimate for the owner: agent builds
  the replay harness in roughly half a day; owner hand-marks 50-100 captured frames (~1-2 h, once);
  each subsequent model/config run is minutes, unattended. Decide go/no-go on that budget.
- `[ ]` **[AGENT] B2 — 4B-at-Q4 box-accuracy experiment** — first harness run if B1 goes.
- `[ ]` **[OWNER+AGENT] B3 — NE-approach root cause** (`bboxToEnuAnchor` back-projection) — agent maps
  the math, owner fixes in the rewrite.
- `[ ]` **[AGENT] B5 — ongoing research topic (owner-designated): grounding-model landscape.** Which
  open-vocab grounders beat OmDet on absent-target hallucination, at what VRAM; measured on OUR frames
  via the harness, never on curated sets (see answer Q5). Revisit each time a serious new model lands.
- `[ ]` **[AGENT] H1 — Hebrew ASR bench**: whisper-large-v3-turbo + VAD, q4/q5/q6/q8 or ONNX, vs
  Parakeet on the same recordings.
- `[x]` **[AGENT] research-1 — DONE:** reading list delivered ->
  `docs/research/2026-08-31-vlm-bt-reading-list.md` (12 entries, ranked by studyable source; BTGenBot,
  Dendron, and the Microsoft VLM-BT planner are the top three for our stack).
- `[x]` **[AGENT] research-2 — DONE:** 7 gaps found; adopted as the subsection below.

### Handoff gaps adopted from research-2 (2026-08-31)
- `[ ]` **[PAIR] G1 — salvage-vs-discard verdict per module BEFORE any rewrite effort.** Explicitly
  rule each module rewrite / keep-as-is / delete, so disposable prototype code never gets a rewrite
  slice. Do this FIRST — it prunes the whole tasklist. (understandlegacycode.com, 7 handover practices)
- `[ ]` **[AGENT] G2 — churn-x-complexity hotspot table** from git log, so the owner orders rewrite
  slices by where bugs actually live, not by module list order. Cheap; agent computes, owner orders.
- `[ ]` **[OWNER] G3 — characterization tests before each rewrite slice.** Pin the OLD behaviour with
  golden-master tests (router/parse/geometry are ideal; Gazebo gates cover the flight laws), so a
  slice cannot silently change behaviour. Intentionally throwaway once real tests exist.
- `[ ]` **[AGENT] G4 — clone/duplication scan before dead-code removal** (jscpd/CPD or equivalent).
  AI-assisted codebases duplicate heavily (GitClear 2025, ~8x duplicated blocks); we measured the
  same pattern here. Collapse duplicates first or the owner rewrites the same logic twice.
- `[ ]` **[OWNER] G5 — fault-localization drill per module:** before signing a module off as
  "understood", predict where a described bug would live, then verify. Finds gaps doc-reading hides.
- `[ ]` **[AGENT] G6 — software supply-chain pass, distinct from drone safety:** hardcoded-secret
  sweep (phone IPs, keys), dependency CVE profile, and a check that private data (ASR recordings,
  transcripts) cannot leak via the repo. One-time, then a checklist line in the onboarding doc.
- `[ ]` **[PAIR] G7 — onboarding-doc authorship revisited.** Research finding: the INCOMING developer
  writing the docs is the practice that forces real questions — which contradicts our D-ownership
  ruling for this one doc. Proposed split: agent drafts the mechanical parts (commands, model lists),
  owner writes the understanding parts (architecture summary, module verdicts from G1). Owner decides.

### Repo & scripts (agent executes on `feature-cleanup-reorg`; owner reviews + commits)
- `[x]` **C5 — preflight script (DONE 2026-09-01: `tools/preflight.sh`)**: ONE script checks every required model/binary/asset and prints what
  is missing (owner: no manual checking). Note: models live in `/root/models`, volume-mounted and
  carried between demo machines — replication by outsiders is a README concern only (fold into C5d).
- `[ ]` **C5c — TTS install scripted** (piper + voice + espeak-ng + aplay).
- `[x]` **C5d — root README rewrite (DONE 2026-09-01)**: real quickstart, 4-arg build.sh, models/replication section.
- `[x]` **R1a (n/a — no config/ dir existed; compiled defaults remain A5b) — `config/` -> `assets/` repoints** (script callers; the 2 compiled defaults are A5b).
- `[x]` **R1b+R2 (DONE 2026-09-01: sim_core points at assets/, dependencies/ deleted) — repoint `sim_core.sh` at `assets/`, delete `dependencies/`** + submodule fossils.
- `[x]` **R1c (DONE 2026-09-01: launcher ported to source/dashboard/run_sitl_demo.sh) — fix the 6 dead `scripts/dashboard/` callers.**
- `[x]` **R3 (DONE 2026-09-01: .gitignore rewritten) — .gitignore cleanup**: drop the duplicate block, the rubicon_orbit dir rule, dead
  patterns, and (owner-approved R3c) every build-artifact pattern already covered by `build/`.
- `[x]` **R4 (DONE 2026-09-01: run_all.sh replaced by test/sitl/run.sh --all; phantoms dropped, verdict quality labeled in scenarios.conf) — run_all.sh**: remove 6 phantom scenarios, fix the 8-vs-4 comment, dead lib guard;
  then write the 6 missing `filter.sh` verdicts or mark those scenarios unverifiable explicitly.
- `[ ]` **R8 — rotate: tests in test_router.py, docs in the command table + README, JSON bodies
  documented**; one mock sign check ([PAIR] for the live half).
- `[~]` **R10c (stale stub pair deleted 2026-09-01; build-devenv.ps1 mirror still open) — write `build-devenv.ps1` mirroring build-devenv.sh; delete the stale one-line pair.**
- `[x]` **R10e (DONE 2026-09-01) — dji_check.sh: derive the NIC from `ip route`.**
- `[x]` **R10g (superseded 2026-09-01: owner ruled spent one-offs get DELETED, no oneoff home; mix_noisebed + yolo-quality removed) — create the one-off home** (`scripts/oneoff/`, date+purpose header rule); move
  mix_noisebed.py (purpose: ASR noise-cutoff bench) and friends into it.
- `[x]` **R12 (DONE 2026-09-01 for all live scripts; frozen integration/ keeps corrected absolute paths) — root-derivation sweep**: ~25 scripts get `ROOT="$(dirname ...)"` instead of
  `/root/groundstation`.
- `[ ]` **[PAIR] R11 — renames** (`gstreamer_udp_cam_rx` -> `gstreamer_cam_rx`, canned->synthetic):
  touch C++ dirs + CMake, so owner runs them with agent-prepared commands.
- `[x]` **[PAIR] P6 — Tello archive (DONE 2026-09-01: archive/tello, archive/slam-tests)**: agent prepares the `git mv` block (scripts/tello, slam tests,
  rviz), owner runs.
- `[x]` **[PAIR] R6 — llm_cv_track (DONE 2026-09-01: archived with llm_cv_scene; zero live refs) **: archive with P2, or agent vendors its 7 cross-package refs if
  the owner wants it runnable.

### Docs (owner ruling: docs are the AGENT'S context insurance -> agent does nearly all of it)
- `[x]` **[AGENT] D1 (DONE 2026-09-01: stale sweep + docs reorganized into runbooks/specs/research) — the 15 stale moves**: agent prepares the exact `git mv` block, owner pastes it.
- `[ ]` **[AGENT] D2a-i + D3 + D5 — all in-place corrections** (indexes, contradictions, ports,
  machine roles, dates, stale claims): agent edits, owner reviews the diff.
- `[ ]` **[AGENT-draft/OWNER-author] C7-doc — the onboarding doc** (clone -> build -> run, C5 models
  section, safety rules, reading order). Authorship split pending G7 decision.
- `[ ]` **[OWNER] D6 — root NOTE.md**: address its two live points (tech-stack blurb + diagram — agent
  drafts, owner verifies), then owner deletes the file.
- `[ ]` **[AGENT] D7 — feature-lands-with-docs line proposed for code-guidelines.**

### Deferred (unchanged, one line each)
- P1 fork merge (after the win; POC shows perception + llm_to_action). P2 track-verb planning.
- P3 battery-RTH. P4 AGPL escape. P5 nav stack. P7 LOCKS.md retire (in D1).
- P8 depth-models note (owner call). P9 fold-in scoping (post-reorg). P10 exoskeletons app items +
  R9 dead wire methods (both wait for the other-dev conversation). P11 reorg spec (after this
  tasklist is prioritized).

---

## 2. ANSWERS FROM THE 2026-08-31 REVIEW

**Q1 (C2 rephrased).** The drill proves the three stops in order of trust. A: the aircraft power
button — a hardware cut that no software can override; proving it first gives every later test a
safety net. B: the phone API-Server toggle — it drops OUR control authority so the drone falls back
to RC/failsafe. C: the DJI stick combination (CSC) — while our virtual stick is active the DJI SDK
MAY ignore it; Test C exists to learn, on our aircraft, whether it does. A and B are pass/fail. C is
measurement. A and B: PASSED. C: pending.

**Q2 (C3).** GMS + GSF are the actual background-telemetry surface; Play Store and TTS were the easy
part. The closing command block is in chat; result to be recorded above.

**Q3 (A13, "which dead node?").** Yes — a compiled executable: `llm_to_action_offboard_mode`, built
from `projects/llm_to_action/source/offboard_ctrl/` on every PX4 configure. It is an early standalone offboard
node, superseded when `px4_backend` moved inside the FMU binary; no script launches it. It carries
its own copies of the PX4 topic strings and sysIDs — deleting it removes the A8 duplication in the
same stroke. One check first: its copy says `vehicle_status_v1`, the live backend says
`vehicle_status_v4`; confirm which matches the px4_msgs in the build before deleting the wrong truth.

**Q4 (B4 — did OmDet actually run?).** Yes. The demo pipeline, precisely: **YOLO26n-seg** did the
per-frame background segmentation (NOT YOLOE — YOLOE never loads; its weight file is not even on
disk). **OmDet-Turbo** did the per-frame open-vocabulary grounding of your highlight phrase — it is
what found "the red backpack" in every frame. **SAM2.1** cut masks from OmDet's boxes. The **VLM**
did three things: answered scene questions, spoke the answers, and ran a ONE-SHOT presence gate per
highlight request — it vetoes OmDet before OmDet is allowed to draw, because OmDet (like any
open-vocab detector) returns a confident box even for absent targets. So the highlight artifacts are
grounded in OmDet's ability, filtered by the VLM's judgment. The confusing `SCENE_HL_BACKEND=vlm`
setting only disables the UNUSED in-Eyes highlighters (YOLOE/LLMDet); OmDet is loaded separately
(`scene_omdet.py:173`) and was live.

**Q5 (B5 — "what synthetic test bullshit?").** The 96%-vs-41% numbers came from an agent-made
selection bench (2026-08-19): 8 curated, ground-level images and 27 prompts, scored for RECALL —
does the model find the odd object. It answered "which grounder finds esoteric things" and was used
to pick LLMDet. It said nothing about the question that mattered live — false fires on ABSENT
targets in aerial/blurry footage — which is exactly how LLMDet then failed. That is the lesson coded
into B1: benchmarks on our system replay OUR captured frames or they are not evidence. The old bench
artifacts no longer exist; nothing to salvage.

**Q6 (B6 clarified).** In the C++ FMU's objective mode the VLM writes a plan ("approach the car")
and the FMU flies it without ever verifying the car exists in the camera frame — a hallucinated
detection becomes real motion. The Python MVD solved this class of error with its presence gate;
the FMU has no equivalent. Task B6/A22b ports the concept: before an APPROACH engages, confirm the
target is visible, else reject the plan.

**Q7 (D ownership).** Ruling adopted: repo docs exist mostly to restore AGENT context across
sessions; therefore the agent maintains them (edits, corrections, the stale sweep, indexes) and the
owner only reviews diffs and runs git. Owner-authored docs remain: NOTE.md's two live points and
anything stating intent only the owner holds.

## 3. Decisions ledger (compact)
S14 owner writes all C++ / agent maps+reviews. S16 Tello deprecated, frozen, scripts archived.
S17+Rev3: CURVE = internal-only capability. NEW: stop removed from vocabulary (hover covers it).
S19 anonymization state accepted. S10 integration/ frozen until the post-win merge. S21 repo-
destruction rule live. S22 features land with docs. C2 A/B passed. Evidence for everything: Rev 2
in git history (3a395e9).
