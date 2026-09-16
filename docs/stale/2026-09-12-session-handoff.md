# Session Handoff — 2026-09-12 (harden2: guard, config merge, dead-code purge, full trace + replayer, live-pane redesign)

## 0. Read this first (entry-point chain; details below)
MEMORY.md (loads every session) -> memory/current-work-and-entry-point.md -> THIS handoff is the resume.
Order to the commit: docs/active/2026-09-12-order-to-commit.md. Full change inventory + what to commit:
docs/active/2026-09-12-commit-manifest.md. The 2026-09-09 reorientation §8 index is now SUPERSEDED by this.

## 1. TL;DR
harden2 (projects/integration_harden2) is THE system: one Gemma-4-E4B does routing+planning+Hebrew answers,
SAM3-nf4 is the eyes, whisper ivrit ASR. Judges CANCELLED; pitch/team-summary CLOSED. This session (from the
A5 bench onward) completed, all OFFLINE-verified (62 tests, bench 410/487, golden-master), all UNCOMMITTED:
- Negation guard A1-A7: subtract-rule negation_only, 24 refuse + 25 pass adversarial set, defense-in-depth.
- Config MERGE + WIRED: config_constants.py + config_defaults.py + config.py adapter; mvd knobs
  source from them; golden-master proves it. MVD_HOME deleted (launchers hardcode integration_harden2).
- Dead-code PURGE (owner: keep YOLO26 background, delete the rest): OmDet, SAM2.1, DictaLM/Hy-MT2 translators,
  Qwen3-VL planner removed from harden2. pipeline.py = direct path only.
- FULL trace + capture + HTML replayer: trace.jsonl (single per-utterance log; retired utterances.jsonl),
  causal audio-clip linking, per-request/per-pass perception capture (raw frames + json, model-agnostic),
  tools/session-replayer/replayer.html.
- LIVE-PANE redesign IN PROGRESS: render_chat rebuilt toward the approved mockup (tools/ui-mockups/live-pane.html);
  tag column, mockup palette, DejaVuSans (proportional sans w/ Hebrew), dump-path header. Tuning over PNGs.
NOTHING is committed and nothing has run LIVE on the webcam/drone with all these changes.

## 2. Owner rulings this session (verbatim intent)
- NO COMMIT until field testing passes (imminent). Commit is LAST, not first (flips reorientation §7).
- Keep the YOLO26 background detector (may recycle); delete the rest of the old 4-model stack, ONLY in harden2.
- MVD_HOME is useless -> DELETE it (was on the 2026-09-10 delete list; launchers now hardcode integration_harden2).
- Retire utterances.jsonl -> trace.jsonl is the single e2e log; reader tools point at it.
- asr_clips/ flat (not asr/clips) since the folder holds only clips now.
- Save RAW frames + metadata per pass, model-agnostic (NO burned-in boxes) -> reusable for A/B across models
  + fine-tuning; the replayer draws boxes.
