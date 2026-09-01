/*
    Standalone, hardware-free unit test for the pure bridge math in
    slam/slam_pose_bridge.hpp:
      - OneEuro filter: passthrough on init, smooths jitter, tracks a ramp w/o big lag
      - ScaleMedian: rejects a single spike among steady samples
      - bridgeMapToMetricEnu: yaw rotation + scale are correct
      - yawAboutZ: recovers a known heading from a quaternion
    Build (see run line in slam_pose_bridge.hpp header comment):
      g++ -std=c++17 -I source/llm_to_action -I source -I <util2-include> \
          source/slam/test/slam_pose_bridge_test.cpp -o /tmp/spbt && /tmp/spbt
    No ROS, no stella, no hardware.
*/
#include "slam/slam_pose_bridge.hpp"
#include <cmath>
#include <cstdio>
#include <cassert>

static bool close(f32 a, f32 b, f32 eps = 1e-3f) { return std::fabs(a - b) < eps; }

int main() {
    /* --- ScaleMedian: one wild spike must not move the median off the steady value. --- */
    {
        ScaleMedian sm;
        for (int i = 0; i < 5; ++i) sm.push(7.0f);
        sm.push(900.0f);                 /* a spike */
        for (int i = 0; i < 3; ++i) sm.push(7.0f);
        assert(close(sm.value(), 7.0f));
    }

    /* --- bridgeMapToMetricEnu: yaw0 = 0 -> pure scale, no rotation. --- */
    {
        BridgeAlignment a;
        bridgeInitYaw(a, 0.0f);
        for (int i = 0; i < 5; ++i) bridgeUpdateScale(a, /*slamVertical*/ 0.5f, /*metricH*/ 1.0f);
        assert(a.mb_haveScale);                          /* scale = 1.0/0.5 = 2.0 */
        Vec3 e = bridgeMapToMetricEnu(a, 1.0f, 0.0f, 1.0f);
        assert(close(e.x, 2.0f) && close(e.y, 0.0f) && close(e.z, 1.0f));
    }

    /* --- yaw0 = +pi/2: a map +x vector rotates to ENU -North (points to -y). --- */
    {
        BridgeAlignment a;
        bridgeInitYaw(a, __scast(f32, M_PI_2));
        /* no scale pushed -> scale defaults to 1.0 */
        Vec3 e = bridgeMapToMetricEnu(a, 1.0f, 0.0f, 0.8f);
        /* rotate (1,0) by -pi/2 -> (0,-1) */
        assert(close(e.x, 0.0f) && close(e.y, -1.0f) && close(e.z, 0.8f));
    }

    /* --- scale guards: ground height and degenerate vertical are rejected. --- */
    {
        BridgeAlignment a;
        bridgeUpdateScale(a, 0.5f, 0.0f);      /* metric height ~0 -> ignored */
        bridgeUpdateScale(a, 0.0f, 1.0f);      /* slam vertical ~0 -> ignored */
        assert(!a.mb_haveScale);
    }

    /* --- yawAboutZ: quaternion for a +pi/2 yaw about z recovers ~pi/2. --- */
    {
        f32 h = __scast(f32, M_PI_2) * 0.5f;
        f32 qz = std::sin(h), qw = std::cos(h);   /* rotation of pi/2 about z */
        assert(close(yawAboutZ(0.0f, 0.0f, qz, qw), __scast(f32, M_PI_2), 1e-3f));
    }

    /* --- OneEuro: first sample is passthrough; a constant + jitter settles near
           the constant; a steady ramp is tracked without a large lag. --- */
    {
        OneEuroFilter f;
        assert(close(f.filter(5.0f, 0.0f), 5.0f));          /* init passthrough */

        OneEuroFilter g;
        f32 y = 0.0f;
        /* alternating +/-0.1 jitter around 10.0 at 30 Hz -> output near 10.0 */
        for (int i = 0; i < 60; ++i) {
            f32 noisy = 10.0f + ((i % 2 == 0) ? 0.1f : -0.1f);
            y = g.filter(noisy, 1.0f / 30.0f);
        }
        assert(close(y, 10.0f, 0.08f));                      /* jitter attenuated */

        OneEuroFilter r;
        f32 out = 0.0f, truth = 0.0f;
        for (int i = 0; i < 60; ++i) {
            truth = 0.5f * static_cast<f32>(i);              /* ramp 0.5/frame */
            out   = r.filter(truth, 1.0f / 30.0f);
        }
        /* a good de-lagging filter tracks a steady ramp closely by the end */
        assert(close(out, truth, 1.0f));
    }

    std::printf("slam_pose_bridge_test: ALL PASS\n");
    return 0;
}
