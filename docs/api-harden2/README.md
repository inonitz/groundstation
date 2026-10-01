# harden2 API (v2.4, 2026-09-26: matches the code after steps 8, 9, 11 and 9a-2)

One C header per module of `projects/integration_harden2`. The Python modules mirror these names
and boundaries. Purpose (owner 2026-09-26): the owner reads the design here; every Python API
change updates its header in the same change, so the two never disagree. SERVICES are built first and handed to the MODULES' constructors (app.h).

| header | module | owns |
|---|---|---|
| runtime.h | runtime/ | the start-up dependency check, die, the status rows (each part owns its row; the board asks each part), supervisor (ProcessSpec -> Process handle), the ROS2 context + Subscription |
| util.h | util/ | the guarded third-party calls (the only try/except), net, process, hebrew, mission helpers |
| dji_app.h | dji_app/ | the phone app (or mock): commands, /tts, the transmit switch, its one status |
| gemma.h | gemma/ | the Gemma server's life, and one request call |
| audio.h | audio/ | mic ASR, phone speech in, speech out (phone or laptop) |
| video.h | video/ | the one frame source and its stall guard |
| sam3.h | sam3/ | the SAM3 service: the backend contract, the loader (its "sam3" row), the SAM3 model |
| perception.h | perception2/ | the vision system: the priority lock, count / highlight / describe tasks (uses sam3.h) |
| control.h | control/ | executes flight: critical commands, missions, the transmit switch |
| recognizer.h | recognizer/ | parses every sentence (fast path first) and routes it |
| log.h | log/ | the session record (checked once at start, no status row), the timings (perf), the read-only tools |
| app.h | app/, keys/ | start order, transcript -> actions, the global keys (keys/: F1 quit, F2 clear, F4 kill), the UI, the scripted run (test/scripted_e2e_run.py) |

config/ has no header: it holds every constant and start-up value the structs above are filled from.

## Rules the headers encode
- Only dji_app talks to the phone app. Only control sends flight commands and flips the transmit switch.
- The recognizer parses every sentence, fast path included, and routes it: critical words and missions
  to control, vision requests to perception (typed). It never speaks or draws.
- Failure: laptop processes restart 3 times, then die. The phone app waits for the user.
  SAM3 dies. The log is checked at start only.
- Nothing throws. Every call returns a status. The only try/except blocks are in util.h's
  guarded calls (one per failure domain), plus the cleanup loop in SysDie.
- Every part with a status row owns it and reports it through its own XxxStatus() call; the
  board only asks (owner ruling 2026-09-24).

Check syntax: `for f in docs/api-harden2/*.h; do gcc -fsyntax-only -x c $f; done`
