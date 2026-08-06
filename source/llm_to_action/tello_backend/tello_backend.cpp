#include "tello_backend.hpp"

#include <chrono>
#include <cstdio>
#include <optional>
#include <string>
#include <ctello.h>

using namespace std::chrono;


TelloBackend::TelloBackend() = default;

TelloBackend::~TelloBackend() {
    stop_impl();
}


u64 TelloBackend::nowUs() {
    return __scast(u64, duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count());
}


bool TelloBackend::sendCmd(const char* cmd, bool awaitAck) {
    {
        std::lock_guard<std::mutex> lk(m_cmdMtx);
        if (!m_tello) return false;
        if (!m_tello->SendCommand(cmd)) return false;
    }
    if (!awaitAck) return true;

    /* Ack wait happens OUTSIDE m_cmdMtx: this mutex only guards SendCommand(),
       not ReceiveResponse(). Otherwise a slow ack (up to 7s below) blocks
       streamLoop()'s rc keepalive from acquiring the lock, starving the drone
       of stick updates for the whole wait -- observed as drift/unresponsiveness
       right after every takeoff/land while the ack was pending.
       ctello ReceiveResponse() is a non-blocking poll; bound the wait so a lost
       ack can never hang the caller (Gemini's `while(!ReceiveResponse())` could). */
    const auto deadline = steady_clock::now() + seconds(7);
    while (steady_clock::now() < deadline) {
        if (m_tello->ReceiveResponse()) return true;
        std::this_thread::sleep_for(milliseconds(10));
    }
    return false;
}


bool TelloBackend::start_impl() {
    if (m_running.load(std::memory_order_relaxed)) return true;

    m_tello = std::make_unique<ctello::Tello>();
    if (!m_tello->Bind()) {
        m_tello.reset();
        return false;
    }
    /* Enter SDK mode and start the video stream before anything flies. */
    if (!sendCmd("command", true)) { m_tello.reset(); return false; }
    sendCmd("streamon", true);

    m_running.store(true, std::memory_order_relaxed);
    m_stateThread  = std::thread(&TelloBackend::stateLoop, this);
    m_streamThread = std::thread(&TelloBackend::streamLoop, this);
    return true;
}


void TelloBackend::stop_impl() {
    if (!m_running.exchange(false, std::memory_order_relaxed)) {
        /* Never fully started (or already stopped): join anything dangling. */
        if (m_streamThread.joinable()) m_streamThread.join();
        if (m_stateThread.joinable())  m_stateThread.join();
        return;
    }
    if (m_streamThread.joinable()) m_streamThread.join();
    if (m_stateThread.joinable())  m_stateThread.join();

    /* Safety on teardown: stop commanding, land, kill the stream. */
    if (m_tello) {
        setRc({});
        sendCmd("land", true);
        sendCmd("streamoff", true);
    }
    m_ioState.store(IOState::STANDBY, std::memory_order_relaxed);
}


void TelloBackend::setRc(RcCommand rc) {
    m_rcA.store(rc.a, std::memory_order_relaxed);
    m_rcB.store(rc.b, std::memory_order_relaxed);
    m_rcC.store(rc.c, std::memory_order_relaxed);
    m_rcD.store(rc.d, std::memory_order_relaxed);
}


f32 TelloBackend::currentYawRad() const {
    /* NOTE: Tello's yaw origin is its power-on heading, not true East, so the
       "world ENU" this yields is a pseudo-world. Fine for relative moves; the
       teleop harness uses set_body_velocity to avoid depending on it at all. */
    return __scast(f32, m_yawDeg.load(std::memory_order_relaxed)) * __scast(f32, M_PI) / 180.0f;
}


BackendStatus TelloBackend::takeoff_impl() {
    setRc({});
    bool ok = sendCmd("takeoff", true);
    if (ok) m_ioState.store(IOState::FLIGHT, std::memory_order_relaxed);
    return { ok ? BackendStatus::Code::OK : BackendStatus::Code::REJECTED };
}

