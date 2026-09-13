#!/usr/bin/env bash
# Whole-system test: every offline lane that stands in for a production run, on identical inputs.
# Lanes live in their own homes (single-home rule); this runner only sequences them and collects
# the reports under results/. One model on the GPU at a time; nothing here touches a drone.
#
#   bash run_all.sh                       # all lanes, current stack (Hy-MT2 + Qwen3-VL) + DictaLM reference
#   LANES=replay,bench bash run_all.sh    # subset: replay | bench | perfect | vision | gemma
#   SESSION=<session dir> LIST=<list.md> bash run_all.sh   # audio-replay inputs (defaults below)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
CMD="$ROOT/bench/hebrew-command-bench"
OUT="$HERE/results/$(date +%Y-%m-%d)"; mkdir -p "$OUT"
LANES="${LANES:-replay,bench,perfect,vision,planning}"
SESSION="${SESSION:-$ROOT/projects/integration_harden/sessions/session-20260908-003702-rog}"
LIST="${LIST:-$ROOT/tools/desk-test/live-test-50.md}"
has(){ case ",$LANES," in *",$1,"*) return 0;; *) return 1;; esac; }
echo "[whole-system] lanes=$LANES -> $OUT"
if has replay; then   # lane 1: recorded push-to-talk clips -> whisper -> Recognizer -> planner, scored vs the list
  for t in hymt2 dicta; do
    python3 "$HERE/run_list.py" "$LIST" --translator $t --from-clips "$SESSION" --out "$OUT/replay-$(basename "$SESSION")-$t.md" > "$OUT/replay-$t.log" 2>&1
    echo "[replay $t] $(tail -1 "$OUT/replay-$(basename "$SESSION")-$t.md")"; sleep 3
  done
fi
if has bench; then    # lane 2: the 413-case bench, both translators (raw JSON lands in hebrew-command-bench/results)
  for t in hymt2 dicta; do
    python3 "$CMD/bench.py" --translator $t --tag whole-$t > "$OUT/bench-$t.log" 2>&1
    echo "[bench $t] $(grep '^| ALL' "$OUT/bench-$t.log")"; sleep 3
  done
fi
if has perfect; then  # planner ceiling: reference English straight to the planner
  python3 "$CMD/bench.py" --perfect-en > "$OUT/perfect-en.log" 2>&1; echo "[perfect-en] $(grep '^| perfect' "$OUT/perfect-en.log" | tr '\n' ' ')"; sleep 3
fi
if has gemma; then    # candidate stack: Gemma 4 E4B as planner on direct Hebrew, and its English ceiling
  python3 "$CMD/bench.py" --planner gemma4 --direct-he --tag whole-gemma4-direct > "$OUT/bench-gemma4-direct.log" 2>&1
  echo "[gemma4 direct-he] $(grep '^| ALL' "$OUT/bench-gemma4-direct.log")"; sleep 3
  python3 "$CMD/bench.py" --perfect-en --planner gemma4 > "$OUT/perfect-en-gemma4.log" 2>&1; echo "[gemma4 perfect-en] $(grep '^| perfect' "$OUT/perfect-en-gemma4.log" | tr '\n' ' ')"; sleep 3
fi
if has vision; then   # lane 3: both VLMs against SAM3 on the bench images + desk frames
  python3 "$HERE/vlm_compare.py" --out "$OUT/vlm-compare" > "$OUT/vlm-compare.log" 2>&1; echo "[vision] $(grep -E '^\| (qwen|gemma)' "$OUT/vlm-compare.md" | cut -c1-160)"
fi
if has vision; then   # lane 3b: from the vision JSON, does SAM3 highlight the asked object from each VLM's phrase
  python3 "$HERE/vision_chain.py" "$OUT/vlm-compare.json" "$OUT/vision-sam3-chain.md" > "$OUT/vision-chain.log" 2>&1; echo "[vision chain] -> $OUT/vision-sam3-chain.md"
  python3 "$HERE/overlays.py" "$OUT/vlm-compare.json" "$OUT/overlays" > "$OUT/overlays.log" 2>&1; echo "[overlays] -> $OUT/overlays/index.md"
fi
if has planning; then # flight planning per case, three stacks side by side, from the newest raw JSON per stack
  python3 "$HERE/planning_table.py" "$OUT/planning-per-case.md"; echo "[planning] -> $OUT/planning-per-case.md"
fi
echo "[whole-system] done -> $OUT"
