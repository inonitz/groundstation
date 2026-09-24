# harden2 API (v2.3, 2026-09-24: matches the code after step 7 and the status redesign)

One C header per module of `projects/integration_harden2`. The Python modules mirror these names
and boundaries. SERVICES are built first and handed to the MODULES' constructors (app.h).

| header | module | owns |
|---|---|---|
| system.h | system/ | die, the status rows (each part owns its row; the board asks each part), supervisor (ProcessSpec -> Process handle), the ROS2 context + Subscription |
| util.h | util/ | the guarded third-party calls (the only try/except), net, process, hebrew, mission helpers |
| dji_app.h | dji_app/ | the phone app (or mock): commands, /tts, the transmit switch, its one status |
| gemma.h | gemma/ | the Gemma server's life, and one request call |
| audio.h | audio/ | mic ASR, phone speech in, speech out (phone or laptop) |
| video.h | video/ | the one frame source and its stall guard |
| perception.h | perception2/ | SAM3 backend, the priority lock, count / highlight / describe tasks |
| control.h | control/ | executes flight: critical commands, missions, the transmit switch |
| recognizer.h | recognizer/ | parses every sentence (fast path first) and routes it |
| log.h | log/ | the session record; checked once at start, no status row |
| app.h | app/ | start order, transcript -> actions, the transmit switch, keys, the UI |

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
