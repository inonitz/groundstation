# Track 1 handoff — self-hosted project tracker (2026-09-10)

For the Track 1 subagent. You own ONE job: help the owner self-host a project tracker and document it.
You do not touch the voice-drone code. Track 2 (the system itself) is handled by the owner and another
session; stay out of it. Work directly with the owner, in your own session, not in the Track 2 chat.

## 0. Read this first (plain summary)
The project is a Hebrew voice interface to a drone. It has grown many parallel work topics and research
threads that are currently tracked only in chat and in docs/NOTES.md. That does not scale for a
multi-person team. Track 1 stands up a real tracker so topics, tasks, and research subtopics live in one
place. Your deliverables: a scripted install, a setup runbook in this repo's handoff style, and the
tracker seeded with the initial structure in section 5. The full project state is in
docs/active/2026-09-09-project-state-and-reorientation.md; read its section 7 for the two-track split.

## 1. Objective
Give a team of four (three technical, one non-technical) one place to see work topics, the tasks under
each, and ongoing research broken into subtopics. Self-hosted, free, no per-seat cost, owner-controlled.

## 2. Owner rulings (verbatim intent, 2026-09-09/10)
- The tracker is ON. It is not optional and it is not parked.
- NOT Plane. The owner read Plane's pricing and does not want it.
- Self-hosted and free, a genuine Jira alternative.
- It must divide three things cleanly: current work topics, the tasks under them, and ongoing research
  efforts in subtopics.
- Host it on a reliable, always-on machine, NOT the 8 GB demo laptop (the laptop's GPU and memory are
  needed for the models).
- Document everything properly, in the style of this repo's handoff docs.

