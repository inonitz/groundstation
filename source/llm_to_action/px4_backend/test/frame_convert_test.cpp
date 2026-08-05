/*
    Standalone, ROS-free unit test for frame_convert.hpp.
    Build:  g++ -std=c++17 -I <util2-include> frame_convert_test.cpp -o /tmp/fct && /tmp/fct
    This exercises the riskiest part of the ENU migration (sign conventions) with
    zero ROS/px4_msgs dependencies, so it runs on any host.
*/
#include "../../frame/frame_convert.hpp"
#include <cmath>
#include <cstdio>
#include <cassert>

static bool close(f32 a, f32 b)  { return std::fabs(a - b) < 1e-4f; }
static bool vclose(Vec3 a, Vec3 b) { return close(a.x, b.x) && close(a.y, b.y) && close(a.z, b.z); }

int main() {
    /* ned_to_enu and enu_to_ned are inverses. */
    Vec3 ned{ 1.0f, 2.0f, 3.0f };
    assert(vclose(enu_to_ned(ned_to_enu(ned)), ned));

    /* Axis identities: NED north(+x) -> ENU north(+y); NED down(+z) -> ENU up(-z). */
    assert(vclose(ned_to_enu({ 1, 0, 0 }), { 0, 1, 0 }));
    assert(vclose(ned_to_enu({ 0, 0, 1 }), { 0, 0, -1 }));

    /* "Forward 1m" FLU at spawn yaw 2.10 rad (NED) matches the NOTES.md-verified result. */
    Vec3 f = flu_to_ned({ 1.0f, 0.0f, 0.0f }, 2.10f);
    assert(close(f.x, std::cos(2.10f)) && close(f.y, std::sin(2.10f)));

    /* ENU "forward 1m" facing East (yawEnu 0) points along +E. */
    Vec3 fe = flu_to_enu({ 1.0f, 0.0f, 0.0f }, 0.0f);
    assert(vclose(fe, { 1, 0, 0 }));

    /* ENU "forward 1m" preserves heading: displacement angle == yawEnu. */
    f32 yawEnu = 0.30f;
    Vec3 rel = flu_to_enu({ 1.0f, 0.0f, 0.0f }, yawEnu);
    assert(close(std::atan2(rel.y, rel.x), yawEnu));

    std::printf("frame_convert_test OK\n");
    return 0;
}
