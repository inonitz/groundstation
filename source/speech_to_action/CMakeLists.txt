cmake_minimum_required(VERSION 3.16)
project(ros2_speech_to_action C CXX)


macro(define_ros2_node EXE_NAME FILE_SOURCES)
   set(FULL_EXE_NAME ${PROJECT_NAME}_${EXE_NAME})

   add_executable(${FULL_EXE_NAME})
   target_sources(${FULL_EXE_NAME} PRIVATE ${FILE_SOURCES})
   target_compile_features(${FULL_EXE_NAME} PRIVATE 
      c_std_11
      cxx_std_17
   )
   target_link_libraries(${FULL_EXE_NAME} PRIVATE 
      UTIL2::util2
      cxxopts::cxxopts
      rclcpp::rclcpp
      px4_msgs::px4_msgs__rosidl_typesupport_cpp
      geometry_msgs::geometry_msgs__rosidl_typesupport_cpp
      # WORKSPACE_CONFIG::ProjectDefaultConfig
   )


   add_custom_target(run_${FULL_EXE_NAME}
      COMMAND ./${FULL_EXE_NAME}
      DEPENDS ${FULL_EXE_NAME}
      WORKING_DIRECTORY ${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY}
      USES_TERMINAL
      COMMENT "Running Sandbox..."
   )
endmacro()


set(KEYBOARD_NODE_SOURCES
   base.hpp
   async_key.hpp
   async_key.cpp
   key_codes.hpp
   key_codes.cpp
   keyboard_node.hpp
   keyboard_node.cpp
)


set(OFFBOARD_CONTROL_NODE_SOURCES
   base.hpp
   offboard_node.hpp
   offboard_node.cpp
)

set(ASR_SERVER_NODE_SOURCES
   asr_node.hpp
   asr_node.cpp
)


define_ros2_node(keyboard_input "${KEYBOARD_NODE_SOURCES}")
define_ros2_node(offboard_mode "${OFFBOARD_CONTROL_NODE_SOURCES}")
define_ros2_node(asr_server "${ASR_SERVER_NODE_SOURCES}")
target_link_libraries(${PROJECT_NAME}_asr_server PRIVATE
   STTSERVER::SpeechToTextServer
)

