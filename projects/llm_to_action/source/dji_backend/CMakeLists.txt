cmake_minimum_required(VERSION 3.16)
project(dji_backend C CXX)

find_package(Threads REQUIRED)

# ---------------------------------------------------------------------------
# WebSocket client selection. The DJI stick stream needs a WS client; we ship
# TWO interchangeable implementations behind one opaque API (dji_ws.hpp):
#   - RawWsClient  : a hand-rolled RFC6455 client over a raw POSIX socket. ZERO
#                    third-party deps. This is the DEFAULT.
#   - WsppWsClient : websocketpp + standalone Asio. Enable with the option below;
#                    fetched header-only (DOWNLOAD_ONLY), like ctello.
# Both are exercised head-to-head by dji_ws_test (built only when websocketpp is on).
# ---------------------------------------------------------------------------
option(GROUNDSTATION_DJI_WS_WEBSOCKETPP 
    "Use websocketpp+Asio for the DJI WS client (default: hand-rolled RFC6455)" OFF
)

set(DJI_BACKEND_LIBRARY_SOURCES
    dji_backend.cpp
    dji_ws_raw.cpp
)
set(DJI_BACKEND_LIBRARY_HEADERS
    dji_backend.hpp
    dji_backend_base.hpp
    dji_status_parse.hpp
    dji_ws.hpp
)

add_library(${PROJECT_NAME}
    ${DJI_BACKEND_LIBRARY_SOURCES}
    ${DJI_BACKEND_LIBRARY_HEADERS}
)
add_library(Drone::dji_backend ALIAS ${PROJECT_NAME})

# Public: our headers + util2 base types / frame math. Private: httplib + nlohmann
# are only needed to compile the .cpp; the public headers keep httplib opaque
# (forward-declared) and the JSON parse lives in dji_status_parse.hpp, which
# dji_backend.hpp does NOT include -- so consumers (and the FMU) never pull them.
target_link_libraries(${PROJECT_NAME}
    PUBLIC  UTIL2::util2 util_base_header
    PRIVATE httplib::httplib nlohmann_json::nlohmann_json Threads::Threads
)
target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_17)

if(GROUNDSTATION_DJI_WS_WEBSOCKETPP)
    # websocketpp + standalone Asio, header-only, DOWNLOAD_ONLY (compile the one
    # TU straight in). Kept exception-clean via the ec-returning API in the .cpp.
    safe_cpm_add_package(
        NAME websocketpp
        GIT_REPOSITORY https://github.com/zaphoyd/websocketpp.git
        GIT_TAG        0.8.2
        GIT_SHALLOW    TRUE
        DOWNLOAD_ONLY  YES
    )
    safe_cpm_add_package(
        NAME asio
        GIT_REPOSITORY https://github.com/chriskohlhoff/asio.git
        GIT_TAG        asio-1-18-2
        GIT_SHALLOW    TRUE
        DOWNLOAD_ONLY  YES
    )
    target_sources(${PROJECT_NAME} PRIVATE dji_ws_wspp.cpp)
    target_compile_definitions(${PROJECT_NAME} PRIVATE DJI_WS_WEBSOCKETPP)
    # SYSTEM so websocketpp/asio headers do NOT trip our -Werror warning set.
    target_include_directories(${PROJECT_NAME} SYSTEM PRIVATE
        ${websocketpp_SOURCE_DIR}
        ${asio_SOURCE_DIR}/asio/include
    )
endif()

# ---------------------------------------------------------------------------
# Tier-1 test: hardware-free unit test of the pure edges (ENU->FlightParam map,
# clamp, JSON serialise, /status parse). No websocket, no drone -- runs anywhere.
# ---------------------------------------------------------------------------
add_executable(dji_convert_test test/dji_convert_test.cpp)
target_link_libraries(dji_convert_test PRIVATE
    UTIL2::util2 util_base_header nlohmann_json::nlohmann_json)
target_compile_features(dji_convert_test PRIVATE cxx_std_17)
add_custom_target(run_dji_convert_test
    COMMAND dji_convert_test
    DEPENDS dji_convert_test
    COMMENT "Running DjiBackend Tier-1 unit test..."
)

# ---------------------------------------------------------------------------
# Tier-2 test (needs the mock running: python3 tools/dji_mock/mock_apiserver.py):
# drives the REAL DjiBackend end-to-end through the mock. Uses the default WS
# client, so it proves the default build needs no websocketpp.
# ---------------------------------------------------------------------------
add_executable(dji_backend_mock_test test/dji_backend_mock_test.cpp)
target_link_libraries(dji_backend_mock_test PRIVATE Drone::dji_backend UTIL2::util2)
target_compile_features(dji_backend_mock_test PRIVATE cxx_std_17)

# ---------------------------------------------------------------------------
# Tier-2 latency probe (needs the mock OR the real phone at host:port): drives
# the REAL DjiBackend and reports the command->action + telemetry round-trip
# latency table. Retargets to the phone by changing host:port -- see
# docs/runbooks/dji-bringup-runbook.md, Task C.
# ---------------------------------------------------------------------------
add_executable(dji_latency_probe test/dji_latency_probe.cpp)
target_link_libraries(dji_latency_probe PRIVATE Drone::dji_backend UTIL2::util2)
target_compile_features(dji_latency_probe PRIVATE cxx_std_17)

# ---------------------------------------------------------------------------
# Tier-2 head-to-head (needs the mock): RawWsClient vs WsppWsClient through the
# same script. Needs BOTH clients, so it is built only when websocketpp is on.
# ---------------------------------------------------------------------------
if(GROUNDSTATION_DJI_WS_WEBSOCKETPP)
    add_executable(dji_ws_test
        test/dji_ws_test.cpp
        dji_ws_raw.cpp
        dji_ws_wspp.cpp
    )
    target_compile_definitions(dji_ws_test PRIVATE ASIO_STANDALONE)
    target_link_libraries(dji_ws_test PRIVATE
        UTIL2::util2 util_base_header httplib::httplib nlohmann_json::nlohmann_json Threads::Threads)
    target_include_directories(dji_ws_test SYSTEM PRIVATE
        ${websocketpp_SOURCE_DIR}
        ${asio_SOURCE_DIR}/asio/include
    )
    target_compile_features(dji_ws_test PRIVATE cxx_std_17)
else()
    message(STATUS "[dji_backend] websocketpp off; skipping dji_ws_test head-to-head (raw client is the default).")
endif()