- Link audio clip <-> utterance CAUSALLY (no C++ change, no timestamp math): the C++ node writes+closes the clip
  BEFORE it publishes the transcript, so Python claims the newest unclaimed asr_clips/*.wav on transcript
  arrival and renames it utt_<seq>.wav.
- Capture EACH SAM3/Gemma pass (a live highlight re-runs ~1/s -> many passes) so tracking under a dynamic
  scene is measurable; group per REQUEST: perception/<seq>-<kind>-<target>/.
- The opencv pane must LOOK like the mockup: fonts, spacing, indentation, colours, everything. Camera size = whatever.
- Every rejection must show WHY in the window; SAM3 must show its confidence.
- UI iteration workflow: I render render_chat to a PNG offline and SendUserFile it (Read is disabled -> I cannot
  view images myself). The owner compares to the mockup and I re-render. This avoids a webcam run per tweak.

## 3. What changed in code (all UNCOMMITTED; the owner runs git)
Full file-by-file inventory is in docs/active/2026-09-12-commit-manifest.md (Bucket A). Headlines:
- recognizer/recognizer.py: negation_only (subtract rule) + continue/slow/speed verbs; `he = he or ""` None-guard.
- recognizer/pipeline.py: DIRECT path only; removed handle_translated/_translate/_plan/plan_fn/dicta_port; added
  observe() callback (he2/flags/kind/target/timings -> the trace, off the bench path).
- recognizer/llama.py: MODELS = gemma4 only; QWEN3VL_EXTRA gone.
- config_constants.py / config_defaults.py: complete superset + video_input()/wire_target()/resolvers/colours.
- config.py: thin adapter sourcing from the two files (every env override preserved).
- mvd.py: perception capture (SessionLog trace.jsonl + causal clip-claim + begin_request/save_pass/
  end_request/det_payload; detect() pass hook); OmDet/SAM2 removed; config knobs from the two files; reject-reason
  + SAM3-score lines; render_chat REBUILT to the mockup (tag column, palette, DejaVuSans, dump header, RTL wrap).
- perception/detectors.py: Eyes = YOLO26 background only.
- perception2/__init__.py: live exports only.
- run_mvd.sh / tools/desk-test/{up,preflight}.sh: translator/xlate/qwen/omdet/MVD_HOME stripped; asr_clips; TZ set;
  F5 push-to-talk banner (was a stale "H").
- tools/desk-test/{show_session,score_session,score_live}.py + tools/bench/{whole-system/run_list,hebrew_asr/gemma_asr}.py:
  read trace.jsonl + asr_clips (fallbacks kept for old sessions). bench.py: qwen3vl PLANNERS removed.
- NEW: tools/session-replayer/replayer.html (+ README, + sample-session), tools/ui-mockups/{live-pane.html, live-pane-render.png}.

## 4. Verification (offline; temp 0, one model on the GPU)
- Offline tests: 62 pass (projects/integration_harden2/test/). Bench: 410/487, 0 changed vs baseline
  (tags negation-guard / -a7 / -final / purge-stage1 / trace-build; results/ dir). golden-master 2/2.
- Replayer JS: `nodejs --check` clean. Capture<->replayer contract: node replica read a real generated session OK.
- NOTHING run live with these changes (no webcam boot, no drone). That is Phase 1 of the order doc.

## 5. NOT done / open (honest)
- LIVE WEBCAM RUN never done with these changes: `VIDEO=webcam MVD_TTS=0 bash /root/groundstation/tools/desk-test/up.sh`
  (mock auto-starts; attach `tmux attach -t mvd`; F5 to talk). This is the Phase-1 gate.
- LIVE-PANE tuning: awaiting owner feedback on the DejaVuSans PNG. Possible: tag width, size, the `.`/`✓` glyphs
  (dropped as FreeMono-risk; DejaVuSans may have them now -> test), row spacing, exact colours.
- PERCEPTION MISS: SAM3 grounded ZERO for "guitars" that were visibly present (0.1 floor). Real grounding issue,
  not UI. Investigate after the pane.
- count median is partly fake: COUNT_GAP (0.3s) < SAM3_PERIOD (1.0s) -> frames 2-3 hit the detect() cache. The
  per-pass capture will show only 1 fresh forward for a count. Flagged; not fixed.
- ASR mis-transcription seen live ("היי עלי לגיטר" garbled) -> reject. ASR quality, separate.
- Owner git rm the 6 orphaned files (2 translator servers + perception2/{detectors,engine,vlm_client,chain_demo}.py);
  commands in docs/active/2026-09-11-harden2-deadcode-purge.md.
- prompts.py dead strings + recognizer.recognize() left for the nuclear review to catalog.
- Nuclear review is USER-INVOKED only: `/thermo-nuclear-code-quality-review` (scope it to projects/integration_harden2,
  "audit the files not the diff"). I cannot launch it. See docs/active/2026-09-11-harden2-deadcode-purge.md end.
- Timings wired but only seen on a synthetic session; a real run fills trace.jsonl timings{}.

## 6. Order to the commit (docs/active/2026-09-12-order-to-commit.md)
Phase 1 webcam -> field test -> fix. Phase 2 nuclear review + apply + cleanup finalize. Phase 3 re-validate
(bench 410/487 + tests + re-test live). Phase 4 owner git rm + commit EVERYTHING (163 paths, see the manifest —
Bucket A = this session, Bucket B = pre-existing pile incl. dead integration_harden/devenv/docs, Bucket C = files
of UNKNOWN origin at 23:47-00:39 to check before committing) + freeze harden2.

## 7. Documents created/updated this session
docs/active/: 2026-09-09-project-state-and-reorientation.md (§8, superseded by this), 2026-09-10-guard-and-config-workplan.md
(A5-A7 + Workstream B), 2026-08-30-cleanup-takeover-audit.md (B1 note), 2026-09-11-harden2-deadcode-purge.md,
2026-09-12-order-to-commit.md, 2026-09-12-commit-manifest.md, 2026-09-12-full-trace-and-replayer-workplan.md,
THIS handoff. docs/NOTES.md: many dated bullets (2026-09-11..12). tools/ui-mockups/live-pane.html (approved mockup).

## 8. Memory files (/root/.claude/projects/-root-groundstation/memory/)
- current-work-and-entry-point.md = the always-loaded anchor (via MEMORY.md); update it to point here.
- judge-material-private.md (judges/competitors/team -> docs/private, gitignored; never name judges).
- phone-ip-is-wifi-gateway.md (IP changes per hotspot; derive from default route).
- retests-on-webcam, no-task-id-jargon, be-critical-not-sycophantic, owner-writes-code-agent-reviews,
  recommendations-are-not-decisions, prefer-bash-over-write-tool, absolute-paths-in-commands, owner-wants-short-reports.

## 9. Temp / scratch files (so nothing is lost)
- Scratchpad: /tmp/claude-0/-root-groundstation/b6dbcb10-0ea0-4938-98fe-05a05fc66e0a/scratchpad/ holds bench
  logs (a5/a7/final/purge/trace-bench.log) and sample-session/ (the synthetic session; COPIED into the repo).
- tools/session-replayer/sample-session/ = a THROWAWAY synthetic demo session (fake gray frames, 0-byte wavs).
  DELETE before committing; it must not ship.
- tools/ui-mockups/live-pane-render.png = the latest rendered pane (re-generated each UI tweak, sent via SendUserFile).
- Bench result JSON/MD in tools/bench/hebrew-command-bench/results/2026-09-1{1,2}-*.

## 10. Standing rules for the next agent (read CLAUDE.md in full)
- Drone safety: NEVER send arm/takeoff/land/stick/motor to a real drone; prepare + hand to the human. Mock only.
- Human owns ALL git (no add/commit/push/rm/branch); suggest commands only. projects/integration/ is FROZEN.
- RTK wrappers for file/search/git ops; Read/Edit/Write via Bash heredoc/sed (auto mode); Read tool is DISABLED
  (cannot view images -> render to PNG + SendUserFile).
- Address every numbered point; decisions into docs immediately; recommendations != decisions; concrete absolute
  paths; short reports; critical pair programmer (lead with disagreement; no unverified numbers).
- Measurement invariants: temp 0, one model on GPU, duration estimate before a GPU run, full tables, re-run the
  bench after touching measured code (recognizer/pipeline) and compare counts. Commit attribution:
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>.

## 11. Resume checklist
1. Read this + order-to-commit + commit-manifest. 2. If the owner has replayer/pane feedback, tune render_chat,
   re-render the PNG (see §9), SendUserFile. 3. Else run the webcam test (§5) — the Phase-1 gate. 4. Fix live
   findings. 5. Only then: nuclear review, cleanup, re-validate, and hand the owner the commit + git rm commands.

## 12. Audit additions (triple-check 2026-09-12) — items the body missed
LATEST UI STATE (after §1 was written): pane font = DejaVuSans (proportional sans, Latin+Hebrew; owner will
supply the browser's exact resolved font via DevTools "Rendered Fonts" and I download/pair it). Fixes landed:
RTL wraps to the VALUE-COLUMN width (was cut off at the right edge); alignment is by PREDOMINANT script
(_is_rtl), not "has any non-ascii"; SYSTEM messages are single-script (PIL bidi mangles mixed Hebrew+English+
quotes+numbers) -> the miss line is English ('no "X" in view -- ...'), the count answer is 'ספרתי N'. UI is
tuned over PNGs: render_chat -> tools/ui-mockups/live-pane-render.png -> SendUserFile (Read tool disabled).

CROSS-REFERENCE POINTERS (exist in the tree; relevant later, mostly post-commit):
- docs/research/asr-noise-robustness.md — Parakeet/English SNR numbers; "ship raw, no denoiser". Remaining:
  a whisper/Hebrew SNR sweep + a low-light SAM3 image benchmark (post-commit, needs the owner's go + datasets).
- docs/active/challenge-form.md — the competition challenge requirements (SNR% numbers come from llm_to_action's
  BUILD_Noisefilter; see the noise doc).
- docs/active/2026-09-10-track1-tracker-handoff.md — self-hosted project manager (OpenProject) on the owner's old
  server, a SEPARATE subagent; PARALLEL, not a commit blocker.
- docs/active/2026-09-09-repo-cleanup-draft.md — the broader repo tidy (folds into Phase-2 cleanup).
- docs/private/ (GITIGNORED, never name judges): 2026-09-09-team-summary-objective.md, competitors-validation.md,
  team-summary-2026-09-09.{md,pdf} — the CLOSED pitch/team-summary objective. See memory judge-material-private.

STALE TOOLING to fix in cleanup: .claude/skills/recognizer-bench/SKILL.md still points at projects/integration_harden
(the DEAD fork) + DictaLM facts; its Hebrew gotchas still apply but the paths are wrong. Retarget to
integration_harden2 or retire it. (The measurement discipline it encodes is still correct.)

OPEN QUESTION still on the table: the owner is finding the browser's resolved font (step 4 above) to supply for an
exact pane match; until then DejaVuSans stands in.
