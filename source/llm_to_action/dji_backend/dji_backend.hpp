#pragma once
/*
    DjiBackend -- the concrete drone backend for a DJI Mini reached over the LAN
    through the Android recon-swarm app (or its mock). A CRTP sibling of
    PX4Backend / TelloBackend: a caller drives it through the same semantic verbs
    (takeoff/land/set_velocity/disarm/odometry/state), so the three are
    interchangeable at the backend interface. It never speaks the app's HTTP/WS
    wire to the outside world.

    ROS-free by construction: no rclcpp, no ROS timers. Two std::thread loops and
    steady_clock -- the same shape as TelloBackend (no DDS needed for a LAN app).
    A thin ROS adapter is added later at FMU integration, not here.

    Two loops:
      - streamLoop  : serialise the latest setpoint to a FlightParam and push it on
                      WS /c/ws/sticks at ~18 Hz. This stream is ALSO the keepalive
                      (stop it and the drone brakes to hover, then DJI failsafes).
      - statusLoop  : poll GET /status/ at ~15 Hz, parse -> telemetry atomics, and
                      dead-reckon horizontal position from velocity3D (GPS is
                      invalid indoors).

    Concurrency: telemetry (statusLoop -> callers) and the setpoint (callers ->
    streamLoop) ride std::atomic scalars -- the no-mutex model proven on Tello.
    The one mutex (m_httpMtx) serialises the HTTP client, since the status poll and
    the takeoff/land verbs issue requests from different threads. The WS socket has
    a single writer (streamLoop) so it needs none.

    Opaque wire types: the WS client (dji_ws.hpp) and httplib::Client are
    forward-declared / kept behind pointers so websocketpp/asio/httplib never leak
    into a consumer's translation unit (nor the FMU's strict warning set).

    Frame: set_velocity takes an ENU world velocity + yaw rate (rad/s CCW+) and
    converts ENU->body FlightParam at the single edge (dji_backend_base.hpp).
*/
#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include "dji_backend_base.hpp"
#include "dji_ws.hpp"                              /* DjiWsClient (opaque impl) */
#include "generic_backend/generic_backend.hpp"    /* GenericBackend CRTP base  */


/* httplib::Client kept opaque: httplib.h is only needed to compile dji_backend.cpp. */
namespace httplib { class Client; }


class DjiBackend : public GenericBackend<DjiBackend> {
public:
    DjiBackend();                                  /* mock defaults (127.0.0.1:8080) */
    DjiBackend(const char* host, u16 port);
    ~DjiBackend();

    DjiBackend(const DjiBackend&)            = delete;
    DjiBackend& operator=(const DjiBackend&) = delete;

    /* ---- backend-interface impls (invoked through GenericBackend<DjiBackend>) ----
       Open the WS stick stream + HTTP client, launch the stream/status threads.
       Returns false if the initial WS connect fails. */
    bool start_impl();
    /* Stop streaming, land (safety), join threads, close sockets. Idempotent. */
    void stop_impl();

    BackendStatus takeoff_impl();
    BackendStatus land_impl();
    /* Stream this ENU world velocity (m/s) + yaw rate (rad/s, CCW+). */
    void          set_velocity_impl(Vec3 worldVelEnu, f32 yawspeed);
    void          disarm_impl();        /* graceful: land.                       */
    void          force_disarm_impl();  /* no motor-kill on the API -> land.      */

    Odometry odometry_impl() const;
    IOState  state_impl() const       { return m_ioState.load(std::memory_order_relaxed); }
    i32      battery_pct_impl() const { return m_batPct.load(std::memory_order_relaxed); }

    /* ---- backend-specific (not part of the backend interface) --------------
       Teleop-direct: body FLU velocity (m/s) + yaw rate (rad/s, CCW+), no
       dependence on the yaw estimate. */
    void set_body_velocity(Vec3 flu, f32 yawspeed);
    bool gotFirstStatus() const { return m_gotFirstStatus.load(std::memory_order_relaxed); }
    bool isFlying() const { return m_isFlying.load(std::memory_order_relaxed); }
    /* Test/diagnostics observability (not control-path). */
    u32  sendFailures() const { return m_sendFailStreak.load(std::memory_order_relaxed); }
    u32  pollMisses()   const { return m_pollMissStreak.load(std::memory_order_relaxed); }
    u64  telemetryStampUs() const { return m_hostStampUs.load(std::memory_order_relaxed); }
    u64  statusRttUs()      const { return m_statusRttUs.load(std::memory_order_relaxed); }

private:
    void streamLoop();
    void statusLoop();
    bool httpPost(const char* path);            /* serialised via m_httpMtx */
    /* Confirm the physical flight state from telemetry (isFlying), so takeoff/land
       do NOT depend on the HTTP verb returning a body -- the real app's POST
       /c/takeoff|/c/land currently send none. */
    bool confirmFlying(bool want, u32 timeoutMs) const;
    void setSetpoint(const FlightParam& p);
    f32  currentYawRad() const { return m_yawEst.load(std::memory_order_relaxed); }
    static u64 nowUs();

    std::string m_host;
    u16         m_port;

    DjiWsClient                       m_ws;      /* single-writer: streamLoop only */
    std::unique_ptr<httplib::Client>  m_http;    /* opaque; guarded by m_httpMtx   */
    std::mutex                        m_httpMtx;

    std::thread       m_streamThread;
    std::thread       m_statusThread;
    std::atomic<bool> m_running{false};

    /* Streamed setpoint (callers -> streamLoop), already body-frame FlightParam. */
    std::atomic<f32> m_vx{0.0f}, m_vy{0.0f}, m_vz{0.0f}, m_yaw{0.0f};

    /* Telemetry (statusLoop -> callers). velocity3D + attitude, plus a
       dead-reckoned position integrated from velocity3D. */
    std::atomic<f32> m_velx{0.0f}, m_vely{0.0f}, m_velz{0.0f};
    std::atomic<f32> m_drx{0.0f},  m_dry{0.0f},  m_drz{0.0f};   /* dead-reckoned pos */
    std::atomic<f32> m_yawEst{0.0f};
    std::atomic<bool> m_isFlying{false};   /* aircraft.isFlying (verb confirmation) */
    std::atomic<i32> m_batPct{kBatteryReadingUnknown};
    std::atomic<u64> m_hostStampUs{0};
    std::atomic<bool> m_gotFirstStatus{false};
    std::atomic<IOState> m_ioState{IOState::STANDBY};

    /* Diagnostics (not control-path): throttled logging counters. */
    std::atomic<u32> m_sendFailStreak{0};
    std::atomic<u32> m_pollMissStreak{0};
    std::atomic<u64> m_statusRttUs{0};   /* last GET /status/ round-trip, us (diagnostics) */
};
