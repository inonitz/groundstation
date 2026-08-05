#pragma once
/*
    GenericBackend<Derived> -- the CRTP seam every concrete drone backend derives
    from. It is the "template header to populate" when adding a new flight system:
    give the derived class the nine *_impl methods below and it plugs into the FMU
    unchanged.

    No virtual, no vtable: dispatch is static, resolved at compile time and
    force-inlined, so the seam costs nothing over calling the concrete method
    directly. Callers keep the plain verb names (start/takeoff/set_velocity/...);
    each backend implements the matching *_impl. A backend missing an *_impl fails
    to compile at the forwarder line -- a clear contract error, not template spew.

    Frame: set_velocity takes an ENU world velocity + yaw rate (rad/s, CCW+); the
    backend converts to its wire frame internally.
*/
#include <util2/C/macro.h>            /* __force_inline */
#include "generic_backend_types.hpp" /* BackendStatus, IOState, Odometry, Vec3 */


template<class Derived>
struct GenericBackend {
    /* ---- lifecycle -------------------------------------------------------- */
    __force_inline bool          start()                     { return d().start_impl(); }
    __force_inline void          stop()                      { d().stop_impl(); }

    /* ---- semantic verbs (non-blocking; progress observed via state()) ------ */
    __force_inline BackendStatus takeoff()                   { return d().takeoff_impl(); }
    __force_inline BackendStatus land()                      { return d().land_impl(); }
    __force_inline void          set_velocity(Vec3 v, f32 y) { d().set_velocity_impl(v, y); }
    __force_inline void          disarm()                    { d().disarm_impl(); }
    __force_inline void          force_disarm()              { d().force_disarm_impl(); }

    /* ---- telemetry / observable state -------------------------------------- */
    __force_inline Odometry      odometry() const            { return d().odometry_impl(); }
    __force_inline IOState       state()    const            { return d().state_impl(); }

private:
    __force_inline Derived&       d()       { return *static_cast<Derived*>(this); }
    __force_inline Derived const& d() const { return *static_cast<Derived const*>(this); }
};
