cmake_minimum_required(VERSION 3.16)
project(tello_backend C CXX)


# ctello's source is fetched DOWNLOAD_ONLY at the workspace root, so we compile
# its single translation unit straight into this library. Bypasses ctellos CMakeLists.txt
# which builds a lot of BULLSHIT
set(TELLO_BACKEND_LIBRARY_SOURCES
    tello_backend.cpp
    ${ctello_SOURCE_DIR}/src/ctello.cpp
)

set(TELLO_BACKEND_LIBRARY_HEADERS
    tello_backend.hpp
    tello_backend_base.hpp
)


add_library(${PROJECT_NAME}
    ${TELLO_BACKEND_LIBRARY_SOURCES}
    ${TELLO_BACKEND_LIBRARY_HEADERS}
)
add_library(Drone::tello_backend ALIAS ${PROJECT_NAME})

# Public: our headers (+ util2 for base types / frame math, pulled transitively).
# Private: ctello.h and spdlog are only needed to compile the .cpp files; the
# public header forward-declares ctello::Tello, so consumers never see them.
target_include_directories(${PROJECT_NAME}
    PRIVATE ${ctello_SOURCE_DIR}/include
)
target_link_libraries(${PROJECT_NAME}
    PUBLIC  UTIL2::util2 util_base_header
    PRIVATE spdlog::spdlog_header_only
)
target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_17)

# ---------------------------------------------------------------------------
# Tier-1 test: hardware-free unit test of the pure edges (enu_to_flu, the state
# parser, the stick mapping). No ctello, no OpenCV, no ROS -- runs anywhere.
# ---------------------------------------------------------------------------
add_executable(tello_convert_test test/tello_convert_test.cpp)
target_link_libraries(tello_convert_test PRIVATE UTIL2::util2 util_base_header)
target_compile_features(tello_convert_test PRIVATE cxx_std_17)
add_custom_target(run_tello_convert_test
    COMMAND tello_convert_test
    DEPENDS tello_convert_test
    COMMENT "Running TelloBackend Tier-1 unit test..."
)

# ---------------------------------------------------------------------------
# Tier-2 teleop harness (ON HARDWARE): keyboard flight + live telemetry +
# camera window. Needs OpenCV (VideoCapture/imshow) and pulls in AsyncKeyHook.
# Guarded so a hardware-less build still succeeds without it.
# ---------------------------------------------------------------------------
find_package(OpenCV QUIET COMPONENTS core imgproc highgui videoio)
if(OpenCV_FOUND)
    add_executable(tello_teleop
        test/tello_teleop.cpp
        ${LLM_TO_ACTION_DIR}/keyboard/async_key.cpp
        ${LLM_TO_ACTION_DIR}/keyboard/key_codes.cpp
    )
    target_link_libraries(tello_teleop PRIVATE
        Drone::tello_backend
        UTIL2::util2
        ${OpenCV_LIBS}
    )
    target_include_directories(tello_teleop PRIVATE ${OpenCV_INCLUDE_DIRS})
    target_compile_features(tello_teleop PRIVATE cxx_std_17)
else()
    message(STATUS "[tello_backend] OpenCV not found; skipping tello_teleop harness.")
endif()

# ---------------------------------------------------------------------------
# Tier-2 SLAM hover-hold node (ON HARDWARE): owns a TelloBackend, subscribes
# stella's slam/pose + slam/tracking_state, holds station and lands on loss.
# Header-only reuse of the offline-tested bridge / controller / recovery FSM in
# projects/slam/source. Uses the ROS imported targets the top-level build already
# find_package'd (rclcpp + geometry_msgs; std_msgs Bool rides in transitively via
# geometry_msgs, same as slam2.hpp). Guarded on the targets so a ROS-less
# configuration still builds the rest of the tree.
# ---------------------------------------------------------------------------
if(TARGET rclcpp::rclcpp AND TARGET geometry_msgs::geometry_msgs__rosidl_typesupport_cpp)
    add_executable(tello_slam_hold
        test/tello_slam_hold.cpp
        ${LLM_TO_ACTION_DIR}/keyboard/async_key.cpp
        ${LLM_TO_ACTION_DIR}/keyboard/key_codes.cpp
    )
    target_link_libraries(tello_slam_hold PRIVATE
        Drone::tello_backend
        UTIL2::util2
        rclcpp::rclcpp
        geometry_msgs::geometry_msgs__rosidl_typesupport_cpp
    )
    target_include_directories(tello_slam_hold PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../../slam   # slam_pose_bridge / hover_hold_control / recovery FSM
    )
    target_compile_features(tello_slam_hold PRIVATE cxx_std_17)
else()
    message(STATUS "[tello_backend] ROS targets not present; skipping tello_slam_hold.")
endif()
