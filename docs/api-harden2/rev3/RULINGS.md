# Step 2: the rulings that change the API (after v2.3, 2026-09-24)

Source: docs/spec-harden2-cleanup.md, the Decision ledger (the owner's words copied by script, the last row
of an ID in force) and the spec's owner sections. "In v2.3" and "in today's header" say where the ruling
already shows. Rulings dated before 2026-09-24 that v2.3 already shows are not repeated.

| ID | the owner's words | what it changes | header | in v2.3 | in today's header |
|---|---|---|---|---|---|
| 1.8 | "separate functions that are chained together. One should make the decision, one should do the acting" | Route decides and sends nothing; Act carries out; Recognize = Route + Act | recognizer.h | no | yes |
| 1.8.1 | SAM3 "Yes, correct"; keyboard "Might need to move to a different folder with a single file"; system/ "Doesn't sound to me like system/* is the right word" | SAM3 is its own module and header; system/ is runtime/; keys/keys.py | sam3.h (new), runtime.h (was system.h), app.h (keys/) | no | yes |
| 1.8.2 | "I agree with everything said here." | services first, then systems, in the owner's terms | README, every header | no | README only (2026-10-01) |
| 3.2.3 | "This should not be part of main ... Don't increase the loading time of main.py" | no dependency check in main; the preflight is its one place | runtime.h, app.h | no (v2.3: 'run first in main') | yes |
| 3.3 | "Everything, should it be necessary, be 'loaded eagerly' - I don't want load times to slip into the app runtime." | everything loads at start, nothing during the run | app.h | no | yes |
| 5 | "Good Fix & Choice for keybindings" | global keys F1 quit, F2 clear, F4 kill, F5 talk; letters never act | app.h | partly (F4 only) | yes |
| D8 | "option A" | every drawing value lives in config | app.h | no | yes |
| D13 | "Yes!" / "Already Addressed this stupid narrative." | the laptop voice's module loads at start only when selected | audio.h | no | yes |
| D15 | "You win." / "I agree with your proposal." + "the app should simply call a single function that 'builds' all the services" | ONE function builds every service (AppServicesCreate) | app.h | no | yes |
| C.1 | "Why does it only hold the mean....?" then "Record everything and calculate metrics later! Keep P25, P50, P75, P95, P99, min & max." | the perf record: every event, every frame | log.h, app.h | no | yes |
| R7 | "Make this configurable inside the config folder, default to 5s." | PERF_FLUSH_SECONDS = 5 | log.h | no | yes |
| V1 | "Option A" | the 20 slowest frames, no threshold | log.h | no | yes |
| M3 | "I meant what ROADMAP.md said." | the e2e perf stage (command -> action) | log.h, dji_app.h, app.h | no | yes |
| Q3 | "option A" | GPU sampling through pynvml | log.h | no | yes |
| Q4 | "test/scripted_e2e_run" | feed.py is test/scripted_e2e_run.py, a separate program | app.h | no | yes |
| U6 | "Option A" | the phone check every 2 s | dji_app.h | no | yes |
| P1 | "option A" (2026-09-28) | the preflight checks only the selected camera | video.h | no | yes |
| O3 | "option A" | one more frame read after a short wait | video.h | no | yes |
| O4 | "Of course, the message should be fixed." | with GATE=vlm the refusal names Gemma | perception.h | no | yes |
| TR16 | "Correct option A: let me put it this way - will YOU ever remember that the git history has this feature? I don't think so, no. Even when you check git histories you only check the messages, rarely what actually changed. Option B: This is what we'll do." | GATE=vlm and GATE=either stay and are tested; working code is never deleted because git keeps it | perception.h | — | not stated |
| S1 (3) | "Yes, run the benchmark. Although, I'd be inclined to say that I agree with you, and am very close to giving you the greenlight here. Just bench it to make sure." (2026-09-29) | a detect encodes the frame once, then runs each concept | sam3.h | no | yes |
| S7 (3) | "WHY HAVENT WE DONE THE CHEAPER OPTION UP UNTIL NOW???? IM SURE IVE FLAGGED THIS IN THE PAST! WHAT THE FUCK CLAUDE! OF COURSE WERE SUPPPOSE TO DO THE CHEAPER OPTION YOU MENTIONED! WHAT THE FUCK!" + "You already know my answer, in this case." | SAM3 saved once in nf4; the loader loads the ready weights | sam3.h | no | yes |
| S2 | "Option A needs to be kept in the backburner, but currently option B is unfortunately what we'll go with. Ideally, we should strive for option A, but the technical debt is too much right now - a new python process API for us, a way to sync & retrieve image data from a memory ring, and to keep SAM3 always up-to-date and not have synchronization problems is not an easy problem to solve just like tha | SAM3 runs in the app's process (its own process: after the freeze) | sam3.h | yes | yes |
| L1 | "Why isn't this done already?" | warm-ups at start: one plan through Gemma, one SAM3 pass; a row is UP only after its warm-up | gemma.h, recognizer.h, sam3.h | no | yes |
| L2 | "Lets try it." | the gate's own boxes are the first drawn update | perception.h | no | yes |
| J3 (3) | "Yes, just keep it in util/" (2026-10-01) | step_text stays in util/ | util.h | yes | yes |
| G6 | "nah, forget it." | fatal.py keeps its name | runtime.h | yes | yes |
| KI2 (2) | "Option A, although I have a question - Do you really not have another way to bench this?" (2026-10-01) | a Gemma request records llama-server's own timings | gemma.h, log.h | no | gemma.h yes; log.h no |
| T1 (2) | "T1 - THEN PUT "STOP ALREADY" AS PART OF THE COMMANDS IN THE EMERGENCY COMMAND TABLE!" (2026-10-02) | the emergency is a table of whole commands | recognizer.h | no | NO |
| STOP1 (3) | "No, that sentence should be "wait 10s" still. What the hell are you saying??? "STOP" WITHOUT AYNTHING ELSE SHOULD STOP REGARDLESS OF THE MODE OF FLYING" (2026-10-02) | a stop word alone halts in every mode; with a duration it waits | recognizer.h | no | NO |
| AUTO1 | "Yes, ofcourse, what the hell are you saying claude? That is why we have a trigger-word for operations like these." (2026-10-02) | auto acts only as the whole sentence | recognizer.h | no | NO |
| TN2 | "NO! I DIDNT JUST DESIGN IT ON THE TWENTY SECOND! IT CARRIED OUT THROUGHOUT THE WHOLE FUCKING PLAN! READ THE HANDOFF DOC ONCE AGAIN! READ THE API HEADERS WE DEVELOPED! CLAUDE! WORK DETERMINISTICALLY FOR THE LOVE OF GOD!" (2026-10-02) | several highlights at once, each its own task until give-up or clear | perception.h | partly (VisionClear(TaskId); 'one at a time' noted as the only form built) | NO: 'replaces the live one' |
| T3C | "Keep it to "clear all". Although, we technically should not have an issue to terminate specific highlight threads, If I remember the design correctly. Otherwise, tell me where I went wrong with my thinking and I'll correct myself." (2026-10-02) | 'clear all' is the form in use; stopping one task is possible | perception.h | yes (0 = clear all) | no task id any more |
| T3C (2) | "Then we should maintain another pain for "active jobs", on which we can click to focus/delete." (2026-10-02) | a pane of active jobs; a click focuses or deletes one | app.h, perception.h | no | NO |
| JR15 | Q116 "option A"; O2 "Correct"; O10 "Correct. Instead of making it nondeterministic, you could hardwire "a little" or "a bit" to a constant value in that range, say 1 meter." (2026-10-01) | 'a bit' / 'a little' is exactly 1 m | recognizer.h | no | NO |
| DES1 | "JUST A SECOND AGO WE SHOWED THAT THERE WAS AN INCONSISTENCY BETWEEN THE IMPLEMENTATION OF THE DESIGN AND THE ACTUAL DESIGN ITSELF! ... How many of these ruling are actually relevant When considering that we ACTUALLY HAVE TO USE OUR DESIGN IN OUR CODE AND NOT SOMETHING ELSE!?" (2026-10-02) | the design decides; the code follows | every header | — | — |
| API1 | "This is not post freeze claude. We were about to freeze because I thought we were matching the current header API. We are not. The Implementation of the python code, and the API headers we devised should be completely identical. of course, there are systems that we haven't converted to API headers, and that is a problem. There should be a 1:1 correspondance between the API headers and our whole p | headers and code 1:1 before the freeze | every header | — | — |

