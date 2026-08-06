/*
    Tier-2 on-hardware teleop harness for TelloBackend.

    Flies a real Tello from the keyboard at a FIXED body velocity (hold-to-move),
    prints live telemetry, and shows the camera feed. This is the "reality, not
    castles of sand" checkpoint -- it needs a Tello on its Wi-Fi, not the CI box.

    Controls (hold to move, release to hover):
      T            takeoff              L            land
      W / S        forward / back       A / D        left / right
      R / F        up / down            Q / E        yaw left / right (CCW / CW)
      Space        hover (zero all)     Esc          land + quit

    Frames: keys drive set_body_velocity (body FLU) directly -- W = +forward --
    so teleop never depends on Tello's drifting yaw estimate.

    Input: AsyncKeyHook reads evdev globally, so run with permission to read
    /dev/input (input group or sudo). Camera: OpenCV VideoCapture over FFMPEG on
    the raw H264 stream -- test-harness only; the real path is gstreamer.

    Build: part of the tello_backend CMake (target: tello_teleop).
*/
#include <atomic>
#include <chrono>
#include <cstdio>
#include <opencv2/opencv.hpp>

#include "tello_backend/tello_backend.hpp"
#include "keyboard/async_key.hpp"
#include "keyboard/key_codes.hpp"


/* Fixed teleop magnitudes (m/s and rad/s). Deliberately gentle for indoor test. */
static constexpr f32 kMoveSpeedMps = 0.4f;
static constexpr f32 kYawRateRadps = 1.0f;

static std::atomic<bool> g_running{true};


/* Holds the current per-axis intent and pushes the composed body velocity to the
   backend on every key event. Runs on the AsyncKeyHook consumer thread. */
struct TeleopState {
    TelloBackend& drone;
    std::atomic<f32> fwd{0.0f}, lat{0.0f}, vert{0.0f}, yaw{0.0f};

    explicit TeleopState(TelloBackend& d) : drone(d) {}

    void push() {
        drone.set_body_velocity({ fwd.load(), lat.load(), vert.load() }, yaw.load());
    }

    /* Diagnostic: setpoint we're commanding + telemetry validity at the moment
       T/L is pressed. Distinguishes "no state feedback yet" (state socket dead,
       see stateLoop's [state] logs) from "state fine, drone just drifting". */
    void logKeyEvent(const char* label) {
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count();
        Odometry od = drone.odometry();
        std::printf("[TIME %lld ms] %s pressed. cmd(fwd=%.2f lat=%.2f vert=%.2f yaw=%.2f) "
                    "telemetry(valid=%d vel=%.2f,%.2f,%.2f alt=%.2fm)\n",
                    (long long)ms, label, fwd.load(), lat.load(), vert.load(), yaw.load(),
                    __scast(int, od.valid), od.vel.x, od.vel.y, od.vel.z, od.pos.z);
    }

    void onKey(KeyCodeEnum key, KeyAction action) {
        const bool down = (action == KeyAction::PRESSED || action == KeyAction::REPEATED);
        const f32  v = kMoveSpeedMps;
        const f32  y = kYawRateRadps;
        switch (key) {
            case KeyCodeEnum::W: fwd.store(down ?  v : 0.0f); break;
            case KeyCodeEnum::S: fwd.store(down ? -v : 0.0f); break;
            case KeyCodeEnum::A: lat.store(down ?  v : 0.0f); break;   /* +left  */
            case KeyCodeEnum::D: lat.store(down ? -v : 0.0f); break;   /* +right */
            case KeyCodeEnum::R: vert.store(down ?  v : 0.0f); break;  /* +up    */
            case KeyCodeEnum::F: vert.store(down ? -v : 0.0f); break;  /* +down  */
            case KeyCodeEnum::Q: yaw.store(down ?  y : 0.0f); break;   /* CCW    */
            case KeyCodeEnum::E: yaw.store(down ? -y : 0.0f); break;   /* CW     */
            case KeyCodeEnum::Space:
                fwd.store(0.0f); lat.store(0.0f); vert.store(0.0f); yaw.store(0.0f);
                break;
            case KeyCodeEnum::T:
                if (down) {
                    logKeyEvent("T/takeoff");
                    std::thread([this]{ drone.takeoff(); }).detach();
                }
                return;
            case KeyCodeEnum::L:
                if (down) {
                    logKeyEvent("L/land");
                    std::thread([this]{ drone.land(); }).detach();
                }
                return;
            case KeyCodeEnum::Escape: if (down) g_running.store(false); return;
            default: return;
        }
        push();
    }
};


int main() {
    TelloBackend drone;
    std::printf("[teleop] connecting to Tello (join its Wi-Fi first)...\n");
    if (!drone.start()) {
        std::printf("[teleop] FAILED to bind/handshake the Tello. Is it on and connected?\n");
        return 1;
    }
    std::printf("[teleop] connected. T=takeoff L=land  WASD=move RF=up/down QE=yaw  Space=hover  Esc=quit\n");

    TeleopState teleop(drone);
    AsyncKeyHook keys;
    if (!keys.create()) {
        std::printf("[teleop] FAILED to install keyboard hook (need /dev/input access).\n");
        drone.stop();
        return 1;
    }
    for (KeyCodeEnum k : { KeyCodeEnum::W, KeyCodeEnum::A, KeyCodeEnum::S, KeyCodeEnum::D,
                           KeyCodeEnum::R, KeyCodeEnum::F, KeyCodeEnum::Q, KeyCodeEnum::E,
                           KeyCodeEnum::T, KeyCodeEnum::L, KeyCodeEnum::Space, KeyCodeEnum::Escape }) {
        keys.bindKey(k, [&teleop](KeyCodeEnum key, KeyAction act) { teleop.onKey(key, act); });
    }

    /* Camera is best-effort: telemetry + control still work without it. */
    cv::VideoCapture cap("udp://0.0.0.0:11111", cv::CAP_FFMPEG);
    if (!cap.isOpened())
        std::printf("[teleop] camera stream not open yet (continuing without video).\n");

    u64 lastTelemetryMs = 0;
    cv::Mat frame;
    while (g_running.load()) {
        if (cap.isOpened() && cap.read(frame) && !frame.empty()) {
            cv::imshow("Tello", frame);
            if (cv::waitKey(1) == 27) g_running.store(false);   /* Esc in window too */
        }

        /* Throttle to ~2 Hz. Fires whether or not telemetry is valid -- if it's
           NOT valid, that's exactly the signal we need to see (state socket dead)
           instead of the print silently never firing for the whole flight. */
        Odometry od = drone.odometry();
        auto nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count();
        if (__scast(u64, nowMs) - lastTelemetryMs > 500ULL) {
            lastTelemetryMs = __scast(u64, nowMs);
            std::printf("[tele] valid=%d alt=%.2fm  vel(F,L,U)=(%.2f,%.2f,%.2f) m/s  yaw=%.1f deg  "
                        "state=%d  cmd(fwd=%.2f lat=%.2f vert=%.2f yaw=%.2f)\n",
                        __scast(int, od.valid), od.pos.z, od.vel.x, od.vel.y, od.vel.z,
                        od.yaw * 180.0f / __scast(f32, M_PI),
                        __scast(int, drone.state()),
                        teleop.fwd.load(), teleop.lat.load(), teleop.vert.load(), teleop.yaw.load());
        }
        if (!cap.isOpened())
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }

    std::printf("[teleop] shutting down: landing + stopping.\n");
    keys.destroy();
    drone.stop();   /* lands + streamoff + joins */
    return 0;
}
