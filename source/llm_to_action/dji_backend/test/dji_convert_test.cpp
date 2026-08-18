/*
    Hardened, hardware-free unit test for the DjiBackend pure edges:
      - enu_vel_to_flightparam (ENU world vel -> body FlightParam, right = -left)
        incl. a rotation-norm invariant across headings
      - the velocity/yaw clamp (envelope saturation, boundary, pass-through)
      - flightparam_to_json (hot-path serialise) + the exact wire field contract
        the app's kotlinx decoder expects ({vx,vy,vz,yaw})
      - parse_status_json against BOTH the mock shape (position3D {x,y,z}) and the
        REAL app shape (position3D {latitude,longitude,altitude}; velocity3D {x,y,z};
        attitude {pitch,roll,yaw}) confirmed from SerializerUtils.kt, plus a fuzz
        battery of malformed inputs that must never throw or crash.
    No ROS, no websocket, no drone -- runs on any host.
*/
#include "dji_backend/dji_status_parse.hpp"   /* nlohmann-first: base (FlightParam) + parse + Odometry */
#include <cmath>
#include <cstdio>
#include <cassert>

static bool close(f32 a, f32 b)   { return std::fabs(a - b) < 1e-3f; }

int main() {
    /* ================= frame map ================= */
    /* Facing East (yaw 0): +East -> forward vx; +North is on the LEFT -> right vy<0. */
    FlightParam east = enu_vel_to_flightparam({ 1, 0, 0 }, 0.0f, 0.0f);
    assert(close(east.vx, 1.0f) && close(east.vy, 0.0f) && close(east.vz, 0.0f));
    FlightParam north = enu_vel_to_flightparam({ 0, 1, 0 }, 0.0f, 0.0f);
    assert(close(north.vx, 0.0f) && close(north.vy, -1.0f));
    /* Facing North (yaw pi/2): +East is on the RIGHT -> vy>0. */
    FlightParam e2 = enu_vel_to_flightparam({ 1, 0, 0 }, __scast(f32, M_PI_2), 0.0f);
    assert(close(e2.vx, 0.0f) && close(e2.vy, 1.0f));
    /* +Up world -> vz up regardless of heading. */
    assert(close(enu_vel_to_flightparam({ 0, 0, 1 }, 0.7f, 0.0f).vz, 1.0f));

    /* Invariant: a body-frame rotation preserves the horizontal speed magnitude
       (within the envelope). Sweep headings AND horizontal velocity directions. */
    for (f32 yaw = -3.0f; yaw <= 3.0f; yaw += 0.37f) {
        for (f32 a = -1.2f; a <= 1.2f; a += 0.5f) {
            for (f32 b = -1.2f; b <= 1.2f; b += 0.5f) {
                FlightParam p = enu_vel_to_flightparam({ a, b, 0 }, yaw, 0.0f);
                f32 in  = std::sqrt(a*a + b*b);
                f32 out = std::sqrt(p.vx*p.vx + p.vy*p.vy);
                if (in <= kDjiMaxSpeedMps) assert(close(in, out));   /* norm preserved */
                else                       assert(out <= kDjiMaxSpeedMps + 1e-3f);
            }
        }
    }

    /* ================= clamp ================= */
    FlightParam fast = enu_vel_to_flightparam({ 100, 0, 0 }, 0.0f, 100.0f);
    assert(close(fast.vx, kDjiMaxSpeedMps) && close(fast.yaw, kDjiMaxYawRateRadps));
    FlightParam slow = enu_vel_to_flightparam({ -100, 0, 0 }, 0.0f, -100.0f);
    assert(close(slow.vx, -kDjiMaxSpeedMps) && close(slow.yaw, -kDjiMaxYawRateRadps));
    /* exactly at the boundary passes through; just under passes through. */
    assert(close(enu_vel_to_flightparam({ kDjiMaxSpeedMps, 0, 0 }, 0.0f, 0.0f).vx, kDjiMaxSpeedMps));
    assert(close(enu_vel_to_flightparam({ kDjiMaxSpeedMps - 0.1f, 0, 0 }, 0.0f, 0.0f).vx, kDjiMaxSpeedMps - 0.1f));
    /* yaw sign passthrough at default (+1). */
    assert(close(enu_vel_to_flightparam({ 0, 0, 0 }, 0.0f, 0.5f).yaw, kDjiYawRateSign * 0.5f));
    /* body-direct helper agrees on axes: forward, +left -> right<0, up. */
    FlightParam bf = flu_vel_to_flightparam({ 0.3f, 0.4f, 0.5f }, 0.0f);
    assert(close(bf.vx, 0.3f) && close(bf.vy, -0.4f) && close(bf.vz, 0.5f));

    /* ================= wire serialise + field contract ================= */
    FlightParam p{ 0.5f, -0.25f, 0.125f, -0.75f };
    char buf[96];
    int n = flightparam_to_json(p, buf, sizeof(buf));
    assert(n > 0 && n < __scast(int, sizeof(buf)));
    nlohmann::json jp = nlohmann::json::parse(buf, nullptr, false);
    assert(!jp.is_discarded() && jp.is_object());
    /* the app's kotlinx FlightParam(vy,vx,yaw,vz) decodes by these exact names. */
    for (const char* k : { "vx", "vy", "vz", "yaw" }) {
        assert(jp.contains(k) && jp[k].is_number());
    }
    assert(close(dji_jf(jp,"vx",0), 0.5f)  && close(dji_jf(jp,"vy",0), -0.25f));
    assert(close(dji_jf(jp,"vz",0), 0.125f) && close(dji_jf(jp,"yaw",0), -0.75f));
    /* zero setpoint serialises cleanly (the keepalive default). */
    assert(flightparam_to_json(FlightParam{}, buf, sizeof(buf)) > 0);

    /* ================= /status parse: mock shape ================= */
    const char* mockShape =
        "{\"aircraft\":{\"isFlying\":true,\"battery\":87,"
        "\"velocity3D\":{\"x\":1.5,\"y\":-0.5,\"z\":0.25},"
        "\"position3D\":{\"x\":2.0,\"y\":3.0,\"z\":1.2},"
        "\"attitude\":{\"pitch\":0.0,\"roll\":0.0,\"yaw\":0.7},"
        "\"gimbalAttitude\":{\"pitch\":0,\"roll\":0,\"yaw\":0}},"
        "\"product\":{\"version\":\"mock-1.0\",\"connection\":true}}";
    StatusTelemetry st{};
    assert(parse_status_json(mockShape, st));
    assert(st.isFlying && st.batteryPct == 87 && st.valid);
    assert(close(st.vel.x, 1.5f) && close(st.vel.y, -0.5f) && close(st.vel.z, 0.25f));
    assert(close(st.pos.x, 2.0f) && close(st.pos.z, 1.2f));
    assert(close(st.yaw, 0.7f));
    Odometry od = status_to_odometry(st, 123456);
    assert(od.valid && od.host_stamp_us == 123456 && close(od.vel.x, 1.5f));

    /* ================= /status parse: REAL app shape ================= */
    /* SerializerUtils.kt: velocity3D {x,y,z}; position3D {latitude,longitude,
       altitude} (GPS); attitude {pitch,roll,yaw}. Our parser reads velocity3D +
       attitude.yaw; position3D lacks x/y/z so pos stays 0 (we dead-reckon). Must
       still parse cleanly with valid=true. */
    const char* realShape =
        "{\"aircraft\":{\"isFlying\":false,\"battery\":63,"
        "\"velocity3D\":{\"x\":0.10,\"y\":-0.20,\"z\":0.03},"
        "\"position3D\":{\"latitude\":32.109,\"longitude\":34.876,\"altitude\":41.2},"
        "\"attitude\":{\"pitch\":1.1,\"roll\":-2.2,\"yaw\":-1.57},"
        "\"gimbalAttitude\":{\"pitch\":-30.0,\"roll\":0.0,\"yaw\":5.0}},"
        "\"product\":{\"version\":\"1.2.3\",\"connection\":true},"
        "\"controller\":{\"version\":\"1.0\",\"connection\":true}}";
    StatusTelemetry rt{};
    assert(parse_status_json(realShape, rt));
    assert(rt.valid && !rt.isFlying && rt.batteryPct == 63);
    assert(close(rt.vel.x, 0.10f) && close(rt.vel.y, -0.20f) && close(rt.vel.z, 0.03f));
    assert(close(rt.pos.x, 0.0f) && close(rt.pos.y, 0.0f) && close(rt.pos.z, 0.0f)); /* GPS not mapped */
    assert(close(rt.yaw, -1.57f));

    /* battery as a JSON double still yields an int percent; missing isFlying -> false. */
    StatusTelemetry bd{};
    assert(parse_status_json("{\"aircraft\":{\"battery\":54.0,\"velocity3D\":{\"x\":0,\"y\":0,\"z\":0}}}", bd));
    assert(bd.batteryPct == 54 && !bd.isFlying && bd.valid);

    /* ================= rejection + fuzz (must never throw/crash) ================= */
    StatusTelemetry bad{};
    assert(!parse_status_json("{\"product\":{}}", bad) && !bad.valid);   /* no aircraft */
    assert(!parse_status_json("{not json", bad));
    assert(!parse_status_json("garbage", bad));
    assert(!parse_status_json("", bad));
    assert(!parse_status_json("[]", bad));
    assert(!parse_status_json("null", bad));
    assert(!parse_status_json("12345", bad));
    assert(!parse_status_json(nullptr, bad));
    assert(!parse_status_json("{\"aircraft\":42}", bad));                /* aircraft not object */

    /* wrong-typed fields inside a valid aircraft object: accept, fall back to defaults. */
    const char* nasty[] = {
        "{\"aircraft\":{\"velocity3D\":5,\"battery\":\"x\",\"attitude\":[1,2,3]}}",
        "{\"aircraft\":{\"velocity3D\":{\"x\":\"NaN\",\"y\":null,\"z\":[]},\"isFlying\":\"yes\"}}",
        "{\"aircraft\":{\"velocity3D\":{\"x\":1e308,\"y\":-1e308,\"z\":0},\"battery\":999999}}",
        "{\"aircraft\":{}}",
        "{\"aircraft\":{\"velocity3D\":{},\"position3D\":{},\"attitude\":{}}}",
    };
    for (const char* body : nasty) {
        StatusTelemetry t{};
        assert(parse_status_json(body, t));    /* has aircraft object -> valid, no crash */
        assert(t.valid);
    }
    /* the "x":"NaN"/null/[] case must fall back to 0, not propagate garbage. */
    StatusTelemetry weird{};
    assert(parse_status_json(nasty[1], weird));
    assert(close(weird.vel.x, 0.0f) && close(weird.vel.y, 0.0f) && close(weird.vel.z, 0.0f));
    assert(!weird.isFlying && weird.batteryPct == kBatteryReadingUnknown);

    std::printf("dji_convert_test OK (frame map + invariants + clamp + wire contract + real/mock/fuzz parse)\n");
    return 0;
}
