/*
    Closed-loop drift-mitigation sim for the hover-hold stack -- test #1's essence,
    offline: a point-mass "drone" with a constant drift disturbance (the blind-VPS
    drift the Tello suffers) and a jittery position measurement, driven by the REAL
    controller (hover_hold_control.hpp) + optional OneEuro (slam_pose_bridge.hpp).

    Proves, with no ROS / no hardware / no shared build:
      - controller OFF: drift accumulates without bound (baseline).
      - controller ON:  the integral cancels the steady drift, position holds near
                        the setpoint.
      - measurement jitter does not destabilise the loop (deadband + OneEuro).

    Deterministic (sinusoidal jitter, fixed disturbance) so it is a real unit test.
    Build:
      g++ -std=c++17 -I source/llm_to_action -I source -I <util2-include> \
          source/slam/test/hover_hold_sim_test.cpp -o /tmp/hhst && /tmp/hhst
*/
#include "slam/hover_hold_control.hpp"
#include "slam/slam_pose_bridge.hpp"
#include <cmath>
#include <cstdio>
#include <cassert>

/* Simulate one hold and return the final horizontal distance from the setpoint (m).
   drift = constant disturbance velocity (m/s, +x). jitterAmp = measurement noise (m).
   useCtrl toggles the controller; useFilter toggles the OneEuro on the measurement. */
static f32 run_hold(f32 drift, f32 jitterAmp, bool useCtrl, bool useFilter,
                    f32 seconds = 20.0f, f32 dt = 1.0f / 30.0f) {
    HoverHoldController ctrl;
    XyOneEuro filt;
    filt.mb_enabled = useFilter;

    f32 tx = 0.0f, ty = 0.0f;         /* true position; setpoint is the origin. */
    f32 t  = 0.0f;
    const int steps = static_cast<int>(seconds / dt);
    for (int i = 0; i < steps; ++i) {
        t += dt;
        /* deterministic jitter: two incommensurate sinusoids so it is not a pure tone. */
        f32 jx = jitterAmp * (std::sin(37.0f * t) + 0.5f * std::sin(101.0f * t));
        f32 jy = jitterAmp * (std::cos(41.0f * t) + 0.5f * std::sin(89.0f * t));

        Vec3 measured = filt.apply({ tx + jx, ty + jy, 0.0f }, dt);
        Vec3 error    = { 0.0f - measured.x, 0.0f - measured.y, 0.0f };   /* setpoint - measured */
        Vec3 cmd      = useCtrl ? ctrl.update(error, dt) : Vec3{ 0.0f, 0.0f, 0.0f };

        /* point-mass: the drone tracks the commanded velocity, plus the drift it cannot feel. */
        tx += (cmd.x + drift) * dt;
        ty += (cmd.y + 0.0f)  * dt;
    }
    return std::sqrt(tx * tx + ty * ty);
}

int main() {
    const f32 drift = 0.15f;   /* m/s of uncommanded drift, like a blind-VPS Tello. */

    /* --- baseline: no controller -> drift accumulates to ~drift*seconds. --- */
    f32 offDist = run_hold(drift, 0.0f, /*useCtrl*/ false, /*useFilter*/ false);
    assert(offDist > 2.5f);            /* 0.15 * 20 = 3.0 m, essentially uncontrolled. */

    /* --- controller ON, no jitter: the integral cancels the steady drift. --- */
    f32 onDist = run_hold(drift, 0.0f, /*useCtrl*/ true, /*useFilter*/ false);
    assert(onDist < 0.10f);            /* held within 10 cm despite constant drift. */
    assert(onDist < offDist * 0.1f);   /* at least a 10x improvement over open-loop. */

    /* --- controller ON with measurement jitter: stays bounded (no blow-up). --- */
    f32 jitterDist = run_hold(drift, 0.03f, /*useCtrl*/ true, /*useFilter*/ false);
    assert(jitterDist < 0.20f);        /* jitter does not destabilise the hold. */

    /* --- heavier jitter, OneEuro ON: still bounded, filter earns its place. --- */
    f32 filtOff = run_hold(drift, 0.06f, /*useCtrl*/ true, /*useFilter*/ false);
    f32 filtOn  = run_hold(drift, 0.06f, /*useCtrl*/ true, /*useFilter*/ true);
    assert(filtOn < 0.25f && filtOff < 0.35f);   /* both bounded; both stay controlled. */

    std::printf("hover_hold_sim_test: ALL PASS  (open-loop=%.2fm  closed-loop=%.3fm  "
                "jitter=%.3fm  filtOn=%.3fm)\n", offDist, onDist, jitterDist, filtOn);
    return 0;
}
