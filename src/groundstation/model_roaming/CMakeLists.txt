cmake_minimum_required(VERSION 3.16)
project(ros2_vlmnav C CXX)


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


set(SOURCES
   cmd.cpp
   offboard.cpp
   main.cpp
)

set(HEADERS
   cmd.hpp
   offboard.hpp
)


set(KEYBOARD_NODE_SOURCES
   base.hpp
   async_key.hpp
   async_key.cpp
   key_codes.hpp
   key_codes.cpp
   px4_keyboard.hpp
   px4_keyboard.cpp
)


set(OFFBOARD_CONTROL_NODE_SOURCES
   base.hpp
   offboard.hpp
   offboard.cpp
)

define_ros2_node(keyboard_input "${KEYBOARD_NODE_SOURCES}")
define_ros2_node(offboard_mode "${OFFBOARD_CONTROL_NODE_SOURCES}")


