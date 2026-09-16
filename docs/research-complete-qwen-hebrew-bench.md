# Qwen3-VL-4B: Hebrew vs English command planning (2026-09-01)

Question (owner): does Qwen handle Hebrew well enough to skip the HE->EN translation hop
(backlog B)? Method: 12 paired HE/EN commands (simple verbs, numerics, 3-4-step
decompositions, a question, one open-ended) against the live 4B Q4_K_M via llama-server,
temp 0, strict whitelist planner prompt (the backlog-C shape). Scored: valid JSON,
whitelist adherence, verb sequence, numeric args. Raw outputs:
scratchpad `qwen_hebrew_results.json` (session-local); rerun script is 60 lines, regenerable.

## Result: English 12/12 correct. Hebrew 5/12.

Hebrew failure modes (all semantic, none formatting):
- "עלה עשרה מטרים" (go up 10) -> `takeoff` (wrong verb)
- "תשעים מעלות" (ninety degrees) -> `degrees: 80` (number-word misread)
- "רד שלושה מטרים" (go down 3) -> `fly_by x:+3` (wrong axis AND sign)
- "המראה" (take off) -> `[]` (read as non-movement)
- 3-step combo -> steps dropped/renumbered; 2-step -> fused into one action
- English also produced a plausible 4-leg square for the open-ended case; Hebrew flew one leg.

## Verdict

- **Backlog B lives: translate HE->EN before Qwen.** The gap is large, systematic, and
  exactly the failure class (numbers, axes, verbs) that flies a drone wrong.
- The planner-prompt shape itself is proven: 12/12 EN with clean whitelist JSON at
  0.2-1.1s/command on Vulkan -- backlog C's core mechanic works today.
- Assume the same for D (EN->HE for voice-out) pending its own check.
- Caveats: n=12, one model/quant, temp 0. Big enough gap that more samples won't flip it.

## Follow-up (same day): full pipeline comparison

Owner directed a proper comparison including DictaLM-3.0-1.7B (2026). Harness + full table:
`tools/bench/hebrew-command-bench/` (isolated, nothing integrated). Outcome: opus-mt->Qwen
10/12 @ 263ms median wins; its only failures are isolated single-word commands ("המראה",
"נחת") that Tier-1 Hebrew verb patterns would catch before translation. DictaLM fails as a
direct Hebrew planner (2/12) and trails as a translator (8/12). RECOMMENDATION (not a
decision): opus-mt-tc-big-he-en translation hop + Hebrew Tier-1 fast path for the short
imperatives. Owner rules before any integration.

## Consequences
- Tier-4 EMERGENCY regex must match Hebrew DIRECTLY (never behind the translation hop) --
  done in `integration_harden/commands.py` same day.
- B model candidates to verify on this box: Helsinki opus-mt-tc-big he<->en vs
  nllb-200-distilled-600M; criteria: latency, short-imperative quality, VRAM next to Qwen.
