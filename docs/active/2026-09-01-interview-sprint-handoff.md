# Interview Sprint Handoff (2026-09-01) — READ FIRST in the new session

The opening context for the next agent session. It carries this session's full state, the owner's
2026-09-01 change of plans, and the reoriented goal hierarchy. Companion docs (all live):
`2026-08-30-cleanup-takeover-audit.md` (frozen tasklist), `2026-08-31-vlm-bt-reading-list.md`
(Phase-2 research), `2026-08-27-run-guide.md` (run commands). Safety + git rules: CLAUDE.md, unchanged
and absolute.

## 1. Situation
- TWO more technical interviews. #1 in 1-2 days (probably less). #2, the MORE IMPORTANT one, at the
  end of ~1.5 weeks. Total runway: ~1.5 weeks.
- It is a RACE: the competing team has the same 1.5 weeks to improve their MVD. Ours must be the best
  it can be in that window.
- Change of plans vs the takeover: the owner and agent CODE TOGETHER again for this sprint. The full
  handoff to owner-only development is POSTPONED, not cancelled. The code restructure remains a
  necessity and resumes after the sprint.
- Working agreement, amended 2026-09-01: agent may write MVD Python again for sprint speed.
  `llm_to_action` C++ stays owner-written (agent maps/reviews). `integration/` stays FROZEN as the
  fallback; sprint work lands in forks or a new fork.

## 2. The goal hierarchy (the "objective salad", resolved)
- **North star (unchanged):** a voice-commanded autonomous camera drone; deterministic verbs fly it.
- **Phase 0 — NOW, 1.5 weeks: the MVD race.** Sprint backlog A-E below. Interview #1 shows whatever
  of A-C is solid; interview #2 shows the full Hebrew loop.
- **Phase 1 — after the sprint: simulator -> IRL.** Simple autonomous control in the wild with USER
  OVERRIDE. It will not be pretty at first; that is accepted.
- **Phase 2 — architecture research.** Assuming Phase 1 works in the wild: research an improved
  architecture that raises the SR% (success rate) of the model against its initial objective. The
  behaviour-tree reading list feeds exactly this phase.
- **Phase 3 — testing "and all of that jazz":** the test-drift fixes, characterization tests, and
  hardening from the frozen tasklist.
- **Parked until after the sprint:** the takeover/refactor tasklist (G1 module verdicts first when it
  resumes), fork merge (after the win), llm_to_action POC work, Tello archive, docs sweep.

## 3. Sprint backlog — A to E, in order

### A. Hebrew ASR, phone-first
- The PHONE already transcribes Hebrew — proven on demo day (judges heard Hebrew on the phone; the
  laptop lacked it). Focus: phone does the transcription; the existing ASR bypass carries it:
  phone -> POST to the groundstation :8080 -> `phone_ears.py` -> `on_text`.
- Owner clarification (2026-09-01): the DEMO phone is NOT the GrapheneOS device — the privacy strip
  (C3) has no effect on the demo speech stack.
- Groundstation Hebrew ASR is the secondary path: whisper-large-v3-turbo + VAD, quantized q4-q8 or
  ONNX, benchmarked vs Parakeet (the old H1 plan). Build only if the phone path needs a fallback.

### B. Hebrew -> English translation before Qwen
- Insert a translation hop so Qwen receives English and emits higher-quality commands. One
  bidirectional model or two one-way models — owner is indifferent.
- Candidate models TO VERIFY (do not trust until measured on our box): Helsinki-NLP
  `opus-mt-tc-big-he-en` + `en-he` (small, fast, Marian), or `facebook/nllb-200-distilled-600M`
  (one model, both directions). Selection criteria: latency on the workstation, quality on short
  imperative commands, VRAM alongside Qwen.
- Integration point: a pre-router hook on `on_text` (translate, then classify), so the Tier-4
  EMERGENCY regex must ALSO match Hebrew directly — a stop shout must never wait on a translation hop.

### C. Multi-command decomposition (the judge-impressor)
- Qwen takes one complex prompt ("go up 10 m, rotate 90 clockwise, then forward 5 m and detect ...")
  and decomposes it into a JSON ARRAY of REST commands for the DJI Backend — the MVD's REST API
  server, explicitly NOT the llm_to_action POC.
- KEY SHORTCUT: the wire already speaks arrays. `POST /c/fly` accepts `{"mission":[Action...]}` and
  `dji_wire.fly_mission()` sends it — so the example above is ONE post:
  `[{"type":"fly_by","z":10},{"type":"spin_by","degrees":90},{"type":"fly_by","x":5}, ...]`.
  Most of C is a Qwen planner prompt + a validator, not new wire code.
- DOCTRINE UPDATE (owner, 2026-09-01): "LLM out of the control loop" is RELAXED, deliberately: Qwen
  may PLAN a bounded sequence of deterministic verbs. It still never streams sticks/velocities.
  Safety bounds are mandatory: verb-type whitelist, numeric clamps (distance/angle caps), reject the
  whole array on any unknown or malformed element, and the EMERGENCY tier fires before any planning.
  Recorded in agent memory.

