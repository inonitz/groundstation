cmake_minimum_required(VERSION 3.16)
project(unified_example ASM C CXX)

set(SOURCES
    exp.cpp
)

set(HEADERS
    exp.hpp
)

add_executable(${PROJECT_NAME})
target_sources(${PROJECT_NAME} PRIVATE ${SOURCES})
target_sources(${PROJECT_NAME} PRIVATE ${HEADERS})

target_compile_features(${PROJECT_NAME} PRIVATE 
    c_std_11
    cxx_std_17
)

# FIX: Explicitly inject OpenCV include paths since the submodule targets lack them
target_include_directories(${PROJECT_NAME} PRIVATE
    ${CMAKE_SOURCE_DIR}/dependencies/opencv/modules/core/include
    ${CMAKE_SOURCE_DIR}/dependencies/opencv/modules/imgproc/include
    ${CMAKE_SOURCE_DIR}/dependencies/opencv/modules/imgcodecs/include
    ${CMAKE_BINARY_DIR}
)

# ${CMAKE_BINARY_DIR}/dependencies/opencv # Required for generated opencv_modules.hpp

target_link_libraries(${PROJECT_NAME} PRIVATE 
    BASE64::base64
    nlohmann_json::nlohmann_json
    llama
    opencv_core
    opencv_imgcodecs
    opencv_imgproc
    UTIL2::util2
    httplib::httplib
    # VLMNAV_WORKSPACE_CONFIG::ProjectDefaultConfig
)

add_custom_target(run_${PROJECT_NAME}
    COMMAND ./${PROJECT_NAME}
    DEPENDS ${PROJECT_NAME}
    WORKING_DIRECTORY ${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY}
    USES_TERMINAL
    COMMENT "Running Sandbox..."
)

add_custom_target(debug_${PROJECT_NAME}
    COMMAND ./${PROJECT_NAME}
    DEPENDS ${PROJECT_NAME}
    WORKING_DIRECTORY ${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY}
    USES_TERMINAL
    COMMENT "Running Debugging Sandbox..."
)