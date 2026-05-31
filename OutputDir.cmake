cmake_minimum_required(VERSION 3.24)


macro(DEFINE_AGGREGATE_OUTPUT_ARTIFACT_DIRECTORY)
    # Using <config> will generate in a multi-generator-dependant way, which is undesirable
    # I'd rather choose it myself using a script.
    # set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/$<CONFIG>")

    # makes sure all dynamic/static/executable objects sit in the same place
    set(WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY 
        "${CMAKE_BINARY_DIR}/bin"
    )

    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY})
    set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY})
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY})
    # prevent installing to system directories
    set(CMAKE_INSTALL_PREFIX "${CMAKE_BINARY_DIR}" CACHE INTERNAL "")
endmacro()
