# Review - harden2 refactor agent adherence (2026-09-21)

Second-agent audit. Checks whether the refactor agent followed docs/spec-harden2-cleanup.md
and docs/review-harden2-thermonuclear-2026-09-21.md for the files it marked DONE (phases 1, 2,
and the standalone review findings). Read-only. Nothing was modified.

## Objective

Confirm three things:
1. The DONE files match the per-file plan and the five principles.
2. The exception count is near zero in our own code.
3. Any deviation from a literal instruction was surfaced, not made silently.

## Setup

- Test gate: MVD_HOME=integration_harden2 MVD_TRANSLATOR=none python3 -m pytest test/ -q. Result: 70 passed.
- Static scan: an AST walk over every .py file under projects/integration_harden2. It counts
  every except handler and raise. Result: 49 except handlers, 6 raise statements.

## Results

### Exception scan by area

| Area | except handlers | Note |
|---|---|---|
| mvd.py | 12 | phase 4, not started |
| session_log.py | 7 | phase 5, not started |
| perception/ (engine, vlm_client, detectors) | 6 | phase 3, to migrate or delete |
| perception2/concept.py | 3 | phase 3, dead subsystem to delete |
| control/dji_wire.py | 2 | narrow: HTTPError, (URLError, OSError) |
| video/camera_stream.py | 6 | 5 broad teardown (log, not swallow) + 1 narrow frame parse |
| recognizer/llama.py | 3 | narrow: subprocess, TimeoutExpired, HTTPError |
| recognizer/pipeline.py | 2 | narrow: ImportError (dual import), JSONDecodeError |
| audio/phone_asr.py | 2 | narrow: OSError (bind), RuntimeError (loop stop) |
| audio/tts_io.py | 2 | narrow: OSError (socket), requests errors |
| audio/ros2_asr.py | 1 | broad teardown (log, not swallow) |
| tests | 3 | legitimate in tests; live_mock_smoke is stale |

The 6 raises are all SystemExit in __main__ self-tests, plus concept.py's dead subsystem. None is a
raise in a live code path.

### Per-file adherence

1. control/dji_wire.py: PASS. The non-loopback host now calls die(), not raise. The loopback check is
   a plain string test, no throw. One narrow HTTPError catch returns the code. The re-raise is deleted;
   an unreachable host returns status 0. This is the safety file and it is correct.

2. audio/tts_io.py: PASS. One slot, a lock, a wake event, a zero-CPU wait. No queue, no poll. It dies on
   an invalid backend and on an unreachable phone at startup. The speak function is chosen once. Both
   catches are narrow and die on a severe failure. Matches the redesign spec.

3. perception2/sam3_backend.py: PARTIAL. A lock was added. It stops two GPU forwards at once and stops a
   torn cache read. But detect() and mask_for_box() are two SEPARATE critical sections, not one. A gate
   or count thread's detect() can still reset the cache between the worker's detect() and its
   mask_for_box(). The worker then reads a cache miss and draws the box without its tight mask. The engine
   handles a None mask, so this degrades quality; it does not crash. The review asked for ONE critical
   section so "the mask cache cannot race". This is a deviation from that literal instruction, and it was
   not surfaced. Severity: low-to-medium.

4. audio/phone_asr.py: MOSTLY PASS, one deviation. The taken-port case dies. writer.close() has no guard.
   call_soon_threadsafe logs a RuntimeError, it does not swallow it. DEVIATION: _extract still calls a bare
   json.loads that can throw on a malformed phone payload. The spec asked for a safe-parse helper that
   returns a status. Principle 1 asks die() on invalid input. The agent did neither and did not surface the
   conflict between the two. A malformed packet now throws into asyncio, which drops that one connection.
   Severity: medium.

5. video/camera_stream.py: PASS with a noted deviation. The frame parse is narrowed to (ValueError,
   TypeError). Teardown logs every error instead of swallowing it. DEVIATION: the spec said rclpy imports
   plainly; the agent used a find_spec guard plus die() on use, because a webcam run needs no ROS. That is
   the better choice, but it was not surfaced. The 5 broad teardown catches are the owner-sanctioned
   "log, do not swallow" pattern, but they contradict the handoff's claim of "narrow boundaries only".

6. audio/ros2_asr.py: PASS. Plain rclpy import. Teardown logs, does not swallow.

7. Clean by scan (no live-path exceptions), consistent with the plan: cam_list.py, config/defaults.py,
   control/kill.py, overlay.py, recognizer/prompts.py, show_session.py, score_session.py,
   video/video_watchdog.py, recognizer/llama.py (3 narrow), recognizer/pipeline.py (2 narrow).

## Analysis

1. The exception discipline in the DONE files is strong. Every remaining catch in a done file is either a
   narrow third-party boundary or a sanctioned log-and-continue teardown. The broad-catch clusters that
   remain are all in the pending phases (mvd, session_log, perception, concept), which is expected.

2. Three deviations from a literal instruction were made without surfacing them: the SAM3 lock granularity,
   the camera_stream rclpy import, and the phone_asr json.loads. The handoff explicitly warned against this.
   Two are the better engineering choice (camera_stream, arguably SAM3). One is questionable (phone_asr).

3. The SAM3 lock is the one that does not fully meet its stated goal. It prevents the crash and the torn
   read, but not the cross-thread cache clobber the review named. A combined detect+mask call, or routing
   all SAM3 calls through the worker thread, would close it. This is worth fixing in phase 3, where the
   backend and its callers are being reworked for the (ok, hits) contract anyway.

## Open items for the owner

- Decide the SAM3 lock granularity: accept the partial fix, or make detect+mask one critical section.
- Decide the phone_asr malformed-input policy: safe-parse to a skipped transcript, or die().
- The camera_stream rclpy find_spec choice looks correct; confirm it is accepted.
