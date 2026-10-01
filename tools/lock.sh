#!/usr/bin/env bash
# The refactor agents' lock table (owner 2026-09-28, handoff 9e): LOCK.md at the repo
# root. Line 1 is LOCKED while this script changes the table, FREE otherwise; below it,
# one row per held resource. flock makes each change atomic: two agents never take one
# resource.
#
#   tools/lock.sh acquire <agent> <resource>...   all or nothing; exit 1 names holders
#   tools/lock.sh wait <agent> <resource>...      acquire; retry every 15 s, up to 9 min
#   tools/lock.sh run <agent> <resource>... -- <command>...
#                                                 wait, run the command, release (always)
#   tools/lock.sh release <agent> <resource>...   "all": every resource of <agent>
#   tools/lock.sh clear <resource>...             main agent only: a dead agent's lock
#   tools/lock.sh status
# A resource is a repo path (projects/integration_harden2/config/constants.py) or a name:
# gpu, webcam, display, suite.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TABLE="$ROOT/LOCK.md"
HEADER="| resource | agent | since |"
WAIT_STEP_S=15
WAIT_MAX_S=540     # under the 10-minute limit of one agent command

# The held rows (every line after the table header).
body() {
    tail -n +5 "$TABLE"
    return
}

# The agent that holds resource $1, or nothing.
holder() {
    body | awk -F'|' -v r="$1" '{
        res = $2
        who = $3
        gsub(/ /, "", res)
        gsub(/ /, "", who)
        if (res == r) print who
    }'
    return
}

# Drop the rows of agent $1 on resource $2 from stdin; "*" matches any agent or resource.
drop_row() {
    awk -F'|' -v a="$1" -v r="$2" '{
        res = $2
        who = $3
        gsub(/ /, "", res)
        gsub(/ /, "", who)
        if ((a == "*" || who == a) && (r == "*" || res == r)) next
        if ($0 != "") print
    }'
    return
}

# Rewrite the table in place (the flock is on this inode): state $1, rows $2.
write_table() {
    {
        echo "$1"
        echo
        echo "$HEADER"
        echo "|---|---|---|"
        if [ -n "$2" ]; then
            printf '%s\n' "$2"
        fi
    } > "$TABLE"
    return
}

acquire() {
    local agent="$1"
    shift
    local busy=""
    local who=""
    local rows=""
    local row=""

    for res in "$@"; do
        who="$(holder "$res")"
        if [ -n "$who" ] && [ "$who" != "$agent" ]; then
            busy+="  $res held by $who"$'\n'
        fi
    done
    if [ -n "$busy" ]; then
        printf 'BUSY\n%s' "$busy"
        return 1
    fi

    rows="$(body)"
    write_table LOCKED "$rows"
    for res in "$@"; do
        if [ -n "$(holder "$res")" ]; then
            continue
        fi
        row="| $res | $agent | $(date -Iseconds) |"
        rows="$(printf '%s\n%s' "$rows" "$row" | sed '/^$/d')"
        write_table LOCKED "$rows"
    done
    write_table FREE "$rows"
    echo "ACQUIRED $*"
    return 0
}

release() {
    local agent="$1"
    shift
    local rows=""

    rows="$(body)"
    if [ "$1" = "all" ]; then
        rows="$(printf '%s\n' "$rows" | drop_row "$agent" "*")"
    fi
    for res in "$@"; do
        rows="$(printf '%s\n' "$rows" | drop_row "$agent" "$res")"
    done
    write_table FREE "$rows"
    echo "RELEASED $*"
    return 0
}

clear_rows() {
    local rows=""

    rows="$(body)"
    for res in "$@"; do
        rows="$(printf '%s\n' "$rows" | drop_row "*" "$res")"
    done
    write_table FREE "$rows"
    echo "CLEARED $*"
    return 0
}

# Take the table's flock, run one table command, drop the flock.
locked() {
    local status=0

    exec 9>>"$TABLE"
    flock 9
    if [ ! -s "$TABLE" ]; then
        write_table FREE ""
    fi
    "$@" || status=$?
    flock -u 9
    exec 9>&-
    return $status
}

wait_for() {
    local waited=0

    while ! locked acquire "$@"; do
        if [ "$waited" -ge "$WAIT_MAX_S" ]; then
            echo "TIMEOUT after ${waited} s: do other work, then try again"
            return 1
        fi
        sleep "$WAIT_STEP_S"
        waited=$((waited + WAIT_STEP_S))
    done
    return 0
}

run_locked() {
    local agent="$1"
    shift
    local resources=()
    local status=0

    while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do
        resources+=("$1")
        shift
    done
    if [ "$#" -eq 0 ] || [ "${#resources[@]}" -eq 0 ]; then
        echo "usage: tools/lock.sh run <agent> <resource>... -- <command>..."
        return 2
    fi
    shift

    wait_for "$agent" "${resources[@]}" || return 1
    "$@" || status=$?
    locked release "$agent" "${resources[@]}" > /dev/null
    return $status
}

main() {
    local cmd="${1:-status}"
    shift || true

    case "$cmd" in
        acquire) locked acquire "$@" ;;
        wait)    wait_for "$@" ;;
        run)     run_locked "$@" ;;
        release) locked release "$@" ;;
        clear)   locked clear_rows "$@" ;;
        status)  locked cat "$TABLE" ;;
        *)
            sed -n '2,15p' "$0"
            return 2
            ;;
    esac
    return
}

main "$@"
