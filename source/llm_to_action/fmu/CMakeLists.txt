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

# Backend-agnostic FMU sources (the seam headers + the node itself).
set(FLIGHT_MANAGEMENT_UNIT_COMMON_SOURCES
    ${LLM_TO_ACTION_DIR}/frame/frame_convert.hpp
    ${LLM_TO_ACTION_DIR}/generic_backend/generic_backend_types.hpp
    ${LLM_TO_ACTION_DIR}/generic_backend/generic_backend.hpp
    ${LLM_TO_ACTION_DIR}/generic_backend/active_backend.hpp
    fmu_node_base.hpp
    fmu_node.cpp
    fmu_node.hpp
    llm_base.hpp
    llamaclient.cpp
    llamaclient.hpp
    spsc_bounded_queue.hpp
    threadpool.hpp
)

# FMU backend(s) to build, from the top-level selection options.
set(FMU_SELECTED_BACKENDS)
if(GROUNDSTATION_BUILD_BACKEND_ALL)
   set(FMU_SELECTED_BACKENDS px4 tello)
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
       $<$<STREQUAL:${backend_name},px4>:Drone::px4_backend>
       $<$<STREQUAL:${backend_name},tello>:Drone::tello_backend>
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
    target_link_libraries(plan_parse_test PRIVATE util_base_header)
    target_compile_features(plan_parse_test PRIVATE cxx_std_17)
    add_custom_target(run_plan_parse_test COMMAND plan_parse_test DEPENDS plan_parse_test)
endif()
