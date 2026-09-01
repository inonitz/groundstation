/*
    DjiBackend implementation. See dji_backend.hpp for the design; this file owns
    everything that needs the actual wire libraries (the WS client + httplib), so
    they never leak into a consumer's translation unit.

    Include order matters: dji_status_parse.hpp pulls nlohmann FIRST (before the
    util2 macro.h that frame_convert drags in), so the two do not collide. httplib
    comes last.
*/
#include "dji_backend/dji_status_parse.hpp"    /* nlohmann-first: StatusTelemetry, parse */
#include "dji_backend/dji_backend.hpp"
#include <httplib.h>

#include <chrono>
#include <cstdio>
#include <string>

using namespace std::chrono;


DjiBackend::DjiBackend() : DjiBackend(kDjiDefaultHost, kDjiDefaultPort) {}
DjiBackend::DjiBackend(const char* host, u16 port) : m_host(host), m_port(port) {}
DjiBackend::~DjiBackend() { stop_impl(); }


u64 DjiBackend::nowUs() {
    return u64(duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count());
}

void DjiBackend::setSetpoint(const FlightParam& p) {
    m_vx.store(p.vx, std::memory_order_relaxed);
    m_vy.store(p.vy, std::memory_order_relaxed);
    m_vz.store(p.vz, std::memory_order_relaxed);
    m_yaw.store(p.yaw, std::memory_order_relaxed);
}


bool DjiBackend::start_impl() {
    if (m_running.load(std::memory_order_relaxed)) return true;

    m_http = std::make_unique<httplib::Client>(m_host, int(m_port));
    m_http->set_connection_timeout(0, 300000);   /* 300 ms */
    m_http->set_read_timeout(1, 0);
    m_http->set_keep_alive(true);

    if (!m_ws.connect(m_host.c_str(), m_port, kDjiSticksPath, 2000)) {
        std::fprintf(stderr, "[dji] WS connect ws://%s:%u%s FAILED\n",
                     m_host.c_str(), unsigned(m_port), kDjiSticksPath);
        m_http.reset();
        return false;
    }
    std::fprintf(stderr, "[dji] WS connected ws://%s:%u%s (client=%s)\n",
                 m_host.c_str(), unsigned(m_port), kDjiSticksPath, DjiWsClient::name());

    m_running.store(true, std::memory_order_relaxed);
    m_statusThread = std::thread(&DjiBackend::statusLoop, this);
    m_streamThread = std::thread(&DjiBackend::streamLoop, this);
    return true;
}

void DjiBackend::stop_impl() {
    if (!m_running.exchange(false, std::memory_order_relaxed)) {
        if (m_streamThread.joinable()) m_streamThread.join();
        if (m_statusThread.joinable()) m_statusThread.join();
        return;
    }
    if (m_streamThread.joinable()) m_streamThread.join();
    if (m_statusThread.joinable()) m_statusThread.join();

    /* Safety on teardown: stop commanding, land, drop the sockets. */
    setSetpoint({});
    if (m_http) httpPost(kDjiLandPath);
    m_ws.close();
    m_http.reset();
    m_ioState.store(IOState::STANDBY, std::memory_order_relaxed);
}


bool DjiBackend::httpPost(const char* path) {
    std::lock_guard<std::mutex> lk(m_httpMtx);
    if (!m_http) return false;
    auto r = m_http->Post(path);
    return r && r->status == 200;
}


/* Poll telemetry until aircraft.isFlying matches `want`, or timeout. The drone is
   the source of truth: takeoff/land succeed when the PHYSICAL state changes, not
   when an HTTP body says so (the app's POST /c/takeoff|/c/land send no body). */
bool DjiBackend::confirmFlying(bool want, u32 timeoutMs) const {
    auto deadline = steady_clock::now() + milliseconds(timeoutMs);
    while (steady_clock::now() < deadline) {
        if (m_gotFirstStatus.load(std::memory_order_relaxed) &&
            m_isFlying.load(std::memory_order_relaxed) == want)
            return true;
        std::this_thread::sleep_for(milliseconds(20));
    }
    return m_isFlying.load(std::memory_order_relaxed) == want;
}

BackendStatus DjiBackend::takeoff_impl() {
    setSetpoint({});
    /* Fire the verb; the ok body is best-effort (fast path for a well-behaved
       server), but telemetry isFlying is the authority. */
    bool ack = httpPost(kDjiTakeoffPath);
    bool ok  = ack || confirmFlying(true, 4000);
    if (ok) m_ioState.store(IOState::FLIGHT, std::memory_order_relaxed);
    return { ok ? BackendStatus::Code::OK : BackendStatus::Code::REJECTED };
}

BackendStatus DjiBackend::land_impl() {
    setSetpoint({});
    bool ack = httpPost(kDjiLandPath);
    bool ok  = ack || confirmFlying(false, 5000);   /* landing takes a few seconds */
    m_ioState.store(IOState::STANDBY, std::memory_order_relaxed);
    return { ok ? BackendStatus::Code::OK : BackendStatus::Code::REJECTED };
}

void DjiBackend::set_velocity_impl(Vec3 worldVelEnu, f32 yawspeed) {
    setSetpoint(enu_vel_to_flightparam(worldVelEnu, currentYawRad(), yawspeed));
}

