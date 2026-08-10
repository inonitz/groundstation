# A3 — Voice interrupt + mission termination

**Status:** scheduled / not started. **Created:** 2026-08-10. **Revised:** 2026-08-09 (session review —
see Revision log). **Branch:** feature-llm-driver (SITL showcase).
**Depends:** spec-1 interrupt path (landed). **ROADMAP:** 3.7, 5.1, 6 (termination).
**Lock:** touches `fmu_node.hpp` (interrupt hook + prompt + new subscription) and `llm_base.hpp`
(verdict schema note) — the contended hotspot; both confirmed **FREE** in `docs/LOCKS.md` as of
2026-08-09. Coordinate with A2 (also touches `fmu_node.hpp`/`fmu_node_base.hpp`, different lines).

## Objective
Let a human end or redirect a mission by voice, and let the model judge its own completion. Route the
ASR transcript into an interrupt with a `[USER]` prompt block, and make each reassess emit a
structured completion verdict first, standing the drone down when the objective is met.

## Grounding (verified against this checkout, 2026-08-09)

**Stale-line-number warning (added 2026-08-10):** the file:line citations below were verified
2026-08-09. `fmu_node.hpp` has grown substantially since (plan-parse rewrite, SEARCH return-to-start,
grammar-constrained VLM output -- see `docs/NOTES.md` 2026-08-09) and is now 2109+ lines. Re-locate
every cited function/line by name before trusting a line number verbatim.
- **The ASR node already exists and already answers the spec's "pick one" UX question.**
  `source/llm_to_action/asr/asr_node.hpp` defines `ASRStandaloneNode`, publishing transcripts to
  `kOutASRServerTranscriptionTopic = "/asr_server/transcribe"` (`asr_node_base.hpp:4`) as
  `std_msgs::msg::String`. It's **push-to-talk (key `H`)**, not wake-word — already decided, don't
  redecide it. `fmu_node.hpp` has **zero references** to this node or topic today — no subscriber
  exists yet; the wiring is fully new work despite the publisher already being there.
- `raiseInterrupt(const char* reason)` at `fmu_node.hpp:1454` is generic and already used for
  `"emergency_boundary"` and `"approach_impact"`. Body:
  ```cpp
  if (m_hasActive) {
      m_stashedTask = m_currTask;
      m_hasStashed  = true;
      m_hasActive   = false;
  }
  m_lastInterruptReason = reason;
  m_interruptPending    = true;
  ```
  `raiseInterrupt("user_command")` needs **no changes** to reuse — but `reason` is a `const char*`
  literal, and `m_stashedTask`/`m_hasStashed` stash the interrupted *plan task*, not new text. There is
  **no existing field for the transcript itself** — add one new member, e.g. `std::string
  m_userCommandText;`, set by the ASR callback immediately before calling `raiseInterrupt`.
- `buildDynamicPrompt()`'s `[INTERRUPT]`/`[ESCALATION]` blocks, exact code at `fmu_node.hpp:1522-1540`:
  ```cpp
  if (m_interruptPending) {
      snprintf(buf, sizeof(buf),
          "[INTERRUPT]\nreason=%s\ninterrupted: %s\n\n",
          m_lastInterruptReason ? m_lastInterruptReason : "unknown",
          m_hasStashed ? m_stashedTask.m_thought : "");
      prompt += buf;
  }
  if (m_interruptEscalated) { prompt += "[ESCALATION]\n..."; }
  prompt += "[EXECUTED COMMAND HISTORY]\n";
  ```
  Insert the new `[USER]` block right after the `[INTERRUPT]` block (before `[ESCALATION]`), gated on
  `m_lastInterruptReason` being the literal `"user_command"` (pointer identity is fine since it's
  always set from the same string literal at the one call site — no `strcmp` needed, matching how
  `m_lastInterruptReason` is already just compared/printed elsewhere, not string-searched), printing
  `m_userCommandText` with the same `snprintf`-into-`buf` idiom.
