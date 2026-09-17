# Scheduled — harden2 field test and freeze

Runs AFTER the cleanup+restructure lands (owner-confirmed order 2026-09-14).

Sequence: webcam smoke test -> nuclear code-quality review (/thermo-nuclear-code-quality-review)
-> outdoor field test on the real drone (human-run, aircraft secured) -> freeze the validated
commit as the baseline (git tag).

Done when: harden2 performs well outdoors and the exact tested commit is tagged as the baseline.
Invariants: temperature 0, one model on the GPU, full bench tables, owner runs every boot and git write.
Becomes a tasks-active/<date>-... folder when started.

## power_profile note (owner 2026-09-16)
- tools/power_profile.py is merged BEFORE the low-light testing (it is a simple script), not deferred to post-freeze. Run it to gauge the laptop field draw -> embedded power budget.

## DEFERRED TASK (owner, 2026-09-17): one-shot resource snapshot, fold into power_profile

- Measure ONCE, while the live harden2 program runs: GPU memory + GPU util, CPU %, and RAM used.
- Fold this into tools/power_profile.py (do NOT build a separate tool). Run it POST-FREEZE on the
  field-tested final system, same as the power reading (a pre-freeze reading churns).
- Purpose: size the embedded/backpack compute + power budget (aligns with the field-power roadmap goal).
- Note: phonikud TTS adds a 307MB int8 G2P on CPU (onnxruntime) + a 60MB Piper voice; include TTS active
  in the snapshot so the number reflects voice-out load, not just vision+LLM.
