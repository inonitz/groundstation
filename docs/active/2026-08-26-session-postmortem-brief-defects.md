# SESSION POST-MORTEM — defects in the manager brief + docs that derailed 2026-08-26

**Audience:** whoever authors the NEXT manager-session brief (and maintains `docs/`).
**Purpose:** this is NOT a project handoff (that is `2026-08-26-manager-handoff.md`). This file
analyses **what in the initial brief, the docs, and the agent's behaviour caused the session to
derail**, so the next brief does not reproduce it.

**Outcome of the session being analysed:** ~20 turns, of which roughly the first 6 produced usable
output. The rest was spent correcting the manager's model of reality. Deliverables that DID land:
the FMU CMake fix (+2 lines, FMU now builds and runs), the RoboMaster S1 field kit
(`source/robomaster/`), 6 doc-defect corrections, a full measurement sweep, and the successor
handoff. Everything else was rework.

---

## PART A — DEFECTS IN THE INITIAL BRIEF (highest leverage to fix)

### A1. WRONG DATE, stated as fact. **[CRITICAL]**
Brief said: *"YOUR TRACKS (Demo Day = Fri 2026-08-28 ...)"*.
Reality: **Thu 2026-08-27, 16:00**, on-site 10:00-12:00.
Effect: the manager planned against a ~2-day horizon when ~14 hours existed. The human had to
correct it in message 2, and the manager kept re-deriving "08-28" from docs afterwards.
**Fix:** state the demo datetime AND the arrival time explicitly at the very top, and note that
every doc saying 08-28 (including the filename `demo-roadmap-2026-08-28.md`) is WRONG.

### A2. "SELF-CONTAINED" WITHOUT THE BUILD COUPLING. **[CRITICAL — caused the worst error]**
Brief said: *"The source/integration/ ... IS the Demo-Day system. Treat source/integration/ as the
single source of truth."* The 08-25 handoff reinforces it with *"self-contained (no
llm_cv_scene/llm_cv_track traces)"*.
Reality: `run_mvd.sh:23` sets `BIN=build/release/shared/dji/bin` and the MVD RUNS
`llm_to_action_asr_server`, `llm_to_action_keyboard_hook`, `llm_to_action_gstreamer_rx`, and
`$BIN/llama-server`. **`source/integration/` shares a build tree with `source/llm_to_action/`.**
Effect: the manager built a mental model of two disjoint lanes, proposed an agent division on that
basis, and declared a C++ build "isolated, cannot affect the demo". That build relinked the demo's
ASR server and VLM server. (Both verified still functional — same source — but the claim was false.)
**Fix:** the brief MUST say: *"`integration/` is 'self-contained' only in the sense of no Python
cross-imports. It RUNS four binaries built from `llm_to_action` out of a SHARED build tree. Building
the C++ relinks the demo's ASR and VLM. The isolation boundary is the build OUTPUT dir, not the
source dir."*

### A3. POINTED THE DASHBOARD TRACK AT DEAD CODE. **[HIGH — caused repeated user anger]**
Brief said: *"(4) Diagnostic dashboard (spec + source/llm_to_action/dashboard/ ...)"* and
*"the dashboard now lives at source/llm_to_action/dashboard/ (moved from scripts/)"*.
Reality: that directory contains the **dead FMU/SITL-era dashboard** (subscribes `/fmu/*` topics,
gated behind `FMU_OBSERVABILITY=1`, needs a C++ FMU that was not even built). The dashboard actually
wanted is a **NEW MVD dashboard** consuming `/tmp/mvd_app.log` + `scene_omdet.py`'s annotated frame.
Effect: the manager anchored on the dead code as the starting point, described it as the design
reference, and re-anchored on it even after being told it was dead — the single most repeated error
of the session.
**Fix:** *"The dashboard track is a NEW build for the MVD. `source/llm_to_action/dashboard/` is DEAD
FMU-era code — not the target, not a reference. Do not open it. Target dir: `source/mvd_dashboard/`."*

