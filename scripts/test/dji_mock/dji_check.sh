#!/usr/bin/env bash
# dji_check.sh - derive the LIVE phone IP (hotspot gateway) and check control + video.
# The phone IP changes on every hotspot restart -- NEVER hardcode it. Run this to get the current one.
GW=$(ip route show dev wlp2s0 | awk '/^default/{print $3}')
[ -n "$GW" ] || { echo "no hotspot gateway on wlp2s0 -- workstation not on the phone hotspot?"; exit 1; }
echo "phone (hotspot gateway) = $GW"
echo -n "control /status : "; curl -s --max-time 4 "http://$GW:8080/status/" || echo "(8080 unreachable)"; echo
echo "video   :5600   :"; timeout 8 python3 "$(dirname "$0")/probe_video.py" "$GW" 5600 5
