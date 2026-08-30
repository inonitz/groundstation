# integration_notify — MVD fork with the "notify on new person" feature

A COPY of `integration/` (untouched). Adds: person tracking + attribute-match notify, a perception-only
mode, and a browser dashboard. The frozen `integration/` remains the fallback for the demo.

## Quick start (webcam, no drone — the morning test)
    bash bootstrap.sh                 # start + prewarm VLM, check models   (run once)
    NOTIFY_ATTRS="in a red shirt" bash run.sh
    # open http://localhost:8090  (dashboard). Walk into frame in a red shirt -> 🔔 + highlight.
    # or arm by voice (press H): "notify me when someone in a red shirt shows up"

## Knobs
- `NOTIFY_ATTRS="..."`   seed the watch at boot (else arm by voice).
- `NOTIFY_TRACKER=iou`   (default, dependency-free) | `osnet` (appearance re-ID; needs torchreid+weights).
- `MVD_NO_ACTIONS=1`     perception-only: cut ALL flight commands (indoor "ask what it sees" demo).
- `MVD_DASH=1`           dashboard direct-emit (default on); dashboard on :8090.

## What's new vs integration/
- `notify.py`            tracker interface (IoUTracker / OSNetTracker) + NotifyEngine + parse_arm.
- `scene_omdet.py`       +hooks: feed persons -> notify; draw marks; voice-arm; perception-only; dash emit.
- `dashboard/serve.py` + `dashboard.html`   left-rail + full-bleed video + subtitle bar, fed by
                          /tmp/mvd_state.json + /tmp/mvd_frame.jpg (the app emits these; GUI optional).
- `bootstrap.sh` / `run.sh`   prepare vs main-course split.

## Tested headless (2026-08-27): tracker fires once per new id, dedups, IoU re-entry limit confirmed;
## NotifyEngine->notify->dashboard state+frame end-to-end PASS. NEEDS LIVE TEST: real webcam+VLM match,
## GUI window, OSNet weights, threshold tuning.
