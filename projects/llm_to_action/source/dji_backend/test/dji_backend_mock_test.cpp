/*
    Full-backend SOAK + acceptance test against the mock ApiServer. Drives the REAL
    DjiBackend (both threads: WS stick stream + httplib /status poll) through the
    semantic verbs, then holds a sustained control stream and checks invariants the
    whole way -- not a 90-frame smoke test.

      start -> wait for telemetry -> takeoff -> stream a varied setpoint at 50 Hz
      for <durationSec> (default 20 s) -> every 500 ms verify: telemetry stays
      FRESH, zero WS send failures, near-zero /status poll misses, dead-reckon
      advancing -> land -> stop.

    Uses the default DjiWsClient (RawWsClient), so it also proves the default build
    needs no websocketpp. Usage: dji_backend_mock_test [host] [port] [durationSec].
*/
#include "dji_backend/dji_backend.hpp"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <thread>

using namespace std::chrono;
using clk = steady_clock;

static u64 now_us() {
    return u64(duration_cast<microseconds>(clk::now().time_since_epoch()).count());
}

int main(int argc, char** argv) {
    const char* host      = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port      = (argc > 2) ? std::atoi(argv[2]) : 8080;
    int         durationSec = (argc > 3) ? std::atoi(argv[3]) : 20;
    std::printf("dji_backend_mock_test -> %s:%d  soak=%ds\n", host, port, durationSec);

    DjiBackend dji(host, u16(port));
    if (!dji.start()) { std::printf("start FAILED (mock not running?)\n"); return 1; }

    for (int i = 0; i < 50 && !dji.gotFirstStatus(); i++)
        std::this_thread::sleep_for(milliseconds(20));
    if (!dji.gotFirstStatus()) { std::printf("no telemetry\n"); dji.stop(); return 1; }
    std::printf("telemetry up: battery=%d%% state=%d\n", dji.battery_pct(), int(dji.state()));

    auto ts = dji.takeoff();
    std::printf("takeoff -> code=%d state=%d\n", int(ts.code), int(dji.state()));

    /* ---- soak: 50 Hz command, varied setpoint, invariants checked each 500 ms ---- */
    const auto  cmdPeriod = milliseconds(20);           /* 50 Hz command rate */
    const auto  t0        = clk::now();
    const auto  tEnd      = t0 + seconds(durationSec);
    u64  maxAgeUs   = 0;
    u32  worstSendFail = 0, worstPollMiss = 0;
    int  checks = 0, freshOk = 0, cmds = 0;

    auto nextCheck = t0 + milliseconds(500);
    while (clk::now() < tEnd) {
        f32 t  = duration_cast<duration<f32>>(clk::now() - t0).count();
        f32 vx = 1.0f;                                  /* body forward 1 m/s */
        f32 yw = 0.5f * std::sin(t);                    /* exercise the yaw field */
        dji.set_velocity(Vec3{ vx, 0.0f, 0.0f }, yw);
        ++cmds;

        if (clk::now() >= nextCheck) {
            ++checks;
            u64 stamp = dji.telemetryStampUs();
            u64 age   = (stamp == 0) ? ~0ull : (now_us() - stamp);
            if (age < 700000) ++freshOk;                /* < 700 ms -> fresh */
            if (age != ~0ull && age > maxAgeUs) maxAgeUs = age;
            worstSendFail = std::max(worstSendFail, dji.sendFailures());
            worstPollMiss = std::max(worstPollMiss, dji.pollMisses());
            nextCheck += milliseconds(500);
        }
        std::this_thread::sleep_for(cmdPeriod);
    }

    Odometry od = dji.odometry();
    dji.set_velocity(Vec3{ 0.0f, 0.0f, 0.0f }, 0.0f);
    std::this_thread::sleep_for(milliseconds(150));
    auto ls = dji.land();
    std::printf("land -> code=%d state=%d\n", int(ls.code), int(dji.state()));
    dji.stop();

    double maxAgeMs = double(maxAgeUs) / 1000.0;
    std::printf("\n--- soak summary ---\n");
    std::printf("  commands=%d  ~ws_frames=%d  ~status_polls=%d  checks=%d\n",
                cmds, durationSec * int(kDjiStreamRateHz), durationSec * int(kDjiStatusPollHz), checks);
    std::printf("  worst send-fail streak=%u  worst poll-miss streak=%u\n", worstSendFail, worstPollMiss);
    std::printf("  telemetry fresh checks=%d/%d  max age=%.0f ms\n", freshOk, checks, maxAgeMs);
    std::printf("  final odometry: vel=(%.2f,%.2f,%.2f) pos=(%.2f,%.2f,%.2f) valid=%d\n",
                double(od.vel.x), double(od.vel.y), double(od.vel.z),
                double(od.pos.x), double(od.pos.y), double(od.pos.z), int(od.valid));

    bool pass =
        (ts.code == BackendStatus::Code::OK) &&
        (ls.code == BackendStatus::Code::OK) &&
        od.valid &&
        (worstSendFail == 0) &&           /* stream never dropped */
        (worstPollMiss <= 2) &&           /* telemetry stayed alive */
        (checks > 0 && freshOk == checks) &&
        (double(od.vel.x) > 0.5) &&       /* telemetry reflects the command */
        (double(od.pos.x) > 0.5 * durationSec);   /* dead-reckon advanced ~1 m/s */

    std::printf("\n==== dji_backend_mock_test: %s ====\n", pass ? "PASS" : "FAIL");
    return pass ? 0 : 1;
}
