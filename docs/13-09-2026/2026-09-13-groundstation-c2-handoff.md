# Session handoff — groundstation-c2 (2026-09-13)

This session was the diagram/presentation agent. It produced a diagram skill, demo diagrams, and a
few decisions. It did no llm_to_action flight work; that track is parked.

## 1. diagram-authoring skill — DONE and installed
- Authors slide-grade diagrams: graphviz lays out, cairo draws, output is outlined SVG plus PNG,
  Canva-safe hex colors.
- Installed in two places: `/root/.claude/skills/diagram-authoring/` (global, synced to
  claude-context) and the repo mirror `.claude/skills/diagram-authoring/`.
- Files: `SKILL.md`, `gvcairo.py` (extended renderer: clusters, bold titles, dim `~` annotations,
  reversed arrows, channel-centered routes), `check.py` (verifier), `clean_svg.py`, `pin.py`.
- Diagrams delivered: `docs/active/assets/diagrams-final/` (harden2 simplified + detailed) and
  `docs/active/assets/diagrams-detailed-v2/` (concise bullet-box detailed). NOTE: docs/active/assets
  is gitignored, so these sit on disk but are not committed.

## 2. Skill A/B benchmark — harness ready, numbers pending quota
- Goal: does the skill change a crawl agent's diagrams and token cost, on the neutral OSS repo
  `/root/Micro-XRCE-DDS-Agent`.
- Pilot 2026-09-12 is INVALIDATED: the baseline discovered the skill, and it ran on Fable 5.1, not a
  pinned model. Cost $7.38 for 2.22 M tokens. Do not cite it.
- Clean, reproducible harness: `docs/active/assets/skill-ab-test/run_ab.sh <model-id>`. It hides the
  skill from both skill dirs for the baseline, asserts isolation, pins the model, runs both arms.
- Plan: publish the skill now; upload numbers and quality reports through the week as quota allows.
  The owner's quota restarts the morning of 2026-09-13.
- Open: the self-contained GitHub repo (README, license, example, before/after) is not built yet.

## 3. llm_to_action — committed as-is, then parked
- State and changes: `projects/llm_to_action/docs/2026-09-13-state-and-changes.md`.
- The finding: the drone hits the car (loom guard fires on the target; monocular depth).
- Fuller runbook: `docs/active/2026-09-10-llm-to-action-demo-handoff.md`.

## 4. SLAM removed from llm_to_action
- Deleted `source/tello_backend/test/tello_slam_hold.cpp`; removed its CMake target. projects/slam is
  now free to archive. See the state doc for the remaining runtime-only reference.

## Open decisions for the owner
- Diagrams are gitignored (`docs/active/assets/`). Commit them with `git add -f`, or keep them out of
  groundstation and only in the future GitHub skill repo.
- Whether to build the GitHub skill repo now.

## Running the A/B benchmark (run_ab.sh)
Command: `docs/active/assets/skill-ab-test/run_ab.sh <model-id>` (also copied to
`tools/diagram-authoring/benchmark/run_ab.sh` in the skill repo).
Example: `run_ab.sh claude-opus-4-8`.
What it does: hides the diagram-authoring skill from both skill dirs, asserts it is gone, pins the
model, runs the baseline arm, restores the skill, runs the with-skill arm. Each arm writes a run.json
(parse `usage` + `num_turns`). Cost: ~2.2 M tokens per arm (pilot). Run one model per quota window;
upload the numbers through the week.
