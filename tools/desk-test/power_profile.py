#!/usr/bin/env python3
"""Dynamic power/energy profiler for a mock or live flight. Assumes NOTHING: it detects the GPU, the
CPU package energy counter (RAPL), and the battery from the system, samples the LIVE draw, and
integrates real samples into watt-hours. Nothing is hardcoded -- not the pack size, not the TDP.

  python3 power_profile.py                         # sample until Ctrl-C, then print the report
  python3 power_profile.py --interval 1 --duration 1200   # 1 s samples for a 20-min flight
  python3 power_profile.py --pack-wh 90            # model flights per pack when no battery is present
  python3 power_profile.py --out /tmp/power.csv    # also write the raw timeline

WHAT A WATT-HOUR IS: a watt (W) is power -- energy used per second, right now. A watt-hour (Wh) is
energy -- power multiplied by time. 90 W running for 1 hour = 90 Wh. To go back: watts = Wh / hours.
A 90 Wh pack delivers 90 W for 1 h, or 30 W for 3 h. A 20-min flight at 90 W uses 90 * (20/60) = 30 Wh.

THREE power sources, whichever exist (so it works on a laptop OR a plugged workstation):
  - battery discharge   = the WHOLE system (CPU+GPU+RAM+board). The most honest total. Needs discharging.
  - CPU package (RAPL)   = the CPU's own energy counter (/sys/class/powercap). Works on AC.
  - GPU power.draw        = the GPU alone (nvidia-smi / rocm-smi). Works on AC.
On AC (no battery drain) the total is CPU+GPU ("compute draw"); it excludes RAM/board/PSU loss, so it is
a LOWER bound. On battery it is the exact whole-system draw.
"""
import argparse, glob, json, os, signal, subprocess, time


def _run(cmd):
    try:    return subprocess.run(cmd, capture_output=True, text=True, timeout=4).stdout.strip()
    except Exception: return ""


def detect_gpu():
    """sampler() -> (power_W, util_pct, mem_MB) for whatever GPU tool exists, else (None, None)."""
    if _run(["bash", "-lc", "command -v nvidia-smi"]):
        def s():
            o = _run(["nvidia-smi", "--query-gpu=power.draw,utilization.gpu,memory.used",
                      "--format=csv,noheader,nounits"])
            if not o: return (None, None, None)
            p, u, m = (x.strip() for x in o.splitlines()[0].split(","))
            f = lambda v: None if v in ("", "[N/A]", "[Not Supported]") else float(v)
            return (f(p), f(u), f(m))
        return "nvidia-smi", s
    if _run(["bash", "-lc", "command -v rocm-smi"]):
        def s():
            try:    d = json.loads(_run(["rocm-smi", "--showpower", "--showuse", "--showmemuse", "--json"])); c = d[sorted(d)[0]]
            except Exception: return (None, None, None)
            def pick(keys):
                for k in c:
                    if any(t in k for t in keys):
                        try: return float(str(c[k]).split()[0])
                        except Exception: pass
                return None
            return (pick(["Average Graphics Package Power", "Power"]), pick(["GPU use", "use (%)"]), pick(["Memory"]))
        return "rocm-smi", s
    return None, None


def detect_rapl():
    """CPU package energy via RAPL. sampler() -> {domain: (energy_uj, wrap_max)}. Sums package domains."""
    doms = []
    for d in sorted(glob.glob("/sys/class/powercap/intel-rapl:*")):
        try:    nm = open(d + "/name").read().strip()
        except Exception: continue
        if not nm.startswith("package") or not os.access(d + "/energy_uj", os.R_OK):
            continue
        try:    mx = float(open(d + "/max_energy_range_uj").read().strip())
        except Exception: mx = None
        doms.append((d, nm, mx))
    if not doms: return None
    def sample():
        out = {}
        for d, nm, mx in doms:
            try: out[nm] = (float(open(d + "/energy_uj").read().strip()), mx)
            except Exception: pass
        return out
    return {"domains": [nm for _, nm, _ in doms], "sample": sample}


def detect_battery():
    """Real battery from /sys. sampler() -> (energy_wh, power_w, status); full_wh = pack size. None if absent."""
    bats = sorted(glob.glob("/sys/class/power_supply/BAT*")) or sorted(
        p for p in glob.glob("/sys/class/power_supply/*")
        if os.path.exists(p + "/type") and open(p + "/type").read().strip() == "Battery")
    if not bats: return None
    b = bats[0]
    def rd(n):
        try: return float(open(os.path.join(b, n)).read().strip())
        except Exception: return None
    def full_wh():
        e = rd("energy_full")
        if e: return e / 1e6
        q, v = rd("charge_full"), rd("voltage_now")
        return (q * v / 1e12) if (q and v) else None
    def sampler():
        e, v, p, q = rd("energy_now"), rd("voltage_now"), rd("power_now"), rd("charge_now")
        energy_wh = (e / 1e6) if e else ((q * v / 1e12) if (q and v) else None)
        power_w = (p / 1e6) if p else None
        if power_w is None:
            i = rd("current_now"); power_w = (i * v / 1e12) if (i and v) else None
        try: status = open(os.path.join(b, "status")).read().strip()
        except Exception: status = "?"
        return (energy_wh, power_w, status)
    return {"path": b, "full_wh": full_wh(), "sample": sampler}


def rapl_delta(prev, cur):
    """Watts between two RAPL samples is handled elsewhere; here: summed Joules consumed prev->cur."""
    j = 0.0
    for nm, (e2, mx) in cur.items():
        if nm not in prev: continue
        e1 = prev[nm][0]
        d = e2 - e1
        if d < 0 and mx: d += mx          # counter wrapped
        j += max(d, 0) / 1e6              # uJ -> J
    return j


