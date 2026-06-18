cmake_minimum_required(VERSION 3.16)
project(px4_ros2_keyboard C CXX)


set(SOURCES
    main.cpp
    async_key.cpp
    key_codes.cpp
)

set(HEADERS
    async_key.hpp
    key_codes.hpp
)


add_executable(${PROJECT_NAME})
target_sources(${PROJECT_NAME} PRIVATE ${SOURCES})
target_sources(${PROJECT_NAME} PRIVATE ${HEADERS})
target_compile_features(${PROJECT_NAME} PRIVATE 
    c_std_11
    cxx_std_17
)
target_link_libraries(${PROJECT_NAME} PRIVATE 
    UTIL2::util2
    cxxopts::cxxopts
    rclcpp::rclcpp
    px4_msgs::px4_msgs__rosidl_typesupport_cpp
    Eigen3::Eigen
    # WORKSPACE_CONFIG::ProjectDefaultConfig
)


add_custom_target(run_${PROJECT_NAME}
    COMMAND ./${PROJECT_NAME}
    DEPENDS ${PROJECT_NAME}
    WORKING_DIRECTORY ${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY}
    USES_TERMINAL
    COMMENT "Running Sandbox..."
)

