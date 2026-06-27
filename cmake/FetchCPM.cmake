cmake_minimum_required(VERSION 3.16)


macro(include_cpm)
    set(CPM_DOWNLOAD_LOCATION "${CMAKE_BINARY_DIR}/cmake/CPM.cmake")
    if(NOT (EXISTS ${CPM_DOWNLOAD_LOCATION}))
        message(STATUS "Downloading CPM.cmake to ${CPM_DOWNLOAD_LOCATION}")
        file(DOWNLOAD https://github.com/cpm-cmake/CPM.cmake/releases/latest/download/get_cpm.cmake ${CPM_DOWNLOAD_LOCATION})
    endif()
    include(${CPM_DOWNLOAD_LOCATION})
endmacro()


macro(safe_cpm_add_package)
    set(options)
    set(oneValueArgs NAME)
    set(multiValueArgs)
    # Parse the arguments to extract the NAME parameter
    cmake_parse_arguments(SAFE_CPM "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

    if(NOT SAFE_CPM_NAME)
        message(FATAL_ERROR "[SafeCPM] NAME argument is required.")
    endif()

    # Check both standard target and namespace alias
    if(NOT TARGET ${SAFE_CPM_NAME} AND NOT TARGET ${SAFE_CPM_NAME}::${SAFE_CPM_NAME})
        CPMAddPackage(${ARGN})
    else()
        message(WARNING "[SafeCPM] Target '${SAFE_CPM_NAME}' already exists. Skipping fetch.")
    endif()
endmacro()