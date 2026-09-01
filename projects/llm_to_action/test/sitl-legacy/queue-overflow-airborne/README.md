# flood-airborne test

In-flight command-storm / backpressure (spec-3, ROADMAP 1.4). Unlike `../flood` (which floods
at startup and never flies), this one flies first and gets flooded **in the air**.

- **Scenario:** `--scenario-queue-overflow-airborne` — injects the canned cross plan at startup, then arms
  a one-shot flood.
- **Trigger:** ~5s after the drone first reaches `FLIGHT`, the FMU injects a 100-action flood
  from a **producer-role `std::async`** (the same path the VLM plans on), so the SPSC queue
  contract holds — the control thread only *launches* it, it never enqueues.
- **World:** `default_car`   **Spawn:** `0,7,3`   (no VLM, no battery drain)

## Run
```
cd scripts/test/flood-airborne
./run.sh            # takes off, flies the cross; ~5s into FLIGHT the flood hits mid-air
./filter.sh         # -> captured_flood_airborne_log.txt (this folder) + digest + PASS/FAIL
```

## Expected behaviour (watch the drone)
- Takes off, starts the cross legs.
- `AIRBORNE FLOOD armed` at startup; `FLOOD test: injecting 100 ...` **after** `TAKEOFF->FLIGHT`.
- A burst of `BACKPRESSURE queue full -> dropped` (queue is already partly full with the cross
  legs, so more than the startup flood is dropped).
- **The drone keeps flying its current leg unbothered** — the storm queues *behind* the live
  plan (FIFO), so it cannot hijack the maneuver. The cross finishes and the drone lands
  (`LANDING->STANDBY`); the leftover `stop`s then drain as no-ops.

## What the filter asserts
- drone reached **FLIGHT** and the flood fired **while airborne** (`flood line after FLIGHT line`);
- **drops > 0** (backpressure engaged) and **maxQsize ≤ usable cap (63)** (bounded);
- (soft) `LANDING->STANDBY` — the flight completed safely; re-run after touchdown if not yet seen.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
