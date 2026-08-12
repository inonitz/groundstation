# Demo Day plan — LOCKED (Insurance Agent, 2026-08-12)

The single durable source for what we present. A fresh session should be able to run the demo from
this file alone.

## Decision

Present a pure-SITL, voice-driven mission on the dashboard. The Tello hardware is NOT bet on. The
challenge is platform-agnostic by its own wording, so SITL is a legitimate demonstration surface, and
it removes the on-stage hardware risk (unvalidated hover-hold, surface-dependent SLAM, prop noise in
the mic).

The mission is not one canned command. It is a chained, re-taskable, perception-conditioned mission,
shown live on the dashboard. That is the peak of the system and the thing the judges actually score:
autonomy in a changing situation.

## The mission (live, ~3 min)

All verbs below are landed in SITL (PX4 EKF2 gives real position, so no SLAM is needed).

1. Operator, push-to-talk on the ground: "Take off and find the man wearing the hat."
   - Proves: free-speech intent parse + CV search. Dashboard shows detections + VLM reasoning live.
2. Autonomous: takeoff -> search -> identify -> approach -> hold.
   - Proves: perception-conditioned action, not a pre-baked waypoint.
3. Operator: "Now follow him."
   - Proves: sequential context. "Him" resolves to the already-identified target. This is the
     medium-priority contextual-perception requirement, demonstrated live.
4. Operator: "Orbit him and keep watching."
   - Proves: re-tasking mid-mission.
5. Q&A: one improvised command from a judge.
   - Proves: not canned. This is where technical credibility is won or lost.

## Why the dashboard is the star

Judges cannot see intelligence in a drone that just moves. They can see it on one screen: what it
heard (transcript), what it sees (detections + depth), what it is thinking (VLM reasoning log), what
it is doing (command history + HUD). That screen is the technical-credibility proof. Keep it on
throughout.

## Must-dos (non-negotiable)

- Pre-warm the VLM before presenting. Cold first-plan is ~27 s; a boot warmup cuts it to ~9 s. A cold
  plan on stage is a dead demo. Owner: manager is wiring the boot warmup — confirm it lands.
- Record a clean run as a backup video. If the live mission flakes, cut to the recording mid-sentence.
  Never dead-air on stage. Highest-leverage prep item.
- Deterministic world + fixed seed so the run reproduces.
- Speak the objective on the ground. Prop noise threatens in-flight capture; push-to-talk.
- Keep the system prompt general enough to survive the one Q&A curveball. Do not overfit to the exact
  rehearsed strings, or an improvised command exposes it.

## Hebrew

The written spec lists Hebrew as a fixed requirement; the judge contact softened it verbally. Cover
both. Run the live mission in English (Parakeet — fast, accurate). Show one canned Hebrew clip through
whisper.cpp early as proof of concept, then switch to English "for latency." One sentence: the
pipeline is language-agnostic, Hebrew is a model swap, gated only on mature local fast Hebrew ASR, and
here is the path. This turns the gap into a roadmap line instead of a miss.

Reasoning a fresh session needs: fast, accurate, local Hebrew ASR is not a solved problem. The best
local Hebrew option (whisper-large-turbo-v3 via whisper.cpp) is ~3 s and not accurate enough.
Parakeet is multiples better on speed and accuracy but European-languages only. We are not pushing the
state of the art here, so English-live + Hebrew-roadmap is the honest and defensible call.

## 6-minute structure

- 0:30 — challenge + one line: "VLM plans, deterministic math flies, everything local."
- 0:30 — architecture, one slide (docs/system-architecture.md diagram).
- 3:00 — the live mission above.
- 1:00 — evidence slide: end-to-end latency ~2 s (live meter), the accuracy-vs-SNR robustness curve,
  the negative-denoise result (see docs/active/asr-noise-robustness.md).
- 1:00 — TRL, roadmap (Hebrew ASR, Tello hardware), why better than existing, hand to team/GTM.

## Open dependency (the one gap between this plan and a live voice demo)

- ASR -> FMU wiring. The FMU does not yet consume /asr_server/transcribe; the objective enters only at
  startup. One subscription that writes m_initialCommand and re-triggers maybePlan(). ~1 hr. Owner:
  manager. Until it lands, the mission is driven by startup objective, not live voice.

## TODO

- Build the end-to-end latency benchmark: mic-release -> first setpoint, after VLM warmup. Put the
  number on the evidence slide. Current estimate ~2 s (VLM plan ~1.5 s dominates).
- Record the backup video once the mission runs clean.
