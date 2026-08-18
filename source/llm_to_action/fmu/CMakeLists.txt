# ---------------------------------------------------------------------------
# Flight Management Unit (FMU) node.
#
# One FMU binary per selected backend. The backend is chosen at configure time
# through the top-level GROUNDSTATION_BUILD_BACKEND_* options; there is no
# default (see the workspace CMakeLists FATAL_ERROR guard). The concrete
# backends are separate libraries (Drone::px4_backend / Drone::tello_backend),
# linked in per selection -- the FMU compiles none of their sources itself.
# Cross-folder sources are referenced through ${LLM_TO_ACTION_DIR}.
# ---------------------------------------------------------------------------

# Backend-agnostic FMU sources (the backend-interface headers + the node itself).
set(FLIGHT_MANAGEMENT_UNIT_COMMON_SOURCES
    ${LLM_TO_ACTION_DIR}/frame/frame_convert.hpp
    ${LLM_TO_ACTION_DIR}/generic_backend/generic_backend_types.hpp
    ${LLM_TO_ACTION_DIR}/generic_backend/generic_backend.hpp
    ${LLM_TO_ACTION_DIR}/generic_backend/active_backend.hpp
    fmu_node_base.hpp
    fmu_node.cpp
    fmu_node.hpp
    perception_runtime.hpp
    llm_base.hpp
    llamaclient.cpp
    llamaclient.hpp
    spsc_bounded_queue.hpp
    threadpool.hpp
)

# FMU backend(s) to build, from the top-level selection options.
set(FMU_SELECTED_BACKENDS)
if(GROUNDSTATION_BUILD_BACKEND_ALL)
   set(FMU_SELECTED_BACKENDS px4 tello dji)
else()
   if(GROUNDSTATION_BUILD_BACKEND_PX4)
      list(APPEND FMU_SELECTED_BACKENDS px4)
   elseif(GROUNDSTATION_BUILD_BACKEND_TELLO)
      list(APPEND FMU_SELECTED_BACKENDS tello)
   endif()
endif()

foreach(backend_name IN LISTS FMU_SELECTED_BACKENDS)
   string(TOUPPER "${backend_name}" backend_name_uppercase)
   set(fmu_executable_target "${PROJECT_NAME}_fmu_${backend_name}")

   add_executable(${fmu_executable_target} ${FLIGHT_MANAGEMENT_UNIT_COMMON_SOURCES})

   target_compile_definitions(${fmu_executable_target} PRIVATE FMU_BACKEND_${backend_name_uppercase})

   target_link_libraries(${fmu_executable_target} PRIVATE
       util_base_header
       BASE64::base64
       nlohmann_json::nlohmann_json
       cv_bridge::cv_bridge
       llama::llama
       opencv_core
       opencv_imgcodecs
       opencv_imgproc
       opencv_highgui
       httplib::httplib
       sensor_msgs::sensor_msgs
       Perception::vision
       $<$<STREQUAL:${backend_name},px4>:Drone::px4_backend>
       $<$<STREQUAL:${backend_name},tello>:Drone::tello_backend>
       $<$<STREQUAL:${backend_name},dji>:Drone::dji_backend>
   )

   target_include_directories(${fmu_executable_target} PRIVATE
       ${moodycamel_readerwriterqueue_SOURCE_DIR}
   )
endforeach()


# ---------------------------------------------------------------------------
# Standalone plan-parse unit test (no ROS). Root include via util_base_header.
# ---------------------------------------------------------------------------
if(GROUNDSTATION_BUILD_TESTS)
    add_executable(plan_parse_test test/plan_parse_test.cpp)
    target_link_libraries(plan_parse_test PRIVATE util_base_header nlohmann_json::nlohmann_json)
    target_compile_features(plan_parse_test PRIVATE cxx_std_17)
    add_custom_target(run_plan_parse_test COMMAND plan_parse_test DEPENDS plan_parse_test)

    # ROS-free unit test for the pure decision points the scenario rewrite exposed:
    # commandIdFromAction (command_id.hpp) + parseTestScenario (test/fmu_test_scenarios.hpp).
    add_executable(fmu_translate_test test/fmu_translate_test.cpp)
    target_link_libraries(fmu_translate_test PRIVATE util_base_header UTIL2::util2)
    target_compile_features(fmu_translate_test PRIVATE cxx_std_17)
    target_include_directories(fmu_translate_test PRIVATE ${LLM_TO_ACTION_DIR})
    add_custom_target(run_fmu_translate_test COMMAND fmu_translate_test DEPENDS fmu_translate_test)

    # ROS-free unit test for perception/detection_query.hpp (block 5.1). perception_types.hpp
    # has zero heavy deps (util2 base types only), so point at the vendored build_yolo repo's
    # include dir directly instead of linking Perception::vision (which would drag in
    # OpenCV/ONNXRuntime for a pure-math, no-YOLO-needed test).
    add_executable(detection_query_test test/detection_query_test.cpp)
    target_link_libraries(detection_query_test PRIVATE util_base_header UTIL2::util2)
    target_include_directories(detection_query_test PRIVATE ${vision_SOURCE_DIR}/vision/include)
    target_compile_features(detection_query_test PRIVATE cxx_std_17)
    add_custom_target(run_detection_query_test COMMAND detection_query_test DEPENDS detection_query_test)

    # ROS-free unit test for perception/target_tracker.hpp (stable target ids). Same pure-math
    # setup as detection_query_test -- util2 base types + the vendored perception_types.hpp only.
    add_executable(target_tracker_test test/target_tracker_test.cpp)
    target_link_libraries(target_tracker_test PRIVATE util_base_header UTIL2::util2)
    target_include_directories(target_tracker_test PRIVATE ${vision_SOURCE_DIR}/vision/include)
    target_compile_features(target_tracker_test PRIVATE cxx_std_17)
    add_custom_target(run_target_tracker_test COMMAND target_tracker_test DEPENDS target_tracker_test)
endif()
