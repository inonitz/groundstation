/*
    Head-to-head WebSocket-client test against the mock ApiServer
    (scripts/test/dji_mock/mock_apiserver.py). Runs BOTH RawWsClient and
    WsppWsClient through the same script and prints a comparison:

      connect -> POST /c/takeoff -> stream FlightParam{vx=+1} at kDjiStreamRateHz
      for ~N frames -> GET /status/ and assert the mock's position advanced ->
      POST /c/land -> close. Reports per-send latency (p50/p95/max) for each.

    Plus a robustness probe on the raw client: connect() to a dead port must FAIL
    fast (bounded by the timeout), never hang.

    ROS-free, drone-free. Build paths come from CMake (websocketpp + Asio +
    cpp-httplib + nlohmann + util2). Usage: dji_ws_test [host] [port].
*/
#include "dji_backend/dji_status_parse.hpp"   /* nlohmann-first: base (FlightParam) + parse + Odometry */
#include "dji_backend/dji_ws.hpp"
#include <httplib.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <thread>
#include <vector>

using clk = std::chrono::steady_clock;

static double pctl(std::vector<double>& v, double p) {
    if (v.empty()) return 0.0;
    std::sort(v.begin(), v.end());
    size_t i = size_t(p * double(v.size() - 1) + 0.5);
    return v[i];
}

static double status_posx(httplib::Client& http) {
    auto r = http.Get(kDjiStatusPath);
    if (!r || r->status != 200) return -1e9;
    StatusTelemetry t{};
    if (!parse_status_json(r->body.c_str(), t)) return -1e9;
    return double(t.pos.x);
}

template <class Client>
static bool run_client(const char* host, int port) {
    std::printf("\n=== %s ===\n", Client::name());
    Client c;
    auto tc0 = clk::now();
    if (!c.connect(host, u16(port), kDjiSticksPath, 2000)) {
        std::printf("  connect FAILED\n");
        return false;
    }
    double connectMs = std::chrono::duration<double, std::milli>(clk::now() - tc0).count();
    std::printf("  connect OK (%.1f ms)\n", connectMs);

    httplib::Client http(host, port);
    auto to = http.Post(kDjiTakeoffPath);
    std::printf("  takeoff -> %s\n", (to && to->status == 200) ? "ok" : "??");

    double posx0 = status_posx(http);

    const int  N      = 90;                              /* ~5 s at 18 Hz */
    const auto period = std::chrono::milliseconds(1000 / kDjiStreamRateHz);
    std::vector<double> lat;
    lat.reserve(size_t(N));
    char buf[96];
    FlightParam p; p.vx = 1.0f;                          /* body forward 1 m/s */
    int sent = 0;
    for (int i = 0; i < N; i++) {
        int len = flightparam_to_json(p, buf, sizeof(buf));
        auto t0 = clk::now();
        bool ok = c.send_text(buf, size_t(len));
        auto t1 = clk::now();
        if (!ok) { std::printf("  send #%d FAILED (disconnected)\n", i); c.close(); return false; }
        lat.push_back(std::chrono::duration<double, std::micro>(t1 - t0).count());
        ++sent;
        std::this_thread::sleep_for(period);
    }

    double posx1 = status_posx(http);
    bool   moved = (posx0 > -1e8 && posx1 > -1e8 && (posx1 - posx0) > 0.5);
    bool   alive = c.connected();

    http.Post(kDjiLandPath);
    c.close();

    double p50 = pctl(lat, 0.50), p95 = pctl(lat, 0.95), mx = pctl(lat, 1.0);
    std::printf("  streamed %d/%d frames; still-connected=%s\n", sent, N, alive ? "yes" : "no");
    std::printf("  send latency  p50=%.1f us  p95=%.1f us  max=%.1f us\n", p50, p95, mx);
    std::printf("  mock position advanced %.2f m (%.2f -> %.2f) : %s\n",
                posx1 - posx0, posx0, posx1, moved ? "PASS" : "FAIL");
    return moved;
}

int main(int argc, char** argv) {
    const char* host = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port = (argc > 2) ? std::atoi(argv[2]) : 8080;
    std::printf("dji_ws_test -> %s:%d\n", host, port);

    /* Robustness: connect to a dead port must fail fast, not hang. */
    {
        RawWsClient dead;
        auto t0 = clk::now();
        bool ok = dead.connect(host, u16(port + 1), kDjiSticksPath, 500);
        double ms = std::chrono::duration<double, std::milli>(clk::now() - t0).count();
        std::printf("robustness: raw connect to dead :%d -> %s in %.0f ms (want fail <1500)\n",
                    port + 1, ok ? "connected?!" : "failed", ms);
        if (ok || ms > 1500) { std::printf("robustness FAIL\n"); return 1; }
    }

    bool raw  = run_client<RawWsClient>(host, port);
    bool wspp = run_client<WsppWsClient>(host, port);

    std::printf("\n==== RESULT ====  raw=%s  websocketpp=%s\n",
                raw ? "PASS" : "FAIL", wspp ? "PASS" : "FAIL");
    return (raw && wspp) ? 0 : 1;
}
