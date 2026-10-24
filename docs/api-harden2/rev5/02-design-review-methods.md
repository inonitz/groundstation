# Design review methods for the design-reviewer agent: what exists (searched 2026-10-07)

Objective: find an established method, or an existing Claude Code skill or agent, for a critical
system-design review of ONE design document by a subagent (the owner, 2026-10-07: "Relying only
on your thinking is a mistake, many people have already thought about our issue").

## 1. Established methods

| method | what it is | what it gives our reviewer |
|---|---|---|
| ATAM, SEI (Kazman, Clements, Klein) | the standard architecture evaluation: business drivers; quality-attribute scenarios in a utility tree; each scenario walked against the architectural approaches; the output is sensitivity points, tradeoff points, risks and non-risks | the walk: take each force of the sketch (a timing budget, a failure mode, a safety rule) as a scenario and trace it through the design; name the risk or the non-risk; name the sensitivity points (one decision that several forces hang on) |
| Design docs at Google (Ubl) | a design doc is reviewed for its trade-offs and cross-cutting concerns; goals and non-goals; alternatives considered; "a doc that reads like an implementation manual is a bad sign" | the gate on the document itself: trade-offs stated; alternatives named; cross-cutting concerns (errors, timing, safety) present |
| Pre-mortem (Klein, HBR 2007) | "the system has failed; list every reason"; prospective hindsight raises the finding of causes by 30 % (Mitchell, Russo, Pennington, 1989) | the reviewer's first pass: write the field failure story before reading for defects |
| First-principles check (the first-principles-skill, open source) | strip assumptions; ground truths; "remove a component; does the system still solve the problem?" | the YAGNI check, done as a removal test per component |

## 2. Existing Claude Code skills and agents

| source | what it does | fit |
|---|---|---|
| AhmedHabiba/architor: `challenge-assumptions` skill + `/review-component` command | an adversarial persona: "a senior architect conducting a design review; your reputation depends on catching problems"; "act as a different architect; forget that you proposed this design"; rules for "why this over X", "convince me", vague requirements turned into numbers, self-correction when the review gets agreeable; seven criteria rated pass / concern / fail: requirements alignment, technology fitness, integration integrity, failure analysis (blast radius; is the fallback wishful), security, operational readiness, scalability honesty ("what breaks first under 10x") | the best fit. It reviews ONE design file. The criteria are written for web services; they map to ours (timing instead of scaling, threads and ownership instead of services) |
| ntcoding/claude-skillz: `architect-refine-critique`, the `critique` agent | "Challenge the design ruthlessly"; finds what is wrong, what could be better, what could be simpler, the gaps; output in CRITICAL / HIGH / MEDIUM / LOW, each with what's wrong, why it matters, a fix; "include uncertain findings; false positives are better than missed issues" | the output format and the stance. Its checklist is DDD-specific (use-cases, bounded contexts) and is not ours |
| dsifry/metaswarm: `design-review-gate` | five reviewer roles in parallel (product, architect, designer, security, CTO); all must APPROVE; up to three rounds | too heavy; a product-feature gate; five agents |
| wshobson/agents `architect-review`; VoltAgent `architect-reviewer` | a "master architect" persona with long lists of patterns (microservices, Kafka, Kubernetes) and no method; one writes a delivery note with invented numbers ("40% improvement") | rejected: no method, no single-document focus, a fabrication habit |
| oimiragieo/agent-studio `architecture-review` | a command that calls a skill; the skill text was not retrievable | skipped |
| the docs: Claude Code subagents | a subagent is Markdown with frontmatter; `model` and `effort` are settable there | the "fable, medium" definition is possible |

## 3. The recommendation: what to build the design-reviewer from
One agent definition, assembled from the sources above; nothing invented:
1. The persona and the stance: architor's `challenge-assumptions` ("a different architect";
   "convince me"; numbers for every vague word; self-correct when agreeable).
2. The first pass: a pre-mortem. The reviewer writes the story of the system failing in the
   field, then lists the causes. Only then does it read for defects.
3. The walk: ATAM's scenario analysis over the forces of the document: each timing budget,
   each failure mode, each safety rule traced through the design; the output names risks,
   non-risks, sensitivity points and tradeoff points.
4. The criteria, architor's seven, mapped to a real-time single-machine system:
   requirements alignment (the forces and the rulings); ownership and concurrency (who owns
   each piece of state; every cross-thread path; a race); timing honesty (the budgets; what
   breaks first at twice the rates); failure analysis (blast radius; is the fallback wishful);
   integration integrity (every hand-off's protocol and ordering); operational readiness (what
   the operator sees when a part fails; the telemetry); simplicity (the removal test per
   component). Each rated pass, concern, or fail.
5. The gate on the document: Google's three checks (trade-offs stated; alternatives named;
   cross-cutting concerns present).
6. The output: the critique agent's format: CRITICAL / HIGH / MEDIUM / LOW; each with what is
   wrong, why it matters, a fix; "include uncertain findings"; written to the agent's own file.
7. The input: ONE design document, plus its drawing. Nothing else is required.

## Sources
- ATAM: https://en.wikipedia.org/wiki/Architecture_tradeoff_analysis_method
- Design docs at Google: https://www.industrialempathy.com/posts/design-docs-at-google/
- The pre-mortem: https://theuncertaintyproject.org/tools/pre-mortem and https://concepts.dsebastien.net/concept/premortem/
- architor: https://github.com/AhmedHabiba/architor (.claude/skills/challenge-assumptions/SKILL.md; .claude/commands/review-component.md)
- claude-skillz: https://github.com/ntcoding/claude-skillz (architect-refine-critique/agents/critique.md)
- first-principles-skill: https://github.com/awesome-skills/first-principles-skill
- metaswarm design-review-gate: https://openskillindex.com/skills/dsifry-metaswarm-design-review-gate
- wshobson/agents: https://github.com/wshobson/agents (plugins/comprehensive-review/agents/architect-review.md)
- VoltAgent: https://github.com/VoltAgent/awesome-claude-code-subagents (categories/04-quality-security/architect-reviewer.md)
- Claude Code subagents: https://docs.claude.com/en/api/agent-sdk/subagents

