cmake_minimum_required(VERSION 3.16)
project(GStreamerReceiverNode
   LANGUAGES C CXX
)


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
      sensor_msgs::sensor_msgs__rosidl_typesupport_cpp
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


set(GST_RECEIVER_SOURCES
   rx_node_2.cpp

)


define_ros2_node(net_packet_decoder_node "${GST_RECEIVER_SOURCES}")
target_link_libraries(${PROJECT_NAME}_net_packet_decoder_node PRIVATE
   GSTREAMER::gstreamer
)
target_deploy_gstreamer(${PROJECT_NAME}_net_packet_decoder_node)

