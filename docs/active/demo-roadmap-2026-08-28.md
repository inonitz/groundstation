# Demo roadmap + challenge anchor (target: 2026-08-28)

Internal planning for the next agents. States the challenge, the COMMITTED demo decision, the known
tension between them, and the stretch options. Dry. Do not re-litigate the committed decision.

## What we are graded on (the challenge, paraphrased)
Control a ground robot OR drone by natural-language VOICE against real-time VIDEO, and perform a
PHYSICAL ACTION in space. Combine NLP + CV + motion control. Demonstrate autonomous operation.
Success example: "go out through the door". Constraints: LOCAL hardware (no cloud); platform-agnostic;
<= 1s from command-end to action-START; Hebrew support; robust to noise (gunfire/explosions), low
light, dynamic scenes. Scoring priority: HIGH = noise robustness, intent accuracy, visual-input
accuracy, minimal extra hardware, action-execution accuracy; MEDIUM = command sequences/context, low
latency; LOW = speaker biometrics. Judging: technical credibility is a required threshold (the demo
must work), then product/field readiness, then team/business/GTM. 6-min talk (EN slides, HE delivery)
+ 4-min Q&A.

## Committed decision (the lead's call, 2026-08-22)
Ship the CURRENT demo: the working Python perception stack (SAM2.1 + Qwen3-VL-4B + OmDet) driven by
English ASR (Parakeet). Rationale, all deliberate:
- **The LLM/VLM stays OUT of the control loop.** A non-deterministic model must never hold motor
  authority -- it can fly the drone into a building. Perception + intent only; any motion is
  deterministic and bounded.
- **English ASR, not Hebrew.** Hebrew ASR exists but is too slow / hit-or-miss (WhisperCPP turbo Q4
  ~3s) for the <=1s + accuracy bar; Parakeet English is ~50x faster and more accurate. The Hebrew
  requirement gap is ACCEPTED and bridged with presentation/demo tricks. Do not re-raise it.
- **No C++ perception engine exists yet.** The Python stack is the real, working system for the demo.

## Known tension (acknowledged, accepted)
The challenge centers physical action / autonomous motion; the committed demo is perception + ASR heavy
and light on autonomous physical action. The lead knows this ("consequences may be bad") and chooses to
proceed and mitigate rather than take on LLM-driven flight risk or an unfinished C++/motion stack under
the deadline. Record it as a known risk, not an open question to reopen.

## Stretch options (only if time; decided WITH the Android dev)
- **Physical llm_to_action demo on the real DJI backend.** Voice -> intent -> DETERMINISTIC verb ->
  DjiBackend. Would satisfy the physical-action requirement, but adds the unverified command->action
  path + the drone-safety rules. Upgrade of the current demo, not a commitment.
- **Ground platform (Robomaster).** Safer home for bounded physical motion (indoors, no fly-away).
  If pursued, VERIFY THE SDK FIRST (Tello-EDU-class gotcha): the official RoboMaster Python SDK for
  external programmatic control is native to the EP / EP Core; the S1's external SDK support is
  historically restricted/flaky. Treat "S1 + SDK works" as UNVERIFIED until proven on the exact unit +
  firmware; if in doubt, get the EP. Also check per-session SDK-enable, connection mode, activation lock.
- A safe way to add SOME physical action without an LLM in the loop, if wanted: deterministic
  gimbal-point / bounded "approach the target" where the VLM only SELECTS the target and a fixed
  controller executes. Keeps non-determinism out of the loop.

## MVD (committed; secure by Mon 2026-08-24 evening)
Voice (English) -> Python perception answers/acts on the live drone video, on the laptop, end to end:
phone (or laptop) ASR -> groundstation smart-CV -> result -> phone (TTS optional, not a graded
requirement). Query classes, by readiness: scene description, referring detection / mark target,
counting, focus-on-detail -- all PROVEN in the gate demo. Deprioritized: the continuous "notify if
someone is behind X" query (medium/low priority) -- design in parallel, ship only if the core is solid.
Route video through the rx_node ROS topic, not the flaky OpenCV capture.

## Timeline
- Sat-Mon 2026-08-24: current demo working + tested end to end on the laptop; secure Monday evening.
- Tue-Wed 2026-08-26: harden + demo tricks; evaluate a stretch (physical llm_to_action or Robomaster)
  only if the core holds; decided with the Android dev.
- Thu 2026-08-28: 6-min demo (EN slides, HE delivery) + Q&A. Lead on technical credibility -- show the
  perception + voice loop actually works, locally.