def pct(xs, q):
    if not xs: return None
    s = sorted(xs); return s[min(len(s) - 1, int(q / 100 * len(s)))]


def integ(ts, ws):
    wh = 0.0
    for i in range(1, len(ts)):
        a, b = ws[i - 1], ws[i]
        if a is None or b is None: continue
        wh += (a + b) / 2 * (ts[i] - ts[i - 1])
    return wh / 3600.0


def stat_line(label, xs, unit="W"):
    xs = [x for x in xs if x is not None]
    if not xs: return f"  {label}: (not available)"
    return (f"  {label}: avg {sum(xs)/len(xs):.1f}  min {min(xs):.1f}  max {max(xs):.1f}  "
            f"p50 {pct(xs,50):.1f}  p95 {pct(xs,95):.1f} {unit}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--duration", type=float, default=0, help="seconds; 0 = until Ctrl-C")
    ap.add_argument("--flight-min", type=float, default=20.0)
    ap.add_argument("--pack-wh", type=float, default=0, help="pack Wh to model flights if no battery")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    gpu_name, gpu_sample = detect_gpu()
    rapl = detect_rapl()
    bat = detect_battery()
    print(f"[power] GPU: {gpu_name or 'none'} | CPU RAPL: {','.join(rapl['domains']) if rapl else 'none'} | "
          f"battery: {('%.1f Wh' % bat['full_wh']) if bat and bat['full_wh'] else 'none (AC/desktop)'}", flush=True)

    t0 = time.time()
    ts, gpu_w, sys_w, e_wh, cpu_w = [], [], [], [], []
    prev_rapl = rapl["sample"]() if rapl else None
    prev_t = t0
    out = open(a.out, "w") if a.out else None
    if out: out.write("t_epoch,t_rel,cpu_w,gpu_w,gpu_util,gpu_mem_mb,sys_w,batt_energy_wh,batt_status\n")
    stop = {"v": False}
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("v", True))
    print("[power] sampling... (Ctrl-C to stop and report)", flush=True)

    while not stop["v"]:
        now = time.time(); rel = now - t0
        gp, gu, gm = gpu_sample() if gpu_sample else (None, None, None)
        be, bp, bs = bat["sample"]() if bat else (None, None, "")
        cw = None
        if rapl:
            cur = rapl["sample"](); t_rapl = time.time()            # stamp AT the read, not loop-top
            dt = t_rapl - prev_t                                     # window must match the energy delta
            if dt > 0.05: cw = rapl_delta(prev_rapl, cur) / dt       # J/s = W
            prev_rapl, prev_t = cur, t_rapl
        ts.append(rel); gpu_w.append(gp); sys_w.append(bp); e_wh.append(be); cpu_w.append(cw)
        if out:
            out.write(f"{now:.3f},{rel:.1f},{cw},{gp},{gu},{gm},{bp},{be},{bs}\n"); out.flush()
        if a.duration and rel >= a.duration: break
        time.sleep(a.interval)
    if out: out.close()

    dur = ts[-1] if ts else 0
    print(f"\n[power] === report ({dur/60:.1f} min, {len(ts)} samples) ===")
    print("  (Wh = watts x hours. watts = Wh / hours. 90 Wh pack = 90 W for 1 h.)")
    print(stat_line("CPU package (RAPL)", cpu_w))
    print(stat_line("GPU         (smi) ", gpu_w))
    cpu_e, gpu_e = integ(ts, cpu_w), integ(ts, gpu_w)

    # compute total = CPU + GPU, per sample where both exist
    comp = [(c + g) for c, g in zip(cpu_w, gpu_w) if c is not None and g is not None]
    comp_avg = (sum(comp) / len(comp)) if comp else None

    s = [x for x in sys_w if x is not None]
    ev = [x for x in e_wh if x is not None]
    sys_avg, sys_energy = (sum(s) / len(s) if s else None), None
    if len(ev) >= 2 and ev[0] > ev[-1]:
        sys_energy = ev[0] - ev[-1]
        if dur > 0: sys_avg = sys_energy / (dur / 3600.0)

    print(f"  energy this window: CPU {cpu_e:.3f} Wh | GPU {gpu_e:.3f} Wh | CPU+GPU {cpu_e+gpu_e:.3f} Wh")
    if sys_avg:
        print(f"  FULL SYSTEM (battery): avg {sys_avg:.1f} W"
              + (f", {sys_energy:.3f} Wh used" if sys_energy else "") + "  <- whole box, the honest total")
        total_w, total_src, pack_note = sys_avg, "full system", "whole box"
    elif comp_avg:
        print(f"  COMPUTE DRAW (CPU+GPU): avg {comp_avg:.1f} W  <- LOWER bound (excludes RAM/board/PSU loss)")
        total_w, total_src, pack_note = comp_avg, "compute (CPU+GPU)", "LOWER bound; add RAM/board/PSU for the wall number"
    else:
        total_w = total_src = None

    pack = (bat["full_wh"] if bat and bat["full_wh"] else None) or (a.pack_wh or None)
    if total_w and pack:
        h = pack / total_w
        print(f"  --> {pack:.0f} Wh pack at {total_w:.1f} W ({total_src}): ~{h*60:.0f} min runtime, "
              f"~{h*60/a.flight_min:.1f} flights of {a.flight_min:.0f} min  [{pack_note}]")
    elif total_w and not pack:
        print(f"  --> draw is {total_w:.1f} W ({total_src}); pass --pack-wh N to get flights per charge.")
    else:
        print("  --> no usable power source. Need nvidia-smi/rocm-smi, RAPL, or a battery.")


if __name__ == "__main__":
    main()
