# First-turn note for the next llm_to_action subagent

You continue the llm_to_action VLM-demo work, paused for demo-day slides.

1. Read `docs/active/2026-09-10-llm-to-action-demo-handoff.md` in full FIRST. It carries the objective,
   what is done (all uncommitted), the runbook, the roadmap, and the standing gotchas plus owner rulings.
   Read the gotchas section before you touch anything.
2. The one thing to know: the drone hits the car. Qwen3-VL-4B plans the mission correctly, but the
   approach fails — the loom guard plus schizo monocular depth cannot tell the target from an obstacle.
   The planner works; the depth grounding is the blocker. Metric depth is the enabler for the roadmap.
3. Hard rules: you run NO git (prepare the commit block; the human runs it). `fmu_node.hpp` is
   vibecoded — fix the one bug, do not refactor. The loom guard is a collision-safety backstop — do not
   weaken it without the owner's explicit OK. Use the `rtk` wrappers for reads, greps, and git.
4. Be a critical pair programmer: push back, hard numbers only, address every point by its number.
5. Start: confirm the build works (`./build.sh release shared px4 build`), reproduce the demo via the
   runbook, then pick the next roadmap item.
