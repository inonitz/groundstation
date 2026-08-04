cmake_minimum_required(VERSION 3.16)
project(llm_to_action C CXX)

set(IS_WSL_ENV)
detect_wsl_env(IS_WSL_ENV)


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
      px4_msgs::px4_msgs__rosidl_typesupport_cpp
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
# Header-Only Target
# ---------------------------------------------------------------------------
add_library(util_base_header INTERFACE)
target_include_directories(util_base_header INTERFACE 
   ${CMAKE_CURRENT_SOURCE_DIR}
)

# ---------------------------------------------------------------------------
# Source Definitions
# ---------------------------------------------------------------------------
set(FLIGHT_MANAGEMENT_UNIT_NODE_NAME_POSTFIX fmu)
set(FLIGHT_MANAGEMENT_UNIT_NODE_SOURCES
    fmu/fmu_node_base.hpp
    fmu/fmu_node.cpp
    fmu/fmu_node.hpp
    fmu/llamaclient.cpp
    fmu/llamaclient.hpp
    fmu/spsc_bounded_queue.hpp
    fmu/threadpool.hpp
)

set(KEYBOARD_NODE_NAME_POSTFIX keyboard_hook)
set(KEYBOARD_NODE_SOURCES
    keyboard/async_key.hpp
    keyboard/async_key.cpp
    keyboard/key_codes.hpp
    keyboard/key_codes.cpp
    keyboard/keyboard_node.hpp
    keyboard/keyboard_node.cpp
    keyboard/keyboard_node_base.hpp
)

set(ASR_SERVER_NODE_NAME_POSTFIX asr_server)
set(ASR_SERVER_NODE_SOURCES
    asr/asr_node_base.hpp
    asr/asr_node.hpp
    asr/asr_node.cpp
)

set(OFFBOARD_CONTROL_MODE_NAME_POSTFIX offboard_mode)
set(OFFBOARD_CONTROL_NODE_SOURCES
    offboard_ctrl/px4_offboard_node_base.hpp
    offboard_ctrl/px4_offboard_node.hpp
    offboard_ctrl/px4_offboard_node.cpp
)

set(GSTREAMER_RECEIVER_NAME_POSTFIX gstreamer_rx)
set(GSTREAMER_RECEIVER_SOURCES
    gstreamer_udp_cam_rx/rx_node.cpp
    gstreamer_udp_cam_rx/rx_node.hpp
    gstreamer_udp_cam_rx/rx_node_base.hpp
)

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------
define_ros2_node(${FLIGHT_MANAGEMENT_UNIT_NODE_NAME_POSTFIX} "${FLIGHT_MANAGEMENT_UNIT_NODE_SOURCES}")
ros2_node_add_library(${FLIGHT_MANAGEMENT_UNIT_NODE_NAME_POSTFIX}
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
    sensor_msgs::sensor_msgs__rosidl_generator_c
    sensor_msgs::sensor_msgs__rosidl_generator_cpp
)
ros2_node_add_include_directory(${FLIGHT_MANAGEMENT_UNIT_NODE_NAME_POSTFIX} 
    ${cv_bridge_INCLUDE_DIRS}
    ${moodycamel_readerwriterqueue_SOURCE_DIR}
)


define_ros2_node(${KEYBOARD_NODE_NAME_POSTFIX} "${KEYBOARD_NODE_SOURCES}")
ros2_node_add_library(${KEYBOARD_NODE_NAME_POSTFIX}
    "$<$<BOOL:${IS_WSL_ENV}>:${X11_LIBRARIES};${X11_Xi_LIB}>"
    util_base_header
)
ros2_node_add_include_directory(${KEYBOARD_NODE_NAME_POSTFIX} 
    "$<$<BOOL:${IS_WSL_ENV}>:${X11_INCLUDE_DIR}>"
)

define_ros2_node(${ASR_SERVER_NODE_NAME_POSTFIX} "${ASR_SERVER_NODE_SOURCES}")
ros2_node_add_library(${ASR_SERVER_NODE_NAME_POSTFIX}
    STTSERVER::SpeechToTextServer
    util_base_header
)

define_ros2_node(${OFFBOARD_CONTROL_MODE_NAME_POSTFIX} "${OFFBOARD_CONTROL_NODE_SOURCES}")
ros2_node_add_library(${OFFBOARD_CONTROL_MODE_NAME_POSTFIX}
    util_base_header
)
ros2_node_add_include_directory(${OFFBOARD_CONTROL_MODE_NAME_POSTFIX}
    "$<$<BOOL:${IS_WSL_ENV}>:${X11_INCLUDE_DIR}>"
)

define_ros2_node(${GSTREAMER_RECEIVER_NAME_POSTFIX} "${GSTREAMER_RECEIVER_SOURCES}")
ros2_node_add_library(${GSTREAMER_RECEIVER_NAME_POSTFIX}
    util_base_header
    GSTREAMER::gstreamer
    CameraPlugin::GazeboGstCameraLibrary
    sensor_msgs::sensor_msgs__rosidl_typesupport_cpp
)
target_deploy_gstreamer(${PROJECT_NAME}_${GSTREAMER_RECEIVER_NAME_POSTFIX})



add_subdirectory(gstreamer_gz_udp_tx)
# There shouldn't be a need for a tello udp transmitter since the tello already sends the Packets 
# add_subdirectory(gstreamer_tello_udp_tx)