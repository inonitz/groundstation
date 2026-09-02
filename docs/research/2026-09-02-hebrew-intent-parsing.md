# Hebrew intent parsing without translation — research lane (opened 2026-09-02, owner-directed)

Goal. Replace Qwen3-VL for COMMAND parsing with something smaller, ideally Hebrew-native, and
skip the translation stage entirely. Perception stays on the VLM by definition.

What we already measured (evidence, not guesses):
- Round 3: DictaLM-3.0-1.7B planning directly from Hebrew scored 152/190 (80%) — with the OLD
  prompt and old schema. Every other arm gained 8–38 pp from the revised prompt. The single
  cheapest experiment in this lane is rerunning direct-Hebrew planning with the revised prompt,
  Hebrew few-shots, and the dx/dy/dz grammar. ~3 min on the existing bench.
- Round 6: Qwen3-VL reading Hebrew itself is dead (72% commands, corrupts numbers).

Landscape (danielrosehill/Hebrew-AI-Models, fetched 2026-09-02):
- No Hebrew function-calling / structured-output model exists in the catalog.
- Small Hebrew LLMs: DictaLM-3.0-1.7B Base/Instruct/**Thinking** (dicta-il), Hebrew Llama-3.2-1B
  fine-tune, native HebrewGPT 1B / 296M (small, likely too weak for compositional missions —
  unverified). The Thinking variant is untested by us and not on disk.
- BERT family (DictaBERT, NeoDictaBERT-bilingual, AlephBERT): classifiers. Right tool for
  ROUTING (intent class, Tier-1 confirmation), wrong tool alone for compositional mission JSON
  (multi-step arrays need generation, not classification).

Candidate ladder, cheapest first:
1. DONE 2026-09-02: dictalm-direct-plan measured 161 -> 165 -> 168/190 (88.4%) across three
   quick iterations (revised prompt + HE shots, + Hebrew sign addendum, + clockwise-idiom shot).
   Still 18-7 behind the 94.2% pipeline (p=0.043). Lane is alive: the gap is shot/LoRA territory.
2. DictaLM-3.0-1.7B-Thinking, same arm (needs scripted download; owner gate on the ~1 GB pull).
3. Generic small instructs with claimed Hebrew (Qwen3-1.7B text, Gemma3-1B): unverified Hebrew;
   only worth testing if 1–2 disappoint.
4. Two-stage: DictaBERT router (command / perception / emergency class) + DictaLM slot filling.
5. LoRA fine-tune of DictaLM-1.7B on Hebrew -> mission-JSON pairs — the true "dedicated parser".
   Data: the same dataset structure as docs/research/2026-09-02-finetune-data-plan.md (1k–5k pairs,
   coverage-balanced). This converges with the military-phraseology data plan: one dataset
   serves both.

VRAM angle (why this lane matters doubly): a 1.7B Q4 parser is ~1.3 GiB vs Qwen3-VL's ~4 GiB,
and the translation stage disappears from the command path. On the 8 GiB laptop that difference
is the whole game.

Open (owner to rule): run candidate 1; greenlight the Thinking-variant download; whether LoRA
data collection starts before or after the interview sprint.
