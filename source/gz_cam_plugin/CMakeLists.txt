cmake_minimum_required(VERSION 3.14)
# include(${CMAKE_SOURCE_DIR}/cmake/FindGStreamer.cmake)
project(GazeboGstCameraPlugin 
    VERSION 1.0.0
    DESCRIPTION "Gazebo-Harmonic Zero-Copy Camera Plugin"
    LANGUAGES C CXX
)

# Find Gazebo Harmonic
find_package(gz-sim8 REQUIRED)
find_package(gz-plugin2 REQUIRED)


set(SOURCES
    gazebo_camera_plugin.cpp
)

set(HEADERS
)


add_library(${PROJECT_NAME} SHARED)
target_compile_definitions(${PROJECT_NAME} PUBLIC GAZEBO_ZC_CAMERA_PLUGIN_EXPORTS)
# if(BUILD_SHARED_LIBS)
#     add_library(${PROJECT_NAME} SHARED)
#     target_compile_definitions(${PROJECT_NAME} PUBLIC GAZEBO_ZC_CAMERA_PLUGIN_EXPORTS)
# else()
#     add_library(${PROJECT_NAME} STATIC)
#     target_compile_definitions(${PROJECT_NAME} PUBLIC GAZEBO_ZC_CAMERA_PLUGIN_STATIC_DEFINE)
# endif()

add_library(CameraPlugin::GazeboGstCameraPlugin ALIAS ${PROJECT_NAME})

target_sources(${PROJECT_NAME} PRIVATE ${SOURCES})
target_sources(${PROJECT_NAME} PRIVATE ${HEADERS})
target_link_libraries(${PROJECT_NAME} PRIVATE
    gz-sim8::core
    GSTREAMER::gstreamer
)

# The minimum C/C++ versions required for the library
target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_17)
target_compile_features(${PROJECT_NAME} PUBLIC c_std_11)
if(BUILD_SHARED_LIBS)
    set_target_properties(${PROJECT_NAME} PROPERTIES 
        C_VISIBILITY_PRESET       hidden
        CXX_VISIBILITY_PRESET     hidden
        VISIBILITY_INLINES_HIDDEN ON
    )
endif()


target_deploy_gstreamer(${PROJECT_NAME})