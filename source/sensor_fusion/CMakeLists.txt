cmake_minimum_required(VERSION 3.16)
project(px4_to_ros2_odometry C CXX)


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


set(ODOMETRY_NODE_SOURCES
   px4_odom.hpp
   px4_odom.cpp
)


define_ros2_node(odometry "${ODOMETRY_NODE_SOURCES}")
target_include_directories(${PROJECT_NAME}_odometry PRIVATE ${moodycamel_readerwriterqueue_SOURCE_DIR})
target_link_libraries(${PROJECT_NAME}_odometry PRIVATE
   px4_msgs::px4_msgs__rosidl_typesupport_cpp
   sensor_msgs::sensor_msgs__rosidl_typesupport_cpp
   geometry_msgs::geometry_msgs__rosidl_typesupport_cpp
   message_filters::message_filters
   nav_msgs::nav_msgs
)

