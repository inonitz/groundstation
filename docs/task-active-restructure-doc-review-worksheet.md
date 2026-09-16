# Document review worksheet — REVIEWED / NON-REVIEWED (2026-09-14)

Split as you asked. Part A is settled and ready to execute. Part B still needs your decision.
The full per-file inventory is kept below as the evidence appendix. I move nothing until Part B closes.

---

# PART A — REVIEWED (settled)

## A1. Target structure (final)

```
docs/
  README.md   ARCHITECTURE.md   ROADMAP.md   HISTORY.md (was NOTES.md)   guidelines.md
  specs/            # TRIMMED to 3 (your 2026-09-14 ruling): spec-dji-websocket-protocol, dji-video-h264-over-tcp, spec-dji-backend
  tasks-active/     # was docs/active; one folder per task: <YYYY-MM-DD>-<task-name>/
  tasks-scheduled/  # was docs/scheduled
  stale/            # historical archive
  research/         # + research/complete/ for finished research
  private/          # gitignored, untouched
```

## A2. Rules (settled)

- Nothing is hard-deleted. A deletion candidate is first recorded in HISTORY.md, then moved to docs/stale.
- A done task folder is summarized into HISTORY.md (date, events, intent), then moved to docs/stale.
- llm_to_action is a SUBPROJECT of this repo. Its docs go to a tasks-active folder in docs/, never "out".
- No runbooks folder. Running something must take 1-2 commands.

## A3. Top-level files (settled)

| File | Action |
|---|---|
| NOTES.md | rename to HISTORY.md; keep updating it daily |
| ARCHITECTURE.md | rewrite to reflect integration_harden2 + llm_to_action; can draft now, finalize after harden2 freeze |
| ROADMAP.md | resync to current direction |
| docs/README.md | keep, refresh |
| system-architecture.md | merge into ARCHITECTURE.md |
| code-guidelines.md + writing-style.md (+ my writing memories) | merge into guidelines.md |
| root README.md | stale (predates harden2); rewrite |
| root NOTE.md | stray scratch; record in HISTORY then move to stale |

## A4. docs/specs (settled by your 2026-09-14 ruling)

Keep THREE, in docs/specs/: `spec-dji-websocket-protocol.md` (the phone-side wire contract), `dji-video-h264-over-tcp.md` (video path of record), `spec-dji-backend.md` (parked C++ backend design). The other three go to HISTORY then stale: `spec-dji-endtoend-bringup.md` (duplicate of the bring-up runbook), `dji-apiserver-review.md` (superseded review), `spec-fmu-cleanup.md` (parked backlog; verify done-state first).

## A5. docs/active -> task folders (settled groupings)

Each row is a task folder under tasks-active/. Historical folders are summarized into HISTORY.md then moved to stale.

| Task folder | Files | Fate |
|---|---|---|
| 2026-08-30-cleanup-takeover | cleanup-takeover-audit | extract live C++ items to HISTORY, then stale |
| 2026-09-03-integration_harden-era | deadcode-purge-report, golive-wiring-handoff, golive-wiring-report, structure-pass-report, nuclear-code-review, manager-handoff(09-02,09-03), asr/sam3/sam31 briefs, live-desk-test report+brief, 09-05 session-handoff, 09-02 state-and-next | removed tree; historical -> HISTORY -> stale |
| 2026-09-06-architecture-diagrams | architecture-diagrams (keeper) + the 4 diagram prompts + simplified-diagram prompt | prompts -> stale; keeper stays until diagrams settled |
| 2026-09-07-vram-perception-campaign | campaign-plan, campaign-results | extract binding rulings to HISTORY, then stale |
| 2026-09-05-llm_to_action-demo | fmu-cleanup-tasklist, fmu-node-split-map, fmu-control-loop-smell-catalog, llm-to-action-presentable-brief, llm-to-action-report, llm-to-action-and-depth-handoff, llm-to-action-demo-handoff (keeper), subagent-bootstrap-note, + scheduled/runtime-drone-config-constants | llm_to_action subproject work; keep active |
| 2026-09-12-harden2-live-test | 09-08 session-handoff, guard-and-config-workplan, harden2-deadcode-purge, full-trace-and-replayer-workplan, commit-manifest, order-to-commit, 09-12 live-test-handoff, 09-12 session-handoff | done items -> HISTORY -> stale; commit-manifest stays live until the freeze commit |
| 2026-09-10-self-hosted-tracker | track1-tracker-decisions, track1-tracker-handoff | see B2 (is this lane still alive?) |
| 2026-09-13-repo-restructure | docs/13-09-2026/{c2-handoff, repo-restructure-plan, restructure-progress, slam-removal-prompt}, 09-09 repo-cleanup-draft, 09-09 project-state-and-reorientation | this restructure; superseded planning drafts fold in |

## A6. Other areas (settled)

| Area | Action |
|---|---|
| docs/research | keep. Move 5 finished (hebrew-intent, finetune-data, qwen-hebrew-bench, asr-noise-robustness, latency) to research/complete/. vlm-bt-reading-list stays. |
| docs/scheduled | energy-terrain -> research; runtime-drone-config-constants -> the llm_to_action task folder. Folder then empties. |
| docs/stale | keep as archive; prune the pure-noise entries (record in HISTORY, they are already archival). |
| docs/private | keep, untouched. |
| docs/active/assets | move to archive/assets. EXCEPTION: diagrams-final/ and diagrams-detailed-v2/ -> archive/diagrams (kept separate, preserved). |
| bench/ | keep. Workflow: result docs live in the bench folder while working; after summarizing, move them to logs/ and record in HISTORY.md + update ARCHITECTURE.md if an architecture migrated. |
| projects/integration_harden2, integration_tts | keep. |
| projects/llm_to_action | keep code (subproject). Its loose docs move to the task folder above. |
| sitl-legacy (18 READMEs) | consolidate into sitl/ (verbatim copies of sitl/SCENARIOS.md). |
| tools/dji_mock, tools/session-replayer | keep. |
| tools/desk-test | keep the data/logs (live-test lists -> datasets/e2e); the launcher tools are no longer relevant -> HISTORY -> stale. |
| tools/diagram-authoring | delete (saved to its own repo); keep .claude/skills/diagram-authoring (deployed). |
| .claude/skills | keep. recognizer-bench already retired (committed). |
| projects/integration_tts/yolo26n-seg.pt | a SYMLINK -> source/integration/yolo26n-seg.pt; move the real weight to /root/models/vision and fix/drop the symlink (verify no load path breaks first). |

## A7. Reformulated action lists

These are the four lists you said were badly written, rewritten so each line states the file, what it is, and the action.

### Rename / merge
- `NOTES.md` -> `HISTORY.md`: the running daily log; rename only, then keep appending.
- `system-architecture.md` -> merge into `ARCHITECTURE.md`: it is the older, thinner duplicate; the merged doc keeps ARCHITECTURE's name.
- `code-guidelines.md` + `writing-style.md` -> `guidelines.md`: one guidelines file; the writing half also folds in the stored writing rules (lists-or-flow, short reports, the result-doc register, README-current, plain naming).

### Rewrite (keep the file, content is stale)
- `ARCHITECTURE.md`: describes the dead OmDet+SAM2 stack and removed trees; rewrite to harden2 + SAM3 + Gemma-4 and the llm_to_action core.
- `ROADMAP.md`: resync to the current cleanup -> test -> freeze direction.
- root `README.md`: predates harden2; rewrite to the current repo shape.

### Archive to stale (record in HISTORY first)
- The whole integration_harden era (removed tree): the go-live wiring, dead-code, structure-pass, and nuclear-review reports, plus the 09-02/09-03 manager handoffs and the consumed session briefs. All document a tree that no longer exists.
- The superseded session handoffs (09-05, 09-07, 09-08, 09-12) once the 2026-09-13 restructure record supersedes them.
- The diagram prompt-artifacts (four one-off subagent prompts) and the invalidated A/B pilot prompts.
- The superseded planning drafts (09-09 repo-cleanup-draft, 09-09 project-state-and-reorientation).

### Move to archive/ (regenerable, not stale)
- `docs/active/assets/` -> `archive/assets/`, except `diagrams-final/` and `diagrams-detailed-v2/` -> `archive/diagrams/` (kept separate for slide reuse).

### Extract binding content, then stale
- `final-objective-context.md` and `2026-09-07-vram-perception-campaign-results.md`: pull the still-binding objective and owner rulings into HISTORY.md / ROADMAP.md, then archive the source.
- `2026-08-30-cleanup-takeover-audit.md`: salvage the still-live C++ backlog items into the llm_to_action task folder, then archive.

---

# PART B — NON-REVIEWED (needs your decision)

## UPDATE 2026-09-14 (pt 3) — Part B nearly closed (supersedes B1/B2 below)