## Rulings from the spec's owner sections (no ledger ID)
| date | where | the ruling | header | in v2.3 | in today's header |
|---|---|---|---|---|---|
| 2026-09-21/22 | refactor handoff 4a, lines 57-59 | "HIGHLIGHT = gate, then a persistent record re-detected ... until the 8 s give-up or CLEAR"; "Task cap VISION_MAX_TASKS = 8" | perception.h | yes | the cap yes; "persistent" overruled by "replaces the live one" |
| 2026-09-22 | the owner's messages (session transcript) | one thread per detection query, up to 8; "Clear Was pressed for this specific/All detection Queries"; "we stopped doing that BECAUSE it was inaccurate" (Gemma boxes) | perception.h | yes | clear-one removed; a dead Gemma box path is in the code |
| 2026-09-23 | spec line 255 | "a dispatcher ... spawns one thread per task, max 8. Count is fire and forget. A highlight thread lives until clear or give-up. Only the SAM3 forward is serialized." | perception.h | yes | as above |
| 2026-09-23 night | spec "object lifecycle and backends" | each module gets its services or callbacks in its constructor; every class has close(); process handles are passed, never the Supervisor | every header | partly: v2.3 perception.h still gives each request its own callback | yes: one VisionSinks at create |
| 2026-09-24 | spec "Owner rulings 2026-09-24 (later)" | each part owns its status row; the board only asks | runtime.h | yes | yes |
| 2026-09-24 | spec | "Yes, delete trace.py." | log.h | yes | yes; LogTraceFile still reads old sessions |
| 2026-09-25 | spec | native programs only from config.NATIVE_BIN_DIR; perf.jsonl always on | runtime.h, log.h | no | yes |
| 2026-09-26 | spec | the headers stay, for the owner to read the design; every Python API change updates its header in the same change | every header | — | followed in the wrong direction on 2026-09-26 (the header was changed to fit the code) |

Rows not found in the ledger by ID: none
