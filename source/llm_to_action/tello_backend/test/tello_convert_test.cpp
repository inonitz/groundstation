/*
    Standalone, hardware-free unit test for the TelloBackend pure edges:
      - enu_to_flu (world ENU velocity -> body FLU sticks, inverse of flu_to_enu)
      - parse_tello_state_branchless (Tello SDK state string -> POD)
      - velocity <-> stick mapping (m/s <-> rc [-100,100])
    Build: g++ -std=c++17 -I <util2-include> tello_convert_test.cpp -o /tmp/tct && /tmp/tct
    No ROS, no ctello, no hardware -- runs on any host.
*/
#include "../../frame/frame_convert.hpp"
#include "../tello_backend_base.hpp"
#include <cmath>
#include <initializer_list>
#include <cstdio>
#include <cassert>

static bool close(f32 a, f32 b)  { return std::fabs(a - b) < 1e-4f; }
static bool vclose(Vec3 a, Vec3 b) { return close(a.x, b.x) && close(a.y, b.y) && close(a.z, b.z); }

int main() {
    /* enu_to_flu is the exact inverse of flu_to_enu across sample headings. */
    for (f32 yaw : { -2.0f, -0.3f, 0.0f, 0.7f, 1.9f }) {
        Vec3 flu{ 0.6f, -0.4f, 0.2f };
        assert(vclose(enu_to_flu(flu_to_enu(flu, yaw), yaw), flu));
    }

    /* Facing East (yawEnu 0): world +East -> body +forward; world +North -> body +left. */
    assert(vclose(enu_to_flu({ 1, 0, 0 }, 0.0f), { 1, 0, 0 }));
    assert(vclose(enu_to_flu({ 0, 1, 0 }, 0.0f), { 0, 1, 0 }));

    /* Facing North (yawEnu pi/2): world +East is on the drone's right -> body left = -1. */
    assert(vclose(enu_to_flu({ 1, 0, 0 }, __scast(f32, M_PI_2)), { 0, -1, 0 }));

    /* --- state parser: a well-formed Tello SDK state line fills every field. --- */
    TelloState st{};
    const char* good =
        "pitch:1;roll:-2;yaw:-45;vgx:3;vgy:4;vgz:5;templ:60;temph:62;tof:10;"
        "h:0;bat:87;baro:123.45;time:9;agx:1.00;agy:-2.00;agz:-998.00;";
    assert(parse_tello_state_branchless(good, st));
    assert(st.yaw == -45 && st.bat == 87 && st.h == 0 && st.vgx == 3);
    assert(close(st.baro, 123.45f) && close(st.agz, -998.0f));

    /* Malformed / truncated -> false, no partial acceptance. */
    TelloState bad{};
    assert(!parse_tello_state_branchless("garbage;not;tello;", bad));
    assert(!parse_tello_state_branchless(nullptr, bad));

    /* --- velocity <-> stick mapping: clamps to +/-100, round-trips within a quantum. --- */
    assert(mps_to_stick( 10.0f) ==  100);   /* over-range saturates high */
    assert(mps_to_stick(-10.0f) == -100);   /* over-range saturates low  */
    assert(mps_to_stick( 0.0f)  ==    0);
    for (f32 v : { -0.8f, -0.25f, 0.0f, 0.4f, 0.9f }) {
        f32 rt = stick_to_mps(mps_to_stick(v));
        assert(std::fabs(rt - v) <= kTelloMaxSpeedMps / 100.0f + 1e-4f);
    }

    /* --- flu_to_rc: body axes map to the right rc sticks (a=lr+right, b=fwd, c=up). --- */
    RcCommand fwd = flu_to_rc({ kTelloMaxSpeedMps, 0, 0 }, 0);
    assert(fwd.b == 100 && fwd.a == 0 && fwd.c == 0 && fwd.d == 0);
    RcCommand left = flu_to_rc({ 0, kTelloMaxSpeedMps, 0 }, 0);
    assert(left.a == -100 && left.b == 0);          /* +left -> stick right = -100 */
    RcCommand up = flu_to_rc({ 0, 0, kTelloMaxSpeedMps }, 0);
    assert(up.c == 100);

    /* --- yaw-rate (rad/s, ENU CCW+) -> yaw stick (Tello CW+): sign flips, saturates. --- */
    assert(yawrate_to_stick( kTelloMaxYawRateRadps) == -100);
    assert(yawrate_to_stick(-kTelloMaxYawRateRadps) ==  100);
    assert(yawrate_to_stick( 0.0f) == 0);

    std::printf("tello_convert_test OK\n");
    return 0;
}
