cmake_minimum_required(VERSION 3.16)
project(unified_example ASM C CXX)


set(SOURCES 
    llamaclient.cpp
    llamaconnect2.cpp
)
set(HEADERS 
    llamaclient.hpp
    threadpool.hpp
)

add_executable(${PROJECT_NAME})
target_sources(${PROJECT_NAME} PRIVATE ${SOURCES})
target_sources(${PROJECT_NAME} PRIVATE ${HEADERS})

target_compile_features(${PROJECT_NAME} PRIVATE 
    c_std_11
    cxx_std_17
)
# target_compile_definitions(${PROJECT_NAME} PRIVATE 
#     CPPHTTPLIB_USE_POLL
# )

target_link_libraries(${PROJECT_NAME} PRIVATE 
    BASE64::base64
    nlohmann_json::nlohmann_json
    llama::llama
    opencv_core
    opencv_imgcodecs
    opencv_imgproc
    opencv_highgui   # Required for cv::imshow visualization
    UTIL2::util2
    httplib::httplib
    rclcpp::rclcpp   # ROS 2 Core
    sensor_msgs::sensor_msgs__rosidl_generator_c
    sensor_msgs::sensor_msgs__rosidl_generator_cpp
    cv_bridge::cv_bridge
)


add_custom_target(run_${PROJECT_NAME}
    COMMAND ./${PROJECT_NAME}
    DEPENDS ${PROJECT_NAME}
    WORKING_DIRECTORY ${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY}
    USES_TERMINAL
    COMMENT "Running Sandbox..."
)