## 3. What to produce (deliverables)
1. A scripted, repeatable install (Docker Compose preferred; script it, do not install by hand — this
   project's container wipes ad-hoc installs on rebuild). Put the script and compose file under
   tools/ (propose the exact path to the owner first).
2. A setup + operations runbook in docs/active/, this handoff's style: install, first-run, backup and
   restore of the data volume, upgrade, and how to reach it on the LAN.
3. The tracker seeded with the section 5 structure.
4. A short "state" note when done: what runs, where, how to back it up, what the owner must still do.

## 4. Recommended tool and the alternatives (owner chooses; this is a recommendation, not a decision)
- OpenProject (recommended). GPL, free to self-host, no seat cost. Its hierarchy fits exactly: projects
  for topics, subprojects for research subtopics, work packages for tasks, plus a built-in wiki for
  research write-ups. Docker Compose deploy, about 4 GB RAM. Mature and stable.
- Huly (alternative). Modern Linear-and-Notion feel, combines issues, documents, and chat. Heavier: it
  wants 8 to 16 GB RAM and more setup. Pick this only if the owner wants the modern feel and the host
  has the memory.
- Redmine or Leantime if the owner wants something lighter; both free and self-hosted, both simpler.
- Not Plane (owner ruling).
Present the trade-off to the owner and let them pick before you build.

## 5. The structure to seed (from the reorientation doc section 7)
Create one topic (project) per line; put its research as subtopics (subprojects or wiki), and leave the
concrete tasks for the owner and team to fill:
- Perception: SAM3 highlight/count, low-light image benchmark, human-labelled vision truth.
- ASR: whisper Hebrew noise robustness (e2e benchmark), English noise (Parakeet, done — archive it).
- Language/routing: the single-model Gemma chain, the negation guard, military slang, operator-mission
  context.
- Vision-conditioned action (challenge 3.1): mark a target, then approach or pass an opening.
- Architecture: this system vs llm_to_action, and their eventual merge.
- Research: deterministic VLM-in-the-loop actions, behaviour-tree production with a VLM, reliability and
  feasibility testing.
- Engineering process: whole-project end-to-end benchmark, per-system human-written test suites (NOT
  written by an agent), dev vs feature vs production branches, CI/CD.
- Repo cleanup: per docs/active/2026-09-09-repo-cleanup-draft.md.

## 6. Host and environment facts
- Do NOT host on the demo laptop (ASUS ROG Strix G16 G614PP, RTX 5070 8 GB — the model machine).
- Per project memory the reliable always-on machine is the desktop workstation (HUANANZHI X79-ZD3,
  RX 7900 GRE 16 GB, NVMe, AX210 WiFi). Confirm its current status and address with the owner before
  you target it; that memory is from 2026-08-21 and may have changed.
- A tracker is CPU + database only. It does not need the GPU. ROCm health on the X79 is irrelevant here.
- Prefer wired Ethernet for the host. Put the data on a persistent volume and script a backup.
- A small always-on VPS is a fine fallback if the owner prefers; the same compose file applies.

## 7. Standing rules for you (the Track 1 subagent)
- THE HUMAN OWNS GIT. You run no git writes: no add, commit, push, rm, or branch changes. Prepare the
  files; the owner commits. Suggest commands with absolute paths; the owner runs them.
- The human runs host-privileged commands (Docker, ports, firewall, the workstation). You prepare exact
  copy-paste commands with absolute paths; the owner runs them and reports back.
- Script every install. Do not install by hand. The dev container wipes ad-hoc installs on rebuild.
- Document decisions in the repo docs the same turn you make them. Chat is lost; the docs are not.
- Recommendations are not decisions. Anything the owner has not ruled stays open.
- Do not stream into the owner's Track 2 chat. Work in your own session. Report to files, not chat.
- Stay in your lane: do not edit the voice-drone code, the benches, or Track 2's docs. Do not touch
  docs/private/ (it is gitignored team-and-judge material, not relevant to you).
- Use the repo's RTK wrappers for shell work (rtk read / ls / grep / git status). The plain Read, Edit,
  and Write tools are denied in this workspace; edit files with Bash heredocs and sed.
- Be a critical pair programmer: give an objective, the cheapest path, and the single strongest reason
  against, before a non-trivial action. No pleasing.

## 8. Gotchas
- The "laptop cold-reboots under load" note in memory is about an OLD ASUS TUF unit being returned, not
  the current demo laptop and not the workstation. Do not repeat it as a workstation risk.
- Docker inside the project's dev container is nested; host the tracker on the workstation or a VPS, not
  inside the dev container.
- Back up the data volume from day one. A tracker with no backup is a single-disk risk.
- Keep the tracker off the model laptop's resources; a heavyweight tracker (Huly) on the demo machine
  would fight the GPU workload.

## 9. Not in scope
- No drone, no aircraft, no control commands. You never touch that path.
- No changes to the voice-drone code, benches, or Track 2 documents.
- No git writes. No repo cleanup execution (that is Track 2's, per its own draft).
- No reading or moving docs/private/.

## 10. Where to look next
- docs/active/2026-09-09-project-state-and-reorientation.md section 7 — the two tracks and the topic list.
- docs/active/2026-09-09-repo-cleanup-draft.md — the branch and process proposal that CI will build on.
- CLAUDE.md — the owner interaction protocol and the git ownership rules, in full.

## 11. Cross-check: what the other handoff docs carry, and what applies to you
The prior handoffs (2026-09-05, -07, -08, the 2026-08-26 manager brief) all carry the same cross-cutting
context. What of it applies to a tracker subagent, and what does not:
- APPLIES: the human owns all git; the owner-interaction protocol (address every point, one idea per
  bullet, decisions into docs immediately, recommendations are not decisions, concrete absolute-path
  commands, short reports, no yapping); script every install; RTK wrappers and heredoc edits because the
  Read/Edit/Write tools are denied; be a critical pair programmer.
- DOES NOT APPLY (deliberately excluded, so you are not confused): the drone-safety rules (you send no
  drone commands at all); the mock-vs-real control targets; the measurement invariants (temp 0, one model
  on the GPU, Wilson/McNemar) — those are for the benchmarking lane, not a tracker; the parallel agent
  lanes and the frozen projects/integration/ — you do not touch code, so lane confusion cannot arise.
- ONE THING THE OTHERS HAVE THAT THIS ONE INTENTIONALLY OMITS: a measurements section. A tracker has
  nothing to measure. If you later benchmark host resource use, add it then, with real numbers.

## 12. Open decisions (ask the owner before you build — added on cross-check with the prior handoffs)
Every handoff in this repo carries an "open decisions" list, because recommendations are not decisions.
Yours, unsettled until the owner rules:
- Which tool: OpenProject (recommended) or Huly (modern, heavier). Owner picks before you deploy.
- Which host: the desktop workstation, or a VPS. Confirm the machine and its address.
- The install path in the repo for the script and compose file (propose tools/tracker/, confirm).
- Whether the wiki lives in the tracker or stays in docs/. Recommend the tracker for team-facing research.
- Access model: LAN only, or reachable off-site (VPN vs exposed port). Security choice, owner's.

## 13. First steps (resume checklist — how to start)
There is no hard deadline; the judge meeting is cancelled. Do it right, not fast.
1. Read this doc, then docs/active/2026-09-09-project-state-and-reorientation.md section 7, then the git
   ownership and owner-protocol parts of CLAUDE.md.
2. Put the section 12 open decisions to the owner as numbered questions. Wait for the rulings.
3. Once the tool and host are chosen, write the scripted install + compose file (do not run privileged
   host commands yourself — hand them to the owner).
4. Stand it up with the owner, confirm it is reachable, and script a data-volume backup on day one.
5. Seed the section 5 structure. Write the setup runbook in docs/active/ as you go, not after.
6. Finish with the short state note (section 3, item 4). Do not touch Track 2.

## 14. Kickoff prompt (paste this into a fresh session to start the Track 1 helper)
You are helping me self-host a project/task manager for a multi-person robotics project (a Jira
alternative, NOT object tracking). Read your full brief first, in this repo:
docs/active/2026-09-10-track1-tracker-handoff.md — it has the objective, my rulings (self-hosted,
free, NOT Plane), the recommended tool (OpenProject; Huly as the modern alternative), the host
guidance (my desktop workstation, not the 8 GB demo laptop), the structure to seed, and the standing
rules (I own all git and all host-privileged commands — you prepare exact copy-paste commands and I
run them; script every install; document in the repo docs; do not touch the drone code or
docs/private/). Then put your open questions to me as a numbered list — the tool, the host machine,
the install path, and the access model — and wait for my answers before you build anything. There is
no deadline. Do it right.
