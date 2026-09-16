# HOVER persistence

Verifies the extracted `stepHover` control law: a HOVER command is a **persistent** hold that
**never completes**, so anything queued after it never runs.

## Scenario (`--scenario-hover`)
`[takeoff, go +1.5m forward, hover, go -1.5m backward, land]`. Because HOVER never completes, the
backward GO and the land can never dequeue.

## Expected
- Drone takes off, flies ~1.5m forward, then holds station there.
- It does **not** reverse. The backward motion never happens; the drone parks at +1.5m.
- Log shows `HOVER activated` then repeated `HOVER holding station`, and **no** further `GO` lines.

## Verdict (`./filter.sh`, auto)
- **PASS** = forward GO ran, HOVER activated + held, and no GO activity after hover.
- **FAIL** = a GO line appears after `HOVER activated` (the back-go ran -> hover leaked), or HOVER
  never activated / never held.

## Your observations
_(fill in)_
