# Agent 1 — authoritative brief: contest, judges, and the CURRENT demo (merged, 2026-08-14)

Merged from two sources: the **Manager** (technical execution, demo state, timeline) and the
**Hebrew/Requirements agent** (the MOD challenge, judging, Hebrew, noise). This file **supersedes**
`agent1-context-brief-2026-08-13.md` and the earlier Hebrew-only Aug-14 draft **wherever they conflict
on the demo or the timeline** — those are pre-pivot. Read the CURRENT STATE box first; it changes what
"the demo" means.

## ⚠ CURRENT STATE — read first (what changed since the older briefs)

1. **The demo pivoted: red-person FOLLOW → car APPROACH+LAND.** "Find the person in red and follow
   them" did not work reliably and is no longer the bet. Reasons, in order: (a) the **camera fed RGB
   bytes as BGR**, so the whole pipeline — dashboard AND the VLM's own image — saw the RED person as
   BLUE (now fixed, BGR→RGB in `gazebo_cam_plugin.cpp`); (b) the running model is the **2B**, which
   cannot reliably disambiguate "the red person" and emits orbit/search garbage; (c) **YOLO cannot
   resolve a person at ~10–16 m** (25–53% conf). The current demo is voice → **"approach the car and
   land near it"** in world **`rubicon_targets`** (Rubicon terrain + one blue hatchback, far 2nd car
   trimmed, 2 people kept for scene). A **car is a canonical COCO class at ~80%+**, so it locks.

2. **Timeline: the "9-hour make-or-break" was the SIM-RECORDING checkpoint, NOT Demo Day.** That
   recording happened and was **not flashy/impressive enough**. Real picture: **Demo Day ~2026-08-28
   (~2 weeks)**; a near-term readiness checkpoint ~2026-08-16/17; we already passed an assessment test.
   The path forward is a **real, proper physical drone + intensive testing**, not more sim polish. So
   the "on stage / prewarm / backup video" advice below is for the eventual live demo — but the next
   two weeks are hardware bring-up and robustness.

Everywhere below that says "the demo is the red person," read "was — now the car"; where it says "on
stage soon," read "Demo Day is ~2 weeks out, on real hardware."

## The challenge (MOD, translated from the Hebrew "Hard Requirements" doc)

Operate a ground robot or drone by natural-language voice commands, in real time, against a live visual
scene. The system takes free speech about the vehicle's situation, interprets intent, analyses the
environment with computer vision, and executes a physical action.

Goals: an intuitive human-machine voice interface; a fusion of NLP + computer vision + motion control;
autonomous action in a changing environment. Success = executing a *complex command in an unplanned
environment*. Flagship example: "exit through the door" — perception-driven, not a canned waypoint.

Fixed requirements (thresholds, not scored points):
- Runs on local hardware. No cloud. STT, LLM, VLM, control — all on-prem.
- Hebrew support.
- Under 1 second from end-of-command to start-of-action.
- Platform-agnostic — demo on a platform of your choice. SITL is legitimate by this wording.
- Works under noise (gunfire, explosions), limited light, and a dynamic scene.

Scored priorities:
- High: noise robustness; intent-parse accuracy; visual-parse accuracy; minimal extra hardware;
  action-execution accuracy vs intent.
- Medium: understand a sequence of commands to build contextual perception; low latency.
- Low: speaker identification (voice biometrics) against hostile takeover.

## What the judges expect on Demo Day

Format: 6 minutes to present, up to 4 minutes of judge questions. English slides, Hebrew delivery
preferred. Three scoring axes:
1. **Technical credibility** — does it actually work. Required threshold; a strong business story cannot
   compensate for weak technical proof.
2. Product and field readiness — how far from a finished product, and what it becomes.
3. Team, business, go-to-market — right team, sound commercial logic, military and dual-use.

Hard line: the tech demo MUST work and solve the challenge as written. Everything else is secondary.

