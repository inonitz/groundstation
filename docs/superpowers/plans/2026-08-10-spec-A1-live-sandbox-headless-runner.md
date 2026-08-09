# A1 — Live Sandbox + Headless SITL Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 20-scenario SITL test matrix runnable with zero human watching (`run_all.sh`), and give a human a recorded, full-stack live sandbox to drive freely (`scripts/sandbox/run.sh`).

**Architecture:** `sim_core.sh` gains three additive capabilities — (1) tee FMU stdout to a deterministic log file instead of relying on tmux scrollback, (2) record real PX4 ground-truth topics to a `ros2 bag`, (3) an optional `HEADLESS=1` mode that polls that ground truth (not FMU's own printed claims) to know when a canned run is over, then tears itself down without a human attaching. All 20 `filter.sh` scripts switch from tmux-pane capture to reading the log file — this is required, not cosmetic, because headless teardown kills the tmux session before `filter.sh` runs. `run_all.sh` and `scripts/sandbox/run.sh` are thin orchestrators built entirely on top of these three capabilities.

**Tech Stack:** bash, tmux, ROS2 (rclcpp/px4_msgs), `ros2 bag record`, existing `scripts/test/lib/sim_core.sh` harness.

## Global Constraints

- Agents run NO git writes (no add/commit/push). Suggest commands for the human at the end of each task.
- No native Read/Edit/Grep — use `rtk read` / `rtk grep` / `rtk ls` / `rtk find` via Bash (repo `CLAUDE.md`).
- This spec's lock scope is `scripts/test/lib/sim_core.sh`, `scripts/test/*/filter.sh`, `scripts/test/run_all.sh`, `scripts/test/override/run.sh`, `scripts/sandbox/run.sh` — **no `fmu_node.hpp` touch**, so `docs/LOCKS.md` does not need to be taken for this spec.
- awk in these scripts must be portable (system awk may be `mawk`) — existing convention, do not introduce GNU-awk-only syntax.
- All paths in `sim_core.sh` are absolute/cwd-independent except knobs that are deliberately relative to the calling scenario directory (`LOG_FILE`, `BAG_DIR`) — preserve that split.
- Full SITL verification (actually flying in Gazebo) is operator-run, same as every existing scenario — these steps are marked **[OPERATOR]**. Steps I can run directly (syntax checks, migration scripts, diff review) are marked **[AGENT]**.

---

## File structure

- **Modify** `scripts/test/lib/sim_core.sh` — add `LOG_FILE` tee, `ros2 bag` recording, `HEADLESS` mode + ground-truth wait, `tmux kill-session` teardown.
- **New** `scripts/test/lib/wait_for_ground_truth.sh` — polls `/fmu/out/vehicle_status_v4` + `/fmu/out/vehicle_land_detected` for real arm/land state; `fixed` mode for scenarios that never take off.
- **Modify** all 20 `scripts/test/*/filter.sh` — populate `$OUT` from `$LOG_FILE` instead of tmux `capture-pane`.
- **New** `scripts/test/run_all.sh` — iterates every scenario headless, aggregates PASS/FAIL.
- **Modify** `scripts/test/override/run.sh` — scripted override-toggle trigger for headless mode.
- **New** `scripts/sandbox/run.sh` — live full-stack launch, recorded, for free-form human driving.

---

### Task 1: LOG_FILE tee sink in sim_core.sh

**Files:**
- Modify: `scripts/test/lib/sim_core.sh`

**Interfaces:**
- Produces: env knob `LOG_FILE` (default `$(pwd)/captured_panes_log.txt`), always populated with FMU stdout+stderr by the time the FMU pane starts printing.

- [ ] **Step 1: Add the `LOG_FILE` knob**

In `scripts/test/lib/sim_core.sh`, find:
```bash
: "${SESSION_NAME:=llmsim}"

# --- fixed config (absolute paths; cwd-independent) ---
```
Replace with:
```bash
: "${SESSION_NAME:=llmsim}"
: "${LOG_FILE:=$(pwd)/captured_panes_log.txt}"   # FMU stdout/stderr tee target; filter.sh reads this, not tmux scrollback

# --- fixed config (absolute paths; cwd-independent) ---
```

- [ ] **Step 2: Tee the FMU pane's output**

Find:
```bash
CMD_FMU="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:$ONNXRUNTIME_LIB_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_FMU && \
    $BUILD_BINARY_DIR/llm_to_action_fmu_px4 \"$FMU_OBJECTIVE\" $FMU_CANNED_FLAG; \
    echo 'FMU stopped'; read"
```
Replace with:
```bash
CMD_FMU="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:$ONNXRUNTIME_LIB_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_FMU && \
    ($BUILD_BINARY_DIR/llm_to_action_fmu_px4 \"$FMU_OBJECTIVE\" $FMU_CANNED_FLAG 2>&1 | tee \"$LOG_FILE\"); \
    echo 'FMU stopped'; read"
```

- [ ] **Step 3: Syntax check [AGENT]**

Run: `bash -n scripts/test/lib/sim_core.sh`
Expected: no output, exit 0.

- [ ] **Step 4: Functional check [OPERATOR]**

Run: `cd scripts/test/rotate-land && ./run.sh` (watch it land as normal), then in a second terminal: `cat scripts/test/rotate-land/captured_panes_log.txt`
Expected: the file exists, is non-empty, and contains the same `ROTATE activated` / `ROTATE complete` lines that used to only show up via `tmux capture-pane`.

- [ ] **Step 5: Suggested commit (human runs)**

```bash
git add scripts/test/lib/sim_core.sh
git commit -m "test: tee FMU stdout to a log file instead of relying on tmux scrollback"
```

---

### Task 2: ros2 bag ground-truth recording + graceful shutdown

**Files:**
- Modify: `scripts/test/lib/sim_core.sh`

**Interfaces:**
- Consumes: nothing new from Task 1.
- Produces: env knobs `RECORD_BAG` (default `1`), `BAG_DIR` (default `$(pwd)/bag_<timestamp>`); global `BAG_PANE_ID` set when recording is on, read by `cleanup()`.

- [ ] **Step 1: Define the bag command**

Find (the block of `CMD_*` definitions, right after `CMD_KEYBOARD`):
```bash
CMD_KEYBOARD="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_FMU && $BUILD_BINARY_DIR/llm_to_action_keyboard_hook; \
    echo 'keyboard stopped'; read"
```
Immediately after it, add:
```bash
: "${RECORD_BAG:=1}"
: "${BAG_DIR:=$(pwd)/bag_$(date +%Y%m%d_%H%M%S)}"
CMD_BAG="ros2 bag record -o \"$BAG_DIR\" \
    /fmu/out/vehicle_odometry \
    /fmu/out/vehicle_status_v4 \
    /fmu/out/vehicle_land_detected \
    /fmu/out/battery_status_v1; \
    echo 'bag recorder stopped'; read"
```
(Topic names verified against this checkout: `/root/PX4-Autopilot/src/modules/uxrce_dds_client/dds_topics.yaml` lists the bare names; `vehicle_status` needs the `_v4` suffix and `vehicle_odometry`/`vehicle_land_detected` don't, per each message's `MESSAGE_VERSION` — same rule already documented in `px4_backend_base.hpp:30-31`.)

- [ ] **Step 2: Launch the bag pane and capture its pane id**

Find:
```bash
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_KEYBOARD"
tmux select-layout -t "$SESSION_NAME:0" tiled
```
Replace with:
```bash
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_KEYBOARD"
if [ "$RECORD_BAG" = "1" ]; then
    BAG_PANE_ID=$(tmux split-window -v -t "$SESSION_NAME:0" -P -F '#{pane_id}' "$CMD_BAG")
fi
tmux select-layout -t "$SESSION_NAME:0" tiled
```

- [ ] **Step 3: Stop the recorder gracefully in cleanup()**

`ros2 bag record` needs SIGINT (not SIGKILL) to finalize `metadata.yaml`, or the bag is unreadable. Find:
```bash
cleanup() {
    echo -e "\n[CLEANUP] Restoring gimbal SDF..."
    if [ -f "${GZ_GIMBAL_SDF_FILE}.bak" ]; then
        mv "${GZ_GIMBAL_SDF_FILE}.bak" "$GZ_GIMBAL_SDF_FILE"
    fi
    echo "[CLEANUP] Killing lingering processes..."
    pkill -9 -f "llm_to_action_"
    pkill -9 -f "llama-server"
    pkill -9 -f "gz"
    pkill -9 -f "px4"
    pkill -9 -f "MicroXRCEAgent"
    echo "[SUCCESS] Clean."
}
```
Replace with:
```bash
cleanup() {
    echo -e "\n[CLEANUP] Restoring gimbal SDF..."
    if [ -f "${GZ_GIMBAL_SDF_FILE}.bak" ]; then
        mv "${GZ_GIMBAL_SDF_FILE}.bak" "$GZ_GIMBAL_SDF_FILE"
    fi
    if [ -n "${BAG_PANE_ID:-}" ]; then
        echo "[CLEANUP] Stopping bag recorder gracefully (SIGINT)..."
        tmux send-keys -t "$BAG_PANE_ID" C-c 2>/dev/null || true
        sleep 2
    fi
    echo "[CLEANUP] Killing lingering processes..."
    pkill -9 -f "llm_to_action_"
    pkill -9 -f "llama-server"
    pkill -9 -f "gz"
    pkill -9 -f "px4"
    pkill -9 -f "MicroXRCEAgent"
    pkill -9 -f "ros2 bag record"
    echo "[SUCCESS] Clean."
}
```

- [ ] **Step 4: Syntax check [AGENT]**

Run: `bash -n scripts/test/lib/sim_core.sh`
Expected: no output, exit 0.

- [ ] **Step 5: Functional check [OPERATOR]**

Run: `cd scripts/test/rotate-land && ./run.sh`, let it land, detach/Ctrl-C to trigger cleanup.
Expected: a `bag_<timestamp>/` directory appears under `scripts/test/rotate-land/` containing `metadata.yaml` + a `.db3` (or mcap) file; `ros2 bag info <dir>` succeeds (a corrupt/ungraceful stop makes this command fail or report 0 messages).

- [ ] **Step 6: Suggested commit (human runs)**

```bash
git add scripts/test/lib/sim_core.sh
git commit -m "test: record PX4 ground-truth topics to a ros2 bag, with graceful SIGINT shutdown"
```

---

### Task 3: HEADLESS mode + ground-truth completion poller

**Files:**
- Create: `scripts/test/lib/wait_for_ground_truth.sh`
- Modify: `scripts/test/lib/sim_core.sh`

**Interfaces:**
- Consumes: nothing new from Task 1/2 (bag recording and the completion poll are independent — the poller reads live topics directly, not the bag file).
- Produces: env knobs `HEADLESS` (default `0`), `HEADLESS_COMPLETION` (`flight`|`fixed`, default `flight`), `HEADLESS_TIMEOUT_SECONDS` (default `120`).

- [ ] **Step 1: Write the poller**

Create `scripts/test/lib/wait_for_ground_truth.sh`:
```bash
#!/bin/bash
# wait_for_ground_truth.sh — the headless "is this run over" signal, sourced from real
# PX4 topics (arming_state + landed), NOT from FMU's own printed log lines. The FMU's
# self-reported "reached"/"complete" text has been wrong before (see ROADMAP 6.4); this
# only trusts what the vehicle itself is telling PX4.
#   flight (default): wait for ARMED, then DISARMED-while-landed.
#   fixed: no flight happens (flood/override) -- just sleep the timeout.
# Usage: wait_for_ground_truth.sh <flight|fixed> <timeout_seconds>
set -uo pipefail
MODE="${1:-flight}"
TIMEOUT="${2:-120}"
POLL_INTERVAL=2
STATUS_TOPIC="/fmu/out/vehicle_status_v4"
LAND_TOPIC="/fmu/out/vehicle_land_detected"
ARMING_STATE_ARMED=2   # px4_msgs::msg::VehicleStatus::ARMING_STATE_ARMED

if [ "$MODE" = "fixed" ]; then
    echo "[wait] fixed mode: sleeping ${TIMEOUT}s"
    sleep "$TIMEOUT"
    exit 0
fi

echo "[wait] flight mode: polling $STATUS_TOPIC / $LAND_TOPIC every ${POLL_INTERVAL}s (timeout ${TIMEOUT}s)"
elapsed=0
seen_armed=0
while [ "$elapsed" -lt "$TIMEOUT" ]; do
    arm_val=$(timeout 3 ros2 topic echo "$STATUS_TOPIC" --once 2>/dev/null | awk -F': *' '/^arming_state:/{print $2; exit}')
    landed_val=$(timeout 3 ros2 topic echo "$LAND_TOPIC" --once 2>/dev/null | awk -F': *' '/^landed:/{print $2; exit}')

    if [ "$arm_val" = "$ARMING_STATE_ARMED" ]; then
        seen_armed=1
    fi
    if [ "$seen_armed" = "1" ] && [ -n "$arm_val" ] && [ "$arm_val" != "$ARMING_STATE_ARMED" ] && [ "$landed_val" = "true" ]; then
        echo "[wait] ground truth: armed then landed+disarmed at t=${elapsed}s"
        exit 0
    fi
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
done
echo "[wait] TIMEOUT after ${TIMEOUT}s (seen_armed=$seen_armed) -- tearing down; filter.sh will judge PASS/FAIL from whatever the log shows"
exit 0
```
Make it executable: `chmod +x scripts/test/lib/wait_for_ground_truth.sh`

- [ ] **Step 2: Gate the attach on HEADLESS, and always kill the session on exit**

Find (end of file):
```bash
tmux select-layout -t "$SESSION_NAME:0" tiled
tmux attach-session -t "$SESSION_NAME"
```
Replace with:
```bash
tmux select-layout -t "$SESSION_NAME:0" tiled

if [ "${HEADLESS:-0}" = "1" ]; then
    : "${HEADLESS_COMPLETION:=flight}"
    : "${HEADLESS_TIMEOUT_SECONDS:=120}"
    echo "[INFO] HEADLESS=1 -- no attach; waiting on ground truth (mode=$HEADLESS_COMPLETION, timeout=${HEADLESS_TIMEOUT_SECONDS}s)"
    "$(dirname "${BASH_SOURCE[0]}")/wait_for_ground_truth.sh" "$HEADLESS_COMPLETION" "$HEADLESS_TIMEOUT_SECONDS"
else
    tmux attach-session -t "$SESSION_NAME"
fi
```

- [ ] **Step 3: Kill the tmux session on teardown**

So a headless `run_all.sh` can reuse `SESSION_NAME="llmsim"` for the next scenario without a stale session blocking `tmux new-session`. Find (inside `cleanup()`, from Task 2):
```bash
    pkill -9 -f "ros2 bag record"
    echo "[SUCCESS] Clean."
}
```
Replace with:
```bash
    pkill -9 -f "ros2 bag record"
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
    echo "[SUCCESS] Clean."
}
```

- [ ] **Step 4: Syntax check [AGENT]**

Run: `bash -n scripts/test/lib/sim_core.sh && bash -n scripts/test/lib/wait_for_ground_truth.sh`
Expected: no output, exit 0.

- [ ] **Step 5: Functional check [OPERATOR]**

Run: `cd scripts/test/rotate-land && HEADLESS=1 HEADLESS_TIMEOUT_SECONDS=90 ./run.sh`
Expected: script returns to the shell prompt on its own (no attach, no manual Ctrl-C needed) once the drone lands and disarms, and `tmux ls` afterward shows no `llmsim` session.

- [ ] **Step 6: Suggested commit (human runs)**

```bash
git add scripts/test/lib/sim_core.sh scripts/test/lib/wait_for_ground_truth.sh
git commit -m "test: add HEADLESS mode driven by real PX4 ground truth, not FMU log text"
```

---

### Task 4: Retrofit all 20 filter.sh to read from LOG_FILE

**Files:**
- Modify: all `scripts/test/*/filter.sh` (20 files; confirmed identical anchor lines `SESSION="${1:-llmsim}"` and `echo "[capture] all panes -> $OUT"` in every one, via `rtk grep -c` over all 20 — each `OUT="..."` filename itself varies per scenario and must be preserved).

**Interfaces:**
- Consumes: `LOG_FILE` from Task 1 (falls back to the same default path if unset, so a human running `./filter.sh` right after `./run.sh` in the same directory needs no env var).

- [ ] **Step 1: Write and run the migration script**

Create `/tmp/claude-0/-root-groundstation/8007dc3d-7aeb-44ab-afbf-012df18fcb9a/scratchpad/migrate_filters.py`:
```python
import glob, re, sys

START = 'SESSION="${1:-llmsim}"\n'
END_MARKER = '[capture] all panes -> $OUT'

NEW_BLOCK_TMPL = '''LOG_FILE="${{1:-$(pwd)/captured_panes_log.txt}}"
if [ ! -f "$LOG_FILE" ]; then
    echo "no FMU log at '$LOG_FILE' -- start a run first with ./run.sh" >&2
    exit 2
fi
cp "$LOG_FILE" "{out}"
echo "[capture] FMU log -> {out}"
'''

changed = []
for path in sorted(glob.glob("scripts/test/*/filter.sh")):
    text = open(path).read()
    if START not in text:
        print(f"SKIP (no anchor): {path}")
        continue
    start_idx = text.index(START)
    end_line_idx = text.index(END_MARKER)
    end_idx = text.index("\n", end_line_idx) + 1
    m = re.search(r'OUT="([^"]+)"', text[start_idx:end_idx])
    if not m:
        print(f"SKIP (no OUT= found): {path}")
        continue
    out_name = m.group(1)
    new_block = NEW_BLOCK_TMPL.format(out=out_name)
    new_text = text[:start_idx] + new_block + text[end_idx:]
    open(path, "w").write(new_text)
    changed.append(path)

print(f"\nmigrated {len(changed)} files")
if len(changed) != 20:
    sys.exit(1)
```
Run: `cd /root/groundstation && python3 /tmp/claude-0/-root-groundstation/8007dc3d-7aeb-44ab-afbf-012df18fcb9a/scratchpad/migrate_filters.py`
Expected: `migrated 20 files`, exit 0.

- [ ] **Step 2: Syntax check every migrated file [AGENT]**

Run: `for f in scripts/test/*/filter.sh; do bash -n "$f" || echo "FAIL: $f"; done`
Expected: no `FAIL:` lines.

- [ ] **Step 3: Spot-check the diff on two files with different OUT names [AGENT]**

Run: `rtk git diff scripts/test/rotate-land/filter.sh scripts/test/battery/filter.sh`
Expected: `rotate-land` now copies into `captured_panes_log.txt`, `battery` into `captured_battery_log.txt` (its pre-existing name preserved) — only the capture mechanism changed, every downstream `grep`/`awk` line is untouched.

- [ ] **Step 4: Functional check [OPERATOR]**

Re-run: `cd scripts/test/rotate-land && ./run.sh` (normal, attached), then `./filter.sh`.
Expected: identical PASS output to before this change — same digest, same verdict, now sourced from the log file instead of a fresh tmux capture.

- [ ] **Step 5: Suggested commit (human runs)**

```bash
git add scripts/test/*/filter.sh
git commit -m "test: read FMU log file in all 20 filter.sh instead of live tmux capture-pane"
```

---

### Task 5: run_all.sh headless regression orchestrator

**Files:**
- Create: `scripts/test/run_all.sh`

**Interfaces:**
- Consumes: `HEADLESS`/`HEADLESS_COMPLETION`/`HEADLESS_TIMEOUT_SECONDS` (Task 3), the migrated `filter.sh` contract (Task 4: exit 0 = PASS, nonzero = FAIL, reads `LOG_FILE` with no args needed).
- Produces: `SKIP_HIGH_VRAM` env knob (default `0`) — set to `1` on constrained hardware to skip `vlm`/`approach-real`/`override` (2026-08-09 operator finding: these three load Qwen3-VL-2B on top of the always-on seg+depth perception models, confirmed ~12GiB VRAM, too much for a laptop GPU).

- [ ] **Step 1: Write the orchestrator**

Create `scripts/test/run_all.sh`:
```bash
#!/bin/bash
# run_all.sh -- headless regression runner. Iterates every scripts/test/<scenario>/,
# runs it HEADLESS (ground-truth completion, not a human watching), invokes that
# scenario's filter.sh, aggregates PASS/FAIL. Nonzero exit if anything failed.
# Usage: cd scripts/test && ./run_all.sh
set -uo pipefail
cd "$(dirname "$0")" || exit 1
SUMMARY_FILE="${SUMMARY_FILE:-$(pwd)/run_all_summary.txt}"
: > "$SUMMARY_FILE"

# scenario -> "completion_mode:timeout_seconds"
# flight = waits on real arm/land ground truth; fixed = scenario never takes off
# (flood: ground-only queue test; override: needs a scripted trigger, see Task 6).
declare -A SCENARIO_CFG=(
    [forward]="flight:90"
    [cross]="flight:90"
    [speed]="flight:90"
    [rotate-land]="flight:90"
    [land-flare]="flight:90"
    [terrain-land]="flight:90"
    [approach]="flight:90"
    [approach-real]="flight:150"
    [approach-impact]="flight:90"
    [vlm]="flight:180"
    [flood]="fixed:30"
    [flood-airborne]="flight:90"
    [battery]="flight:120"
    [battery-rth]="flight:120"
    [battery-landnow]="flight:120"
    [override]="fixed:60"
    [boundary]="flight:120"
    [interrupt-storm]="flight:150"
    [orbit]="flight:120"
    [search]="flight:150"
)

# High-VRAM scenarios (2026-08-09 operator finding): these three set LAUNCH_VLM=1, which loads
# Qwen3-VL-2B (-ngl 99 -c 65536, full GPU offload, 64k context) IN ADDITION to the seg+depth ONNX
# perception models every scenario already loads -- confirmed ~12GiB VRAM on the operator's machine,
# too much for a laptop-class GPU. SKIP_HIGH_VRAM=1 (default 0) skips these three; set it on
# constrained hardware. If a specific one of these three isn't actually the culprit, narrow this list
# rather than removing the mechanism -- the underlying LAUNCH_VLM=1 cost is real for all three.
HIGH_VRAM_SCENARIOS=(vlm approach-real override)
: "${SKIP_HIGH_VRAM:=0}"
is_high_vram() {
    local n="$1" s
    for s in "${HIGH_VRAM_SCENARIOS[@]}"; do [ "$n" = "$s" ] && return 0; done
    return 1
}

PASS=0
FAIL=0
SKIP=0

for dir in */; do
    name="${dir%/}"
    [ "$name" = "lib" ] && continue
    [ -f "$dir/run.sh" ] || continue
    if [ "$SKIP_HIGH_VRAM" = "1" ] && is_high_vram "$name"; then
        echo "$name: SKIP (high VRAM, SKIP_HIGH_VRAM=1)" | tee -a "$SUMMARY_FILE"
        SKIP=$((SKIP + 1))
        continue
    fi
    cfg="${SCENARIO_CFG[$name]:-flight:90}"
    mode="${cfg%%:*}"
    timeout_s="${cfg##*:}"

    echo "=== $name (mode=$mode timeout=${timeout_s}s) ==="
    ( cd "$name" && HEADLESS=1 HEADLESS_COMPLETION="$mode" HEADLESS_TIMEOUT_SECONDS="$timeout_s" ./run.sh )
    run_status=$?
    if [ "$run_status" -ne 0 ]; then
        echo "$name: FAIL (run.sh exit $run_status)" | tee -a "$SUMMARY_FILE"
        FAIL=$((FAIL + 1))
        continue
    fi

    ( cd "$name" && ./filter.sh )
    filter_status=$?
    if [ "$filter_status" -eq 0 ]; then
        echo "$name: PASS" | tee -a "$SUMMARY_FILE"
        PASS=$((PASS + 1))
    else
        echo "$name: FAIL (filter.sh exit $filter_status)" | tee -a "$SUMMARY_FILE"
        FAIL=$((FAIL + 1))
    fi
done

echo "---"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP  (summary: $SUMMARY_FILE)"
[ "$FAIL" -eq 0 ]
```
Make it executable: `chmod +x scripts/test/run_all.sh`

- [ ] **Step 2: Syntax check [AGENT]**

Run: `bash -n scripts/test/run_all.sh`
Expected: no output, exit 0.

- [ ] **Step 3: Single-scenario dry run via the real orchestrator [OPERATOR]**

Temporarily edit `SCENARIO_CFG` (or add a `--only <name>` guard, operator's call) to run just `rotate-land` through `run_all.sh` end to end.
Expected: `PASS=1 FAIL=0` printed, matching the standalone `./run.sh && ./filter.sh` result from Task 3/4's checks.

- [ ] **Step 4: Full matrix run [OPERATOR, once B-track isn't competing for the SITL machine]**

Run: `cd scripts/test && ./run_all.sh`
Expected: `PASS=20 FAIL=0` (or `PASS=19 FAIL=0` if override's Task 6 trigger isn't landed yet — see Task 6).

- [ ] **Step 5: Suggested commit (human runs)**

```bash
git add scripts/test/run_all.sh
git commit -m "test: add run_all.sh, a fully headless run of the 20-scenario SITL matrix"
```

---

### Task 6: Scripted override trigger for headless mode

**Files:**
- Modify: `scripts/test/override/run.sh`

**Interfaces:**
- Consumes: `/fmu/in/override` (`std_msgs/msg/Bool`, confirmed at `source/llm_to_action/fmu/fmu_node_base.hpp:46`), `HEADLESS` knob from Task 3.

- [ ] **Step 1: Add the headless trigger**

Current file:
```bash
#!/bin/bash
# Manual operator override test (spec-3, ROADMAP 6.2 / ARCH 11).
# Bool /fmu/in/override toggles takeover; while engaged, keys on /keyboard/in/raw fly the
# drone (WASD=plane, arrows=alt/yaw, Space=hover). Handback resumes autonomy + re-plans.
# sim_core.sh already launches the keyboard node pane. LAUNCH_VLM=1 so handback re-plans.
# Run:  cd scripts/test/override && ./run.sh    ; then do the MANUAL STEPS in README.md
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, find the car, approach it, then land."
FMU_CANNED_FLAG=""              # VLM-driven so a handback has something to re-plan
LAUNCH_VLM=1
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../lib/sim_core.sh
```
Replace with:
```bash
#!/bin/bash
# Manual operator override test (spec-3, ROADMAP 6.2 / ARCH 11).
# Bool /fmu/in/override toggles takeover; while engaged, keys on /keyboard/in/raw fly the
# drone (WASD=plane, arrows=alt/yaw, Space=hover). Handback resumes autonomy + re-plans.
# sim_core.sh already launches the keyboard node pane. LAUNCH_VLM=1 so handback re-plans.
#
# Manual run:   cd scripts/test/override && ./run.sh   ; then do the MANUAL STEPS in README.md
# Headless run: HEADLESS=1 ./run.sh -- scripts the /fmu/in/override toggle itself (engage,
#               hold, release) since filter.sh's PASS bar is "engaged" being observed; no
#               human keypresses are simulated, so the release/replan lines stay WARN-only,
#               same as a human run that never presses a movement key.
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, find the car, approach it, then land."
FMU_CANNED_FLAG=""              # VLM-driven so a handback has something to re-plan
LAUNCH_VLM=1
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"

if [ "${HEADLESS:-0}" = "1" ]; then
    (
        sleep 25   # let TAKEOFF clear FLIGHT before toggling override
        ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data: true}" >/dev/null 2>&1
        sleep 5
        ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data: false}" >/dev/null 2>&1
    ) &
    disown
fi

source ../lib/sim_core.sh
```

- [ ] **Step 2: Syntax check [AGENT]**

Run: `bash -n scripts/test/override/run.sh`
Expected: no output, exit 0.

- [ ] **Step 3: Functional check [OPERATOR]**

Run: `cd scripts/test/override && HEADLESS=1 HEADLESS_COMPLETION=fixed HEADLESS_TIMEOUT_SECONDS=60 ./run.sh`, then `./filter.sh`.
Expected: `filter.sh` reports `ok engaged x1` and PASSes without any manual keypress or topic publish from the operator.

- [ ] **Step 4: Wire it into run_all.sh [AGENT]**

`override`'s `SCENARIO_CFG` entry in Task 5 is already `fixed:60`, which matches this trigger's timing — no further change needed there.

- [ ] **Step 5: Suggested commit (human runs)**

```bash
git add scripts/test/override/run.sh
git commit -m "test: script the override toggle so the override scenario runs fully headless"
```

---

### Task 7: scripts/sandbox/run.sh — live full-system sandbox

**Files:**
- Create: `scripts/sandbox/run.sh`

**Interfaces:**
- Consumes: `sim_core.sh` as-is (Tasks 1-3), non-headless attach path (default `HEADLESS=0`), `RECORD_BAG=1` (Task 2).

- [ ] **Step 1: Write the sandbox launcher**

Create `scripts/sandbox/run.sh`:
```bash
#!/bin/bash
# scripts/sandbox/run.sh -- live full-system sandbox: Gazebo + PX4 + FMU + VLM + perception,
# free-form objective, human-driven (attaches tmux like any manual test run), and recorded
# to a ros2 bag for later replay. Not a canned scenario -- always VLM-driven.
# Usage: ./run.sh ["<objective text>"] [world_name]
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="${1:-Explore the area and describe what you see.}"
FMU_CANNED_FLAG=""
WORLD_NAME="${2:-default_car}"
SPAWN_POSE="0,7,3"
LAUNCH_VLM=1
RECORD_BAG=1
mkdir -p "$(pwd)/bags"
BAG_DIR="$(pwd)/bags/$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$(pwd)/bags/$(basename "$BAG_DIR")_fmu_log.txt"
source ../test/lib/sim_core.sh
```
Make it executable: `chmod +x scripts/sandbox/run.sh`

- [ ] **Step 2: Add a .gitignore for recorded artifacts**

Create `scripts/sandbox/.gitignore`:
```
bags/
```

- [ ] **Step 3: Syntax check [AGENT]**

Run: `bash -n scripts/sandbox/run.sh`
Expected: no output, exit 0.

- [ ] **Step 4: Functional check [OPERATOR]**

Run: `cd scripts/sandbox && ./run.sh "Take off and orbit the car."`
Expected: the familiar tmux layout attaches (PX4, RX, FMU, keyboard, VLM, plus a new bag-recorder pane), the drone flies the free-form objective under normal manual/voice control, and on detach/Ctrl-C, `bags/<timestamp>/` contains a valid bag (`ros2 bag info` succeeds) plus `bags/<timestamp>_fmu_log.txt`.

- [ ] **Step 5: Suggested commit (human runs)**

```bash
git add scripts/sandbox/run.sh scripts/sandbox/.gitignore
git commit -m "feat: add scripts/sandbox/run.sh, a recorded live full-system sandbox"
```

---

## Self-review

**Spec coverage against `docs/scheduled/2026-08-10-spec-A1-live-sandbox-headless-runner.md`:**
- "live full-system launch... free-form objective... manual interrupts... record it" → Task 7.
- "headless runner that executes every canned scenario, captures FMU stdout to a file... asserts pass/fail, reports" → Tasks 1, 3, 5.
- "`--log-file` sink in `sim_core.sh`" → Task 1 (named `LOG_FILE` to match the existing knob-naming convention in the file, e.g. `SESSION_NAME`, `WORLD_NAME`).
- "`run_all.sh` iterates scenario dirs, runs each headless, invokes filter.sh, aggregates a summary, returns nonzero on any failure" → Task 5.
- "kills the false FAIL on rerun tmux artifact" → Task 4 (all filters read a plain file now, no scrollback limit to exceed).
- Acceptance: "sandbox brings the live stack up and records a replayable bag" → Task 7 (bag) + Task 2 (recording mechanism it depends on).
- The plan's added ground-truth completion detection and the override scripted trigger go beyond the original spec text, per this session's discussion: the original "false FAIL" framing was about capture fragility, but the deeper concern raised was that FMU-printed log lines aren't ground truth. Tasks 3 and 6 close that gap using real PX4 topics instead of trusting FMU's self-report for *when a run is over* (not yet for cross-checking its *claims* — that's the agreed fast-follow, out of scope here).

**No-placeholder scan:** every step has runnable code or an exact command; no TBD/TODO markers remain.

**Type/name consistency check:** `LOG_FILE`, `BAG_DIR`, `BAG_PANE_ID`, `HEADLESS`, `HEADLESS_COMPLETION`, `HEADLESS_TIMEOUT_SECONDS`, `RECORD_BAG` are spelled identically everywhere they're introduced (Tasks 1-3) and everywhere they're consumed (Tasks 5-7).
