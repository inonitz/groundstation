include(ExternalProject)


macro(DEFINE_LIBRARY_FETCH_OF_LLAMA_CPP_WITH_EXTERNAL_PROJECT)
    # =============================================================================
    # Why is this shit required when one can just use ExternalProject_Add / git submodule / CPM?
    # For isolating llama-cpp completely via ExternalProject. 
    # whisper-cpp & llama-cpp use different ggml commits, which in turn,
    # creates target collisions in the CMake global namespace if fetched together
    # =============================================================================
    set(LLAMA_UPSTREAM_SOURCE_REPOSITORY              "https://github.com/ggerganov/llama.cpp.git")
    set(LLAMA_TARGET_COMPILATION_BRANCH               "master")
    set(LLAMA_COMPILED_BINARY_BASE_NAME               "llama")

    # Target Namespaces Describing Linking Intent
    set(LLAMA_TARGET_FOR_STATIC_MONOLITHIC_LINKING    "llama::static")
    set(LLAMA_TARGET_FOR_SHARED_ISOLATED_GGML_LINKING "llama::shared")
    set(LLAMA_TARGET_AGNOSTIC_ALIAS                   "llama::llama")

    # External Build Step Orchestrators
    set(LLAMA_INTERNAL_STATIC_BUILD_STEP              "llama_cpp_internal_static")
    set(LLAMA_INTERNAL_SHARED_BUILD_STEP              "llama_cpp_internal_shared")

    # Compilation Output Isolation Roots
    # Depends on cmake/OutputDir.cmake
    set(LLAMA_STATIC_BUILD_ISOLATION_DIRECTORY        "${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY}/llama_static")
    set(LLAMA_SHARED_BUILD_ISOLATION_DIRECTORY        "${WORKSPACE_GLOBAL_CUSTOM_BUILD_OUTPUT_DIRECTORY}/llama_shared")

    # Artifact Path Resolution
    set(LLAMA_STATIC_COMPILED_LIBRARY_FILE_PATH       "${LLAMA_STATIC_BUILD_ISOLATION_DIRECTORY}/bin/${CMAKE_STATIC_LIBRARY_PREFIX}${LLAMA_COMPILED_BINARY_BASE_NAME}${CMAKE_STATIC_LIBRARY_SUFFIX}")
    set(LLAMA_SHARED_COMPILED_LIBRARY_FILE_PATH       "${LLAMA_SHARED_BUILD_ISOLATION_DIRECTORY}/bin/${CMAKE_SHARED_LIBRARY_PREFIX}${LLAMA_COMPILED_BINARY_BASE_NAME}${CMAKE_SHARED_LIBRARY_SUFFIX}")
    set(LLAMA_STATIC_HEADERS_DIRECTORY                "${LLAMA_STATIC_BUILD_ISOLATION_DIRECTORY}/include")
    set(LLAMA_SHARED_HEADERS_DIRECTORY                "${LLAMA_SHARED_BUILD_ISOLATION_DIRECTORY}/include")

    # Feature Disabling & Hardware Acceleration Flags
    set(LLAMA_OPTIMIZED_COMPILER_FEATURE_FLAGS
        -DLLAMA_BUILD_EXAMPLES=OFF
        -DLLAMA_BUILD_COMMON=ON
        -DLLAMA_BUILD_SERVER=ON
        -DLLAMA_BUILD_TOOLS=ON
        -DLLAMA_BUILD_UI=OFF
        -DLLAMA_LLGUIDANCE=OFF
        -DNO_ISA_EXTENSIONS=ON
        -DGGML_VULKAN=ON
        -DGGML_CUDA=OFF
        -DGGML_METAL=OFF
        -DGGML_MUSA=OFF
        -DGGML_SYCL=OFF
        -DBUILD_GMOCK=OFF
        -DINSTALL_GTEST=OFF
    )


    if(NOT BUILD_SHARED_LIBS)
        # 1. Static Library Declaration
        ExternalProject_Add(${LLAMA_INTERNAL_STATIC_BUILD_STEP}
            GIT_REPOSITORY ${LLAMA_UPSTREAM_SOURCE_REPOSITORY}
            GIT_TAG        ${LLAMA_TARGET_COMPILATION_BRANCH}
            GIT_SHALLOW    TRUE
            PREFIX         "${LLAMA_STATIC_BUILD_ISOLATION_DIRECTORY}"
            BUILD_BYPRODUCTS "${LLAMA_STATIC_COMPILED_LIBRARY_FILE_PATH}"
            CMAKE_ARGS
                ${LLAMA_OPTIMIZED_COMPILER_FEATURE_FLAGS}
                -DBUILD_SHARED_LIBS=OFF
                -DCMAKE_INSTALL_PREFIX=${LLAMA_STATIC_BUILD_ISOLATION_DIRECTORY}
                -DCMAKE_INSTALL_LIBDIR=bin

            USES_TERMINAL_CONFIGURE ON
            USES_TERMINAL_BUILD     ON
            USES_TERMINAL_INSTALL   ON
        )

        add_library(${LLAMA_TARGET_FOR_STATIC_MONOLITHIC_LINKING} STATIC IMPORTED GLOBAL)
        file(MAKE_DIRECTORY "${LLAMA_STATIC_HEADERS_DIRECTORY}")
        set_target_properties(${LLAMA_TARGET_FOR_STATIC_MONOLITHIC_LINKING} PROPERTIES
            IMPORTED_LOCATION             "${LLAMA_STATIC_COMPILED_LIBRARY_FILE_PATH}"
            INTERFACE_INCLUDE_DIRECTORIES "${LLAMA_STATIC_HEADERS_DIRECTORY}"
        )
        add_dependencies(${LLAMA_TARGET_FOR_STATIC_MONOLITHIC_LINKING} ${LLAMA_INTERNAL_STATIC_BUILD_STEP})

    else()
        # 2. Shared Library Declaration
        ExternalProject_Add(${LLAMA_INTERNAL_SHARED_BUILD_STEP}
            GIT_REPOSITORY   ${LLAMA_UPSTREAM_SOURCE_REPOSITORY}
            GIT_TAG          ${LLAMA_TARGET_COMPILATION_BRANCH}
            GIT_SHALLOW      TRUE
            PREFIX           "${LLAMA_SHARED_BUILD_ISOLATION_DIRECTORY}"
            BUILD_BYPRODUCTS "${LLAMA_SHARED_COMPILED_LIBRARY_FILE_PATH}"
            CMAKE_ARGS
                ${LLAMA_OPTIMIZED_COMPILER_FEATURE_FLAGS}
                -DBUILD_SHARED_LIBS=ON
                -DCMAKE_INSTALL_PREFIX=${LLAMA_SHARED_BUILD_ISOLATION_DIRECTORY}
                -DCMAKE_WINDOWS_EXPORT_ALL_SYMBOLS=ON
                -DCMAKE_INSTALL_LIBDIR=bin
                
            USES_TERMINAL_CONFIGURE ON
            USES_TERMINAL_BUILD     ON
            USES_TERMINAL_INSTALL   ON
        )

        add_library(${LLAMA_TARGET_FOR_SHARED_ISOLATED_GGML_LINKING} SHARED IMPORTED GLOBAL)
        file(MAKE_DIRECTORY "${LLAMA_SHARED_HEADERS_DIRECTORY}")
        set_target_properties(${LLAMA_TARGET_FOR_SHARED_ISOLATED_GGML_LINKING} PROPERTIES
            IMPORTED_LOCATION             "${LLAMA_SHARED_COMPILED_LIBRARY_FILE_PATH}"
            INTERFACE_INCLUDE_DIRECTORIES "${LLAMA_SHARED_HEADERS_DIRECTORY}"
        )
        add_dependencies(${LLAMA_TARGET_FOR_SHARED_ISOLATED_GGML_LINKING} ${LLAMA_INTERNAL_SHARED_BUILD_STEP})
    endif()


    # 3. Finally, the build artifact agnostic definition
    if(BUILD_SHARED_LIBS)
        add_library(${LLAMA_TARGET_AGNOSTIC_ALIAS} ALIAS ${LLAMA_TARGET_FOR_SHARED_ISOLATED_GGML_LINKING})
    else()
        add_library(${LLAMA_TARGET_AGNOSTIC_ALIAS} ALIAS ${LLAMA_TARGET_FOR_STATIC_MONOLITHIC_LINKING})
    endif()
endmacro()