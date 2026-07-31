cmake_minimum_required(VERSION 3.14)
# Moved to top-level cmakelists.txt
# include(${CMAKE_SOURCE_DIR}/cmake/FindGStreamer.cmake)
project(GazeboGstCamera
    VERSION 1.0.0
    DESCRIPTION "Gazebo-Harmonic Zero-Copy Camera Plugin"
    LANGUAGES C CXX
)


# Find Gazebo Harmonic
find_package(gz-sim8 REQUIRED)
find_package(gz-plugin2 REQUIRED)


set(GAZEBO_GSTREAMER_CAMERA_INTERFACE_LIBRARY_NAME
    ${PROJECT_NAME}_lib
)


set(SOURCES
    gazebo_cam_plugin.cpp
    gazebo_cam_plugin_base.hpp
)

set(HEADERS
    gazebo_cam_plugin.hpp
    spsc_ringbuffer.hpp
)


# Gazebo plugins must be shared libraries
add_library(${PROJECT_NAME} SHARED)
add_library(CameraPlugin::GazeboGstCameraPlugin ALIAS ${PROJECT_NAME})
target_sources(${PROJECT_NAME} PRIVATE ${SOURCES})
target_sources(${PROJECT_NAME} PRIVATE ${HEADERS})
target_link_libraries(${PROJECT_NAME} PRIVATE
    gz-sim8::core
    GSTREAMER::gstreamer
    UTIL2::util2
)

# Interface library only to headers. Allows for header use inside the project.
add_library(${GAZEBO_GSTREAMER_CAMERA_INTERFACE_LIBRARY_NAME} INTERFACE)
add_library(CameraPlugin::GazeboGstCameraLibrary ALIAS ${GAZEBO_GSTREAMER_CAMERA_INTERFACE_LIBRARY_NAME})
target_sources(${GAZEBO_GSTREAMER_CAMERA_INTERFACE_LIBRARY_NAME} INTERFACE ${HEADERS})


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