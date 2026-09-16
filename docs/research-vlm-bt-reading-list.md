# VLM/LLM -> Behaviour-Tree generation: reading list (2026-08-31)

> 2026-09-01: this list feeds PHASE 2 of the reoriented roadmap - the post-sprint architecture
> research aimed at raising the system's SR% against its initial objective (see
> `2026-09-01-interview-sprint-handoff.md` section 2). Not sprint material.

Owner request: papers + repos with READABLE SOURCE where an LLM/VLM plus internal context generates
behaviour trees for autonomous control. Ranked by studyable code. Benchmarks quoted are the authors'
own numbers, unverified by us. (unverified) = link found via search, contents not fetched.

## Tier 1 — read the code first (best fit for our stack)
1. **BTGenBot** (IROS 2024) — fine-tuned ~7B LLM (LoRA) emits BehaviorTree.CPP XML from NL task + one
   example; C++ ROS2 `bt_client` executes, `bt_validator` checks the tree. Real igus ReBeL arm + sim.
   Closest match to us: C++, BT.CPP, small local model.
   Paper: https://arxiv.org/abs/2403.12761  Repo: https://github.com/AIRLab-POLIMI/BTGenBot
2. **BTGenBot-2** (IJCNN 2026) — a 1B model + available-action list -> BT.CPP XML (authors: 90%
   zero-shot / 98% one-shot). Isaac Sim manipulation + Jackal/Nav2. Inference + fine-tune notebooks.
   Paper: https://arxiv.org/abs/2602.01870  Repo: https://github.com/AIRLab-POLIMI/BTGenBot-2
3. **Microsoft scene-aware BT planner** — VLM generates a BT whose condition nodes are free-text
   predicates; a second VLM pass evaluates them against camera images at runtime. Directly relevant
   to our presence-gate concept. Includes a human tree-editing frontend.
   Paper: https://arxiv.org/abs/2501.03968  Repo: https://github.com/microsoft/scene-aware-robot-BT-planner
4. **Dendron** — the INVERSE architecture, and validation of our doctrine: the LLM never generates
   the tree; LM inference is a NODE TYPE inside a hand-written BT, keeping the model out of control
   flow. Fully local HuggingFace models, Python.
   Paper: https://arxiv.org/abs/2404.07439  Repo: https://github.com/RichardKelley/dendron

## Tier 2 — methodology + runnable code
5. **KIOS** — LLM + RAG over a skill knowledge base emits BTs as JSON, then iteratively REPAIRS them
   from execution + human feedback. Franka Panda + sim. (Real-robot Docker image unavailable.)
   Repo: https://github.com/ProNeverFake/kios
6. **LLM-HBTP** (ICRA 2025) — LLM supplies goal/action priors; a heuristic BT-expansion algorithm
   (HOBTEA) builds the tree, so it is correct by construction — LLM guides search, never emits XML.
   Repo: https://github.com/DIDS-EI/LLM-HBTP
7. **BTPG** (IJCAI 2025) — BT-planning gym: four algorithms (incl. HOBTEA) on three sims; the best
   single codebase for comparing BT-planning approaches side by side.
   Paper: https://www.ijcai.org/proceedings/2025/969  Repo: https://github.com/DIDS-EI/BTPG
8. **MRBTP** (AAAI 2025) — multi-robot extension of the same line. Repo: https://github.com/DIDS-EI/MRBTP (unverified)

## Tier 3 — papers only (no public code found)
9.  **LLM-as-BT-Planner** — 4 in-context-learning schemes + SFT for BT-format plans; arm assembly. https://arxiv.org/abs/2409.10444
10. **LLM-BT** — ChatGPT reasons steps, BERT parses them into a BT, tree expands during execution. https://arxiv.org/abs/2404.05134
11. **Cao & Lee 2023** — foundational Phase-Step prompting for hierarchical BT generation. https://arxiv.org/abs/2302.12927
12. **Code-BT** (IJCAI 2025) — LLM writes modular code from selected robot APIs; the BT is EXTRACTED
    from the code's control structure (authors: +16-29% over direct generation). https://www.ijcai.org/proceedings/2025/980

Index tracking the space: https://github.com/GT-RIPL/Awesome-LLM-Robotics

## Takeaway for our design (agent read, not a decision)
Two viable shapes for us: (a) BTGenBot-style — small local model emits BT.CPP XML, validated before
execution, deterministic nodes do the flying (our doctrine holds: the model plans, never drives);
(b) Dendron-style — hand-written tree, model calls confined to perception/condition nodes (our
presence gate becomes a condition node, per the Microsoft paper). (b) is the smaller step from
today's FMU; (a) is the bigger capability jump. Decide during P9 scoping.
