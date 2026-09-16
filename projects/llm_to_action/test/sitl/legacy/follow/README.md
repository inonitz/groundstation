# FOLLOW (scripted)

Gates the FOLLOW control law (soon `stepFollow`). Scripted (`--scenario-follow`, VLM off) so it is
deterministic: `[takeoff, follow target_index=0 standoff_cm=200]` in the `moving_person` world.

FOLLOW is a **yaw-only visual servo** -- it centres the person and holds standoff (backs off if too
close), never chases forward, and never self-completes.

## Expected / verdict (`./filter.sh`, auto)
- **PASS** = a sustained stream of `FOLLOW(yaw-only)` ticks (>=20), one stable track id, no
  `follow_no_target` release. Prints mean pixel-centering error + min(range-standoff) for insight.
- **FAIL** = never locked (no ticks), lost the target (`follow_no_target`), or the id churned.