RESOLVED by your rulings:
- B1 (live harden2 reference docs): `2026-09-08-harden2-architecture.md`, `2026-09-10-harden2-run-arguments.md`,
  and `2026-09-09-dji-apiserver-architecture.md` STAY in docs/* for now. Final placement deferred; no forced fold.
- UI rewrite is DONE -> `2026-09-12-ui-rewrite-IN-PROGRESS.md` -> record in HISTORY, then stale.
- `challenge-form.md` -> docs/private.
- self-hosted-tracker docs (`track1-tracker-decisions`, `track1-tracker-handoff`): the lane is being pursued,
  but the docs have no point -> record in HISTORY, then stale.

STILL OPEN — your call (now explained):
- `mvd-voice-command-table.md` — INTENT: the definitive reference table mapping each spoken command ->
  DjiWire call -> the exact DJI `/c/fly` POST JSON, for the frozen English demo (source: integration_tts
  commands.py/router.py/dji_wire.py). It is our-side wire/command reference. RECOMMEND: keep as the
  integration_tts command reference (or fold beside the DJI wire spec in docs/specs).
- `2026-09-10-track2-execution-draft.md` — CONTENT: a rev5 DRAFT of the full voice-drone system plan in 7
  steps (verify perception -> save+guard+commit harden2 -> OUTDOOR validate + freeze -> cleanup -> noise/
  low-light benchmarks -> features off the baseline -> fuse llm_to_action). It IS the system-plan content,
  but it is SUPERSEDED: it orders outdoor-freeze BEFORE cleanup (you later reversed that), still calls
  integration/ the frozen fallback (now integration_tts), and cites the old 415/466 bench (now 410/487).
  RECOMMEND: extract the durable 7-step arc into ROADMAP.md, then archive the draft. It is not a living master doc.


## B1. Structural gap: no home for LIVE harden2 reference docs

The new structure has `ARCHITECTURE.md` (being rewritten) but no bucket for living operational reference of the LIVE system. You removed runbooks, and `specs/` is now only the three DJI files. Three current, useful docs therefore have no home:

- `2026-09-08-harden2-architecture.md` — harden2 architecture with measured numbers, env switches, boot command (a prime SOURCE for the ARCHITECTURE.md rewrite).
- `2026-09-10-harden2-run-arguments.md` — every harden2 run env var/argument, read from the code.
- `2026-09-09-dji-apiserver-architecture.md` — the phone REST/WS API reference from the Kotlin source.

Decision needed: do these (a) fold into `ARCHITECTURE.md`, (b) get a new `docs/reference/` bucket, or (c) join `docs/specs/`? My recommendation: harden2-architecture folds into ARCHITECTURE.md; run-arguments becomes a "Run" section of ARCHITECTURE or the README; dji-apiserver-architecture joins docs/specs (it is the phone-side API contract).

## B2. Edge files — each needs a call

| File | The question | My recommendation |
|---|---|---|
| `mvd-voice-command-table.md` | The old English MVD verb table. Keep as the integration_tts (frozen English demo) command reference, or archive? | Keep as integration_tts reference (it documents the frozen demo's verbs). |
| `2026-09-12-ui-rewrite-IN-PROGRESS.md` | The OpenCV live-pane rewrite resume doc. Still pending, or shipped/abandoned? | Confirm status; if shipped -> stale, else keep in the harden2-live-test folder. |
| `challenge-form.md` | The canonical scored MOD requirement form; all status docs map to it. Keep where, and is it competition/judge material -> docs/private? | Move to docs/private (competition material) but keep it as the canonical reference. |
| `2026-09-10-track2-execution-draft.md` | The rev5 voice-drone system plan (steps 1-7). Current master plan, or superseded? | It is the active system plan; fold its live content into ROADMAP.md, then archive the draft. |
| self-hosted-tracker lane (`track1-tracker-decisions`, `track1-tracker-handoff`) | Is the self-hosted project-tracker lane still being pursued, or dropped? | If dropped -> HISTORY -> stale; if alive -> keep the task folder. |

## B3. My formulation of A5/A7 (Part A)

You said the earlier action lists were badly written; A5 and A7 are the rewrite. If the grouping or the phrasing is still wrong, mark it and I fix it — no execution until you sign off.

---

# Full file inventory

Every doc file in the repo (archive/ and docs/private/ excluded). Grouped by area. Path, content in
<=2 sentences, and my verdict. Verdicts are suggestions; you rule.

## Folders overview

| Folder | What it holds | Target under the new structure |
|---|---|---|
| docs/ (top) | README, ARCHITECTURE, ROADMAP, NOTES, guidelines, code-guidelines, writing-style, system-architecture | README/ARCHITECTURE/ROADMAP stay; NOTES->HISTORY; code-guidelines+writing-style->guidelines.md; system-architecture MERGE into ARCHITECTURE |
| docs/active/ | the dumping ground: session handoffs, plans, reports, one-off prompts | DISSOLVE into tasks-active/<date>-<task>/ (or stale/delete) |
| docs/active/assets/ | demo-day slides + diagram sources (gitignored) | presentation material: keep gitignored / move to private / delete superseded sets |
| docs/research/ | investigations + reading lists | research/ (keep) |
| docs/runbooks/ | how-to-run guides | DECIDE (dropped from structure; suggest keep a runbooks/) |
| docs/scheduled/ | future-subsystem specs | tasks-scheduled/ |
| docs/specs/ | DJI interface/protocol specs (parked C++ track) | DECIDE (suggest MOVE-OUT->llm_to_action) |
| docs/stale/ | historical archive | stale/ (keep, prune noise) |
| docs/private/ | gitignored personal | out of scope, untouched |
| docs/13-09-2026/ | THIS session's restructure docs | tasks-active/2026-09-13-repo-restructure/ |
| bench/<name>/ | benchmark scripts + result docs | keep; results/ per-run dumps CONSOLIDATE into RESULTS.md |
| projects/integration_harden2/ | the LIVE system + component READMEs | keep (fix integration_harden fork-drift in headers) |
| projects/integration_tts/ | the FROZEN demo fallback | keep |
| projects/llm_to_action/ | parked C++ track (OTHER DEV) | keep in place; sitl-legacy/ superseded by sitl/ (DECIDE) |
| tools/dji_mock, tools/session-replayer | tooling READMEs | keep |
| tools/desk-test/ | live-test lists + checklists | some are e2e datasets -> datasets/e2e; DECIDE |
| tools/diagram-authoring/ | diagram skill dev home | DUPLICATE of .claude/skills/diagram-authoring; DECIDE canonical |
| .claude/skills/ | agent skills | keep (recognizer-bench DELETE) |



## docs/ tree - per file


### docs/ top-level + research + scheduled

# Doc triage D — docs/ top-level + research/ + scheduled/

Reviewed 2026-09-13. Today's reality: LIVE = integration_harden2 (Gemma-4 planner + SAM3 perception +
whisper-ivrit ASR + recognizer sieve). Dead/removed: integration, integration_harden, integration_notify, slam
(-> archive/, purged at freeze). Perception moved OmDet+SAM2.1 -> SAM3. llm_to_action = parked C++ tree
(other dev). integration_tts = frozen English fallback.

| File | Purpose (what it is FOR) | Status | Last-relevant date | Suggested disposition | Overlaps/notes |
|---|---|---|---|---|---|
| docs/ARCHITECTURE.md | Detailed spec of the C++ FMU flight-core (20 Hz loop, backends, verbs) + bolt-on perception/MVD appendices | partially-stale | FMU core to 2026-09-06; perception appendix to 2026-09-06 desk log | REWRITE (trim/replace perception+MVD sections) / KEEP-IN-PLACE core | Core = parked llm_to_action tree, still its source of truth. Perception appendices name dead trees + old stack. See staleness notes. |
| docs/NOTES.md | Running dev change-log + gotcha archive, newest at bottom (2026-08-09 -> 2026-09-13) | current | 2026-09-13 (restructure entry) | KEEP-IN-PLACE | Log by nature; old entries citing dead trees are history, not staleness. Authoritative record; check before re-diagnosing. |
| docs/README.md | Index/map of the docs/ tree (top docs + folder buckets) | current | ~2026-09-02 (folder scheme) | KEEP-IN-PLACE | Lists active/runbooks/specs/research/stale/scheduled. Does not mention the 2026-09-13 repo-root restructure (bench/->top, archive/), but scope is docs/ only. |
| docs/ROADMAP.md | Consolidated objective tree with per-goal status (flight core + perception) | partially-stale | Last synced 2026-08-20; tail update 2026-09-02 | REWRITE (re-sync to harden2/SAM3/Gemma + restructure) | "Perception-first" banner + perception section name archive/llm_cv_track, OmDet, SAM2.1, Qwen3-VL, projects/slam, integration_harden. See staleness notes. |
| docs/system-architecture.md | Diagram-centric one-shot overview of the C++ FMU target system (mermaid dataflow) | stale | 2026-08-12 | CONSOLIDATE->ARCHITECTURE.md (or ARCHIVE docs/stale) | Redundant with ARCHITECTURE.md; older + thinner. Names Qwen3-VL-2B, Parakeet, Tello. Pre-Gemma/SAM3/harden2. See notes. |
| docs/research/2026-08-31-vlm-bt-reading-list.md | Ranked reading list: LLM/VLM -> behaviour-tree generation, for post-sprint PHASE 2 research | current | 2026-08-31 | KEEP-IN-PLACE | Self-contained, explicitly "not sprint material"; open research lane (decide during P9). No stale product claims. |
| docs/research/2026-09-01-qwen-hebrew-bench.md | Bench: can Qwen plan directly from Hebrew, skip HE->EN translation? | partially-stale | 2026-09-01 | KEEP-IN-PLACE (research record) | Data valid. Verdict "translate HE->EN before Qwen" OVERTAKEN: harden2 runs Gemma-4 reading Hebrew directly, no translator (NOTES 2026-09-10). |
| docs/research/2026-09-02-finetune-data-plan.md | Fine-tune dataset sizing/shape guidance (closed Hebrew military lexicon, LoRA) | current | 2026-09-02 | KEEP-IN-PLACE | Ballpark labeled unverified. Fix-order (glossary->few-shot->LoRA) still applies if fine-tune pursued. |
| docs/research/2026-09-02-hebrew-intent-parsing.md | Research lane: small Hebrew-native parser to replace Qwen + drop translation | partially-stale | 2026-09-02 | KEEP-IN-PLACE (research record) | Lane goal (Hebrew-native, no translation) essentially realized by Gemma-4-direct in harden2. DictaLM/LoRA specifics still open. |
| docs/research/asr-noise-robustness.md | Benchmark: ASR intent accuracy vs gunfire/explosion SNR; proves "ship raw, no denoiser" | partially-stale | ~2026-08 (Parakeet run) | KEEP-IN-PLACE (research) | Doctrine (ship raw, confidence gating dead) current. But curve is for Parakeet-TDT-0.6b; LIVE ASR is whisper ivrit-large-v3-turbo -> curve is model-specific, may need re-run. |
| docs/research/latency-2026-08-22/README.md | Real-drone DJI link latency measurement (WS + telemetry RTT) | current | 2026-08-22 | KEEP-IN-PLACE | Standalone hardware result, verdict transport PASS. Point-blank range caveat noted in-doc. |
| docs/scheduled/2026-08-07-battery-rth-energy-terrain-subsystem.md | Deferred spec: smart return-to-home energy model + terrain-aware landing | current | 2026-08-07 | KEEP-IN-PLACE (scheduled/) | Honestly labeled deferred; deps (odometry integral, pack voltage, downward depth, SLAM map) not yet present. |
| docs/scheduled/2026-08-08-runtime-drone-config-constants.md | Deferred spec: load per-drone FMU tuning constants from profile file, not constexpr | current | 2026-08-08 | KEEP-IN-PLACE (scheduled/) | Targets the C++ FMU (ROADMAP 9.14). NOTE: harden2 already did a Python config_constants/config_defaults merge (NOTES 2026-09-10/11) — different system, same idea; conceptual overlap only. |

## Big-doc staleness notes

**ARCHITECTURE.md** (what a rewrite must fix)
- Perception "llm_cv_track / llm_cv_scene" section (2026-08-20) is the old stack: OmDet-Turbo + SAM2.1 + Qwen3-VL, and points at `archive/llm_cv_track/README.md`. Live stack is SAM3 + Gemma-4.
- "Voice pipeline components" section names `projects/integration_harden/recognizer/` and `.../perception/` and `scene_omdet.py` as live — integration_harden is a DEAD tree (archived). Recognizer/perception now live in integration_harden2.
- "Integration MVD" section describes `projects/integration/` (English) as "the Demo-Day system"; that tree is now the FROZEN fallback renamed integration_tts. Names Qwen3-VL translate on :18090 / DictaLM :18091 — harden2 runs no translator (Gemma reads Hebrew directly).
- Core FMU spec (loop, backends, verbs, ENU, §7 translator) remains accurate for the parked llm_to_action tree; annotated as living to 2026-09-06.

**NOTES.md**
- Not stale by nature — it is an append-only log; early entries reference dead trees and Tello because that was reality then. Newest entries (2026-09-11..13) correctly describe harden2/SAM3/Gemma and the restructure.
- Only risk: it is 3436 lines. If the owner wants it trimmed, the pre-2026-09 flight-core entries could split to a NOTES history file, but that is optional, not a correctness fix.

**ROADMAP.md**
- "Last synced: 2026-08-20" and the CURRENT PHASE banner still frame the world as the pre-Demo-Day perception-first pivot; today's live system (harden2) and Demo-Day cancellation are not reflected.
- Perception section + status lines name archive/llm_cv_track/scene_omdet.py, OmDet-Turbo, SAM2.1, Qwen3-VL — all superseded by SAM3.
- Block 7 SLAM points at `projects/slam/source/` (removed to archive/). integration_harden referenced in the 2026-09-02 tail. Objective-tree structure is sound; the status/paths need re-sync.

**system-architecture.md**
- Names Qwen3-VL-2B, Parakeet-q4 ASR, `high_level_navigation_node`, DJI Tello as a live target — all superseded (Gemma-4, whisper-ivrit, Tello dropped 2026).
- Dated 2026-08-12, no living-spec annotations (unlike ARCHITECTURE.md which is maintained to 2026-09-06); it is a frozen snapshot.
- Describes the same C++ FMU system as ARCHITECTURE.md but at diagram/overview altitude only.

## Consolidation groups

- **ARCHITECTURE.md vs system-architecture.md** — both document the C++ FMU/llm_to_action system. ARCHITECTURE.md is the maintained, detailed living spec; system-architecture.md is an older, thinner mermaid overview. KEEPER = ARCHITECTURE.md. Suggest folding the useful diagrams into it (or ARCHIVE system-architecture.md to docs/stale). Two files whose names differ only in style invite confusion.
- **Perception appendices in ARCHITECTURE.md + ROADMAP.md perception section** — both re-describe the standalone perception stack with the dead OmDet/SAM2/Qwen paths. A single current perception description belongs in one place (harden2's own README is the live source); the two top-level docs should point to it rather than duplicate a stale copy.
- **Hebrew-parsing research trio** (2026-09-01-qwen-hebrew-bench, 2026-09-02-hebrew-intent-parsing, 2026-09-02-finetune-data-plan) — one connected investigation into Hebrew command handling. Not duplicates (bench / lane plan / data plan), keep separate, but their shared conclusion (Hebrew-native, skip translation) is what harden2 shipped via Gemma; a one-line "outcome: realized in harden2" pointer on each would prevent re-litigation.


### docs/active/ - tracked set

# Doc triage — docs/active/ (tracked set A), 2026-09-13

Relevance frame: LIVE = `integration_harden2`. FROZEN demo = `integration_tts`.
`llm_to_action` = parked C++ (other dev). DEAD/removed = `integration`, `integration_harden`,
`integration_notify`, `slam`. Any doc whose subject is a removed tree is historical by definition.

| File | Purpose (<=15 words) | Status | Last-relevant date | Suggested disposition | Overlaps/notes |
|---|---|---|---|---|---|
| 2026-08-30-cleanup-takeover-audit.md | Master refactor/takeover tasklist: C++ rewrite, dead-code, perception/ASR research backlog | stale | 2026-09-11 (one B1 note) | DECIDE | Rev 3 audit; mixes `llm_to_action` C++ backlog (parked) with dead `integration_harden`; salvage live C++ items before archiving |
| 2026-09-02-asr-session-brief.md | One-off delegated-agent brief to run the Hebrew ASR benchmark round | prompt-artifact | 2026-09-03 | ARCHIVE(docs/stale) | ASR pick settled (whisper-turbo Q5); brief consumed. Group: session briefs |
| 2026-09-02-manager-handoff.md | Manager handoff: protocol/rails/state as of 09-02 night (integration_harden) | superseded | 2026-09-02 | ARCHIVE(docs/stale) | Superseded on STATE by 09-03 handoff; protocol content duplicated forward. Group: manager-handoffs |
| 2026-09-02-sam3-session-brief.md | One-off delegated-agent brief to evaluate SAM3/3.1 vs SAM2.1 | prompt-artifact | 2026-09-04 | ARCHIVE(docs/stale) | SAM3-nf4 adopted + in harden2; brief consumed. Group: session briefs |
| 2026-09-02-state-and-next.md | 5-line tombstone: "RETIRED 2026-09-04", redirects to moved stale copy | superseded | 2026-09-04 | DELETE | Content already at docs/stale/2026-09-02-state-and-next.md; this is a dead redirect stub |
| 2026-09-03-deadcode-purge-report.md | Result report: Tier-1 dead-code deletions + 4 bug fixes in integration_harden | stale | 2026-09-03 | ARCHIVE(docs/stale) | Describes REMOVED tree. Group: nuclear-code-review execution |
| 2026-09-03-golive-wiring-handoff.md | One-off implementer brief to wire Recognizer into integration_harden live app | prompt-artifact | 2026-09-03 | ARCHIVE(docs/stale) | Tree removed; brief consumed. Manager-noted embedded prompt-injection block (data only). Group: go-live pair |
| 2026-09-03-golive-wiring-report.md | Result report: Recognizer wired into integration_harden scene_omdet + run_mvd | stale | 2026-09-03 | ARCHIVE(docs/stale) | Describes REMOVED tree. Group: go-live pair (keeper of the pair over the handoff) |
| 2026-09-03-manager-handoff.md | Manager handoff: full board/state/rulings as of 09-03 evening (integration_harden) | superseded | 2026-09-03 | ARCHIVE(docs/stale) | Most complete early-Sept handoff but about dead tree; later 09-05/07/08 supersede. Group: manager-handoffs |
| 2026-09-03-structure-pass-report.md | Result report: Tier-3/4 structural refactor of integration_harden | stale | 2026-09-03 | ARCHIVE(docs/stale) | Describes REMOVED tree. Group: nuclear-code-review execution |
| 2026-09-04-live-desk-test-report.md | Prep report: mock logging, Hebrew ASR quant, tools/desk-test scripts for desk boot | stale | 2026-09-04 | ARCHIVE(docs/stale) | Targets integration_harden desk boot; harden2 has its own run.sh. Some tools/ artifacts persist |
| 2026-09-04-sam31-session-brief.md | One-off delegated-agent brief to make quantized SAM3.1 fit 8GB in production | prompt-artifact | 2026-09-04 | ARCHIVE(docs/stale) | SAM3.1 quant/tracking DEFERRED (memory); SAM3-nf4 is live. Group: session briefs |
| 2026-09-05-session-handoff.md | Live-test agent session dump: desk-test bootstrap, mock, ASR, dataset recorder | superseded | 2026-09-05 | ARCHIVE(docs/stale) | Superseded by 09-07/09-08 handoffs. Group: session-handoffs |
| 2026-09-07-session-handoff.md | Session dump: VRAM/translator campaign; self-declares superseded by 09-08 | superseded | 2026-09-07 | ARCHIVE(docs/stale) | Header says "read 2026-09-08-session-handoff.md first". Group: session-handoffs |
| 2026-09-07-vram-perception-campaign-plan.md | The PLAN (6 steps) for the VRAM+translator measurement campaign | superseded | 2026-09-07 | ARCHIVE(docs/stale) | Executed; superseded by its results doc. Group: VRAM campaign pair |
| 2026-09-07-vram-perception-campaign-results.md | Measured scorecard + owner rulings: deploy Hy-MT2 Q4, SAM3 prerequisite | superseded | 2026-09-07 | DECIDE | Decisions still valid for harden2 (Hy-MT2 + SAM3-nf4). Extract rulings to NOTES/bench, then move. Group: VRAM campaign pair (keeper) |
| final-objective-context.md | "The compass": objective, safety, PROVEN/NOT-proven for Demo-Day 08-27 MVD | stale | 2026-08-27 | DECIDE | Names `integration/` (now integration_tts) as the MVD, C++ as destination; predates harden2. Update to current state or archive |
| fmu-cleanup-tasklist.md | Living tasklist for the C++ FMU (llm_to_action) refactor + SITL tests | stale | 2026-08-18 | MOVE->projects/llm_to_action | Documents PARKED C++ tree owned by another dev; belongs beside it. Group: FMU C++ docs |
| fmu-node-split-map.md | Proposal to split the 3166-LOC fmu_node.hpp (llm_to_action C++) | stale | (undated, ~2026-08) | MOVE->projects/llm_to_action | Same parked C++ tree; pairs with fmu-cleanup-tasklist. Group: FMU C++ docs |
| mvd-voice-command-table.md | ASR->DjiWire->DJI POST command reference for the old English MVD | stale | 2026-08-25 | MOVE->projects/integration_tts | Source-of-truth = `integration/commands.py` (now frozen integration_tts, English); not harden2 Hebrew |
| nuclear-code-review.md | Code-quality review of integration_harden that drove the two 09-03 reports | superseded | 2026-09-03 | ARCHIVE(docs/stale) | Source review; executed then tree removed. Group: nuclear-code-review execution (keeper of that set) |

## Consolidation groups

1. **integration_harden code-review + execution set** (all target the now-removed tree):
   `nuclear-code-review.md` (source review) -> `2026-09-03-deadcode-purge-report.md` +
   `2026-09-03-structure-pass-report.md` (its two execution reports). Keeper if any kept:
   `nuclear-code-review.md`. Archive the trio together.

2. **Manager-handoff series** (superseded chain about integration_harden):
   `2026-09-02-manager-handoff.md` -> `2026-09-03-manager-handoff.md`. Keeper of the two:
   `2026-09-03` (supersedes on state). Both eventually superseded by 09-05/07/08 (outside this set).

3. **Session-handoff series** (live-test agent dumps, superseded):
   `2026-09-05-session-handoff.md` -> `2026-09-07-session-handoff.md`. No keeper in this set;
   the live successor is `2026-09-08-session-handoff.md` (not in set). Archive both.

4. **One-off delegated-agent session briefs** (prompt-artifacts, all consumed):
   `2026-09-02-asr-session-brief.md`, `2026-09-02-sam3-session-brief.md`,
   `2026-09-04-sam31-session-brief.md`. No keeper; archive together.

5. **Go-live wiring pair**: `2026-09-03-golive-wiring-handoff.md` (brief/prompt-artifact) +
   `2026-09-03-golive-wiring-report.md` (result). Keeper: the report. Both stale (tree removed).

6. **VRAM campaign pair**: `2026-09-07-vram-perception-campaign-plan.md` (plan) +
   `2026-09-07-vram-perception-campaign-results.md` (results). Keeper: results — but extract its
   owner rulings (Hy-MT2 Q4, SAM3 prerequisite) to NOTES/bench first, since they still bind harden2.

7. **FMU C++ docs** (parked llm_to_action tree, other dev): `fmu-cleanup-tasklist.md` +
   `fmu-node-split-map.md`. Not superseded, just misfiled in docs/active; move both beside their tree.

8. **Objective/compass**: `final-objective-context.md` + `mvd-voice-command-table.md` both describe
   the pre-harden2 MVD (integration/ -> integration_tts). Decide: refresh the compass to harden2, or
   archive; move the command table beside the frozen demo it documents.


### docs/active/ - untracked (2026-09-04 to 09-10)

# docs/active triage — untracked, 2026-09-04 to 2026-09-10 (Batch B)

Reviewed 2026-09-13. READ-ONLY. Dispositions are suggestions for the owner, not decisions.
Context: LIVE = integration_harden2. integration_harden = DEAD intermediate (per track2 draft, NOT a fallback).
projects/integration = frozen fallback. llm_to_action = parked C++ lane (other dev). Judge meeting cancelled.

| File | Purpose (<=15 words, what it is FOR) | Status | Last-relevant | Suggested disposition | Overlaps/notes |
|---|---|---|---|---|---|
| 2026-09-04-live-desk-test-brief.md | Session brief: boot integration_harden on desk, mock control, ASR quantize, desk scripts, test plan | stale | 2026-09-04 | ARCHIVE(docs/stale) | Targets DEAD harden tree; tasks done/superseded by harden2. Instruction brief for a past session |
| 2026-09-05-fmu-control-loop-smell-catalog.md | Catalog of code smells in llm_to_action fmu_node.hpp control loop (test hooks, depth hardcodes) | current (parked lane) | 2026-09-05 | MOVE->docs/ (llm_to_action) or CONSOLIDATE->llm_to_action lane | Factual code analysis, still valid; cited by demo-handoff sec8. llm_to_action parked |
| 2026-09-05-llm-to-action-presentable-brief.md | Manager BRIEF telling a subagent to make llm_to_action presentable for judges | stale (prompt/brief) | 2026-09-05 | ARCHIVE(docs/stale) | Judges cancelled; the instruction, not the result. Pairs with 09-05 report |
| 2026-09-05-llm-to-action-report.md | Report: llm_to_action demo-polish results + addenda (4B swap, auto-land guard, SITL sweeps) | superseded (detailed record) | 2026-09-10 | CONSOLIDATE->llm_to_action lane (keep as detail) | Detailed measured record behind the 09-10 demo-handoff summary |
| 2026-09-06-architecture-diagrams.md | Judge-review architecture diagrams (mermaid+prose) across integration/harden/harden2/llm_to_action | superseded | 2026-09-08 | ARCHIVE(docs/stale) | Covers DEAD harden tree; predates 09-10 diagram redo + harden2-architecture; judges cancelled |
| 2026-09-06-llm-to-action-and-depth-handoff.md | Session handoff: llm_to_action demo polish + full monocular-depth benchmark study | superseded | 2026-09-10 | CONSOLIDATE->2026-09-10-llm-to-action-demo-handoff | Superseded by the 09-10 handoff; depth study still cited from there |
| 2026-09-08-harden2-architecture.md | harden2 architecture: mermaid diagrams, measured numbers, env switches, boot command | current | 2026-09-08 | MOVE->docs/specs (or fold into docs/ARCHITECTURE.md) | LIVE-system reference. Some numbers stale (415/466 vs current 410/487); diagram sources superseded by 09-10 finals |
| 2026-09-08-session-handoff.md | Session handoff: live tests, nine guard/parser fixes, whole-system test, Gemma 4 probe | superseded | 2026-09-08 | ARCHIVE(docs/stale) | Superseded by project-state (09-09) + guard-workplan (09-10); resume pointer moved on |
| 2026-09-09-dji-apiserver-architecture.md | Reference: phone recon-swarm Android REST/WS API (ports, routes, MSDK calls) from Kotlin source | current | 2026-09-09 | MOVE->docs/specs | Durable wire-protocol spec harden2 talks to; overlaps API section of harden2-architecture |
| 2026-09-09-project-state-and-reorientation.md | Project state, challenge-form scorecard, two-track replan, resume pointers | current | 2026-09-11 | KEEP-IN-PLACE (active hub) | Orientation hub; links track1/track2/repo-cleanup/guard-workplan. sec8 resume pointer dated 09-11 |
| 2026-09-09-repo-cleanup-draft.md | DRAFT proposal: repo cleanup/restructure, commit order, target shape, branch model | current (draft) | 2026-09-10 | KEEP-IN-PLACE | Directly feeds THIS restructure; = track2 step 4. Flagged DRAFT |
| 2026-09-10-detailed-diagram-redo-prompt.md | One-off subagent PROMPT: redo detailed harden2 diagram with rejection feedback | prompt-artifact | 2026-09-10 | DELETE (or ARCHIVE) | Diagram-prompt series; output lives in docs/active/assets/diagrams-final |
| 2026-09-10-detailed-diagram-subagent-prompt.md | One-off subagent PROMPT: produce detailed harden2 diagram (TEST output dir) | prompt-artifact | 2026-09-10 | DELETE (or ARCHIVE) | Diagram-prompt series; test-run instructions |
| 2026-09-10-detailed-diagram-v2-prompt.md | One-off subagent PROMPT: re-layout detailed diagram v2 for readability | prompt-artifact | 2026-09-10 | DELETE (or ARCHIVE) | Diagram-prompt series |
| 2026-09-10-guard-and-config-workplan.md | Living workplan: negation guard + config-merge, status log (mostly DONE) + assurance-math appendix | current | 2026-09-11 | KEEP-IN-PLACE (active) | Memory RESUME points here; = track2 step 2. Guard shipped, config wired offline |
| 2026-09-10-harden2-run-arguments.md | Reference: every harden2 run env var/argument, read from code, with defaults | current | 2026-09-10 | MOVE->docs/runbooks | Overlaps harden2-architecture "Switches"; notes SCENE_TTS is a no-op (use MVD_TTS=0) |
| 2026-09-10-llm-to-action-demo-handoff.md | Current handoff for llm_to_action VLM demo; carries PARKED status (2026-09-12) | current (parked lane) | 2026-09-12 | MOVE->docs/ (llm_to_action) / KEEP | KEEPER of the llm_to_action lane; supersedes 09-06 depth handoff; subagent-bootstrap points here |
| 2026-09-10-simplified-diagram-subagent-prompt.md | One-off subagent PROMPT: simplified harden2 slide diagram | prompt-artifact | 2026-09-10 | DELETE (or ARCHIVE) | Diagram-prompt series |
| 2026-09-10-subagent-bootstrap-note.md | One-off first-turn note pointing the next llm_to_action subagent at the demo-handoff | prompt-artifact | 2026-09-10 | DELETE (or ARCHIVE) | Subsumed by the demo-handoff header; llm_to_action parked |
| 2026-09-10-track1-tracker-decisions.md | Track 1 tracker: owner rulings + verified facts (OpenProject/VPN/VPS/SaaS comparisons) | current (tracker lane) | 2026-09-11 | MOVE->docs/ (tracker lane) / KEEP | Companion to track1-handoff; separate lane, not drone code |
| 2026-09-10-track1-tracker-handoff.md | Track 1 handoff/brief: self-host a project tracker, deliverables, seed structure | current (tracker lane) | 2026-09-10 | MOVE->docs/ (tracker lane) / KEEP | Separate lane; overlaps track1-decisions + project-state sec7 |
| 2026-09-10-track2-execution-draft.md | Track 2 execution DRAFT (rev5): the voice-drone system plan, steps 1-7 | current (draft) | 2026-09-10 | KEEP-IN-PLACE | Active drone-system plan; overlaps project-state sec7/sec8, repo-cleanup (step4), guard-workplan (step2) |

## Consolidation groups

### 1. Diagram prompt-artifacts (one-off subagent prompts) — DELETE the prompts
- 2026-09-10-detailed-diagram-redo-prompt.md
- 2026-09-10-detailed-diagram-subagent-prompt.md
- 2026-09-10-detailed-diagram-v2-prompt.md
- 2026-09-10-simplified-diagram-subagent-prompt.md
Throwaway instructions to diagram-drawing subagents. No keeper among them; the real output is the rendered
SVG/PNG/DOT under docs/active/assets/diagrams-final (outside this batch). 2026-09-06-architecture-diagrams.md
is the superseded in-doc diagram set for the same content — archive it.

### 2. llm_to_action lane (parked) — keeper is the 2026-09-10 demo-handoff
- KEEPER: 2026-09-10-llm-to-action-demo-handoff.md (current, carries the PARKED-2026-09-12 ruling).
- Keep as detailed backup: 2026-09-05-llm-to-action-report.md (measured results), 2026-09-05-fmu-control-loop-smell-catalog.md (code analysis).
- Superseded/archive-or-delete: 2026-09-05-llm-to-action-presentable-brief.md (brief), 2026-09-06-llm-to-action-and-depth-handoff.md (older handoff), 2026-09-10-subagent-bootstrap-note.md (redundant bootstrap).
All belong to a parked lane owned by another dev; move the survivors out of docs/active into an llm_to_action doc area.

### 3. Track/reorientation planning cluster — hub + active plans stay, tracker lane splits off
- HUB / KEEP: 2026-09-09-project-state-and-reorientation.md (scorecard + two-track replan + resume pointers).
- Active drone-system plan (KEEP-IN-PLACE): 2026-09-10-track2-execution-draft.md, 2026-09-09-repo-cleanup-draft.md (draft), 2026-09-10-guard-and-config-workplan.md.
- Separate tracker lane (move to own doc area): 2026-09-10-track1-tracker-handoff.md + 2026-09-10-track1-tracker-decisions.md — self-hosted project tracker, not drone code.

### 4. Superseded session handoffs — archive
- 2026-09-04-live-desk-test-brief.md (targets DEAD harden tree), 2026-09-08-session-handoff.md.
Both superseded by project-state (09-09) and the guard-workplan resume pointer.

### 5. Live-system architecture references — move to docs/specs
- 2026-09-08-harden2-architecture.md (LIVE system; refresh stale bench numbers) and
  2026-09-09-dji-apiserver-architecture.md (phone API spec). Durable references that overlap each other's
  API section; plus the run-arguments reference belongs in docs/runbooks.


### docs/active/ - untracked (2026-09-11/12) + assets + docs/13-09-2026

# Doc triage C — docs/active (late), assets, docs/13-09-2026

Scope: 27 files. Read-only pass, 2026-09-13. Dispositions are SUGGESTIONS for the owner, not decisions.

| File | Purpose (<=15 words) | Status | Last-relevant date | Suggested disposition | Overlaps/notes |
|---|---|---|---|---|---|
| docs/active/2026-09-11-harden2-deadcode-purge.md | Record of the 4-model-stack purge in harden2; YOLO26 kept, rest deleted (DONE) | superseded | 2026-09-11 | ARCHIVE(docs/stale) | Folded into commit-manifest + restructure-progress; work DONE |
| docs/active/2026-09-12-ab-baseline-prompt.md | Task prompt: baseline (no-skill) arm of the diagram-authoring A/B | prompt-artifact | 2026-09-12 | CONSOLIDATE->assets/skill-ab-test/ | Pair with ab-withskill-prompt; belongs beside skill-ab-test/NOTES |
| docs/active/2026-09-12-ab-withskill-prompt.md | Task prompt: with-skill arm of the diagram-authoring A/B | prompt-artifact | 2026-09-12 | CONSOLIDATE->assets/skill-ab-test/ | Pair with ab-baseline-prompt |
| docs/active/2026-09-12-commit-manifest.md | Full change inventory (buckets A/B/C) for the deferred harden2 commit | current | 2026-09-12 | KEEP-IN-PLACE | Live commit reference (commit deferred to freeze); overlaps order-to-commit + session-handoff |
| docs/active/2026-09-12-full-trace-and-replayer-workplan.md | Design + status of trace.jsonl + per-pass capture + HTML replayer (built) | superseded | 2026-09-12 | MOVE->docs/specs | Work DONE; still the trace/session-layout format spec. Overlaps session-handoff |
| docs/active/2026-09-12-live-test-handoff.md | Tactical live-test handoff + compass + owner-reordered order-of-operations | current | 2026-09-12 | KEEP-IN-PLACE | Overlaps session-handoff + order-to-commit; ordering re-superseded by repo-restructure-plan |
| docs/active/2026-09-12-order-to-commit.md | Phased sequence to the harden2 commit (test->clean->retest->commit) | superseded | 2026-09-12 | CONSOLIDATE->docs/13-09-2026/repo-restructure-plan.md | restructure-plan explicitly reorders this (cleanup FIRST) |
| docs/active/2026-09-12-session-handoff.md | Big harden2 session handoff: guard, config merge, purge, trace, UI | superseded | 2026-09-12 | ARCHIVE(docs/stale) | Superseded as resume by restructure-progress + c2-handoff; fullest harden2 narrative — DECIDE |
| docs/active/2026-09-12-ui-rewrite-IN-PROGRESS.md | Resume doc + code snippets to finish the opencv live-pane rewrite | current | 2026-09-12 | KEEP-IN-PLACE | Mid-flight per memory; contains unapplied _draw_pane patch |
| docs/active/challenge-form.md | Canonical scored requirement text (Hebrew MOD form); all status docs map to it | current | reference | MOVE->docs/specs | Reference; slide-scope/-numbers/-notes cite these section numbers |
| docs/active/assets/diagrams-new/slide-scope.md | Scope slide: form lines split delivered/WIP/deferred (Hebrew) | asset | 2026-09-12 | CONSOLIDATE->slide assets | Overlaps slide-scope-notes + slide-numbers; sits in a rendered-output dir |
| docs/active/assets/skill-ab-test/NOTES.md | Methodology + invalidated pilot log for the diagram-skill A/B benchmark | current | 2026-09-13 | KEEP-IN-PLACE | Harness reference; pilot INVALIDATED (Fable, contaminated); ties the two ab-prompts |
| docs/active/assets/slide-method.md | "How we chose" slide: per-stage candidates/yardstick/result/pick | asset | 2026-09-12 | CONSOLIDATE->slide assets | Condensed twin of slides-research |
| docs/active/assets/slide-numbers.md | Slide: numbers scored against each form line (met/partly/not) | asset | 2026-09-12 | CONSOLIDATE->slide assets | Overlaps slide-scope + slide-scope-notes |
| docs/active/assets/slide-scope-notes.md | Speaker notes, one per form line (delivered/WIP/deferred) | asset | 2026-09-12 | CONSOLIDATE->slide assets | Speaker-note twin of slide-scope |
| docs/active/assets/slides-research.md | Master research deck: full measurement tables (ASR/translate/vision/system) | asset | 2026-09-12 | CONSOLIDATE->slide assets (keeper) | Superset of slide-method; richest slide source |
| docs/active/assets/diagrams-old/dji-apiserver-detailed.drawio | OLD drawio source: DJI API-server data path, detailed | asset | superseded | ARCHIVE(docs/stale) | drawio source; superseded by diagrams-new/diagrams-final (skill-rendered) |
| docs/active/assets/diagrams-old/dji-apiserver-simplified.drawio | OLD drawio source: DJI API-server, simplified | asset | superseded | ARCHIVE(docs/stale) | Superseded by diagrams-new dji-apiserver-simplified-rendered |
| docs/active/assets/diagrams-old/harden2-detailed.drawio | OLD drawio source: harden2 full architecture | asset | superseded | ARCHIVE(docs/stale) | Superseded by diagrams-new/diagrams-final harden2-detailed |
| docs/active/assets/diagrams-old/harden2-language.drawio | OLD drawio source: harden2 language/ASR sub-flow | asset | superseded | ARCHIVE(docs/stale) | Sub-diagram; folded into new detailed set |
| docs/active/assets/diagrams-old/harden2-perception.drawio | OLD drawio source: harden2 perception (SAM3) sub-flow | asset | superseded | ARCHIVE(docs/stale) | Sub-diagram; folded into new detailed set |
| docs/active/assets/diagrams-old/harden2-simplified.drawio | OLD drawio source: harden2 simplified overview | asset | superseded | ARCHIVE(docs/stale) | Superseded by diagrams-new harden2-simplified-clean/hub |
| docs/active/assets/harden2-simplified-demoday.drawio | Stray drawio: harden2-vs-demo-day comparison (actor "Pilot") | asset | superseded | MOVE->diagrams-old (then ARCHIVE) | Loose at assets root; same old drawio family |
| docs/13-09-2026/2026-09-13-groundstation-c2-handoff.md | Handoff of the diagram/presentation agent session; skill + A/B + slam | current | 2026-09-13 | KEEP-IN-PLACE | This restructure folder; notes assets/ is gitignored |
| docs/13-09-2026/repo-restructure-plan.md | THIS restructure source-of-truth: target tree, decisions, dataset tooling | current | 2026-09-13 | DECIDE | Session working doc; supersedes order-to-commit ordering |
| docs/13-09-2026/restructure-progress.md | THIS restructure progress: done/deferred + ordered bulk-session checklist | current | 2026-09-13 | DECIDE | Session working doc; companion to repo-restructure-plan |
| docs/13-09-2026/slam-removal-prompt-for-llm_to_action.md | Coordination message asking llm_to_action owner to drop the slam dependency | prompt-artifact | 2026-09-13 | KEEP-IN-PLACE | Pending owner reply; ARCHIVE once slam is cleared/archived |

## Consolidation groups

1. Diagram sources — OLD vs NEW (keeper = the new skill-rendered set).
   - Superseded: all six `diagrams-old/*.drawio` + the stray root `harden2-simplified-demoday.drawio`.
   - Keeper: `diagrams-new/` (skill-rendered SVG+PNG+.dot) plus delivered `diagrams-final/` /
     `diagrams-detailed-v2/` named in the c2-handoff.
   - Suggestion: ARCHIVE the drawio sources; they are hand-authored originals replaced by graphviz/.dot.
   - Caveat: `assets/` is gitignored (per c2-handoff) — none committed; separate owner call on `git add -f`.

2. Presentation slide assets (keeper = slides-research.md).
   - Members: `slides-research.md` (master tables), `slide-method.md` (condensed decisions),
     `slide-numbers.md`, `slide-scope-notes.md`, `diagrams-new/slide-scope.md`; `challenge-form.md` = shared ref.
   - Overlap: scope/numbers/notes restate the same form-line mapping at different verbosity.
   - Suggestion: gather the six slide .md under one `docs/assets/slides/`; `slides-research.md` is the
     fullest source, the rest are derived cuts. Keep `challenge-form.md` as the canonical spec (MOVE->docs/specs).

3. Skill A/B test artifacts (keeper = skill-ab-test/NOTES.md).
   - Members: `2026-09-12-ab-baseline-prompt.md`, `2026-09-12-ab-withskill-prompt.md` (prompt pair),
     `assets/skill-ab-test/NOTES.md` (methodology + invalidated pilot), plus run_ab.sh + run.json in skill-ab-test/.
   - Suggestion: move both prompt .md into `assets/skill-ab-test/` so the harness is self-contained.
   - Note: pilot INVALIDATED (ran on Fable, skill leaked into baseline) — do not cite its numbers.

### Secondary group — harden2 commit/handoff chain (session-state docs, overlapping)
`commit-manifest.md`, `order-to-commit.md`, `live-test-handoff.md`, `session-handoff.md`,
`full-trace-and-replayer-workplan.md`, `deadcode-purge.md`. The 2026-09-12 harden2 session record.
The 2026-09-13 `restructure-progress.md` + `repo-restructure-plan.md` + `c2-handoff.md` are the newer
source-of-truth and re-order/absorb much of them. `commit-manifest` stays live (commit deferred to freeze);
`order-to-commit` and `session-handoff` are the clearest supersession candidates.


### docs/runbooks + docs/specs + docs/stale

# Doc triage E — runbooks / specs / stale

Reviewed 2026-09-13 for the pre-freeze restructure. LIVE system = `projects/integration_harden2`;
`integration_tts` = frozen fallback; `llm_to_action` = parked C++ tree. Drone path = DJI aircraft via
on-phone API server (websocket + REST). Purpose stated from content, not title.

Key cross-cutting facts:
- The old `projects/integration` MVD was RETIRED in the 2026-09-13 restructure, so every runbook that
  runs `projects/integration/run_mvd.sh` or the `integration_notify` fork is superseded for harden2.
- The DJI **WS `/c/ws/sticks` velocity** path belongs to the PARKED C++ `llm_to_action` `DjiBackend`.
  The MVD (harden2) drives via **REST `POST /c/fly` mission actions**. So the DjiBackend/FMU specs are
  parked-track design, not the live path.
- The phone-app build/install docs stay relevant to ANY DJI path (harden2 included).

## Runbooks

| File | Purpose (<=15 words) | Status | Last-relevant | Disposition | Notes |
|---|---|---|---|---|---|
| 2026-08-27-demo-runbook.md | Demo-day run-of-show for the old `integration` MVD + llm_to_action bench segment | superseded | 2026-08-27 | MOVE->docs/stale | Runs retired `projects/integration/run_mvd.sh`; harden2 has its own run.sh. Kill-drill content duplicated in kill-switch-verification.md. |
| 2026-08-27-morning-checklist.md | Pre-demo checklist: notify webcam test, Gazebo pitch shot, latency capture, kill switch | superseded | 2026-08-27 | MOVE->docs/stale | Targets `integration_notify` + `integration` (retired) and SITL-legacy paths. |
| 2026-08-27-run-guide.md | Copy-paste run commands for frozen `integration/` + `integration_notify` fork | superseded | 2026-08-27 | MOVE->docs/stale | Both trees retired/forked away; harden2 run.sh replaces it. recognize.py still-image tool is the only reusable bit. |
| dji-bringup-runbook.md | Bench steps to take DjiBackend from mock to real drone over WiFi + latency table | current | 2026-08-22 | KEEP-IN-PLACE | Parked-track (C++ DjiBackend) but holds REAL measured numbers: telemetry RTT 35.6/46.8 ms, WiFi WS RTT 16.4/23.6 ms @5GHz. Executes spec-dji-endtoend-bringup.md (overlap). |
| dji-phone-build-graphene-runbook.md | Build MSDK v5 ExoSkeletons app from CLI, install on GrapheneOS, WiFi to workstation | current | 2026-08-27 | KEEP-IN-PLACE | Needed for any DJI path. Pinned toolchain + GrapheneOS sandboxed-Play gotcha + tunnel-off. Overlaps exoskeletons handoff. |
| exoskeletons-android-studio-handoff.md | Bring the same MSDK v5 app up in Android Studio; the "no run config" fix | current | 2026-08-22 | CONSOLIDATE->dji-phone-build-graphene-runbook.md | Same app, same toolchain pins; AS-specific vs CLI-specific. Merge into one app-build doc. |
| kill-switch-verification.md | Mandatory A/B/C kill-switch drill before any armed DJI command | current | 2026-08-26 | KEEP-IN-PLACE | Canonical safety drill; cited by CLAUDE.md + demo-runbook. Stale IP flagged in its own header; results table still blank. |

## Specs

| File | Purpose (<=15 words) | Status | Last-relevant | Disposition | Notes |
|---|---|---|---|---|---|
| dji-apiserver-review.md | Code review of ExoSkeletons ApiServer + integration punch-list (video/gimbal/position) | superseded | 2026-08-17 | CONSOLIDATE->spec-dji-websocket-protocol.md | Most fixes landed (video done, silent-verb workaround accepted). Fold surviving open Qs (gimbal, indoor pose) into the protocol spec. |
| dji-video-h264-over-tcp.md | Raw H.264/H.265-over-TCP design + Kotlin VideoTcpStreamer + confirmed HW results | current | 2026-08-22 | KEEP-IN-PLACE | High reference value: CONFIRMED codec H.264, 1920x1080, ~24 fps, e2e p50 ~320 ms. The DJI video path of record. |
| spec-dji-backend.md | Spec for the C++ Linux DjiBackend (CRTP sibling of PX4/Tello) | current (parked) | 2026-08-17 | KEEP-IN-PLACE | Design of record for the parked llm_to_action DjiBackend. Mark parked-track. |
| spec-dji-endtoend-bringup.md | Spec: take DjiBackend mock->real, decode video, measure latency (Tasks A/B/C) | duplicate | 2026-08-22 | CONSOLIDATE->dji-bringup-runbook.md | Same Tasks A/B/C the bringup runbook executes step-by-step. Keep one (runbook has filled numbers). |
| spec-dji-websocket-protocol.md | FROZEN DJI bridge wire contract: endpoints, FlightParam, response shapes | current | 2026-08-26 | KEEP-IN-PLACE | Canonical interface spec. Header notes MVD uses REST /c/fly, WS-sticks is parked-track. |
| spec-fmu-cleanup.md | Task backlog to clean up/decompose fmu_node.hpp (C++ FMU) | superseded (parked) | 2026-08-26 | DECIDE | Task list for the parked FMU tree; some tasks likely landed. Verify done-state, then KEEP-IN-PLACE (parked) or MOVE->docs/stale. |

## Stale (already archived; archive-vs-delete call)

| File | Purpose (<=15 words) | Status | Last-relevant | Disposition | Notes |
|---|---|---|---|---|---|
| 2026-08-20-djibackend-handoff.md | DjiBackend<->app test-now plan + in-depth rundown of both sides | stale | 2026-08-20 | DELETE | Superseded by spec-dji-backend + websocket-protocol; git history covers it. |
| 2026-08-20-phase2-detector-feeltest.md | Qualitative detector feel-test (D-FINE, OmDet-Turbo) to escape AGPL Ultralytics | stale | 2026-08-20 | KEEP-AS-ARCHIVE | Rationale for the OmDet adoption; thin but explains a real CV decision. |
| 2026-08-21-drone-bringup-status-and-next.md | Snapshot: drone flies, app installed, 4 app compile bugs patched | stale | 2026-08-21 | DELETE | Status snapshot; gotchas (m2.zip dep, leakcanary, adb) captured in graphene runbook + memory. |
| 2026-08-23-cleanup-postpoc-grapheneos.md | Throwaway GrapheneOS STT-hack notes, "revert after Thursday" | stale | 2026-08-23 | DELETE | Self-declared disposable scaffolding. Prime delete. |
| 2026-08-25-mvd-integration-handoff.md | "MVD done" handoff for source/integration + fixes log | stale | 2026-08-25 | DELETE | Superseded by later handoffs; integration tree retired. |
| 2026-08-26-manager-brief.md | Top-of-stack manager brief (project framing + state) | stale | 2026-08-26 | DELETE | Superseded framing doc; no durable technical content not held elsewhere. |
| 2026-08-26-s1-interface-jailbreak-guide.md | RoboMaster S1 firmware ladder + jailbreak odds analysis | stale | 2026-08-26 | KEEP-AS-ARCHIVE | Abandoned platform (S1 SDK trap; buy EP instead), but detailed firmware intel if ever revisited. Pair with next. |
| 2026-08-26-s1-jailbreak-runbook.md | RoboMaster S1 exact jailbreak + interface commands | stale | 2026-08-26 | KEEP-AS-ARCHIVE | Companion command sheet to the S1 guide; abandoned platform. Consolidate the pair or delete both. |
| 2026-08-26-session-postmortem-brief-defects.md | Meta postmortem on doc defects that derailed a session | stale | 2026-08-26 | DELETE | Process lesson only; no technical content. |
| 2026-08-26-t1-t2-options-map.md | Options map (measured, mock) for sequencing the 08-27 demo | stale | 2026-08-26 | DELETE | Time-boxed to the 08-27 demo; superseded. |
| 2026-09-01-interview-sprint-handoff.md | Sprint handoff: two-interview race, reoriented goals | stale | 2026-09-01 | DELETE | Superseded by later handoffs (2026-09-03 manager-handoff etc.). |
| 2026-09-01-repo-churn-heatmap.md | Git churn analysis ranking real tools vs one-off slop | stale | 2026-09-01 | DELETE | One-off analysis feeding the restructure; git regenerates it. |
| 2026-09-01-repo-restructure.md | Records the 2026-09-01 monorepo layout decision (projects/, archive/, docs/) | stale | 2026-09-01 | KEEP-AS-ARCHIVE | Prior-restructure rationale; useful context for the restructure now, though layout has moved on (harden2). |
| 2026-09-02-state-and-next.md | Self-declared SUPERSEDED running log, kept for provenance only | superseded | 2026-09-04 | DELETE | Doc itself says content moved to permanent homes; keep nothing. |
| 2026-09-07-campaign-rawlog.md | VRAM + perception campaign results (translator picks, Hy-MT2 vs tgemma) | superseded | 2026-09-07 | DELETE | Consolidated into bench RESULTS.md (commit 61b4834); this is the raw log. |
| LOCKS.md | Parallel-session file-lock registry for FMU hotspots | stale | 2026-09-01 | DELETE | Spent coordination artifact; no reference value. |
| demo-roadmap-2026-08-28.md | Demo roadmap + challenge/scoring anchor | stale | 2026-08-28 | DELETE | Planning doc; challenge criteria duplicated in mission-brief. |
| integration-mvd-2026-08-24.md | 4-tier command-router MVD build checklist (one-day sprint) | stale | 2026-08-24 | DELETE | Superseded by harden2; contains stale real phone IP. |
| mission-brief-2026-08-15.md | Original shared mission brief: challenge, platform-by-elimination, roster | stale | 2026-08-15 | KEEP-AS-ARCHIVE | Origin doc; records why DJI Mini was chosen (Tello/Parrot out) + MOD challenge criteria. |
| project_overview.md | Advisor briefing: Tello-primary off-board stack, "Being A/B" navigation | stale | ~2026-08 | KEEP-AS-ARCHIVE | Pre-DJI era; outdated platform, but the founding architecture framing. Superseded by docs/ARCHITECTURE.md. |
| spec-android-docker-bridge.md | Feasibility spike: Android-in-Docker (redroid) to replace the phone bridge | stale | ~2026-08 | KEEP-AS-ARCHIVE | Rejected approach (physical phone won); reference if the container bridge is ever revisited. |
| system-architecture-slides.md | 12-slide architecture deck (Tello/SITL era, mermaid) | stale | ~2026-08 | DELETE | Outdated (Tello/PX4 focus); superseded by docs/ARCHITECTURE.md. |

## Consolidation groups

- Three 08-27 demo docs (`demo-runbook`, `morning-checklist`, `run-guide`): all old-`integration`/`integration_notify` demo-day material -> archive together; harden2 `run.sh` replaces them.
- App-build pair (`dji-phone-build-graphene-runbook` + `exoskeletons-android-studio-handoff`): same MSDK app, same pinned toolchain -> one app-build runbook (CLI + AS sections).
- DJI bring-up pair (`dji-bringup-runbook` + `spec-dji-endtoend-bringup`): runbook executes the spec's Tasks A/B/C -> keep the runbook (has filled latency numbers), fold in the spec rationale.
- DJI protocol pair (`spec-dji-websocket-protocol` + `dji-apiserver-review`): frozen contract + its closed punch-list -> fold surviving open Qs into the protocol spec.
- S1 jailbreak pair (`s1-interface-jailbreak-guide` + `s1-jailbreak-runbook`): odds/firmware + commands for an abandoned platform -> merge into one S1 archive doc, or delete both.
- Superseded logs (`2026-09-02-state-and-next`, `2026-09-07-campaign-rawlog`): content already moved to permanent homes -> delete.

## Top DELETE candidates (safe now)

`2026-08-23-cleanup-postpoc-grapheneos` (self-declared disposable), `2026-09-02-state-and-next`
(self-declared superseded), `2026-09-07-campaign-rawlog` (moved to RESULTS.md), `LOCKS`,
`2026-09-01-repo-churn-heatmap`, `2026-08-26-session-postmortem-brief-defects`,
`2026-08-26-t1-t2-options-map`, `2026-08-20-djibackend-handoff`, `system-architecture-slides`.


## Component files - per file


### bench/ - per file

# bench/ per-file inventory (2026-09-14)

Live benches: hebrew-command-bench, whole-system, sam3-mask-bench. Retired (archival docs done this session): hebrew_asr, yolo26-depth-bench, depth-sota-bench, model-cpu-or-gpu.

| Path | Content (<=2 sentences) | Verdict |
|---|---|---|
| bench/README.md | Prologue + shared measurement procedure + index of all benchmarks. Current-state top-level doc. | KEEP-IN-PLACE |
| bench/hebrew-command-bench/README.md | Live bench README: Recognizer under test, current scorecard, rulings, files, methodology. Current-state doc for the live bench. | KEEP-IN-PLACE |
| bench/hebrew-command-bench/CASES.md | Full enumeration of every sentence tested (204 commands, 54 verbose, 7 emergency, 128 perception, 20 military). Current reference of test coverage. | KEEP-IN-PLACE |
| bench/hebrew-command-bench/results/RESULTS.md | Authoritative scorecard: Objective/Setup/Results (current scorecard + negation adversarial set + per-milestone evolution table)/Analysis/Conclusions + Superseded. The current-state results doc. | KEEP-IN-PLACE |
| bench/hebrew-command-bench/results/HISTORY.md | Designated rounds archive (rounds 1-6, ablations, superseded scorecards), each marked superseded with dates. The history archive the convention prescribes. | KEEP-IN-PLACE |
| bench/hebrew-command-bench/results/2026-09-01-perception-dump.md | Round-4 perception-command translation dump for owner review. Per-run report; rounds already summarized in HISTORY.md. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-01-round5-dump.md | Round-5 multi-hop translation dump for owner review. Per-run report; folded by HISTORY round 5. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-01-round6-dump.md | Round-6 perception translation dump for owner review. Per-run report; folded by HISTORY round 6. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-01-test-evidence.md | Dated test-evidence report (router unit tests, PhoneEars live loop, Qwen3-VL direct HE/EN, six-pipeline matrix). Per-run evidence snapshot from 2026-09-01. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-02-bench-dump.md | Perception translation dump for owner review. Per-run report superseded by HISTORY 2026-09-02 entries. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-02-slang-dump.md | Military-phraseology translation dump for owner review. Per-run report; military set now tracked in scorecard. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-08-unified-gemma4.md | Per-run scorecard: Gemma4 through harden2 unified call, all sets (415/487) vs Hy-MT2->Qwen. Dated run report; captured by RESULTS.md evolution table. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-10-negation-baseline.md | Per-run scorecard, negation-guard baseline (410/487). Dated run; in RESULTS.md evolution row. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-11-negation-guard-a7.md | Per-run scorecard, negation-guard a7 iteration (410/487). Dated ablation run. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-11-negation-guard-final.md | Per-run scorecard, negation-guard final (410/487). Dated ablation run. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-11-negation-guard.md | Per-run scorecard, negation-guard iteration (410/487). Dated ablation run. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-11-purge-stage1.md | Per-run scorecard, purge stage 1 (410/487). Dated ablation run. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-12-control.md | Per-run scorecard, control run (410/487). Dated ablation run. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-12-skip-apply-he.md | Per-run scorecard, skip-apply-HE variant (404/487, a regression arm). Dated ablation run. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-12-trace-build.md | Per-run scorecard, trace-build run (410/487). Dated ablation run. | CONSOLIDATE-INTO-RESULTS.md |
| bench/hebrew-command-bench/results/2026-09-13-restructure-verify.md | Per-run scorecard verifying the restructure left scores unchanged (410/487). Dated confirmation run matching current RESULTS.md. | CONSOLIDATE-INTO-RESULTS.md |
| bench/sam3-mask-bench/README.md | Live bench README: SAM3.x vs SAM2.1 on mask/latency/VRAM and whether SAM3 text-mode replaces OmDet, with current results and open decisions. Current-state doc. | KEEP-IN-PLACE |
| bench/sam3-mask-bench/RESULTS.md | Authoritative demo-suite results (2026-09-03): SAM3 as concept segmenter, per-test overlays, VRAM, SAM3 vs SAM3.1, core finding. The bench's single results doc. | KEEP-IN-PLACE |
| bench/sam3-mask-bench/INTEGRATION-HANDOFF.md | Self-contained brief for the (now shipped) SAM3-nf4 + VLM-concept integration tasks: decisions in force, measured evidence, verified model-load path. Integration already landed per git log; still the cited measured-evidence reference. | DECIDE |
| bench/sam3-mask-bench/results/2026-09-03-engine-ab.md | Dated engine-level A/B (OmDet+SAM2.1 vs SAM3-nf4) through PerceptionEngine, latency + box IoU totals. Per-run report backing RESULTS.md core finding. | CONSOLIDATE-INTO-RESULTS.md |
| bench/sam3-mask-bench/results/sam3-quantization.md | Full Objective/Setup/Results/Analysis study of SAM3 quant family + torch.compile latency on RTX 5070 (compile beats weight format). Distinct current study on a different axis than RESULTS.md; cited in memory. | KEEP-IN-PLACE |
| bench/sam3-mask-bench/tests/README.md | Current-state README for the SAM3 demo test suite (9 tests, 6 categories, manifest.json), method per test. Describes the live test harness. | KEEP-IN-PLACE |
| bench/whole-system/README.md | Live bench README: offline stand-in for the full Hebrew voice-drone stack, four lanes, decision rule, files. Current-state doc. | KEEP-IN-PLACE |
| bench/whole-system/results/RESULTS.md | Authoritative 2026-09-08 stack-swap + vision result doc (Objective/Setup/Results/Analysis/Conclusions/Superseded); states it consolidates the dated fragment reports. Current-state results doc. | KEEP-IN-PLACE |
| bench/depth-sota-bench/DEPTH-BENCHMARKS.md | Completed depth-model benchmark (2026-09-06) with an explicit "Status (archival, 2026-09-13)" section. Archival standalone record done this session. | HANDLED |
| bench/hebrew_asr/README.md | ASR-round scorecard for the Hebrew voice loop; carries the 2026-09-13 archival note declaring the round complete and this the standalone record. Archival doc done this session. | HANDLED |
| bench/model-cpu-or-gpu/README.md | where-models-run: GPU census, pair-loading, CPU-offload latency; ASR round marked COMPLETED (moved to hebrew_asr), planned lanes historical. Retired-bench standalone record. | HANDLED |
| bench/model-cpu-or-gpu/RECORDING-SPEC.md | Team recording spec + read-aloud script (2026-09-02) to build the ASR eval set. The ASR round it served is complete and retired; leftover planning artifact. | STALE |
| bench/yolo26-depth-bench/README.md | Retired-benchmark standalone archival record: objective, setup, numbers, run counts, verdict; scripts/weights archived at freeze. Archival doc done this session. | HANDLED |
| bench/yolo26-depth-bench/results.md | Raw ONNX-runtime CPU latency table (per-percentile) for yolo26n-depth. Numbers now embedded in the archival README; redundant raw table. | CONSOLIDATE-INTO-RESULTS.md |
| bench/yolo26-depth-bench/results_ladder.md | Raw size-ladder table (GPU/CPU p50 per model size). Numbers folded into the archival README; redundant raw table. | CONSOLIDATE-INTO-RESULTS.md |
| bench/yolo26-depth-bench/results_torch.md | Raw PyTorch CPU/CUDA thread-sweep latency table. Numbers folded into the archival README; redundant raw table. | CONSOLIDATE-INTO-RESULTS.md |


### projects/ - per file

# Docs inventory — projects/ (integration_harden2, integration_tts, llm_to_action)

Read-only per-file inventory for the restructure. Built 2026-09-14. Paths relative to `/root/groundstation`.

| Path | Content (<=2 sentences) | Verdict |
|---|---|---|
| projects/integration_harden2/README.md | The LIVE MVD stack: voice -> 4-tier router -> deterministic verbs or Recognizer/perception, over drone/webcam video; documents layout, data flow, verification, mock/real run, and the HUMAN-only real-flight runbook plus 2026-09-08 runtime switches (SCENE_SEG=sam3, MVD_TRANSLATOR=hymt2) and the M-key operator kill. Header calls it a FORK of integration_harden for the Gemma-4 E4B stack, but the body and all example paths still say `integration_harden/` — stale internal paths. | KEEP-IN-PLACE (fix stale `integration_harden` paths in body) |
| projects/integration_harden2/perception/README.md | The OLD highlight backend: OmDet open-vocab detect + SAM2.1 masks + Qwen3-VL presence gate, models injected, self-test on CPU. Superseded on the live path by perception2 (SCENE_SEG=sam3 is default); kept only as the `SCENE_SEG=omdet` fallback and pending deletion once sam3 is confirmed live. | KEEP-IN-PLACE (deletion pending per perception2 ruling) |
| projects/integration_harden2/perception2/README.md | The SAM3-nf4 twin of perception: one model does open-vocab detect AND masks, self-contained, plus a concept front-end that expands a phrase into synonym nouns for SAM3. Now the live default backend; documents precision/speed table (nf4/bf16/fp8), the collective-target gate open decision, and an OWNER DECISION to flip default + delete perception/ + rename this package after the live test. | KEEP-IN-PLACE (owner decision pending: rename + delete perception/) |
| projects/integration_harden2/recognizer/README.md | The Hebrew Recognizer component: utterance -> mission / planner-English / VLM-English / rejection, stages 0-6, single-home with the Hebrew bench importing it in place. Lists the 2026-09-08 bench-gated guards (answer-mode, number idioms, few-shot echo, clockwise sign) and the sync rule. | KEEP-IN-PLACE |
| projects/integration_harden2/recognizer/PROMPTS.md | Generated dump of the exact recognizer prompts (edit prompts.py, not this): the app's 5-action speech-to-intent prompt reconstructed from SpeechResolving.kt, plus the revised planning scaffold with Signs/Directions, Refusals, and 6 few-shot pairs. Reference artifact, regenerated from code. | KEEP-IN-PLACE (generated — do not hand-edit) |
| projects/integration_tts/README.md | The FROZEN demo-fallback MVD: same 4-tier voice router -> simple verbs or scene_omdet (OmDet+SAM2+Qwen), over drone footage, with the HUMAN-only real-flight runbook and hazards. Header/body call the folder `integration/`, an older naming than the `integration_tts/` path. | KEEP-IN-PLACE (frozen fallback — internal name says `integration/`) |
| projects/llm_to_action/README.md | Top README for the PARKED C++ off-board autonomy stack (VLM plans, C++ FMU flies, browser dashboard): ROS2 node table, one-backend build, SITL demo, dashboard, repo layout, safety. Accurate and current. | KEEP-IN-PLACE (other dev's tree) |
| projects/llm_to_action/docs/2026-09-13-state-and-changes.md | Current state/handoff: parked behind harden2 (2026-09-12), the one open finding (loom guard at fmu_node.hpp:826 fires on the target car because monocular depth fails up close), the changes in the last commit (Qwen3-VL-4B default, approach auto-land only on empty queue, new vlm dashboard demo, serve.py signal handlers), and SLAM removal. | KEEP-IN-PLACE (other dev's tree — current handoff) |
| projects/llm_to_action/source/dashboard/README.md | The "A2 live dashboard": stdlib serve.py bridge (rclpy + ThreadingHTTPServer) + dashboard.html serving annotated camera, depth, HUD, VLM log over MJPEG/SSE. Documents topics, run/port/quality knobs, on-demand image subscription, and the FMU_OBSERVABILITY=1 gate. | KEEP-IN-PLACE (other dev's tree) |
| projects/llm_to_action/test/sitl/README.md | The CONSOLIDATED SITL suite: one run.sh + scenarios.conf + verdicts/ replacing the 20 old per-scenario dirs; documents --list/--free/--verdict/--all and SKIP_HIGH_VRAM. Explicitly states `../sitl-legacy/` is the old tree kept only until this suite survives one full `--all` sweep, then deleted. | KEEP-IN-PLACE (other dev's tree — the successor) |
| projects/llm_to_action/test/sitl/SCENARIOS.md | Single file concatenating every per-scenario README at consolidation (2026-09-01): what each of ~18 scenarios proves (approach, battery, cross, follow, hover, orbit, override, queue-overflow, etc.). Duplicates the sitl-legacy per-scenario READMEs verbatim — this is their consolidated home. | KEEP-IN-PLACE (other dev's tree — replaces the legacy per-dir READMEs) |
| projects/llm_to_action/test/sitl-legacy/README.md | Old SITL harness overview: one folder per feature, each with run.sh/filter.sh/README.md sourcing lib/sim_core.sh, plus the workflow and how to add a feature. Superseded by test/sitl (consolidated suite); marked for deletion after one `--all` sweep. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/TESTING.md | Old follow/hover end-to-end test guide (logtest.sh/digest.sh/watch.sh, dashboard watch, "what good looks like"); references the crowd/ scenario and paths under sitl-legacy. Superseded by the consolidated test/sitl suite. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/approach/README.md | Closed-loop APPROACH toward a synthetic (no-YOLO) detection then land; milestone digest, default_car world. Identical to its SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/approach-impact/README.md | Verifies the APPROACH motion-gate: a synthetic off-nominal "reached" must raise approach_impact interrupt, not approach_ok; auto PASS/FAIL, empty world. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/approach-real/README.md | Same APPROACH servo with REAL ONNX seg+depth vs the car, plus motion-gate and looming-fill backstop; milestone digest, default_car. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/battery-landnow/README.md | Battery land-in-place failsafe: forced 8% mid-flight must land where it is (not RTH); auto PASS/FAIL, empty world. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/battery-rth/README.md | Battery return-to-origin failsafe: forced 18% mid-flight must fly home then land/disarm; auto PASS/FAIL, empty world. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/cross/README.md | Cross pattern (fwd/left/back/right 1m, re-anchored each leg) as an FLU sanity check; milestone digest, default_car. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/dashboard/README.md | Headless FOLLOW demo (moving_person, Gazebo headless, FMU_OBSERVABILITY=1) + dashboard bridge + self-assessing PASS/FAIL verdict, watched in the browser. Duplicated by source/dashboard's demo launcher; legacy path. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/follow/README.md | Gates the FOLLOW yaw-only visual servo (scripted, VLM off): sustained FOLLOW ticks, one stable track id, no release = PASS. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/hover/README.md | Verifies HOVER is a persistent hold that never completes, so the queued back-go and land never run; auto PASS/FAIL. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/interrupt-storm/README.md | Verifies interrupt-storm escalation (escalated=1 + [ESCALATION] block) AND recovery re-plan in rubicon_targets with VLM on; hard PASS/FAIL + soft recovery. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/obstacle-stop/README.md | Verifies the velocity-scaled emergency boundary: a synthetic close obstacle must raise emergency_boundary interrupt, stale snapshots must not; auto PASS/FAIL, empty world. README still titled "boundary test". Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/orbit/README.md | ORBIT the car with real perception: lock center from medianed depth then fly the circle from odometry, camera-track the car, land; milestone digest, plus tuning knobs and a DJI Tello note. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/override/README.md | Interactive manual-override test: Enter engages/releases reversible takeover (WASD/arrows fly), handback re-plans via VLM, battery failsafe still outranks; PASS/FAIL. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/queue-overflow/README.md | Task-queue backpressure: 100 stops injected pre-takeoff must stay bounded (moodycamel cap 60, ~63 usable), drops>0, nothing silently lost; drone intentionally never flies. README titled "flood test". Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/queue-overflow-airborne/README.md | In-flight backpressure: fly the cross, then a 100-action flood mid-air from a producer async must queue behind the live plan (FIFO), bounded, drone unbothered. README titled "flood-airborne test". Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/rotate/README.md | ROTATE granularity regression: 90 deg CW then 200 deg CCW the LONG way (not 160 shortest-path), net swept angle matches; PASS/FAIL. README titled "rotate-land test". Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/search/README.md | Gates the SEARCH advance-and-scan control law (scripted, VLM off) in rubicon_targets, spawned facing away; PASS = SEARCH activated then SEARCH DETECTED, hands to APPROACH. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |
| projects/llm_to_action/test/sitl-legacy/vlm/README.md | Full VLM-driven run (Qwen3-VL plans the verbs, no scenario): needs the VLM model + Vulkan; milestone digest of VLM wake/plan/GO/APPROACH, no PASS/FAIL. Identical to SCENARIOS.md section. | DECIDE (superseded by test/sitl) |

## Notes

- **sitl-legacy is uniform and superseded.** All 18 per-scenario READMEs are byte-for-byte identical to their sections in `test/sitl/SCENARIOS.md`. The consolidated `test/sitl/README.md` states the whole `sitl-legacy/` tree is kept only until the new suite survives one full `--all` sweep, then deleted. Verdict for every sitl-legacy file = DECIDE (owner runs the sweep, then deletes).
- **harden2 header/path drift.** The harden2 top README and the perception/recognizer sub-READMEs still carry `integration_harden` headers and example paths (the fork was copied 2026-09-08). Live system, so KEEP-IN-PLACE, but the paths are stale.
- **perception vs perception2 in harden2.** perception2 (SAM3) is the live default; perception (OmDet+SAM2.1) is the fallback and is explicitly slated for deletion + package rename once sam3 is confirmed on a live test (owner decision pending).


### tools, skills, repo root - per file

# Inventory — tools/, .claude/skills/, repo root (2026-09-14)

| Path | Content (<=2 sentences) | Verdict |
|------|--------------------------|---------|
| `README.md` | Repo overview, layout, quickstart. Lists projects/integration{,_notify,_tts,_harden} but NOT integration_harden2 (the live system), and only dji_mock/devenv/preflight under tools/ — predates the restructure. | STALE (rewrite for harden2 + current tools) |
| `NOTE.md` | Loose pre-demo brainstorm: build assumptions, ASR presentation topics, Thursday scrum scene ideas (rubicon_world). Not the architectural log; that is docs/NOTES.md. | DELETE (stray scratch; real log is docs/NOTES.md) |
| `tools/dji_mock/README.md` | DJI bring-up/test toolkit: health check, telemetry/WS/video latency probes, offline mocks, ROS rx_node view, app build. Current, safety-aware (no-motors, derive phone IP from gateway). | KEEP-IN-PLACE |
| `tools/session-replayer/README.md` | Browser replayer for integration_harden2 session-* folders; reads trace.jsonl + per-pass frames/JSON, draws boxes client-side. Current, matches live system. | KEEP-IN-PLACE |
| `tools/desk-test/checklist-2026-09-09.md` | Dated judges-day (10:00) run checklist: team doc, deck slides/diagrams, testing tick-list. One-day artifact; judges were cancelled. | STALE (dated) |
| `tools/desk-test/live-run-2026-09-09.md` | Dated judges-morning run sheet: webcam+mock (A), phone+drone (B), real-control video (C) with kill drill. Tied to the cancelled 2026-09-09 event. | STALE (dated) |
| `tools/desk-test/live-test-50.md` | 50 Hebrew live-mic utterances (34 cmd / 16 perception) with expected fly_by/spin outputs. e2e test dataset. | MERGE->datasets/e2e |
| `tools/desk-test/live-test-75.md` | 75 all-new Hebrew utterances in 3 sets of 25, each tagged with probe + target dataset set. e2e test dataset. | MERGE->datasets/e2e |
| `tools/desk-test/live-test-e2e-50.md` | 50 cases sampled uniformly from the 488-case dataset (quota per set), each with case id + file tag. e2e test dataset. | MERGE->datasets/e2e |
| `tools/desk-test/live-test-subset.md` | 24 cases drawn from hebrew-command-bench, grouped A–H (moves/verbs/turns/chains/verbose/rejects/emergency/perception). e2e test dataset. | MERGE->datasets/e2e |
| `tools/diagram-authoring/README.md` | README for the standalone diagram-authoring skill (graphviz+cairo pipeline): install, quickstart, tool table, benchmark. This is the skill's dev home (README + benchmark + examples + LICENSE). | KEEP-IN-PLACE |
| `tools/diagram-authoring/benchmark/README.md` | A/B method: same model/repo/prompt, skill physically removed for baseline arm; ~2.2M tokens/arm. Reference harness, env-specific paths. | KEEP-IN-PLACE |
| `tools/diagram-authoring/benchmark/ab-baseline-prompt.md` | Baseline-arm crawl prompt: two C++ diagrams of Micro-XRCE-DDS-Agent, no skill, rtk-only, scoped reads, fixed output paths. | KEEP-IN-PLACE (benchmark input) |
| `tools/diagram-authoring/benchmark/ab-withskill-prompt.md` | With-skill-arm prompt: identical task but first invokes the diagram-authoring skill; same efficiency/output rules. | KEEP-IN-PLACE (benchmark input) |
| `tools/diagram-authoring/skill/SKILL.md` | Full diagram-authoring method (ground-truth-first, dot->gvcairo->check->clean_svg, box rules). Byte-identical to .claude/skills/diagram-authoring/SKILL.md — this is the source home. | KEEP-IN-PLACE (source home; DUP of deployed copy) |
| `.claude/skills/architecture-survey/SKILL.md` | Deletion-test survey skill: find shallow modules worth deepening, findings-only report to docs/research/, never edits. disable-model-invocation. Current. | KEEP-IN-PLACE |
| `.claude/skills/diagram-authoring/SKILL.md` | Deployed copy of the diagram-authoring skill, identical to tools/diagram-authoring/skill/SKILL.md. Two homes for one component. | DECIDE (dup; pick canonical home vs tools/ copy) |
| `.claude/skills/recognizer-bench/SKILL.md` | Recognizer + Hebrew-bench workflow skill (harden2 recognizer, unified_bench, dev loop, gotchas). Retired this restructure. | DELETE |
| `.claude/skills/thermo-nuclear-code-quality-review/SKILL.md` | Strict maintainability/abstraction review skill (1k-line smell, spaghetti, code-judo). Vendored 2026-09-01, disable-model-invocation. Current. | KEEP-IN-PLACE |
