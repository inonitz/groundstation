#!/usr/bin/env python3
"""Plot DJI link latency from measure_*.py CSVs.
Usage: plot_latency.py <telemetry.csv> <wsrtt.csv> <out_dir>
Emits latency_overview.png (timeseries + histogram per metric) and latency_overlay.png."""
import sys, csv
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

def load(path, okcol=None):
    t, v = [], []
    for r in csv.DictReader(open(path)):
        if okcol and r.get(okcol) == "0": continue
        try: t.append(float(r["t_ms"]) / 1000.0); v.append(float(r["rtt_ms"]))
        except Exception: pass
    return np.array(t), np.array(v)

tel_t, tel_v = load(sys.argv[1], okcol="ok")
ws_t,  ws_v  = load(sys.argv[2])
outdir = sys.argv[3]
P = np.percentile

fig, ax = plt.subplots(2, 2, figsize=(14, 8))
for i, (name, t, v, color) in enumerate([
    ("Telemetry  GET /status/   (full read: ws->phone->drone->back)", tel_t, tel_v, "#1f77b4"),
    ("WS transport  /c/ws/echo   (ws->phone->back, no drone)",        ws_t,  ws_v,  "#d62728")]):
    p50, p95, p99 = P(v, 50), P(v, 95), P(v, 99)
    a = ax[i, 0]
    a.plot(t, v, ".", ms=1.4, color=color, alpha=0.30)
    for p, ls in [(p50, "--"), (p95, "-."), (p99, ":")]:
        a.axhline(p, color="k", ls=ls, lw=0.9)
    a.text(0.995, 0.96, f"p50 {p50:.1f}  p95 {p95:.1f}  p99 {p99:.1f} ms",
           ha="right", va="top", transform=a.transAxes, fontsize=8,
           bbox=dict(fc="white", ec="0.7", alpha=0.85))
    a.set_title(name, fontsize=9); a.set_xlabel("time (s)"); a.set_ylabel("RTT (ms)")
    a.set_ylim(0, P(v, 99.5) * 1.35); a.grid(alpha=0.25)
    h = ax[i, 1]
    h.hist(v, bins=120, range=(0, P(v, 99) * 1.5), color=color, alpha=0.85)
    h.axvline(p50, color="k", ls="--", lw=0.9); h.axvline(p95, color="k", ls="-.", lw=0.9)
    h.set_title(f"distribution   n={len(v)}   mean={v.mean():.1f}   max={v.max():.0f} ms", fontsize=9)
    h.set_xlabel("RTT (ms)"); h.set_ylabel("count"); h.grid(alpha=0.25)
fig.suptitle("DJI link latency — 2026-08-22 | drone 1.5 m from RC (point-blank, best case) | 5 GHz hotspot",
             fontsize=11)
fig.tight_layout(rect=[0, 0, 1, 0.96]); fig.savefig(outdir + "/latency_overview.png", dpi=110)

fig2, a2 = plt.subplots(figsize=(14, 4))
a2.plot(tel_t, tel_v, ".", ms=1.2, color="#1f77b4", alpha=0.28, label="telemetry (full read)")
a2.plot(ws_t,  ws_v,  ".", ms=1.2, color="#d62728", alpha=0.28, label="WS transport (no drone)")
a2.axhline(np.median(tel_v), color="#1f77b4", ls="--", lw=1.2)
a2.axhline(np.median(ws_v),  color="#d62728", ls="--", lw=1.2)
a2.set_ylim(0, 80); a2.set_xlabel("time (s)"); a2.set_ylabel("RTT (ms)")
a2.set_title(f"transport vs full-read over 6 min — median gap {np.median(tel_v)-np.median(ws_v):.0f} ms = drone-read cost",
             fontsize=10)
a2.legend(fontsize=9, markerscale=10); a2.grid(alpha=0.25)
fig2.tight_layout(); fig2.savefig(outdir + "/latency_overlay.png", dpi=110)
print("wrote latency_overview.png + latency_overlay.png to", outdir)

# --- optional 4th arg: video e2e CSV (idx,latency_ms) from measure_video_e2e.py ---
if len(sys.argv) > 4:
    import csv as _csv
    vv = [float(r["latency_ms"]) for r in _csv.DictReader(open(sys.argv[4])) if r.get("latency_ms")]
    core = [x for x in vv if x >= 50]   # drop <50ms false brightness-matches
    if vv:
        fig3, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(14, 4))
        ax_a.plot(range(len(vv)), vv, ".", ms=3, color="#2ca02c", alpha=0.6)
        ax_a.axhline(np.median(core) if core else np.median(vv), color="k", ls="--", lw=0.9)
        ax_a.set_title("video e2e latency over samples", fontsize=10)
        ax_a.set_xlabel("sample"); ax_a.set_ylabel("ms"); ax_a.grid(alpha=0.25)
        c = np.array(core) if core else np.array(vv)
        ax_b.hist(c, bins=40, color="#2ca02c", alpha=0.85)
        ax_b.axvline(np.median(c), color="k", ls="--", lw=0.9)
        ax_b.set_title(f"distribution (>=50ms, n={len(c)}) p50={np.median(c):.0f} p95={np.percentile(c,95):.0f} ms",
                       fontsize=10)
        ax_b.set_xlabel("ms"); ax_b.set_ylabel("count"); ax_b.grid(alpha=0.25)
        fig3.suptitle("DJI video glass->perception e2e (flash-detect)", fontsize=11)
        fig3.tight_layout(rect=[0,0,1,0.94]); fig3.savefig(outdir + "/latency_video_e2e.png", dpi=110)
        print("wrote latency_video_e2e.png")
