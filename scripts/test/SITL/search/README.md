# SEARCH (scripted)

Gates the SEARCH control law (soon `stepSearch`), replacing the dead `search_follow/` + the contrived three-people world. Scripted (`--scenario-search`, VLM off): `[takeoff, search car]` in the
`rubicon_targets` world (the real rubicon map, with 2 people + 2 cars), spawned **facing away** so the drone must scan to find someone.

SEARCH advance-and-scans; on a confident detection the node logs `SEARCH DETECTED` and hands the
track straight to APPROACH.

## Verdict (`./filter.sh`, auto)
- **PASS** = `SEARCH activated` then `SEARCH DETECTED target=car`.
- **FAIL** = activated but never detected (scanned / timed out without a find).
