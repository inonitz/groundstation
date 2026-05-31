cmake_minimum_required(VERSION 3.24)


# Thanks to the following gentlemen:
# https://stackoverflow.com/a/77419222
# https://medium.com/@alasher/colored-c-compiler-output-with-ninja-clang-gcc-10bfe7f2b949
macro(enable_coloured_diagnostics_if_available)
    if("${CMAKE_CXX_COMPILER_ID}" STREQUAL "GNU")
        add_compile_options(-fdiagnostics-color=always)

    elseif("${CMAKE_CXX_COMPILER_ID}" STREQUAL "Clang")
        add_compile_options(-fansi-escape-codes)
        add_compile_options(-fcolor-diagnostics)
    else()
        message(STATUS
            "didn't find appropriate flags for coloured output (compiler=${CMAKE_CXX_COMPILER_ID})"
        )
    endif()
endmacro()