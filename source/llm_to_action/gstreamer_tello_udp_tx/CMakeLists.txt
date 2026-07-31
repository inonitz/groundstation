cmake_minimum_required(VERSION 3.14)
project(DjiTelloUDPCameraLibrary 
    VERSION 1.0.0
    DESCRIPTION "Gazebo-Harmonic Zero-Copy Camera Plugin"
    LANGUAGES C CXX
)


set(SOURCES
)

set(HEADERS
)


# Gazebo plugins must be shared libraries
add_library(${PROJECT_NAME} SHARED)
target_compile_definitions(${PROJECT_NAME} PUBLIC GAZEBO_ZC_CAMERA_PLUGIN_EXPORTS)
add_library(CameraPlugin::DjiTelloUDPCameraLibrary ALIAS ${PROJECT_NAME})

target_sources(${PROJECT_NAME} PRIVATE ${SOURCES})
target_sources(${PROJECT_NAME} PRIVATE ${HEADERS})
target_link_libraries(${PROJECT_NAME} PRIVATE
    GSTREAMER::gstreamer
    UTIL2::util2
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
