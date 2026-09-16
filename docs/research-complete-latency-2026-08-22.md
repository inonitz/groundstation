# DJI link latency — 2026-08-22

Measured on the real drone over the phone-hotspot link. READ-ONLY probes; no motors armed.

## Measurement conditions (matters — these are best-case)
- **Range: drone 1.5 m from the RC-N3**, RC on the desk directly below the workstation.
  This is a **point-blank RF path** — near-zero air-interface loss. Demo-range flight WILL add to these numbers.
- Link: workstation on the phone's 5 GHz hotspot (WiFi); ethernet reserved for the dev link.
- Phone: Pixel 8 Pro, ExoSkeletons app "API Server" screen, aircraft via RC-N3 USB.
- Each leg: 6 min continuous. Tools: `tools/dji_mock/measure_{telemetry,ws_rtt}.py`.

## Results
| Leg | p50 | p95 | p99 | max | mean | jitter | samples | loss |
|-----|-----|-----|-----|-----|------|--------|---------|------|
| WS transport (`/c/ws/echo`, no drone) | 16.4 | 23.6 | 36.1 | 152 | 17.2 | 6.8 | 7157 | 0 |
| telemetry (`GET /status/`, full read)  | 35.6 | 46.8 | 62.5 | 1064 | 36.5 | 14.3 | 9867 | 0 |

All values ms. Telemetry = WS transport + the drone-read cost (MSDK fetching FC keys over the RC<->aircraft RF link).
Median gap ~19 ms = that drone-read cost.

## Graphs
![overview](latency_overview.png)
![overlay](latency_overlay.png)

Regenerate: `python3 tools/dji_mock/plot_latency.py <telemetry.csv> <wsrtt.csv> <out_dir>`

## Verdict — transport: PASS
p95 24 ms (transport) / 47 ms (full read), zero loss over ~17k requests, tight jitter. Both ~20-40x under the
1 s command budget. **The WiFi link is not the constraint** — at point-blank range. Re-check at demo range.
The only open latency number is **command->action** (leg 4) — rotor spin-up on top of this transport, human-run.

## Raw data
CSVs: `tools/dji_mock/out/telemetry_20260822_091108.csv`, `.../wsrtt_20260822_095650.csv`.
(Void runs kept but excluded: `telemetry_..090431` = 503 chain-down; `wsrtt_20260822.csv` = pre-fix control-frame desync.)
