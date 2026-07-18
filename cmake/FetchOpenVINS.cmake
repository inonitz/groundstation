include(ExternalProject)

macro(DEFINE_LIBRARY_FETCH_OF_OPENVINS_WITH_EXTERNAL_PROJECT)
    # OpenVINS hardcodes ${CMAKE_SOURCE_DIR} when globbing source files.
    # In FetchContent/CPM, ${CMAKE_SOURCE_DIR} points to the top-level workspace root.
    # Due to the mismatch between what OpenVINS expects & what it gets,
    # This causes the glob to miss the OpenVINS sources entirely.
    # Because no sources are found, the library target files are never built.
    # The toolchain then fails with a "library not found" linker error (-lov_msckf).
    # ExternalProject_Add is used to spawn an isolated CMake process.
    # The Isolation points ${CMAKE_SOURCE_DIR} to the OpenVINS folder, creating the targets correctly.
    # Changing ${CMAKE_SOURCE_DIR} to ${CMAKE_CURRENT_SOURCE_DIR} upstream would fix this natively.
    # I will not maintain a fork.
    set(OPENVINS_UPSTREAM_SOURCE_REPOSITORY              "https://github.com/rpng/open_vins.git")
    set(OPENVINS_TARGET_COMPILATION_BRANCH               "master")
    set(OPENVINS_COMPILED_BINARY_BASE_NAME               "ov_msckf_lib")

    # Define clean target names to eliminate linker path conflicts
    set(OPENVINS_TARGET_AGNOSTIC_ALIAS                   "open_vins::ov_msckf_lib")
    set(OPENVINS_INTERNAL_BUILD_STEP                     "open_vins_internal_build")
    set(OPENVINS_BUILD_ISOLATION_DIRECTORY               "${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY}/open_vins")

    # Resolve exact library output file layout paths
    set(OPENVINS_COMPILED_LIBRARY_FILE_PATH              "${OPENVINS_BUILD_ISOLATION_DIRECTORY}/lib/${CMAKE_SHARED_LIBRARY_PREFIX}${OPENVINS_COMPILED_BINARY_BASE_NAME}${CMAKE_SHARED_LIBRARY_SUFFIX}")
    set(OPENVINS_HEADERS_DIRECTORY                       "${OPENVINS_BUILD_ISOLATION_DIRECTORY}/include")

    # Forward dependency paths down to the isolated build process
    set(OPENVINS_FORWARDED_COMPILER_FLAGS
        -DENABLE_ROS=OFF
        -DCMAKE_PREFIX_PATH=${CMAKE_PREFIX_PATH}
    )

    # Spawn isolated process to download and compile the dependency safely
    ExternalProject_Add(${OPENVINS_INTERNAL_BUILD_STEP}
        GIT_REPOSITORY ${OPENVINS_UPSTREAM_SOURCE_REPOSITORY}
        GIT_TAG        ${OPENVINS_TARGET_COMPILATION_BRANCH}
        GIT_SHALLOW    TRUE
        SOURCE_SUBDIR  ov_msckf
        PREFIX         "${OPENVINS_BUILD_ISOLATION_DIRECTORY}"
        BUILD_BYPRODUCTS "${OPENVINS_COMPILED_LIBRARY_FILE_PATH}"
        CMAKE_ARGS
            ${OPENVINS_FORWARDED_COMPILER_FLAGS}
            -DBUILD_SHARED_LIBS=ON
            -DCMAKE_INSTALL_PREFIX=${OPENVINS_BUILD_ISOLATION_DIRECTORY}
        USES_TERMINAL_CONFIGURE ON
        USES_TERMINAL_BUILD     ON
        USES_TERMINAL_INSTALL   ON
    )

    # Register the isolated binary into the local target space
    add_library(${OPENVINS_TARGET_AGNOSTIC_ALIAS} SHARED IMPORTED GLOBAL)
    file(MAKE_DIRECTORY "${OPENVINS_HEADERS_DIRECTORY}")
    set_target_properties(${OPENVINS_TARGET_AGNOSTIC_ALIAS} PROPERTIES
        IMPORTED_LOCATION             "${OPENVINS_COMPILED_LIBRARY_FILE_PATH}"
        INTERFACE_INCLUDE_DIRECTORIES "${OPENVINS_HEADERS_DIRECTORY};${OPENVINS_HEADERS_DIRECTORY}/open_vins"
    )
    add_dependencies(${OPENVINS_TARGET_AGNOSTIC_ALIAS} ${OPENVINS_INTERNAL_BUILD_STEP})
endmacro()