- **No existing "verdict object" parsing — this needs a genuinely new parse step, not a reuse of the
  current `"thought"` handling** (corrects the original spec's implicit assumption). `translateToBaseCommands`
  (`fmu_node.hpp:1601`) skips any array element without `"action"` — that includes the documented
  leading `{"thought": "..."}` preamble (`llm_base.hpp:118-123`), which today is **silently discarded
  entirely**, not stored anywhere. `extractJsonArray` just slices `[`...`]`. So a leading verdict object
  structurally coexists fine (the action-parsing loop already ignores non-`action` elements) but nothing
  currently *reads* it. **Design decision (resolves the spec's ambiguity):** don't invent a second
  top-level object — extend the existing first-element schema to
  `{"thought": "...", "objective_complete": bool, "reason": "..."}`, defaulting
  `objective_complete`/`reason` via `.value(...)` (so old-format responses / other call sites that don't
  set these fields degrade to `false`/`""`, not a parse error). Add one new read of `plan[0]` before the
  per-action loop in `translateToBaseCommands`; if `objective_complete` is true, enqueue `land` (or
  `stop` if not airborne — reuse the same `airborne` check already computed in `buildDynamicPrompt` via
  `od.pos.z > 0.3f`) and return without processing further actions in the array.
- `stop` is already a valid, fully-wired action (`fmu_node.hpp:1631-1632`, `CmdStop`,
  `CommandID::STOP = 2`) — no new command type needed for the termination path.

## Scope
- **In:**
  1. Subscribe to `/asr_server/transcribe` (`std_msgs::msg::String`) in `fmu_node.hpp`'s constructor,
     alongside the existing `m_subOverride` subscription (same pattern). Callback stores the transcript
     into the new `m_userCommandText` member and calls `raiseInterrupt("user_command")`.
  2. `[USER]` block in `buildDynamicPrompt()`, inserted as described above.
  3. Extend the first-array-element schema to include `objective_complete`/`reason` (update
     `kSystemPrompt` in `llm_base.hpp`'s OUTPUT FORMAT section to document the new fields), and add the
     `plan[0]` read + early `land`/`stop` enqueue in `translateToBaseCommands`.
- **Out:** wake-word UX (already resolved — push-to-talk exists, don't redo it). RTH-on-voice (needs
  metric origin, out of scope until SLAM/position work lands).

## Files
- Modify: `source/llm_to_action/fmu/fmu_node.hpp` (subscription, `m_userCommandText` member, `[USER]`
  block, `plan[0]` verdict read in `translateToBaseCommands`).
- Modify: `source/llm_to_action/fmu/llm_base.hpp` (`kSystemPrompt` OUTPUT FORMAT section documents the
  new fields on the first array element).
- Modify: `source/llm_to_action/fmu/fmu_node.cpp` (two new canned flags, see Tests below).

## Tests to create
- **[AUTO]** `--canned-voice`: inject a transcript (bypassing the real ASR node, same way other canned
  scenarios bypass the VLM) → assert an interrupt is raised (`INTERRUPT (reason=user_command`) and the
  `[USER]` block appears in the next prompt (this requires either a debug log line printing the
  assembled prompt on interrupt, or logging `m_userCommandText` directly at raise time — pick whichever
  is cheaper; the existing `RCLCPP_INFO` tag convention applies).
- **[AUTO]** `--canned-complete`: force a plan response with `objective_complete: true` → assert a
  terminal `land`/`stop` action fires and no further planning cycle starts (`m_missionActive` should
  flip false, matching how a normal `LANDING->STANDBY` already ends a mission — confirm that reuse
  rather than inventing new termination state).
- **[HUMAN]** live spoken "done, land" (press-to-talk key `H`) stands the drone down (one confirmation
  run).

## Acceptance
Canned voice stands the drone down; the completion verdict fires on a met objective in SITL; live
voice confirmed once.

## Change-impact (per `docs/code-guidelines.md`)
- **What this changes:** additive subscription + prompt block (no behavior change when no transcript
  arrives — `m_interruptPending` stays false). The `objective_complete` field is new but defaulted via
  `.value(...)`, so any existing canned/VLM response missing it behaves exactly as today (false ->
  normal planning continues). The `translateToBaseCommands` early-return-on-complete path is new control
  flow, gated on a field that cannot appear in current traffic.
- **Breaks existing behavior:** no, if the default is correctly `false` for a missing field — this is
  the one thing to verify carefully in review, since a bug defaulting to `true` would silently
  land every existing VLM-driven scenario immediately.
- **Tests that re-run as-is:** all 20 SITL scenarios (A1) — none produce `objective_complete: true`, so
  none should observe new behavior. Worth explicitly asserting this (a regression here would be quiet
  and dangerous, per the note above).
- **Tests that are new:** the three listed above.

## Agent notes
The one spec that must serialize on `fmu_node.hpp`. Take the lock, land the interrupt hook, release,
then the prompt/parse work as a second short hold — per `docs/LOCKS.md`, prefer many short holds over
one long one. Gates demo S3 (A4).

## Revision log
- 2026-08-09: confirmed ASR node already exists and is push-to-talk (spec's open UX question is
  already answered by existing code, don't redecide); found the transcript needs a new owned-string
  member (`m_lastInterruptReason` is a bare pointer, can't hold it); found `translateToBaseCommands`
  currently discards the `"thought"` preamble entirely, so the verdict needs a genuinely new parse step,
  not a reuse of existing handling — resolved by extending the first-element schema rather than adding
  a second top-level object; confirmed `docs/LOCKS.md` shows both `fmu_node.hpp`/`llm_base.hpp` FREE;
  added the `.value(...)` default-false safety note under change-impact since a wrong default would
  silently break every existing scenario.