### D. Hebrew voice-out (after A-C)
- Chain: Qwen's English answer -> EN->HE translation (same model family as B) -> verbalize.
- One check before building on the phone path: confirm the DEMO phone's Android TTS has a HEBREW
  voice installed (`/tts` with `lang=he` / `iw`). English worked on demo day; Hebrew voice presence
  is unverified. If absent: install a Hebrew-capable engine on the demo phone, or go
  groundstation-only.
- Groundstation Hebrew TTS: piper has NO official Hebrew voice (believed, unverified — check the
  voices index first). Candidates to research: `facebook/mms-tts-heb`, RHVoice Hebrew, anything
  newer. The laptop TTS plumbing from `integration_tts` (piper+espeak, queue, phone+laptop dual
  output) is reusable — only the engine/voice changes.

### E. Vision improvement (research starts the day after A-D land)
- Current state: works, not well enough ("hit or miss on real-world specific requests").
- Owner needs a DEEP-DIVE doc on how the current MVD works — the agent wrote it, the owner has not
  dug in. Agent owes: per-file walkthrough of the perception pipeline (YOLO26n-seg background,
  OmDet-Turbo highlight grounding, SAM2.1 masks from OmDet boxes, VLM presence-gate + Q&A) with the
  control flow of `scene_omdet.py`. See the Rev-2 audit's B4 answer for the summary version.
- Research then decides the improvement (grounding-model landscape = the B5 topic; the eval-harness
  B1 idea is the measuring instrument if its time cost is accepted).
- The NOTIFY demo (`integration_notify`) still needs its live test — carried over, still pending.

## 4. Technical anchors for the new session
- Repo: /root/groundstation. Branch state: feature-llm-smart-scene merged/merging to master;
  sprint work on a new branch (owner runs git; agent NEVER writes git — CLAUDE.md).
- MVD run: `bash /root/groundstation/projects/integration_tts/run_mvd.sh dji real` (PHONE_IP auto from
  gateway; ASR_CAPTUREID default 1). Mock control: `... dji` + mock_apiserver on 127.0.0.1:8079.
- Phone: IP = WiFi gateway, :8080 control/status/tts, :5600 raw H.264. App = exoskeletons repo.
- VLM: Qwen3-VL-4B via llama-server :18090 (Vulkan). 2B is the SITL-safe fallback.
- Wire: `projects/integration*/dji_wire.py`; router tiers in `commands.py`/`router.py`; phone ASR in
  `phone_ears.py`; TTS client in `voice.py`.
- Models live in /root/models (volume-mounted, travels between machines).
- The container loses ad-hoc installs on rebuild (it ate the TTS binaries once) — script every
  install the sprint adds.

## 5. Standing rules for the new session (unchanged unless listed in §1)
- DRONE SAFETY rules in CLAUDE.md: absolute. Agent never sends arm/motor commands to real hardware;
  mock-only (127.0.0.1). Human runs everything armed.
- Git: human owns ALL writes; repo-destruction forbidden (0% rule).
- RTK wrappers for reads/greps; Bash heredoc for file edits; absolute paths in every command.
- `integration/` frozen. Features land with their docs, same change.
- Critical pair-programmer mode: lead with disagreement, no unverified claims, OBJECTIVE/ROI/KILL-SHOT
  gate on non-trivial actions.


## 6. Session-opening note (paste this to start the new manager session)

> You are the new manager agent for the voice-drone interview sprint.
>
> 1. Before doing ANYTHING, read in order: `CLAUDE.md` in full (drone safety, git rules, and the
>    Owner Interaction Protocol are absolute), then
>    `docs/active/2026-09-01-interview-sprint-handoff.md` (situation, goal hierarchy, backlog),
>    then `docs/active/2026-08-30-cleanup-takeover-audit.md` (frozen tasklist) and
>    `docs/runbooks/2026-08-27-run-guide.md` (how the MVD runs).
> 2. Situation: two technical interviews - #1 in 1-2 days or less, #2 (the important one) at the
>    end of ~1.5 weeks. This is a race against another team's MVD.
> 3. Work the backlog in order: A phone-first Hebrew ASR -> B Hebrew->English translation before
>    Qwen -> C Qwen multi-command decomposition into the DJI Backend's /c/fly mission array ->
>    D English->Hebrew + TTS voice-out -> E vision research + the MVD deep-dive doc + the notify
>    live test.
> 4. Working agreement: you may write MVD Python for sprint speed; all llm_to_action C++ is
>    owner-written (you map, explain, review). `integration/` is frozen. The human runs every git
>    write and anything that can arm a real drone - no exceptions, ever.
> 5. First reply: state the goal hierarchy and backlog A-E in your own words, flag anything you
>    think is wrong or missing (critical pair-programmer mode - disagree first), and propose your
>    concrete plan for A. Write no code until I confirm.
