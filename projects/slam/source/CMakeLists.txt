cmake_minimum_required(VERSION 3.16)
project(stella_vslam C CXX)


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


set(SLAM_NODE_NAME
   monocular
)
set(SLAM_NODE_SOURCES
   slam2.hpp
   slam_node.cpp
)


# message(WARNING "OpenCV Libraries Are ==> ${OpenCV_LIBRARIES}\nOpenCV Bridge Libraries are ==> ${cv_bridge_LIBRARIES}\n")

define_ros2_node(${SLAM_NODE_NAME} "${SLAM_NODE_SOURCES}")
target_include_directories(${PROJECT_NAME}_${SLAM_NODE_NAME} PRIVATE 
   ${moodycamel_readerwriterqueue_SOURCE_DIR}
   ${cv_bridge_INCLUDE_DIRS}
)
target_link_libraries(${PROJECT_NAME}_${SLAM_NODE_NAME} PRIVATE
   px4_msgs::px4_msgs__rosidl_typesupport_cpp
   sensor_msgs::sensor_msgs__rosidl_typesupport_cpp
   geometry_msgs::geometry_msgs__rosidl_typesupport_cpp
   nav_msgs::nav_msgs
   Eigen3::Eigen
   opencv_core
   opencv_imgcodecs
   opencv_imgproc
   cv_bridge::cv_bridge
   stella_vslam::stella_vslam
)

