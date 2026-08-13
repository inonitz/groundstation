# Agent-1 status (for the Manager)

_Written 2026-08-12 — delivered via file because the /tmp/cc-socks agent mesh was down and SendMessage could not route to the Manager session._

**State: DONE.** Full recovery block lives in [sitl-agent1-follow-spec.md](sitl-agent1-follow-spec.md)
— DONE / WIP / TODO, files changed, gotchas + reasoning, how-to-test, and the suggested commit
message. It is in the repo, so it travels with the code push.

## Suggested commit message (agent-1)

```
fmu: FOLLOW visual servo + HOVER + SEARCH-by-tag + stable-id tracker + perception-coast; grammar hardening; SITL follow test tooling
```

## Files touched (all agent-1)

- `source/llm_to_action/fmu/` — fmu_node.hpp, fmu_node_base.hpp, llamaclient.hpp, llm_base.hpp, perception_runtime.hpp
- `source/llm_to_action/perception/` — target_tracker.hpp, detection_query.hpp
- `scripts/test/SITL/` — logtest.sh, digest.sh, TESTING.md, follow/, crowd/, search_follow/, dependencies/three_people.sdf
- `docs/active/sitl-agent1-follow-spec.md`, `docs/NOTES.md`

## Notes

- Build: px4 + tello both rebuilt clean after the 640-image / prompt revert.
- No blockers on agent-1. Standing by for the human's "re-bundle" signal to snapshot the final sessions tarball.
- **Do NOT re-add** the VLM image-cut (640→448) or the "VISIBLE NOW" prompt directive — the human explicitly rejected both. Reverted.

## Reply to the two-demo brief (full assessment in sitl-agent1-follow-spec.md)

**DEMO 1 (colour FOLLOW): READY in current binary — no new FOLLOW code.** Resolve-once works because
`[PERCEPTION]` already lists each person as `{track_id, bbox, ...}` and the VLM sees the raw colour
image; it bridges "red" → track_id by bbox coordinates and emits `follow.target_id`. Pins via
`detectionByTrackId`; tracker holds it; distractors never steal it; forward=0 already. Only external
deps: the world file `rubicon_tree.sdf` + hardcoded actor positions, and `wait_for_ground_truth.sh`.
LOUD FLAGS: (1) colour→id is a 2B spatial call — make RED unambiguously the centre lane; (2) VLM
resolve speed is the demo risk (prewarm is yours); (3) fallback if correlation is flaky = send the
ANNOTATED (#id) frame to the VLM — needs human sign-off, not done.

**DEMO 2 KEY Q — VLM-bbox instead of YOLO label: YES.** Two corrections to your brief:
- **ORBIT is already built** (full odometry-circle servo at fmu_node ~L1103; only YOLO coupling is the
  seed `strcmp(det.label, orb.target)` + median_depth). "Geometry not built" is stale.
- APPROACH already supports a fixed world anchor (`m_cannedApproachTargetEnu` + synthetic-injection rig).
Both need, at activation only, a bbox centroid + one depth sample to freeze an ENU anchor; then they run
on odometry — no per-frame YOLO. house/window are static, so a one-shot VLM bbox suffices. The ONLY new
primitive: `medianDepthInRect(bbox)` on the retained depth mat. This unlocks house+window without YOLO
ever seeing them. Build plan is in the spec; NOT starting until DEMO 1 lands.
