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

## Noise-robustness read on the live demo (what the SNR data flags)

The SITL demo has no prop noise; the only noise is the room. So the mic SNR is set by the venue and
the mic choice, not the drone. The curve (docs/active/asr-noise-robustness.md) holds >=87% intent from
+20 down to 0 dB, ~80% at -4 dB, and collapses past -6 dB.

Per-command risk in the mission:

- Beat 1, "take off and find the man wearing the hat" — highest risk. It is compound, and the
  discriminating word is the attribute "hat". Below 0 dB a single corrupted keyword flips the intent
  even when character-accuracy still looks high. The curve is char-level; one wrong noun is a wrong
  mission.
- Beats 3-4, "now follow him" / "orbit him" — two-word commands. Low redundancy, so one corrupted
  word is total loss. The capture window is short, which helps.

Mitigations, ranked by leverage:

1. Use a close-talk / headset mic on stage. It raises source SNR ~15-20 dB and puts every command in
   the safe +10..+20 band regardless of the room. Single highest-leverage item. Do NOT use the laptop
   mic — that is the "garbage mic" that produced the worst stress-test results.
2. Operator read-back before the drone acts. It catches the corrupted-keyword case. In a noisy room it
   is mandatory, not optional. Already in the pipeline design (confidence gating is dead; read-back is
   the net).
3. Push-to-talk, spoken close and deliberately.

Honesty line for judges: the floor is ~-6 dB — noise about twice as loud as the command. Below that,
do not claim it works. The operational answer is close-mic + read-back, and the curve proves intent
holds to 0 dB when noise does reach the mic. If judges play gunfire at the demo, expect the -4..-6
band and let read-back save the run; offer them the close mic rather than blasting the laptop mic.

## Latency benchmark — ASR->FMU LANDED 2026-08-12, ready to run

The wiring is in: fmu_node.hpp subscribes to kOutASRServerTranscriptionTopic (/asr_server/transcribe)
and asrCallback() runs start(text) on the ground (STANDBY) or re-tasks in flight. So the mic->setpoint
path now exists end to end.

> HARDWARE-SPECIFIC — MUST run on the DEMO LAPTOP, not a dev box. Latency is dominated by the
> VLM plan time, which scales with the GPU. A number measured on any other machine is
> meaningless for the demo. (Attempted on the dev box 2026-08-12; abandoned for this reason.)

Definition: t0 = push-to-talk release (end of captured audio), t1 = first velocity setpoint emitted
for the new objective. Report t1 - t0 after VLM warmup.

Instrumentation (two log stamps, no logic change):
- asr_node: log capture-end (t0) and transcript-publish time.
- fmu_node asrCallback: log receive time; first set_velocity of the new plan: log time (t1).
mic->setpoint = (transcript-publish - capture-end)  [ASR inference]
              + (first-setpoint - transcript-receive) [VLM plan + translate + control tick].

How to run (interactive, ~10 min, needs a human at the mic OR the mic-less variant below):
1. Bring the stack up: `scripts/simenv.sh` (tmux: XRCE, PX4/Gazebo, ASR,
   FMU/offboard, VLM llama-server on Vulkan0:8080). Gimbal SDF is auto-patched and restored on exit.
2. WARM THE VLM FIRST — cold first plan is ~27 s, warm ~9 s. Send one throwaway objective and wait
   for a plan before timing anything. Do not time a cold plan.
3. Mic-less, reproducible variant (measures the VLM-dominated half, transcript->setpoint):
   `ros2 topic pub --once /asr_server/transcribe std_msgs/msg/String "{data: 'take off and find the
   man wearing the hat'}"` and read the FMU log delta from receive to first set_velocity.
4. Full mic variant: push-to-talk, speak the objective, read the asr_node + FMU log deltas.
Expected ~2 s, dominated by the ~1.5 s VLM plan. The ASR-inference half on Parakeet-q4 is a few hundred
ms on a short command.

Why not auto-run here: the full flight stack + a shared 4 GB GPU + timestamp edits to the contended
fmu_node.hpp are not safe to spin up unattended in a background session mid multi-agent work. Run it
interactively, or hand to the session that owns fmu_node.hpp for the two log stamps.

VLM assets (for reference): llama-server at build/release/shared/px4/bin/llama_shared/bin/, model
/root/models/vlm/Qwen3-VL-2B-Instruct/Qwen3-VL-2B-Instruct-Q4_K_M.gguf + mmproj-BF16.gguf, -c 1024,
--flash-attn on, port 8080.

## Stage readiness (keep ready)

- Backup video: record one clean run of the full mission after ASR->FMU lands and the mission runs
  green. Store off-repo. If the live run flakes, cut to it mid-sentence. Highest-leverage prep item.
- Deterministic seed: there is no seed knob in the SITL launch today (checked scripts/, config/). To
  make the run reproducible, add a fixed PX4/Gazebo sim seed plus a fixed actor spawn to the world
  launch. Owner: Agent 1 (world + fmu.hpp is a locked hotspot). Flag, do not edit. Until it exists,
  rehearse the exact spawn positions so the run is repeatable in practice.
