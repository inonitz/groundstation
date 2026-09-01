> **STATUS 2026-08-26 — read first.** The system was field-flown on 2026-08-25 (>3 h, incl. a classroom
> flight), but the **formal A/B/C kill drill below was NOT recorded.** RUN AND RECORD it before any
> armed session tomorrow — the boxes are honestly still unchecked. The `10.222.215.92` in the curl
> examples is **stale**: the phone IP is the WiFi gateway, derive it. Current **software** stops:
> emergency = `POST /c/fly [{"type":"delay","seconds":0}]` (halt — stops motion, keeps stick control).
> The **hardware** kills below are unchanged and remain the real net.

# Kill-switch verification — MANDATORY before any armed command (leg 4)

Purpose: prove every stop actually stops the motors **before** we ever arm for a latency run.
Do this once, record the results, then legs 4/5 may proceed.

**The assistant runs NONE of this.** Every motor-spinning step is human-run. The assistant only
prepares commands and this checklist. A verbal "go" is not authorization for the assistant to fire.

## Why this exists
On 2026-08-21 an arm command was fired at a drone resting loose on a desk; motors spun and the human
was injured stopping it by hand. This procedure ensures the stop is proven and the airframe secured first.

## Preconditions — ALL required, no exceptions
- [ ] **Props OFF.** Removes lift and the cutting hazard.
- [ ] **Aircraft rigidly clamped, or firmly held by a second person, in open space.** NOT resting on the desk.
      Spinning motors walk the airframe even with props off.
- [ ] Area clear; nothing the airframe can snag; eye protection sensible.
- [ ] Battery > 30 %, RC on, phone on hotspot, API Server ON.
- [ ] Chain up: `curl -s http://10.222.215.92:8080/status/` returns aircraft JSON (not 503).
- [ ] You can recite the three kills below from memory before starting.

## The three kills (surest first)
1. **Aircraft POWER BUTTON hold ~3-5 s** — hardware cut. Overrides everything, always works. THE trusted net.
2. **Phone API Server toggle OFF** (or force-close the app) — drops OUR virtual-stick authority; motors go to RC/failsafe.
3. **DJI CSC** — both sticks to the bottom-inner corners together. MAY be overridden while our virtual stick
   is active — testing whether it is is the whole point.

## Procedure — each test in its own arm cycle; the power button is your net EVERY time
Between cycles: confirm motors fully stopped and the airframe still secured before re-arming.

### Test A — prove the trusted hardware kill (establish the net)
1. Human: start motors via the RC normally (CSC / RC takeoff), our software NOT in the loop.
2. Human: hold the aircraft power button 3-5 s. **Motors must stop within ~5 s.** Record the time.
   -> You now have a proven stop for the rest of the tests.

### Test B — our-software authority vs API-toggle
1. API Server ON, our control path connected.
2. Human runs the takeoff the assistant prepared (below). Motors spin (props off, clamped).
3. Human: flip the **API Server toggle OFF**. **Motors must stop / return to failsafe within ~2 s.**
   If not -> power-button kill immediately. Record behavior + time.

### Test C — CSC under our authority
1. Human: re-arm via the assistant-prepared takeoff. Motors spin (props off, clamped).
2. Human: perform **CSC**. Observe: do motors stop, or is CSC overridden by our virtual stick?
   Either result is acceptable as long as it is KNOWN and recorded. If overridden -> power-button.

## What the assistant PREPARES (and never sends)
The takeoff our control path uses (HUMAN runs it, drone clamped + props off):
```
curl -X POST http://10.222.215.92:8080/c/takeoff
```
Note: the FC may refuse/abort takeoff with props removed (a safety feature). If it will not sustain
motor spin props-off, do NOT switch to props-on on the desk. Use a rigid test clamp in open space and
the human's judgment, power button in hand. When in doubt, stop.

## Pass criteria (must hold before leg 4)
- [ ] Test A: power-button hold stops motors < 5 s. **Non-negotiable.**
- [ ] Test B: API-toggle OFF drops authority < 2 s.
- [ ] Test C: CSC behavior recorded (stop or overridden — either, as long as known).
Only when A and B pass do we proceed to command->action (leg 4).

## Record results here
| Test | Kill | Stopped? | Time to stop | Notes |
|------|------|----------|--------------|-------|
| A | power button |  |  |  |
| B | API toggle OFF |  |  |  |
| C | CSC |  |  |  |
