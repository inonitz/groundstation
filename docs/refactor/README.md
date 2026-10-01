# Refactor agents: the shared rules

Four agents work the harden2 task list (docs/task-active-harden2-refactor-handoff.md, section 9d)
in parallel. The main agent wrote this file and each agent's brief. Every agent follows this file.

| section | content |
|---|---|
| Read first | the reading order |
| The agents | names, tasks, ROS domains |
| Hard rules | safety, git, the files you never edit |
| Locks | LOCK.md and tools/lock.sh |
| Checks | what every task ends with |
| Your doc | brief, notes, progress |
| Waiting and questions | dependencies between agents; questions for the owner |

## Read first
1. Your doc, docs/refactor/<your-name>_doc.md. The brief at its top is your order.
2. This file.
3. docs/guidelines.md: "All guidelines at a glance", then "Project rules learned in harden2".
   CLAUDE.md loads by itself.
4. docs/task-active-harden2-refactor-handoff.md, section 9d: the full text of your tasks. It wins
   over the short form in your brief.
5. docs/spec-harden2-cleanup.md: the section "Owner rulings 2026-09-27 and 2026-09-28" (the
   approved design), and the rows of "Decision ledger 2026-09-26 .. 2026-09-28" that your brief names.
6. docs/HISTORY.md: the entries your brief names. The newest entries are at the end.

## The agents
| name | tasks (9d), in order | ROS_DOMAIN_ID |
|---|---|---|
| recognizer | A1 -> B1 -> A2 | 11 |
| perf | C1 -> C2 -> C3 -> C4 (the layout D1-D7 comes later, in a second brief) | 12 |
| bench | B5 + B6 -> B3 -> B7 -> B2 | 13 |
| investigator | E2 -> E1 | 14 |

## Hard rules
- Safety: never send an arm, takeoff, land, stick, velocity or motor command to a real drone.
  Control runs only against the mock at 127.0.0.1. Never set DJI_REAL. The scripted run refuses
  anything but the mock; keep it so.
- Git: no git writes. No add, commit, stash, checkout, restore, reset, rm, mv, branch or worktree.
  Read-only git (status, log, diff, show) is fine. Delete and move files with plain rm and mv.
- The other agents' work and the owner's commits stay. Never revert a file to HEAD. Never undo a
  change you did not make.
- If the tool refuses an rm, do not retry. Write the exact command under "For the owner" in your doc.
- Never edit: docs/HISTORY.md, docs/spec-harden2-cleanup.md,
  docs/task-active-harden2-refactor-handoff.md, docs/task-active-harden2-session-log-2026-09-23.md,
  this file, another agent's doc, .claude/. The main agent owns them. Write a proposed HISTORY entry
  in your own doc instead.
- projects/integration_tts/ is frozen. Do not edit it.
- Read and search with the rtk wrappers (rtk read, rtk grep, rtk ls, rtk find).
- Script every install: a new package goes into tools/devenv/install-runtime-deps.sh, and into
  system/deps.py when the app needs it. Lock the install script first.
- Never ask the owner. Write the question under "OPEN" in your doc (an ID, the options, your
  recommendation first), then do other work.
- Style: docs/guidelines.md. Python lines under 90 characters; guard clauses; one statement per
  line; an explicit return; WHY comments. A try exists only in util/guarded.py. Prose in short
  sentences, one idea each. Banned words: wire, seam, load-bearing, sieve.

## Locks
The table is /root/groundstation/LOCK.md. Change it only with tools/lock.sh:
```
/root/groundstation/tools/lock.sh status
/root/groundstation/tools/lock.sh acquire <name> <resource>...
/root/groundstation/tools/lock.sh wait <name> <resource>...
/root/groundstation/tools/lock.sh run <name> <resource>... -- <command>...
/root/groundstation/tools/lock.sh release <name> <resource>...     # or: release <name> all
```

