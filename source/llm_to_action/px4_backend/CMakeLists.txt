cmake_minimum_required(VERSION 3.16)
project(px4_backend C CXX)


# PX4 flight backend: a ROS-side GenericBackend implementation talking to a PX4
# FC / SITL over px4_msgs. Linked into the FMU (Drone::px4_backend) exactly like the
# Tello backend -- the FMU no longer compiles these translation units itself. No explicit
# STATIC/SHARED: honours BUILD_SHARED_LIBS (the build.sh static/shared arg) like every other lib.
add_library(${PROJECT_NAME}
    px4_backend.cpp
    px4_backend.hpp
    px4_backend_base.hpp
)
add_library(Drone::px4_backend ALIAS ${PROJECT_NAME})

# PUBLIC: everything the public headers expose (rclcpp handles, px4_msgs types,
# util2 base types / frame math) so consumers inherit them transitively.
target_link_libraries(${PROJECT_NAME}
    PUBLIC
        UTIL2::util2
        util_base_header
        rclcpp::rclcpp
        px4_msgs::px4_msgs__rosidl_typesupport_cpp
)
target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_17)


# ---------------------------------------------------------------------------
# Hardware-free unit test of the pure frame math (ENU<->NED). No ROS.
# ---------------------------------------------------------------------------
if(GROUNDSTATION_BUILD_TESTS)
    add_executable(frame_convert_test test/frame_convert_test.cpp)
    target_link_libraries(frame_convert_test PRIVATE util_base_header UTIL2::util2)
    target_compile_features(frame_convert_test PRIVATE cxx_std_17)
    add_custom_target(run_frame_convert_test COMMAND frame_convert_test DEPENDS frame_convert_test)
endif()
