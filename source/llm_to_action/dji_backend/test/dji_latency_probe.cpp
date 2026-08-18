/*
    dji_latency_probe -- measure the REAL control loop's latency, through the REAL
    DjiBackend, against whatever host:port you point it at. Same binary for the mock
    (validates the method, gives a floor) and the phone (the real numbers).

    It reports two legs of the Task-C table (spec-dji-endtoend-bringup.md):

      command->action : t0 = a step setpoint is emitted on Linux; t1 = the drone's
                        velocity3D crosses a threshold in the NEXT fresh telemetry
                        sample. Both stamps are Linux steady_clock, so no clock
                        sync is needed. This is the scored <1 s number. We step in
                        BODY forward (set_body_velocity), so it does not depend on
                        the yaw estimate or on velocity3D's exact frame -- we watch
                        the velocity MAGNITUDE rise, which is frame-agnostic.
      telemetry RTT   : the backend times each GET /status/ round-trip; we sample
                        that (statusRttUs) over a quiet window.

    The other two legs are measured outside this binary: video glass-to-Linux (film
    a millisecond clock, compare the decoded frame) and the WiFi baseline
    (scripts/test/dji_mock/ws_latency.py). See the runbook.

    Against the mock, command->action is a floor: the mock sets velocity3D straight
    from the sticks with no drone dynamics, so you measure WS-tick + poll-tick, not
    real spin-up. The real drone adds WiFi + rotor spin-up. That is the point of
    running it on the bench.

    Usage: dji_latency_probe [host] [port] [trials] [rttSecs]
           defaults: 127.0.0.1 8080 20 5
    SAFETY: this arms and commands the drone. PROPS OFF / TETHERED for the first run.
*/
#include "dji_backend/dji_backend.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>

using namespace std::chrono;
using clk = steady_clock;

static u64 now_us() { return u64(duration_cast<microseconds>(clk::now().time_since_epoch()).count()); }
static f32 speed(const Odometry& o) {
    return std::sqrt(o.vel.x * o.vel.x + o.vel.y * o.vel.y + o.vel.z * o.vel.z);
}

/* nearest-rank percentile on a copy-sorted vector (ms). */
static double pctile(std::vector<double> xs, double p) {
    if (xs.empty()) return 0.0;
    std::sort(xs.begin(), xs.end());
    long k = long(std::round((p / 100.0) * double(xs.size() - 1)));
    if (k < 0) k = 0;
    if (k >= long(xs.size())) k = long(xs.size()) - 1;
    return xs[size_t(k)];
}
static void row(const char* leg, std::vector<double>& xs) {
    if (xs.empty()) { std::printf("  %-20s %4d      --       --       --   ms\n", leg, 0); return; }
    double mx = *std::max_element(xs.begin(), xs.end());
    std::printf("  %-20s %4zu  %7.1f  %7.1f  %7.1f   ms\n",
                leg, xs.size(), pctile(xs, 50), pctile(xs, 95), mx);
}

int main(int argc, char** argv) {
    const char* host    = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port    = (argc > 2) ? std::atoi(argv[2]) : 8080;
    int         trials  = (argc > 3) ? std::atoi(argv[3]) : 20;
    int         rttSecs = (argc > 4) ? std::atoi(argv[4]) : 5;

    const f32 kStepMps    = 1.0f;          /* body-forward step from rest         */
    const f32 kRiseThresh = 0.3f * kStepMps; /* "responded" when |vel| crosses this */
    const f32 kRestThresh = 0.15f;         /* "at rest" when |vel| below this       */

    std::printf("dji_latency_probe -> %s:%d  trials=%d  rttWindow=%ds\n", host, port, trials, rttSecs);
    std::printf("SAFETY: this arms + commands the drone -- PROPS OFF / TETHERED.\n");

    DjiBackend dji(host, u16(port));
    if (!dji.start()) { std::printf("start FAILED (nothing listening at %s:%d?)\n", host, port); return 1; }

    for (int i = 0; i < 100 && !dji.gotFirstStatus(); i++)
        std::this_thread::sleep_for(milliseconds(20));
    if (!dji.gotFirstStatus()) { std::printf("no telemetry\n"); dji.stop(); return 1; }
    std::printf("telemetry up: battery=%d%%\n", dji.battery_pct());

    auto ts = dji.takeoff();
    std::printf("takeoff -> code=%d\n", int(ts.code));
    std::this_thread::sleep_for(milliseconds(500));   /* let the stream settle */

    /* ---- command->action: N step trials ---------------------------------- */
    std::vector<double> cmd2act;
    int misses = 0;
    for (int i = 0; i < trials; i++) {
        /* settle back to rest */
        dji.set_body_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
        auto restDl = clk::now() + milliseconds(1500);
        while (clk::now() < restDl && speed(dji.odometry()) > kRestThresh)
            std::this_thread::sleep_for(milliseconds(2));

        u64  lastStamp = dji.telemetryStampUs();
        u64  t0 = now_us();
        dji.set_body_velocity(Vec3{kStepMps, 0.0f, 0.0f}, 0.0f);

        u64  t1 = 0;
        auto riseDl = clk::now() + milliseconds(1500);
        while (clk::now() < riseDl) {
            u64 st = dji.telemetryStampUs();
            if (st != lastStamp) {                     /* a fresh telemetry sample */
                if (speed(dji.odometry()) > kRiseThresh) { t1 = st; break; }
                lastStamp = st;
            }
            std::this_thread::sleep_for(milliseconds(1));
        }
        if (t1 > t0) cmd2act.push_back(double(t1 - t0) / 1000.0);
        else { ++misses; std::printf("  trial %2d: no rise in 1.5s\n", i); }
    }

    /* ---- telemetry round-trip: sample the backend's per-GET timing --------- */
    dji.set_body_velocity(Vec3{0.0f, 0.0f, 0.0f}, 0.0f);
    std::vector<double> rtt;
    u64  lastRtt = 0;
    auto rttDl = clk::now() + seconds(rttSecs);
    while (clk::now() < rttDl) {
        u64 r = dji.statusRttUs();
        if (r != 0 && r != lastRtt) { rtt.push_back(double(r) / 1000.0); lastRtt = r; }
        std::this_thread::sleep_for(milliseconds(5));
    }

    auto ls = dji.land();
    std::printf("land -> code=%d\n", int(ls.code));
    dji.stop();

    std::printf("\n=== DJI end-to-end latency  (%s:%d) ===\n", host, port);
    std::printf("  leg                     n   median     p95      max\n");
    row("command->action", cmd2act);
    row("telemetry GET RTT", rtt);
    std::printf("\n  not measured here: video glass->Linux (film a ms clock);"
                " WiFi baseline (ws_latency.py).\n");
    if (misses) std::printf("  WARNING: %d/%d command->action trials saw no response.\n", misses, trials);

    /* A run is usable if takeoff/land confirmed and we captured most trials. */
    bool ok = (ts.code == BackendStatus::Code::OK) &&
              (ls.code == BackendStatus::Code::OK) &&
              (int(cmd2act.size()) >= (trials * 3) / 4) &&
              !rtt.empty();
    std::printf("\n==== dji_latency_probe: %s ====\n", ok ? "OK" : "INCOMPLETE");
    return ok ? 0 : 1;
}