| resource | lock it for |
|---|---|
| gpu | any GPU work: llama-server (Gemma), SAM3, whisper, torch on CUDA. One GPU job at a time. |
| webcam | /dev/video* |
| display | a window: the whole-app test's Xvfb screen :97, or DISPLAY |
| suite | every pytest run, one module or all (the tests share ports and processes) |
| a repo path | a shared file, while you edit it |

The shared files (lock the path, edit, release at once):
- projects/integration_harden2/config/constants.py, config/__init__.py, config/defaults.py
- projects/integration_harden2/run.sh, README.md, test/README.md, test/support.py, test/test_log.py
- projects/integration_harden2/app/main.py, app/ui.py, log/__init__.py
- docs/spec-harden2-run-arguments.md, docs/api-harden2/README.md
- bench/README.md, bench/recognizer/README.md, .gitignore
- tools/devenv/install-runtime-deps.sh, tools/devenv/Dockerfile

A file that only you edit needs no lock; your brief lists them under "Yours".
- Take everything you need in one call: acquire is all or nothing. Release as soon as you finish.
- Keep a GPU turn short. Release gpu between measurement series, so another agent can run.
- A command longer than 9 minutes: acquire, run it in the background with its output in a file,
  and release when it ends.
- If you started llama-server or any other process, stop it before you release gpu.
- On BUSY or TIMEOUT: do other work from your list, then try again.
- Before you end a run: `tools/lock.sh release <name> all`.

## Checks (every task ends with all of them)
```
cd /root/groundstation/projects/integration_harden2
python3 -m flake8 --isolated --select=E30,E501,E70,E731 --max-line-length=89 .
python3 -m pyflakes .
python3 /root/groundstation/tools/audit_exceptions.py /root/groundstation/projects/integration_harden2
ROS_DOMAIN_ID=<yours> /root/groundstation/tools/lock.sh run <name> suite -- python3 -m pytest -q test/
```
- Run the suite twice. The baseline at the start (commit 9fc6c67): 215 passed, 2 skipped; lint
  clean; the audit prints "except handlers: 5".
- If a failure is in another agent's files, do not fix it. Note it in your doc, and run again after
  that agent's next checkpoint.
- A test you rewrite: say so loudly in your doc, with the ruling that changed the behavior. New
  logic gets a new test and a mutation check (break the code, see the test fail, restore the code).
- Sync the header in docs/api-harden2/ of every module you change.
- Y2: name every benchmark that imports a module you changed (rtk grep in bench/), and fix it.
- Update the current-state docs you affect: docs/spec-harden2-run-arguments.md (run.sh, settings,
  flags), projects/integration_harden2/README.md (layout), test/README.md (the test list),
  bench/README.md (the benchmark list). A README holds the current state, not history.
- Write the change-impact table (docs/guidelines.md, "Change-impact analysis") for each task.

## Your doc
docs/refactor/<name>_doc.md has these parts.
- Top: the brief. Do not edit it.
- "Notes": what you changed, where and why, for the next agent. Keep it current.
- "OPEN" and "For the owner": questions, and commands the owner must run.
- Bottom, "Progress": the first line holds your model ID and the output of `echo $CLAUDE_EFFORT`.
  Then one checkpoint entry per finished task, and at the milestones of a long task: the task ID,
  the files changed, the checks with their real output lines, the change-impact table, your
  self-check of each point of the task text in 9d, and a proposed HISTORY entry (measurements and
  verdicts).

## Waiting and questions
- Only the main agent ticks a task in 9d, after it validates the task. A task that needs another
  agent's task waits until that task shows [x] in 9d.
- One exception: bench's B3 needs only recognizer's JSON format. recognizer writes it in its doc,
  in the section "B1 JSON format", and bench starts B3 when that section is filled.
- If all your remaining tasks wait: release all, write "WAITING for <task>" at the end of Progress,
  and end your run. The main agent resumes you.
- Your final message to the main agent has at most 15 lines: the tasks done, the checks, OPEN
  questions, "For the owner" items, WAITING. The details stay in your doc.