## 4. Methods for a real-time control system (searched 2026-10-07, after the owner's objection)
The owner: "We are not building web services, we're building a real time system for robotics."
Architor's seven criteria (security, scaling, vendor lock-in) are dropped. The methods below are
the ones the safety-critical and real-time fields use for a design review.

| method | what it is | the reviewer's use of it |
|---|---|---|
| STPA, Leveson and Thomas (MIT) | a hazard analysis for control systems: 1 the losses and the system-level hazards; 2 the control structure: controllers, controlled processes, control actions, feedback; 3 the unsafe control actions, four kinds: a needed action not given; a harmful action given; an action too early, too late, or out of order; an action stopped too soon or held too long; 4 the loss scenarios: why the controller issued the unsafe action, or why a correct action was not carried out (a delayed path, a wrong process model, missing feedback) | our system IS a control structure: the operator and the app control the aircraft; the feedback is the phone's replies and the frames. The reviewer models it and walks the four kinds of unsafe action for each control action: the mission, the stop, the manual switch, a vision job. It fits a drone with an operator in the loop exactly |
| HAZOP guide words, IEC 61882 | a deviation study: for every flow, apply NO, MORE, LESS, AS WELL AS, PART OF, REVERSE, OTHER THAN, EARLY, LATE, BEFORE, AFTER; a team asks what each deviation does | for every hand-off in the sketch (each queue, each message, each shared slot, each HTTP call): what if it is missing, duplicated, partial, late, early, out of order, or the wrong one. The message queue and the frame buffer get the full word list |
| FMEA | per component: the failure modes, the effect on the system, the severity, how it is detected, the response | per thread, per process, per queue: what fails, what the operator sees, who detects it, what the design does |
| the latency budget method (industrial control) | the sensor-to-actuator budget is a worst-case bound, decomposed into additive stages (sampling, transport, scheduling, execution, output); "the bound comes from analysis, and the test confirms it"; "p99 is not worst case" | the command-to-action budget (under 1 s) is decomposed hop by hop: listener, queue, main loop frame, trigger match, command queue, platform worker, HTTP; each stage gets its worst case, not its median; the same for the frame-to-screen path |
| the critical design checklist (Beatty, the System Safety list) | the items a review must cover for real-time software: expected errors handled; failure modes not handled; deadlock; the schedulability of every task; maximum task response times; jitter and end-to-end constraints; non-deterministic structures; task precedence; uncontrolled priority inversion; resource sizing | the concurrency section of the review, item by item, against the sketch's threads and queues |
| the ROS 2 real-time design rules | "the real-time threads should never be blocked on the non-real-time threads"; "prefer atomics to mutexes when possible"; no page faults and no heap allocation in the real-time path; "thoroughly test multithreaded code for deadlock and livelock"; measure minimum, maximum and average latency | the rules for the main loop and the frame path; a check that no blocking call sits on the owner thread; the atomics-over-mutex rule the owner already stated (SK4) |
| the pre-mortem, ATAM's scenario walk, Google's document checks, the first-principles removal test | from section 1 | unchanged |

What exists as a ready Claude Code skill for this: nothing found. The two agent collections hold
an "embedded-systems" developer persona (microcontrollers, RTOS, power modes) with no review
method; the one "embedded real-time software engineer" skill page holds no text. So the reviewer
is assembled from the methods above, not downloaded.

## 5. The recipe, revised
1. The stance: a different architect reviews; the design's author is not in the room. Every
   vague word becomes a number. (From the adversarial reviewer skills; the only part kept.)
2. The first pass: a pre-mortem. The field failure story, then its causes.
3. The control structure: STPA step 2 drawn from the document; then the four unsafe-action
   kinds for each control action; then the loss scenarios through the design's paths.
4. The deviation study: HAZOP's guide words over every hand-off in the drawing.
5. The timing walk: the latency budget decomposed per hop with worst cases, for the emergency
   path and the frame path; what breaks first at twice the rates.
6. The concurrency checklist: Beatty's items and the ROS 2 rules against every thread, queue
   and shared slot; no blocking call on the owner thread; atomics over mutexes.
7. FMEA per component: failure, effect, detection, response.
8. ATAM's output: risks, non-risks, sensitivity points, tradeoff points.
9. The document checks: trade-offs stated; alternatives named; cross-cutting concerns present.
10. The removal test: each component removed in thought; does the system still meet the forces.
11. The output format: CRITICAL / HIGH / MEDIUM / LOW; each with what is wrong, why it matters,
    the force it breaks, a fix; uncertain findings included and marked.
12. The input: one design document, with its drawing. The report goes to the agent's own file.

Sources added: STPA summaries at https://sassofia.com/wp-content/uploads/2024/10/Systems-Theoretic-Process-Analysis-STPA.pdf and https://arxiv.org/pdf/2604.05749 ; HAZOP guide words https://www.riskythinking.com/risk_assessment_toolkit/help/guide_words ; the latency budget https://promwad.com/news/latency-budget-industrial-control-systems ; Beatty's checklist https://lists.techfak.uni-bielefeld.de/pipermail/systemsafety/2013-August/000539.html ; the ROS 2 real-time proposal https://design.ros2.org/articles/realtime_proposal.html .
