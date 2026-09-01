#pragma once
/*
    Compile-time backend selector. The FMU includes THIS (never a concrete
    backend header) and refers to `ActiveBackend`, so the FMU stays a plain,
    non-templated class -- one concrete backend type per binary, chosen at CMake
    configure time via FMU_BACKEND (PX4|TELLO|ALL).

    There is NO default: a translation unit compiled without an FMU_BACKEND_*
    macro is a hard error here, matching the CMake FATAL_ERROR when FMU_BACKEND
    is unset. Selecting a backend is a deliberate configuration decision.

    make_active_backend() hides the per-backend constructor asymmetry (PX4 needs
    the ROS Node + callback group; Tello, being ROS-free, needs nothing) behind
    one uniform signature. This keeps the FMU non-templated -- an `if constexpr`
    in the (non-template) FMU ctor would NOT discard-check its dead branch, so the
    wrong-arity make_unique would fail to compile. The factory sidesteps that: only
    the selected build's overload is ever compiled. This header is FMU-only glue,
    so it may name ROS types; the TelloBackend class itself stays ROS-free.
*/
#include <memory>
#include <rclcpp/rclcpp.hpp>   /* factory signature only (FMU is always a ROS node) */

#if defined(FMU_BACKEND_TELLO)
#   include "tello_backend/tello_backend.hpp"
    using ActiveBackend = TelloBackend;
    inline std::unique_ptr<ActiveBackend>
    make_active_backend(rclcpp::Node* node, rclcpp::CallbackGroup::SharedPtr cbg) {
        (void)node; (void)cbg;   /* Tello is ROS-free: needs neither. */
        return std::make_unique<TelloBackend>();
    }
#elif defined(FMU_BACKEND_PX4)
#   include "px4_backend/px4_backend.hpp"
    using ActiveBackend = PX4Backend;
    inline std::unique_ptr<ActiveBackend>
    make_active_backend(rclcpp::Node* node, rclcpp::CallbackGroup::SharedPtr cbg) {
        return std::make_unique<PX4Backend>(node, cbg);
    }
#elif defined(FMU_BACKEND_DJI)
#   include "dji_backend/dji_backend.hpp"
    using ActiveBackend = DjiBackend;
    inline std::unique_ptr<ActiveBackend>
    make_active_backend(rclcpp::Node* node, rclcpp::CallbackGroup::SharedPtr cbg) {
        (void)node; (void)cbg;   /* DJI (LAN app) is ROS-free: needs neither. */
        return std::make_unique<DjiBackend>();
    }
#else
#   error "No FMU backend selected. Set -DFMU_BACKEND=PX4|TELLO|ALL at CMake configure time."
#endif
