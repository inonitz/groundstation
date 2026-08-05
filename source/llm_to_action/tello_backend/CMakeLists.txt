cmake_minimum_required(VERSION 3.16)
project(tello_backend C CXX)

# ---------------------------------------------------------------------------
# TelloBackend library (ROS-free). The FMU/consumers drive it through the same
# semantic verbs as PX4Backend; ctello stays an implementation detail.
#
# ctello's source is fetched DOWNLOAD_ONLY at the workspace root, so we compile
# its single translation unit straight into this library. That deliberately
# bypasses ctello's own CMake -- which builds example executables and hard-
# requires find_package(OpenCV) -- since we only want the command/state client.
# ---------------------------------------------------------------------------
add_library(${PROJECT_NAME} STATIC
    tello_backend.cpp
    tello_backend.hpp
    tello_backend_base.hpp
    ${ctello_SOURCE_DIR}/src/ctello.cpp
)
add_library(Drone::tello_backend ALIAS ${PROJECT_NAME})

# Public: our headers (+ util2 for base types / frame math, pulled transitively).
# Private: ctello.h and spdlog are only needed to compile the .cpp files; the
# public header forward-declares ctello::Tello, so consumers never see them.
target_include_directories(${PROJECT_NAME}
    PUBLIC  ${CMAKE_CURRENT_SOURCE_DIR}
    PRIVATE ${ctello_SOURCE_DIR}/include
)
target_link_libraries(${PROJECT_NAME}
    PUBLIC  UTIL2::util2
    PRIVATE spdlog::spdlog_header_only
)
target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_17)

# ---------------------------------------------------------------------------
# Tier-1 test: hardware-free unit test of the pure edges (enu_to_flu, the state
# parser, the stick mapping). No ctello, no OpenCV, no ROS -- runs anywhere.
# ---------------------------------------------------------------------------
add_executable(tello_convert_test test/tello_convert_test.cpp)
target_link_libraries(tello_convert_test PRIVATE UTIL2::util2)
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
        ${CMAKE_CURRENT_SOURCE_DIR}/../keyboard/async_key.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/../keyboard/key_codes.cpp
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
