#pragma once
/*
    TelloBackend -- the concrete drone backend for a DJI Ryze Tello.

    Owns EVERYTHING platform-specific: the ctello command/state client, the state
    poll thread, and the ~20Hz `rc` stream thread. A caller drives it through the
    same semantic verbs as PX4Backend (takeoff/land/set_velocity/disarm/odometry/
    state) so the two are interchangeable at the seam. It never speaks the Tello
    SDK strings to the outside world.

    ROS-free by construction: no rclcpp, no ROS timers. Its own std::thread loops
    and steady_clock. This is the deliberate difference from PX4Backend (which is
    a ROS node) -- Tello needs no DDS, so we don't drag it in. A thin ROS adapter
    is added later at FMU integration, not here.

    Concurrency: shared telemetry (state thread -> callers) rides std::atomic
    scalars, the proven no-mutex model. The one mutex here (m_cmdMtx) serialises
    writes to the single command socket, since takeoff/land/stream all SendCommand
    from different threads -- that is socket serialisation, not shared-scalar state.

    Frame: canonical world frame is ENU. set_velocity takes an ENU world velocity
    and converts ENU->body-FLU->stick at the single edge (enu_to_flu + flu_to_rc).
*/
#include <atomic>
#include <memory>
#include <mutex>
#include <thread>
#include "tello_backend_base.hpp"


/* Kept opaque so ctello.h (and its spdlog/OpenCV pull) stays out of consumers'
   translation units; the full type is only needed in tello_backend.cpp. */
namespace ctello { class Tello; }


class TelloBackend {
public:
    TelloBackend();
    ~TelloBackend();

    TelloBackend(const TelloBackend&)            = delete;
    TelloBackend& operator=(const TelloBackend&) = delete;

    /* Bind the SDK, enter command mode + streamon, launch state/stream threads.
       Returns false if the initial bind/handshake fails. */
    bool start();
    /* Stop streaming, land (safety), join threads. Idempotent; dtor calls it. */
    void stop();

    /* ---- semantic verbs (non-blocking; progress observed via state()) ------ */
    BackendStatus takeoff();
    BackendStatus land();
    /* Stream this ENU world velocity (m/s) + yaw rate (rad/s, CCW+). */
    void          set_velocity(Vec3 worldVelEnu, f32 yawspeed);
    /* Teleop-direct: body FLU velocity (m/s) + yaw rate (rad/s, CCW+); no
       dependence on the drifting yaw estimate. W = +forward. */
    void          set_body_velocity(Vec3 flu, f32 yawspeed);
    void          disarm();        /* graceful: land.      */
    void          force_disarm();  /* emergency: motors off. */

    /* ---- telemetry / observable state -------------------------------------- */
    Odometry odometry() const;
    IOState  state() const { return m_ioState.load(std::memory_order_relaxed); }
    bool     gotFirstState() const { return m_gotFirstState.load(std::memory_order_relaxed); }

private:
    void stateLoop();
    void streamLoop();
    void setRc(RcCommand rc);
    f32  currentYawRad() const;
    /* Serialised SendCommand; optionally waits for the SDK "ok" ack. */
    bool sendCmd(const char* cmd, bool awaitAck);
    static u64 nowUs();

    std::unique_ptr<ctello::Tello> m_tello;

    std::thread m_stateThread;
    std::thread m_streamThread;
    std::atomic<bool> m_running{false};

    /* Streamed setpoint (callers -> stream loop). */
    std::atomic<i32> m_rcA{0}, m_rcB{0}, m_rcC{0}, m_rcD{0};

    /* Shared telemetry (state loop -> callers). Ints in native SDK units. */
    std::atomic<i32> m_yawDeg{0}, m_heightCm{0}, m_batPct{0};
    std::atomic<i32> m_vgx{0}, m_vgy{0}, m_vgz{0};
    std::atomic<u64> m_hostStampUs{0};
    std::atomic<bool> m_gotFirstState{false};

    std::atomic<IOState> m_ioState{IOState::STANDBY};

    std::mutex m_cmdMtx;  /* serialises the single command socket. */
};
