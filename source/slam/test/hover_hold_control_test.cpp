/*
    Standalone, hardware-free unit test for slam/hover_hold_control.hpp.
      - zero / deadband error -> zero command
      - sign: measured behind setpoint (+error) -> + velocity toward it
      - proportional region below the clamp
      - large error -> output clamps at maxVel
      - sustained error -> integral helps but is anti-windup clamped (no blow-up)
      - reset() drops the integrator
    Build:
      g++ -std=c++17 -I source/llm_to_action -I source -I <util2-include> \
          source/slam/test/hover_hold_control_test.cpp -o /tmp/hhct && /tmp/hhct
*/
#include "slam/hover_hold_control.hpp"
#include <cmath>
#include <cstdio>
#include <cassert>

static bool close(f32 a, f32 b, f32 eps = 1e-4f) { return std::fabs(a - b) < eps; }

int main() {
    const f32 dt = 1.0f / 30.0f;

    /* --- zero error and sub-deadband error both command nothing. --- */
    {
        HoverHoldController c;
        Vec3 v = c.update({ 0.0f, 0.0f, 0.0f }, dt);
        assert(close(v.x, 0.0f) && close(v.y, 0.0f) && close(v.z, 0.0f));
        Vec3 v2 = c.update({ 0.02f, -0.02f, 0.0f }, dt);   /* < 3cm deadband */
        assert(close(v2.x, 0.0f) && close(v2.y, 0.0f));
    }

    /* --- proportional region + sign. First tick: v = Kp*err (I still ~0). --- */
    {
        HoverHoldController c;               /* Kp = 0.8 */
        Vec3 v = c.update({ 0.2f, 0.0f, 0.0f }, dt);
        /* err 0.2 m, first tick I ~ 0.15*0.2*dt = tiny. Expect ~0.16 + tiny, well under clamp. */
        assert(v.x > 0.15f && v.x < 0.18f);  /* positive: drive toward the setpoint */
        assert(close(v.y, 0.0f));
    }

    /* --- large error saturates the output at maxVel (0.4). --- */
    {
        HoverHoldController c;
        Vec3 v = c.update({ 5.0f, 0.0f, 0.0f }, dt);
        assert(close(v.x, c.m_cfg.mk_maxVel));
    }

    /* --- sustained moderate error: integral must clamp, output must not blow up. --- */
    {
        HoverHoldController c;
        Vec3 v{};
        for (int i = 0; i < 2000; ++i) v = c.update({ 0.1f, 0.0f, 0.0f }, dt);
        assert(std::fabs(c.m_ix) <= c.m_cfg.mk_maxIntg + 1e-4f);   /* anti-windup held */
        assert(std::fabs(v.x)    <= c.m_cfg.mk_maxVel  + 1e-4f);   /* output clamped   */
    }

    /* --- reset() drops the integrator. --- */
    {
        HoverHoldController c;
        for (int i = 0; i < 100; ++i) c.update({ 0.1f, 0.1f, 0.0f }, dt);
        assert(std::fabs(c.m_ix) > 0.0f && std::fabs(c.m_iy) > 0.0f);
        c.reset();
        assert(close(c.m_ix, 0.0f) && close(c.m_iy, 0.0f));
    }

    std::printf("hover_hold_control_test: ALL PASS\n");
    return 0;
}
