# Code review, 2026-10-01 (road step 4)

## Pass 1: the files changed on 2026-10-01 (/code-review high). 9 findings, all fixed.
- test_app.py: the app start check now allows interpreter flags; the Gemma check finds the pid by its port (ss).
- perf_report.py: `run.sh perf` shows Gemma's server prompt and answer times; a failed request is skipped, not 0.
- gemma/client.py: records cache_n too; a true/false timing is not a number; docstrings updated (also log/perf.py).
- test helpers: one RecordingPerf in test/support.py; the Gemma tests set their reply through monkeypatch.
- Checks: lint clean; audit 5; 252 passed, 2 skipped, twice; 3 mutation checks caught; end-to-end passed (42.03 s).

## Pass 2: all harden2 code (/code-review high, master...feature-hardening-mvd). 10 findings, all VERIFIED 2026-10-02 in the code (7 by running it); not fixed yet (the fix pass, ruling D1).
| # | file | finding |
|---|---|---|
| 1 | perception2/vision.py:381 | an old highlight's late update overwrites a new highlight; its HL_CLEARED wipes the new one |
| 2 | perception2/vision.py:336 | a clear during the gate does nothing: the highlight registers later and appears anyway |
| 3 | sam3/model.py:242 | mask_for_box reads a one-entry cache; verify passes or another task's detect wipe it: boxes drawn without masks |
| 4 | recognizer/fast_path.py:37 | "continue" anywhere in a sentence (for example "continue forward 5 m") becomes AUTO; the request is dropped |
| 5 | app/turns.py:102 | a refused vision task (8 alive) leaves "thinking..." on screen |
| 6 | perception2/engine.py:98 | kept boxes and masks can differ in length; masks pair with the wrong box |
| 7 | recognizer/guards.py:67 | the echo guard reads numbers with nums_en on Hebrew: a real command equal to a few-shot plan is refused |
| 8 | app/ui.py:79 | on VIDEO=webcam a 7.5 s camera drop ends the whole app |
| 9 | video/ros_stream.py:41 | on VIDEO=dji the display loop redraws the same frame without a pause (a full core) |
| 10 | recognizer/fast_path.py:46 | "stop tracking" sends the emergency halt; the clear is never reached |

## Not run
- /thermo-nuclear-code-quality-review: its skill sets disable-model-invocation; only the owner can start it.
- run.sh kill_stack's loose `pkill -9 -f` (found 2026-10-01, KI1): not in either pass; on the list for fixing.

## Recognizer fixes from the joint review (for the same fix pass, ruling D1)
- A stop word with a duration ("stop for 10 seconds") waits that long; a stop word alone halts in every mode (STOP1 (3)).
- A question ("is it possible to land now?") goes to Gemma, never to a flight keyword (clip 35; JR9).
- "Roger, continuing the scan, over" flew 1 m: nothing may fly (clip 61; JR11).
- "a bit" / "a little" = exactly 1 m (O10; JR15).
- Military (MIL1): "one more pass", "returning to the rally point", "fly low along the wadi" must fly nothing;
  "immediate takeoff, scramble" must take off (Gemma plans `home`); "climb to 800 feet" must climb 243.8-244 m
  (Gemma plans 800 m: feet read as meters).

## Pass 3: the changes of 2026-10-01/02 (/code-review high). 10 findings, all fixed 2026-10-02 (HISTORY).

## Open with the owner before the fix pass
- Fast-path auto word "המשך": RULED (AUTO1): auto only when the whole sentence is the auto command.

