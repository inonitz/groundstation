cmake_minimum_required(VERSION 3.24)


macro(USE_CCACHE_PROGRAM_IF_EXISTS)
    find_program(CCACHE_PROGRAM ccache)
    if(CCACHE_PROGRAM)
        set(CMAKE_ASM_COMPILER_LAUNCHER  "${CCACHE_PROGRAM}")
        set(CMAKE_C_COMPILER_LAUNCHER    "${CCACHE_PROGRAM}")
        set(CMAKE_CXX_COMPILER_LAUNCHER  "${CCACHE_PROGRAM}")
        # set(CMAKE_CUDA_COMPILER_LAUNCHER "${CCACHE_PROGRAM}") # CMake 3.9+
    endif()
endmacro()
