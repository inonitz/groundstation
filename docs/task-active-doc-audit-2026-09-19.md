# Documentation & consistency audit — 2026-09-19

Method: 4 read-only audit agents (specs, harden2 live docs, task docs, bench/research) + a
repo-wide code-token sweep. Everything below was verified against live code. Status legend:
[FIXED] this session · [CODE->REVIEW] code staleness, deferred to the nuclear code review ·
[OWNER-GIT] needs the human's git · [OWNER-DECISION] needs a ruling · [OK] correct as-is.

## 1. Safety
1. harden2 README hazard note claimed `stop` fires `/c/stop` (motor-kill). Live `stop` = `wire.halt()`
   (POST /c/fly `[{"delay":0}]`), preempts motion, KEEPS control. `manual` = `/c/stop`. [FIXED]

## 2. Live-system docs — described the deleted world as current
2.  harden2 `README.md` — BASIC 4-tier router, DictaLM/Hy-MT2, `config.py`, dead TTS/translate env. [FIXED]
3.  `recognizer/README.md` — 4-tier router, translator stages, ports. [FIXED]
4.  `recognizer/PROMPTS.md` — old 5-action English prompt shown as live. [FIXED: reframed as bench
    precursors + added a Live-prompt section (8-action unified {kind,target_en,mission})]
5.  `perception2/README.md` — omdet as default (live=sam3), dead `MVD_TRANSLATOR` boot line. [FIXED]
6.  `perception/README.md` — not marked legacy. [FIXED]
7.  `spec-harden2-architecture.md` — BASIC tier + "deterministic mission, no model" path. [FIXED]
8.  `spec-fmu-architecture.md` — MVD sections: 4-tier/BASIC, Qwen-VL/OmDet/DictaLM, dead paths. [FIXED:
    superseded marker; C++ FMU body untouched]
9.  bench `README.md` — 5-stage sieve/translator framing, scorecard 410. [FIXED: Gemma routing, 412/487]
10. bench `results/RESULTS.md` — numbers stop at 09-12 (410). [FIXED: 412, 09-17 + 09-19 milestones]

## 3. Broken / dangling links
11. `CLAUDE.md:54,230` -> code-guidelines.md / writing-style.md (merged into guidelines.md). [FIXED]
12. `spec-dji-backend.md` — 5 broken links. [FIXED]
13. `spec-dji-websocket-protocol.md:3`. [FIXED]
14. `spec-dji-apiserver-architecture.md:27-34` asset links. [FIXED]
15. `spec-harden2-architecture.md:99` asset link. [FIXED]
16. harden2 `README.md:86` -> missing `docs/runbooks/kill-switch-verification.md`. [FIXED -> CLAUDE.md]
17. `research-complete-latency-2026-08-22.md` — broken image links. [FIXED]
18. `research-vlm-bt-reading-list.md` — dangling xref. [FIXED]
19. `spec-fmu-architecture.md:368,387` — `docs/active/` links inside the C++ FMU body. [OWNER-DECISION:
    fix now or fold into the FMU cleanup]

## 4. Outdated numbers / historical framing
20. `research-2026-09-18-command-typing-fast-vs-gemma.md` — sieve-deleted note. [FIXED: note added]
21. `research-complete-qwen-hebrew-bench.md`, `research-complete-hebrew-intent-parsing.md` — reversed
    verdict (translate-first). [FIXED: SUPERSEDED banners; history preserved]
22. bench `CASES.md` — stale case count. [FIXED: snapshot banner]

## 5. Code-level staleness (CODE, not docs) -> NUCLEAR CODE REVIEW
23. Dead translator machinery: `recognizer/recognizer.py` translate stage, `recognizer/llama.py`,
    `recognizer/run_hymt2_server.sh`, `recognizer/run_dicta_server.sh` — harden2 skips translation. [CODE->REVIEW]
24. Stale Qwen3-VL comments: `mvd.py:8`, `perception/vlm_client.py:2`, `perception/__init__.py:2`,
    `audio/phone_asr.py:13`, `perception2/concept.py:9`. Default is Gemma-4-E4B. [CODE->REVIEW]
25. Unused `dji_wire` wrappers: scan_ground/gimbal_pitch/track_me/follow_me/go_home_to_user/wave/
    spin_by/fly_by (Gemma sends raw action dicts through fly_mission). [CODE->REVIEW]
26. `config/constants.py:5` docstring lists deleted toggles (MVD_DRONE, qwen3vl). [CODE->REVIEW, minor]

## 6. Config / launcher mismatch
27. `run_llama_server.sh:12` still branches `MVD_PLANNER=gemma4|qwen3vl`, but `config/__init__.py:93`
    hardcodes `PLANNER="gemma4"` (MVD_PLANNER deleted). The qwen3vl branch is orphaned. [OWNER-DECISION:
    remove qwen3vl branch -> gemma4-only?]

## 7. Task docs now DONE — archive candidates
28. Archive (they now contradict the live system): `slam-removal-prompt`, `restructure-plan`,
    `doc-review-worksheet`, `restructure-c2-handoff`, `cleanup-plan`, `live-testing-handoff`,
    `thermo-review-integration_harden2`, `ponytail-review`. (e.g. cleanup-plan still says the config
    package is "NOT STARTED / REJECTED"; live-testing-handoff shows BASIC as current.) [OWNER-GIT]
    KEEP ACTIVE: both `task-scheduled-*`, `runtime-drone-config-constants`, `thermo-review-repo`.

## 8. Notes / corrections
- Live `SCENE_TTS` set is `phone|phonikud|off` (espeak/piper/both were removed). Earlier briefs said otherwise.
- Already clean (no change): docs `README.md`, `ROADMAP.md`, `guidelines.md`, `spec-harden2-run-arguments.md`,
  `spec-dji-video-h264-over-tcp.md`.

## Tally
- Doc/link/number inconsistencies found: 22 -> all FIXED (except #19, an owner call).
- Code-level inconsistencies: 4 -> deferred to the nuclear code review (#23-26).
- Config/launcher mismatch: 1 -> owner ruling (#27).
- Task docs to archive: 8 -> owner git (#28).
