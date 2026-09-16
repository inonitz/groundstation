# llm_to_action — make it presentable for the judges (2026-09-05)

Author: groundstation-3c (manager). Executor: a new subagent, spawned by the owner.
Owner ruling date: 2026-09-05. This document stands alone. Read it in full before acting.

## 1. Objective

Make `projects/llm_to_action/` presentable for the judges' meeting.

Owner ruling on what "presentable" means, in priority order:

1. **DEMO POLISH — primary.** The system must run cleanly and look good live. The owner ruled
   this above code quality, in his words: "I lean towards option 2 more than 3".
2. **CODE-QUALITY CLEANUP — secondary and bounded.** The owner explicitly warned against assuming
   a large cleanup: "don't be so sure we're going to perform the QC cleanup to the degree that you
   expect". Propose before you cut. Do not start a large refactor on your own judgement.

Dropped by the manager: a separate "repo hygiene / CMake tidy" scope. The owner questioned it and
the manager withdrew it. Fix a build file only when a change of yours requires it.

## 2. What the judges will actually look at

`projects/llm_to_action/source/dashboard/` is the judge-facing surface. Its README calls it
"a lean browser dashboard for the off-board VLM autonomy stack". It shows, live:

- the annotated camera stream with detection boxes baked in
- the depth colormap
- the flight HUD with the detection list
- the VLM reasoning log, plus the objective and executed-command history

That is the demo. Treat the dashboard and the path that feeds it as the top priority.

## 3. Roles and rails

- The aircraft is NEVER real here. This is PX4 SITL and Gazebo, which is simulation, so it is safe
  for you to run yourself. Run it. Do not send any command to a real drone or a phone IP.
- The owner ruled Gazebo is CHEAP: "it takes a couple of minutes not an hour". So verify every
  behaviour-touching change in Gazebo. A compile is not proof of behaviour.
- You run NO git writes. Prepare a commit block in house style; the owner runs it.
- Do not weaken or bypass a safety check to make a demo pass.
- The tree already holds uncommitted work from another session, including changes to
  `source/asr/asr_node.{cpp,hpp}` and `source/keyboard/`. Do not revert or clobber them.
  `key_codes.cpp` was deliberately DELETED and inlined into `key_codes.hpp`.

## 4. Verified state — do not re-derive

The manager checked each of these on 2026-09-05.

| # | Fact | Evidence |
|---|---|---|
| 1 | `llm_to_action` is 12,084 lines of C++ across ROS2 nodes: `asr`, `dji_backend`, `fmu`, `perception`, `keyboard`, `frame`, `generic_backend`, `tello_backend`, `gstreamer_udp_cam_rx`, `dashboard`. | `wc -l` over the tree |
| 2 | There is NO top-level README for `llm_to_action`. Only `source/dashboard/` has one. A judge opening the project finds source and nothing else. | `ls projects/llm_to_action/*.md` |
| 3 | **The dashboard README's run command is STALE.** It says `python3 scripts/dashboard/serve.py`. That path does not exist. The real file is `projects/llm_to_action/source/dashboard/serve.py`. | `find`, verified |
| 4 | The dashboard directory also holds `run_sitl_demo.sh`, `assess.py`, `mock_data.py` and `dashboard.html`. | `ls` |
| 5 | **Silent-blank-dashboard trap.** All dashboard topics publish ONLY when the FMU runs with `FMU_OBSERVABILITY=1`. With the gate off the FMU publishes nothing and the dashboard shows no data, with no error. | `source/dashboard/README.md` |
| 6 | The SITL harness is `test/lib/sim_core.sh`. It is sourced, never run directly. It brings up PX4 SITL, Gazebo and the FMU, plus an optional VLM, in one tmux session. Scenarios live in `test/sitl-legacy/`. | `test/lib/sim_core.sh` |
| 7 | `source/fmu/fmu_node.hpp` is 2,858 lines and is the flight control loop. Its refactor is already scoped in `docs/active/fmu-cleanup-tasklist.md`, which carries its own rules. | `wc -l`, that tasklist |
| 8 | The dashboard depends only on the ROS runtime (`rclpy`, `cv_bridge`, `cv2`) plus the Python standard library. Its README forbids adding websockets, rosbridge or foxglove. Respect that. | `source/dashboard/README.md` |

## 5. Task 1 — demo polish (primary)

Goal: the owner starts the demo, and it works the first time, in front of judges.

Start by running the demo yourself in Gazebo and writing down every rough edge you hit. Your own
first-run experience is the best available proxy for the judges' experience. Then fix them.

Known items to fix, from the manager's read:

1. **The stale dashboard run path** (fact 3). Fix the README, and check every other command in it
   actually works from a clean shell.
2. **The observability trap** (fact 5). A judge-facing demo must never show a blank dashboard with
   no explanation. Either the demo launcher sets `FMU_OBSERVABILITY=1` itself, or the dashboard
   says plainly on screen that the FMU is running with observability off. Pick one and say why.
3. **`run_sitl_demo.sh`**: run it end to end. Confirm it brings up the sim and the dashboard fills
   with data. Report exactly what a first-time operator must do, in order.
4. **Startup and failure messages**: if a dependency, topic, model or port is missing, the demo must
   fail fast with a message naming the fix. It must not half-start or hang.
5. **Log noise**: the panes the owner shows on screen should be readable. Cut spam that carries no
   information during a normal run. Do not remove warnings or errors.

Anything else you find that would embarrass the system live is in scope. Report it before large
changes.

## 6. Task 2 — a top-level README (primary, low cost, high visibility)

Write `projects/llm_to_action/README.md`. It does not exist, and it is the first thing a judge opens.

Follow `docs/writing-style.md`. READMEs are current state, not an archive: a short introduction,
a section table, then only current content.

It must cover: what the system is, the ROS2 node graph and what each node does, how to build it,
how to run the SITL demo, and how to open the dashboard. Keep it honest. Do not describe behaviour
you have not run.

## 7. Task 3 — code-quality cleanup (secondary, BOUNDED, propose first)

The owner warned against a large cleanup. So:

- Do NOT begin the `fmu_node.hpp` refactor. It has its own tasklist and its own rules, and the
  owner has not ruled it in scope for this session.
- Instead, produce a SHORT ranked list of cleanup candidates you found while doing tasks 1 and 2:
  what it is, why it matters, and the risk of changing it.
- Send that list to the owner through the manager. Do not act on it until he rules.
- Exception: if a cleanup is required to make the demo work, do it as part of task 1 and say so.

## 8. Out of scope

- Any command to a real drone or a real phone IP.
- The desk-test lane and `integration_harden`. Another session owns that.
- Wiring `perception2/` or SAM3 into anything.
- `projects/integration/` is FROZEN. Never change it.
- Any git write.

## 9. Reporting

- Write the report to `/root/groundstation/docs/active/2026-09-05-llm-to-action-report.md`.
- House register per `docs/writing-style.md`: Objective, Setup, Results as neutral tables with every
  column, numbered Analysis, then Conclusions and open items. It must stand alone.
- Label any number you did not measure as "unverified".
- Put bulk output in files. Chat summaries stay short.

## 10. Cost discipline — read this

The manager runs on an expensive model, and every message between you and it costs a full turn of
the owner's budget. The owner is conserving and has told both sides to minimise messages.

- Do not message the manager for anything this brief or the repo answers.
- Send ONE message when the work is done.
- Send ONE message if you are blocked for more than 20 minutes.
- Send ONE message with the task-3 cleanup list when you have it.