## The demo — what we locked, why it pivoted, what it is now

**Originally locked (the aspiration):** Demo 1 = voice "find the person in red and follow them in
place" in `rubicon_tree` — three static person models, centre one recoloured red, FOLLOW pins the red
`track_id` (yaw + vertical, forward clamped ≤ 0) under two distractors. Demo 2 (orbit house→window)
**CUT** — YOLO is COCO-80 with no house/window/door class, so the servo has nothing to lock. Demo 3
(physical Tello hat-follow + voice "land") stretch only, Agent 5, hover-hold still hardware-unvalidated.

**Why Demo 1 pivoted** (see CURRENT STATE): color-channel bug + the 2B can't disambiguate red + YOLO
can't resolve a distant person. FOLLOW-on-red is not dead as a *capability* — it is your lane — but it
is not the recorded or near-term bet.

**Current demo (the bet):** voice → **"approach the car and land near it"**, world `rubicon_targets`,
spawn `0,3,3` (blue hatchback ~6 m dead ahead). The FMU finishes deterministically after the FIRST
plan so it rides the 2B only once — see "Deterministic chain" below. "person"/"car" is the only
reliable perception anchor; keep behaviour robust to one improvised phrasing — a rehearsed-only demo
fails the Q&A curveball.

## The camera color bug (why "disambiguate by colour" was silently failing)

Our gz→udp camera plugin (`gazebo_cam_plugin.cpp`) declared its appsrc caps `format=BGR` while the gz
camera sensor emits **R8G8B8**. So RGB bytes were fed to gstreamer as BGR → **red and blue swapped for
the entire pipeline**, dashboard AND the VLM's image alike. **Fixed (BGR→RGB).** If any earlier
conclusion was "the model can't identify the red target," that was the *plumbing, not the model*. Any
reasoning premised on "it sees blue" is void.

## Hebrew — the honest position

Fast, accurate, *local* Hebrew ASR is not a solved problem. The best local Hebrew option
(whisper-large-turbo-v3 via whisper.cpp) is ~3 s and not accurate enough. Parakeet is multiples better
on speed and accuracy but is European-languages only. So: run the live demo in **English on Parakeet**,
show **one canned Hebrew clip** through whisper.cpp as proof of concept, and state plainly that the
pipeline is language-agnostic and Hebrew is a model swap gated only on mature local Hebrew STT. That
converts a fixed-requirement gap into a roadmap line. The judge contact softened Hebrew verbally, but
it is written as fixed — cover it, do not ignore it.

## Noise robustness — measured, and it is a strength

SNR sweep: real gunfire/explosion beds mixed into clean command clips at controlled SNR, transcribed,
plotted. Parakeet-q4 on raw audio holds ~92% intent at 0 dB (speech and gunfire equally loud), ~80% at
−4 dB, collapses only past −6 dB. See [asr-noise-robustness.md](asr-noise-robustness.md).

Hard-won decisions a fresh session must not relitigate:
- **Ship raw audio.** Every denoiser tested (GTCRN neural, SpeexDSP, classical) was net-negative — the
  ASR is trained on noisy speech and beats a generic front-end.
- **No confidence gate.** Token-probability confidence does not track correctness. Safety net is
  operator read-back before the drone acts.
- "Explosion-proof" is a robustness spec, not a denoiser task. Real mitigations: model robustness,
  capture-side hardening (close-talk mic + push-to-talk), and read-back.

Live evidence on our own demo commands: "Find the human that is red, approach it, and then land near
it" transcribed *perfectly* with combat noise overlaid at 1:1. Intent-carrying words survive the noise.

## Voice pipeline state

- **ASR:** Parakeet-TDT-0.6B q4, local. File passthrough via `parakeet-cli`; publishes on
  `/asr_server/transcribe` for the live path.