BackendStatus TelloBackend::land_impl() {
    setRc({});
    bool ok = sendCmd("land", true);
    m_ioState.store(IOState::STANDBY, std::memory_order_relaxed);
    return { ok ? BackendStatus::Code::OK : BackendStatus::Code::REJECTED };
}

void TelloBackend::set_velocity_impl(Vec3 worldVelEnu, f32 yawspeed) {
    Vec3 flu = enu_to_flu(worldVelEnu, currentYawRad());
    setRc(flu_to_rc(flu, yawrate_to_stick(yawspeed)));
}

void TelloBackend::set_body_velocity(Vec3 flu, f32 yawspeed) {
    setRc(flu_to_rc(flu, yawrate_to_stick(yawspeed)));
}

void TelloBackend::disarm_impl()       { land_impl(); }
void TelloBackend::force_disarm_impl() { sendCmd("emergency", false); }


Odometry TelloBackend::odometry_impl() const {
    Odometry od;
    od.pos = { 0.0f, 0.0f, __scast(f32, m_heightCm.load(std::memory_order_relaxed)) / 100.0f };
    od.vel = { __scast(f32, m_vgx.load(std::memory_order_relaxed)) / 100.0f,
               __scast(f32, m_vgy.load(std::memory_order_relaxed)) / 100.0f,
               __scast(f32, m_vgz.load(std::memory_order_relaxed)) / 100.0f };
    od.yaw          = currentYawRad();
    od.host_stamp_us = m_hostStampUs.load(std::memory_order_relaxed);
    od.valid        = m_gotFirstState.load(std::memory_order_relaxed);
    return od;
}


void TelloBackend::stateLoop() {
    const auto period = milliseconds(1000 / kTelloStatePollHz);
    u32 consecutiveMisses = 0, unparsable = 0;
    while (m_running.load(std::memory_order_relaxed)) {
        std::optional<std::string> s = m_tello->GetState();  /* separate socket from cmd. */
        if (s) {
            TelloState st{};
            if (parse_tello_state_branchless(s->c_str(), st)) {
                m_yawDeg.store(st.yaw, std::memory_order_relaxed);
                m_heightCm.store(st.h, std::memory_order_relaxed);
                m_batPct.store(st.bat, std::memory_order_relaxed);
                m_vgx.store(st.vgx, std::memory_order_relaxed);
                m_vgy.store(st.vgy, std::memory_order_relaxed);
                m_vgz.store(st.vgz, std::memory_order_relaxed);
                m_hostStampUs.store(nowUs(), std::memory_order_relaxed);
                if (!m_gotFirstState.exchange(true, std::memory_order_relaxed))
                    std::fprintf(stderr, "[state] first valid GetState() parsed OK (line=\"%s\")\n", s->c_str());
                consecutiveMisses = 0;
            } else if (++unparsable == 1 || unparsable % kTelloStatePollHz == 0) {
                std::fprintf(stderr, "[state] GetState() line failed to parse (#%u): \"%s\"\n", unparsable, s->c_str());
            }
        } else if (++consecutiveMisses % kTelloStatePollHz == 0) {
            std::fprintf(stderr, "[state] no GetState() response for %u polls (~%us) -- state socket may be dead\n",
                         consecutiveMisses, consecutiveMisses / kTelloStatePollHz);
        }
        std::this_thread::sleep_for(period);
    }
}


void TelloBackend::streamLoop() {
    const auto period = milliseconds(1000 / kTelloStreamRateHz);
    while (m_running.load(std::memory_order_relaxed)) {
        char buf[48];
        std::snprintf(buf, sizeof(buf), "rc %d %d %d %d",
                      m_rcA.load(std::memory_order_relaxed),
                      m_rcB.load(std::memory_order_relaxed),
                      m_rcC.load(std::memory_order_relaxed),
                      m_rcD.load(std::memory_order_relaxed));
        sendCmd(buf, false);   /* Tello does not ack `rc`. */
        std::this_thread::sleep_for(period);
    }
}
