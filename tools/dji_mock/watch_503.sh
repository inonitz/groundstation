#!/usr/bin/env bash
# SAFE (GET only). Watch the phone API server's connection gate: log every change of the /status/ HTTP code, so the
# eco/sleep timeout that turns 200 into 503 can be read off the clock. Owner ask 2026-09-08 ("make sure the drone
# receives commands and it won't go into sleep mode"). Usage: bash tools/dji_mock/watch_503.sh [phone_ip] [period_s]
IP="${1:-${PHONE_IP:-10.222.215.92}}"; T="${2:-10}"; last=""
echo "watching http://$IP:8080/status/ every ${T}s (Ctrl-C to stop). 2xx = ready; 503 = RC/aircraft/product not connected or aircraft in eco; 000 = not answering"
while true; do
    code=$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://$IP:8080/status/" 2>/dev/null)
    if [ "$code" != "$last" ]; then echo "$(date +%H:%M:%S) /status/ -> $code"; last="$code"; fi
    sleep "$T"
done