- **ASR → FMU:** LANDED. `fmu_node.hpp` subscribes to `/asr_server/transcribe`; `asrCallback` runs
  `start(text)` on the ground and re-tasks in flight. Spoken objective → plan → flight, end to end.
  (Plus a 200 ms min-record guard so a momentary PTT tap can't inject a garbage transcript.)
- **VLM:** Qwen3-VL-**2B** via llama-server, GBNF grammar-constrained (takeoff-first pinned). **This is
  the 2B, not a 9B** — plan for its limits (one good plan, then deterministic execution). Pre-warm it;
  cold first plan ~27 s, warm ~9 s. A cold plan on stage is a dead demo.

## Latency

Target <1 s (fixed requirement); realistic ~2 s, dominated by the ~1.5 s VLM plan. HARDWARE-SPECIFIC —
measure on the actual demo machine, not a dev box; VLM time scales with the GPU. Note the demo laptop
is a 4 GB GTX 1050 Ti (why it's the 2B, not a 9B). Recipe in [demo-plan-spec.md](demo-plan-spec.md).

## Deterministic execution chain (FMU) — rides the 2B only ONCE

After the first plan, the FMU finishes the mission without asking the planner again:
- **SEARCH-found → auto-APPROACH** the found track. (The 2B kept re-issuing SEARCH after finding the
  car — infinite loop; now a found detection activates APPROACH in-place.)
- **APPROACH-complete → auto-LAND.** (The 2B would skip the land; `completeCurrent` chains a LAND on
  any APPROACH finish.)
- Supporting: **blind SEARCH promotes to LARGE** (reach ~24 m); **label aliasing** so YOLO
  "person"/"car" matches a natural-language target ("human in red"/"the car") — exact strcmp failed
  before and the search stared straight past the target; **approach altitude floor**
  (`kApproachMinAnchorAltEnu = 0.8 m`) so a low/hallucinated bbox can't fly the drone into the ground;
  **`kSearchMinConfidence` 0.35 → 0.25**.
All in `fmu_node.hpp` / `fmu_node_base.hpp`. **Pull before you touch the SEARCH or APPROACH branches —
I rewrote both.** See `LOCKS.md`.

## The honesty stance (how we present it)

We explicitly rejected a fully-canned demo: the `--canned-approach` synthetic rig shows
`approach(canned_target)` with an empty DET — judges spot that instantly. The demo uses **real
perception and real approach**; only the *planner decision* is bypassed after the first plan. The model
genuinely reads the spoken objective, produces the first plan, and its `thought` shows on the
dashboard. Real detection + real control, deterministic close-out. Keep prompt/grammar work consistent
with that framing — technical credibility is the judges' hard threshold.

## Your lane / what not to break

- You own `llm_base.hpp` (prompt) and `llamaclient.hpp` (grammar). Your "SEE IT? FLY TO IT" rule and the
  scoped search-clause are good and complementary to the FMU chain — keep them.
- Do NOT assume FOLLOW-on-red-person is the demo; it is the car approach+land (FOLLOW stays your lane
  as a capability).
- Do NOT design for per-step re-planning; 2B latency ~30 s/plan → the win is ONE plan then
  deterministic execution.
- The color fix means perception is truthful now — reasoning premised on "it sees blue" is void.

## Stage / Demo-Day must-dos (for the eventual live run, ~Aug 28)

- Pre-warm the VLM. Record a clean backup video; cut to it if the live run flakes — never dead-air.
- Deterministic world + fixed spawn so the run reproduces (no seed knob yet; rehearse exact spawns).
- Close-talk / headset mic, not the laptop mic. Push-to-talk. Speak on the ground.
- Keep the system prompt general enough to survive one improvised Q&A command.

## Git state

The technical work above is on `feature-llm-driver` (being promoted to default). If you branched
earlier, pull/rebase so you have: the camera color fix, label aliasing, the search→approach→land chain,
the approach altitude floor, and the `rubicon_targets` car scenario.