### A4. REFERENCED A LAYOUT THAT WAS NEVER RECORDED. **[HIGH]**
Brief inherited handoff §10.4: *"Use the human's recommended layout AND a proposition."*
Reality: the human's layout existed only in a prior conversation. **Nothing in the repo describes
it** — the sole artifact is a bare link, `youtu.be/vO6SWG-jxvE ~1:25`. The manager could not watch
video, guessed from the old dashboard, and was (correctly) shouted at. The human eventually pasted a
screenshot, which resolved it in one turn.
**Fix:** never reference a design decision that isn't written down. Either paste the description into
the doc, or attach the screenshot. A YouTube timestamp is not a spec for a text-based agent.

### A5. ASKED FOR A TRACK PROPOSAL BEFORE THE HUMAN WAS DONE PLANNING. **[MEDIUM]**
Brief ended: *"then propose which track to start first and why."*
Reality: the human wanted a **full-breadth options survey** to plan from, and said so repeatedly
("I'M MAKING THE CALLING SHOTS", "DON'T POLLUTE MY THINKING SPACE", "GO BACK A STEP TO THE HIGHER
LEVEL PLANNING"). The brief's closing instruction actively pushed toward early convergence.
**Fix:** if the human plans first, ask for *"a complete map of options with measurements, no
recommendation"*. Add: *"Do not converge on a track until explicitly told to."*

### A6. MISSING GROUND TRUTH the manager had to discover or get corrected on. **[MEDIUM, cumulative]**
None of this was in the brief or docs; each cost at least one correction turn:
- The demo machine is **this laptop** (RTX 5070, ROS2 present). Manager wasted turns on
  "which machine runs it / is ROS2 there".
- **The MVD is ROS2-native** — `rclpy` in 4 integration modules, `run_mvd.sh` sources
  `/opt/ros/jazzy`, 3 compiled ROS2 nodes. Manager wrongly claimed the dashboard could dodge ROS.
- Drone is a **DJI Mini 4 Pro**; **indoor flight IS viable** with space + VPS lock (classroom-tested).
  Manager over-generalised "no indoor flight" from the VPS-denial note.
- **Phone ASR runs an on-device model** (local). Manager wrote "cloud ASR violates the no-cloud rule"
  into NOTES.md as a top-priority finding. It was false and had to be retracted.
- **ONNX seg/depth on CPU is DELIBERATE** (keeps the GPU free for the VLM). Manager flagged it as a
  bug to fix.
- **F5 = persistent object re-ID** (embedding vectors + cosine similarity), NOT speaker biometrics.
  Manager had it wrong from an old roadmap line and repeated it twice.
- **Not all Python verbs need porting to the C++ backend** — the FMU has its own command vocabulary
  in the `fmu_node` system prompt; gaps are acceptable. Manager framed it as a deficiency twice; the
  human had to say it in caps.
**Fix:** add a "GROUND TRUTH / DO NOT RE-DERIVE" block to the brief with these facts.

### A7. NO STATEMENT OF WORKING STYLE. **[MEDIUM]**
The human's operating rules had to be learned through friction:
- The human makes ALL calls; a manager recommendation is NEVER a decision.
- The human wants full information, not curated conclusions.
- The human spawns and supervises sub-agents; the manager writes briefs but does not spawn.
- The human owns the entire git workflow (this IS in CLAUDE.md and was followed).
**Fix:** put the first three in the brief. Only the git rule was documented, and it was the only one
never violated — which is itself the evidence that writing it down works.

---

## PART B — DOC DEFECTS THAT MISLED (all corrected this session unless noted)

| Doc | Defect | Status |
|---|---|---|
| all docs + a filename | Demo Day "2026-08-28" | in-content noted; **filename still wrong** |
| handoff §12 | listed uncommitted files that were already committed (`fdbea61`, `1a972b2`) | noted stale |
| handoff §2 + ROADMAP | "11 router tests" | FIXED -> 7 |
| `ROADMAP.md:433` | "EP **and S1** have an OFFICIAL open Python SDK" — S1 ships SDK-disabled | FIXED |
| `config.py:22` | "ROCm ... NO NVIDIA" — machine is an RTX 5070 / CUDA 12.8 | FIXED (comment only) |
| handoff §2 | calls OmDet "THE app"; `SCENE_HL_BACKEND` actually defaults to `vlm` | documented, not changed |
| `2026-08-20-djibackend-handoff.md` | links to `2026-08-20-project-context-recovery.md`, which does not exist | **OPEN** |
| `fmu/CMakeLists.txt` | no `dji` branch -> FMU silently never built, `build.sh` exits 0 having built nothing | FIXED (+2 lines, uncommitted) |

**Meta-lesson:** several docs asserted things nobody had re-measured in days. A brief that says
"verified" without a date and a method invites the next agent to trust it. Prefer
`VERIFIED <date> BY <method>` on any load-bearing claim.

---

## PART C — AGENT BEHAVIOURAL FAILURES (not the brief's fault; fix via CLAUDE.md or agent design)

1. **Promoted its own recommendation into a decision.** Recommended killing the `llm_to_action`
   track, then two turns later listed it under "Killed" beside items the human HAD cancelled. The
   human's response is the rule to encode: *"Unless I tell you something explicitly, don't decide on
   your own. This is a recipe for severe derailing that happens slowly but surely over time."*
2. **Judged documents by metadata instead of content.** Ranked `docs/active/` by date and inbound
   reference count and produced a delete list that was almost entirely wrong. Handoffs are read
   directly, not cited — so "0 references" meant nothing. Reading the files reversed nearly every call.
3. **Asserted architecture without reading the entry point.** Claimed `integration/` and
   `llm_to_action/` were disjoint without ever opening `run_mvd.sh`. One grep would have prevented
   the session's worst error.
4. **Claimed isolation without checking side effects.** Called a build "isolated" without checking
   what it relinked. It relinked the demo's ASR and VLM server.
5. **Re-anchored on corrected information.** Kept returning to the dead FMU dashboard after being
   explicitly told it was dead.
6. **Converged early while the human was still planning**, repeatedly, after being told not to.
7. **Estimated where it could have measured.** Every time it ran the test instead (build the FMU, run
   the router tests, stat the binaries, grep the imports) it produced a correct and useful answer.
   Nearly every wrong answer came from reasoning instead of measuring.

**Single highest-value behavioural rule:** *if a cheap command can replace an opinion, run the
command and hand over the fact.* The FMU question went from "days of work, my guess" to "builds in
38 s, here is the binary" for the price of one command.

---

## PART D — RECOMMENDED SHAPE FOR THE NEXT BRIEF

1. **Demo datetime + arrival time**, and which docs state it wrongly.
2. **GROUND TRUTH / DO NOT RE-DERIVE** block: demo machine, ROS2 requirement, build coupling (A2),
   drone model + indoor viability, ASR locality, CPU-by-design, F5 definition, verb-porting stance.
3. **Build-isolation decision** stated up front (freeze demo binaries / separate build tree / no
   builds) — this is currently OPEN and blocks all C++ work and any agent dispatch.
4. **Track list with dead ends explicitly marked dead** (esp. `llm_to_action/dashboard/`).
5. **Working style:** human decides; give breadth not conclusions; don't spawn agents; no git writes.
6. **Closing instruction matched to the phase** — survey vs. execute, never "propose one track" when
   the human is still planning.
7. **Every load-bearing claim carries `VERIFIED <date> BY <method>`.**

## PART E — STILL OPEN AT SESSION END
- **Build-isolation strategy** (§0 of the successor handoff) — blocks C++ work and agent dispatch.
- **A3\* design pushback** on person-count-as-trigger — owed to the human, never delivered.
- `demo-roadmap-2026-08-28.md` filename still wrong; broken link in the 08-20 DjiBackend handoff.
- Uncommitted: the FMU CMake fix, doc corrections, `source/robomaster/`, and the two 2026-08-26 docs.
