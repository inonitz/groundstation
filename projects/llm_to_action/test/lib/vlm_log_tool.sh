#!/bin/bash
# ==============================================================================
# vlm_log_tool.sh — list/aggregate (or wipe) the per-run VLM prompt/response logs.
#
# The FMU writes one JSONL file per run under kVlmPromptLogDir (see
# projects/llm_to_action/source/fmu/fmu_node_base.hpp), named vlm_prompts_<stamp>.jsonl,
# one JSON record per VLM call. This tool is the debug companion for A2.
#
# Usage:
#   vlm_log_tool.sh            list every log file (record count + size) + total.
#   vlm_log_tool.sh --clean    delete everything under the log dir.
# ==============================================================================
set -euo pipefail

# Keep in sync with kVlmPromptLogDir in fmu_node_base.hpp.
LOG_DIR="${VLM_PROMPT_LOG_DIR:-/root/groundstation/vlm_logs}"

if [[ "${1:-}" == "--clean" ]]; then
    if [[ -d "$LOG_DIR" ]]; then
        rm -f "$LOG_DIR"/*.jsonl 2>/dev/null || true
        echo "cleaned: $LOG_DIR"
    else
        echo "nothing to clean: $LOG_DIR does not exist"
    fi
    exit 0
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    grep '^#' "$0" | sed 's/^# \{0,1\}//'
    exit 0
fi

if [[ ! -d "$LOG_DIR" ]]; then
    echo "no log dir yet: $LOG_DIR (no VLM run has written a log)."
    exit 0
fi

shopt -s nullglob
files=("$LOG_DIR"/*.jsonl)
if [[ ${#files[@]} -eq 0 ]]; then
    echo "0 log files in $LOG_DIR"
    exit 0
fi

total_bytes=0
printf '%-40s %8s %10s\n' "FILE" "RECORDS" "BYTES"
for f in "${files[@]}"; do
    records=$(wc -l < "$f" | tr -d ' ')
    bytes=$(wc -c < "$f" | tr -d ' ')
    total_bytes=$((total_bytes + bytes))
    printf '%-40s %8s %10s\n' "$(basename "$f")" "$records" "$bytes"
done
printf '%-40s %8s %10s\n' "TOTAL (${#files[@]} files)" "" "$total_bytes"