void DjiBackend::set_body_velocity(Vec3 flu, f32 yawspeed) {
    setSetpoint(flu_vel_to_flightparam(flu, yawspeed));
}

void DjiBackend::disarm_impl()       { land_impl(); }
/* The app exposes no motor-kill; the safe stop is a land (DJI also brakes to
   hover on stream loss). */
void DjiBackend::force_disarm_impl() { setSetpoint({}); httpPost(kDjiLandPath); m_ioState.store(IOState::STANDBY, std::memory_order_relaxed); }


Odometry DjiBackend::odometry_impl() const {
    Odometry od;
    od.pos = { m_drx.load(std::memory_order_relaxed),
               m_dry.load(std::memory_order_relaxed),
               m_drz.load(std::memory_order_relaxed) };
    od.vel = { m_velx.load(std::memory_order_relaxed),
               m_vely.load(std::memory_order_relaxed),
               m_velz.load(std::memory_order_relaxed) };
    od.yaw           = m_yawEst.load(std::memory_order_relaxed);
    od.host_stamp_us = m_hostStampUs.load(std::memory_order_relaxed);
    od.valid         = m_gotFirstStatus.load(std::memory_order_relaxed);
    return od;
}


void DjiBackend::streamLoop() {
    const auto period = milliseconds(1000 / kDjiStreamRateHz);
    char buf[96];
    while (m_running.load(std::memory_order_relaxed)) {
        FlightParam p;
        p.vx  = m_vx.load(std::memory_order_relaxed);
        p.vy  = m_vy.load(std::memory_order_relaxed);
        p.vz  = m_vz.load(std::memory_order_relaxed);
        p.yaw = m_yaw.load(std::memory_order_relaxed);

        int  len = flightparam_to_json(p, buf, sizeof(buf));
        bool ok  = (len > 0) && m_ws.send_text(buf, size_t(len));
        if (!ok) {
            u32 streak = m_sendFailStreak.fetch_add(1, std::memory_order_relaxed) + 1;
            if (streak == 1 || streak % kDjiStreamRateHz == 0)
                std::fprintf(stderr, "[dji] WS send failed x%u -- reconnecting\n", streak);
            /* Drone brakes to hover while the stream is down; try to restore it. */
            m_ws.close();
            m_ws.connect(m_host.c_str(), m_port, kDjiSticksPath, 1000);
        } else {
            m_sendFailStreak.store(0, std::memory_order_relaxed);
        }
        std::this_thread::sleep_for(period);
    }
}

void DjiBackend::statusLoop() {
    const auto period = milliseconds(1000 / kDjiStatusPollHz);
    u64 lastUs = 0;
    while (m_running.load(std::memory_order_relaxed)) {
        std::string body;
        bool got = false;
        {
            std::lock_guard<std::mutex> lk(m_httpMtx);
            if (m_http) {
                auto reqT0 = steady_clock::now();
                auto r = m_http->Get(kDjiStatusPath);
                if (r && r->status == 200) {
                    body = std::move(r->body); got = true;
                    m_statusRttUs.store(u64(duration_cast<microseconds>(steady_clock::now() - reqT0).count()),
                                        std::memory_order_relaxed);
                }
            }
        }
        if (got) {
            StatusTelemetry t{};
            if (parse_status_json(body.c_str(), t)) {
                u64 now = nowUs();
                m_velx.store(t.vel.x, std::memory_order_relaxed);
                m_vely.store(t.vel.y, std::memory_order_relaxed);
                m_velz.store(t.vel.z, std::memory_order_relaxed);
                m_yawEst.store(t.yaw, std::memory_order_relaxed);
                m_isFlying.store(t.isFlying, std::memory_order_relaxed);
                if (t.batteryPct != kBatteryReadingUnknown)
                    m_batPct.store(t.batteryPct, std::memory_order_relaxed);

                /* Dead-reckon position from velocity3D (GPS is invalid indoors).
                   Single writer here, so plain load+store on the atomics is safe. */
                if (lastUs != 0) {
                    f32 dt = f32(now - lastUs) / 1e6f;
                    m_drx.store(m_drx.load(std::memory_order_relaxed) + t.vel.x * dt, std::memory_order_relaxed);
                    m_dry.store(m_dry.load(std::memory_order_relaxed) + t.vel.y * dt, std::memory_order_relaxed);
                    m_drz.store(m_drz.load(std::memory_order_relaxed) + t.vel.z * dt, std::memory_order_relaxed);
                }
                lastUs = now;
                m_hostStampUs.store(now, std::memory_order_relaxed);
                if (!m_gotFirstStatus.exchange(true, std::memory_order_relaxed))
                    std::fprintf(stderr, "[dji] first /status parsed (bat=%d%%, flying=%d)\n",
                                 t.batteryPct, int(t.isFlying));
                m_pollMissStreak.store(0, std::memory_order_relaxed);
            }
        } else {
            u32 streak = m_pollMissStreak.fetch_add(1, std::memory_order_relaxed) + 1;
            if (streak % kDjiStatusPollHz == 0)
                std::fprintf(stderr, "[dji] /status poll miss x%u (~%us)\n", streak, streak / kDjiStatusPollHz);
        }
        std::this_thread::sleep_for(period);
    }
}
