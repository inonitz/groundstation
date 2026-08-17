# Agent 1 — project context brief (from Manager, 2026-08-13)

You've been heads-down on FOLLOW and are missing the project-wide picture. Here it is.

## The demo (make-or-break, hours away)

The headline is a pure-SITL, voice-driven mission on the dashboard. The operator speaks an
objective; ASR → FMU → the VLM plans → the drone flies it. The physical Tello is NOT bet on.
We locked three demos, in priority order.

**Demo 1 — the bet, must work.** Voice: *"find the person in red and follow them in place."*
World is `dependencies/rubicon_tree.sdf` — the Rubicon map plus three people rendered as
**static models** (I switched them from gz-classic `<actor>` to `<model>`; Harmonic wasn't
rendering the actors, so the drone saw zero people). The centre one is recoloured **red**; all
three use the person mesh, so YOLO tags each "person" and the VLM disambiguates by colour.
**Your job:** confirm FOLLOW resolves and pins the red one's `track_id` and holds it (yaw +
vertical, forward clamped ≤ 0) while the two distractors never steal it. This is what we're
betting on.

**Demo 2 — orbit house → window: cut as designed.** I verified the YOLO model directly: it's
the 80-class COCO set, with no house / window / building / door class. So the visual servo has
nothing to lock onto and the VLM just spins in search — we saw exactly that (every plan said
"no detections, search for the house"). We're reworking it as geometry (fly to a detectable
target framed *through* a real window opening), not perception. The "real" version — letting
the VLM steer with `rotate`/`go` toward what it visually **sees** (it's a vision model; YOLO's
blindness doesn't apply to it) instead of being forced into YOLO-anchored search — is **your**
future lane in the planning prompt/grammar. Post-demo.

**Demo 3 — physical Tello hat-follow + voice "land":** stretch only, Agent 5, hover-hold still
hardware-unvalidated.

## What the Manager changed tonight (so you're not surprised)

- **ASR → FMU voice wiring is in and working end to end** (log-proven): an empty objective idles
  in STANDBY, the first spoken transcript calls `start()`, and speaking in flight re-tasks the
  VLM (mirrors the override handback). `fmu_node.hpp` / `fmu_node.cpp`.
- **Fixed four sim-launch bugs:** the Gazebo GUI never opened (`sim_core` exported `HEADLESS=0`,
  but PX4 only launches the gui when HEADLESS is *empty*); the drone auto-armed in voice mode
  (`sim_core`'s `:=` clobbered an intentionally-empty objective); the keyboard pane silently
  failed (tmux pane overflow — every node is now its own tmux window); and the invisible people
  (actors → models, above).
- **VLM prewarm** added (cold first plan ~27 s → ~9 s warm). Your ~30 s VLM-speed risk should be
  largely handled by this — re-check and shout if it still stalls.
- **Prompt edit in your file:** I added a camera→`go` frame bridge to `llm_base.hpp` right after
  the `go` doc (image LEFT = +y / RIGHT = −y, upper = +z, always drive +x, with the "right is
  −y" warning + example), because the VLM kept flipping `go` signs. Additive, compiles clean,
  noted in `LOCKS.md`. A rebuild is running so it lands in the binary — **pull before you touch
  `llm_base.hpp`** so you don't clobber it.

## Constraints

No git writes — the human owns the whole git workflow; suggest commits, never stage/commit.
Voice is the trigger. "person" is the only reliable perception anchor we have.

## Your focus now

Make Demo 1 rock-solid: FOLLOW locks the red person in `rubicon_tree`, survives the two
distractors, and re-acquires cleanly on brief loss. ORBIT / window is deprioritized
(perception-blocked). If VLM speed still bites after the prewarm, that is the one thing that can
sink the demo — flag it immediately.
