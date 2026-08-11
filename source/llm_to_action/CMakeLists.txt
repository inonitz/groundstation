cmake_minimum_required(VERSION 3.16)
project(llm_to_action C CXX)

# Root of this module; subdirectories reference sibling sources through this
# instead of relative path-walking.
set(LLM_TO_ACTION_DIR ${CMAKE_CURRENT_SOURCE_DIR})

set(IS_WSL_ENV)
detect_wsl_env(IS_WSL_ENV)


# ---------------------------------------------------------------------------
# Shared ROS2 node helpers. Defined here (global scope) so every node
# subdirectory added below can call them without redefinition.
# ---------------------------------------------------------------------------
function(define_ros2_node EXE_NAME FILE_SOURCES)
   set(FULL_EXE_NAME ${PROJECT_NAME}_${EXE_NAME})

   add_executable(${FULL_EXE_NAME})
   target_sources(${FULL_EXE_NAME} PRIVATE ${FILE_SOURCES})
   target_compile_features(${FULL_EXE_NAME} PRIVATE
      c_std_11
      cxx_std_17
   )
   target_compile_definitions(${FULL_EXE_NAME} PRIVATE
      $<$<BOOL:${IS_WSL_ENV}>:__WSL__=1>
   )
   target_link_libraries(${FULL_EXE_NAME} PRIVATE
      UTIL2::util2
      cxxopts::cxxopts
      rclcpp::rclcpp
      geometry_msgs::geometry_msgs__rosidl_typesupport_cpp
   )

   add_custom_target(run_${FULL_EXE_NAME}
      COMMAND ./${FULL_EXE_NAME}
      DEPENDS ${FULL_EXE_NAME}
      WORKING_DIRECTORY ${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY}
      USES_TERMINAL
      COMMENT "Running ROS2 Node - ${FULL_EXE_NAME}..."
   )
endfunction()

function(ros2_node_add_library EXE_NAME)
   set(FULL_EXE_NAME ${PROJECT_NAME}_${EXE_NAME})
   target_link_libraries(${FULL_EXE_NAME} PRIVATE
      ${ARGN}
   )
endfunction()

function(ros2_node_add_include_directory EXE_NAME)
   set(FULL_EXE_NAME ${PROJECT_NAME}_${EXE_NAME})
   target_include_directories(${FULL_EXE_NAME} PRIVATE
      ${ARGN}
   )
endfunction()


# ---------------------------------------------------------------------------
# Header-Only Target -- single include root for the whole module. Every target
# links this to get root-relative includes (no relative path-walking).
# ---------------------------------------------------------------------------
add_library(util_base_header INTERFACE)
target_include_directories(util_base_header INTERFACE
   ${CMAKE_CURRENT_SOURCE_DIR}
)


# ---------------------------------------------------------------------------
# Nodes -- each lives in its own folder with its own CMakeLists.txt. Backends
# come before the FMU so its Drone::tello_backend link target exists.
# ---------------------------------------------------------------------------
# Exactly one backend is selected (top-level FATAL_ERROR guard enforces it), so
# build only that backend's library. gstreamer_gz_udp_tx (the Gazebo camera plugin,
# which pulls gz-sim8/gz-plugin2) and offboard_ctrl (the PX4 offboard publisher) are
# PX4/SITL-only -- a Tello build skips them and thus never pulls gz-sim8 or px4_msgs.
if(GROUNDSTATION_BUILD_BACKEND_PX4 OR GROUNDSTATION_BUILD_BACKEND_ALL)
   add_subdirectory(px4_backend)
   add_subdirectory(gstreamer_gz_udp_tx)
endif()
if(GROUNDSTATION_BUILD_BACKEND_TELLO OR GROUNDSTATION_BUILD_BACKEND_ALL)
   add_subdirectory(tello_backend)
endif()

add_subdirectory(fmu)
add_subdirectory(keyboard)
add_subdirectory(asr)
if(GROUNDSTATION_BUILD_BACKEND_PX4 OR GROUNDSTATION_BUILD_BACKEND_ALL)
   add_subdirectory(offboard_ctrl)
endif()
add_subdirectory(gstreamer_udp_cam_rx)
# There shouldn't be a need for a tello udp transmitter since the tello already sends the Packets
# add_subdirectory(gstreamer_tello_udp_tx)
