cmake_minimum_required(VERSION 3.24)
include(CheckCXXCompilerFlag)
include(CMakePushCheckState)
include(CheckIPOSupported)

macro(check_sanitizer_support FLAG_TO_CHECK OUTPUT_VAR)
    cmake_push_check_state()
    
    set(CMAKE_REQUIRED_FLAGS "${FLAG_TO_CHECK}")
    set(CMAKE_REQUIRED_LINK_OPTIONS "${FLAG_TO_CHECK}")
    
    check_cxx_compiler_flag("${FLAG_TO_CHECK}" ${OUTPUT_VAR})
    
    cmake_pop_check_state()
endmacro()




set(SANITIZER_ADDRESS_INTERFACE_NAME
    workspace_cfg_address_sanitizer_interface
)
set(SANITIZER_UNDEFINED_BEHAVIOUR_INTERFACE_NAME
    workspace_cfg_ubsan_sanitizer_interface
)
set(SANITIZER_MEMORY_INTERFACE_NAME
    workspace_cfg_memory_sanitizer_interface
)
set(SANITIZER_AGGREGATE_INTERFACE_NAME
    workspace_cfg_sanitizers
)

set(LINK_TIME_OPT_INTERFACE_NAME
    workspace_cfg_lto_ipo
)

set(PROJECT_CONFIG_INTERFACE_NAME
    generic_project_cfg
)


check_sanitizer_support("-fsanitize=address" COMPILER_HAS_ASAN_NOT_MSVC)
check_sanitizer_support("/fsanitize=address" COMPILER_HAS_ASAN_MSVC)
check_sanitizer_support("-fsanitize=undefined" COMPILER_HAS_UBSAN_NOT_MSVC)
check_sanitizer_support("/fsanitize=undefined" COMPILER_HAS_UBSAN_MSVC)
check_sanitizer_support("-fsanitize=memory" COMPILER_HAS_MEMSAN_NOT_MSVC)
check_sanitizer_support("/fsanitize=memory" COMPILER_HAS_MEMSAN_MSVC)
check_ipo_supported(
    RESULT LTO_SUPPORT_CHECK_RESULT 
    OUTPUT LTO_SUPPORT_CHECK_OUTPUT
)




# Configure Interface Projects For Different Sanitizers
add_library(${SANITIZER_ADDRESS_INTERFACE_NAME} INTERFACE)
add_library(WORKSPACE_CONFIG::AddressSanitizerInterface ALIAS ${SANITIZER_ADDRESS_INTERFACE_NAME})

if(COMPILER_HAS_ASAN_NOT_MSVC)
    target_compile_options(${SANITIZER_ADDRESS_INTERFACE_NAME} INTERFACE -fsanitize=address -fno-omit-frame-pointer)
    target_link_options(${SANITIZER_ADDRESS_INTERFACE_NAME} INTERFACE -fsanitize=address)

elseif(MSVC AND COMPILER_HAS_ASAN_MSVC)
    target_compile_options(${SANITIZER_ADDRESS_INTERFACE_NAME} INTERFACE /fsanitize=address /Zi /Oy-)
    target_link_options(${SANITIZER_ADDRESS_INTERFACE_NAME} INTERFACE /fsanitize=address)

else()
    message(WARNING "Address Sanitizer (-fsanitize=address OR /fsanitize=address) not supported by this compiler\n")
endif()


add_library(${SANITIZER_UNDEFINED_BEHAVIOUR_INTERFACE_NAME} INTERFACE)
add_library(WORKSPACE_CONFIG::UBSanInterface ALIAS ${SANITIZER_UNDEFINED_BEHAVIOUR_INTERFACE_NAME})

if(COMPILER_HAS_UBSAN_NOT_MSVC)
    target_compile_options(${SANITIZER_UNDEFINED_BEHAVIOUR_INTERFACE_NAME} INTERFACE -fsanitize=undefined)
    target_link_options(${SANITIZER_UNDEFINED_BEHAVIOUR_INTERFACE_NAME} INTERFACE -fsanitize=undefined)

elseif(MSVC AND COMPILER_HAS_UBSAN_MSVC)
    target_compile_options(${SANITIZER_UNDEFINED_BEHAVIOUR_INTERFACE_NAME} INTERFACE /fsanitize=undefined)
    target_link_options(${SANITIZER_UNDEFINED_BEHAVIOUR_INTERFACE_NAME} INTERFACE /fsanitize=undefined)

else()
    message(WARNING "Undefined Behaviour Sanitizer (-fsanitize=undefined OR /fsanitize=undefined) not supported by this compiler\n")
endif()


add_library(${SANITIZER_MEMORY_INTERFACE_NAME} INTERFACE)
add_library(WORKSPACE_CONFIG::MemorySanitizerInterface ALIAS ${SANITIZER_MEMORY_INTERFACE_NAME})

if(COMPILER_HAS_MEMSAN_NOT_MSVC)
    target_compile_options(${SANITIZER_MEMORY_INTERFACE_NAME} INTERFACE -fno-omit-frame-pointer -fsanitize=memory)
    target_link_options(${SANITIZER_MEMORY_INTERFACE_NAME} INTERFACE -fsanitize=memory)

elseif(MSVC AND COMPILER_HAS_MEMSAN_MSVC)
    target_compile_options(${SANITIZER_MEMORY_INTERFACE_NAME} INTERFACE /fsanitize=memory /Zi /Oy-)
    target_link_options(${SANITIZER_MEMORY_INTERFACE_NAME} INTERFACE /fsanitize=memory)

else()
    message(WARNING "Memory Sanitizer (-fsanitize=memory OR /fsanitize=memory) not supported by this compiler\n")
endif()


# declare_optional_interface_library_different_sanitizers()
macro(DECLARE_OPTIONAL_INTERFACE_LIBRARY_DIFFERENT_SANITIZERS)
    # Final Sanitizer Interface
    add_library(${SANITIZER_AGGREGATE_INTERFACE_NAME} INTERFACE)
    add_library(WORKSPACE_CONFIG::Sanitizers ALIAS ${SANITIZER_AGGREGATE_INTERFACE_NAME})

    target_link_libraries(${SANITIZER_AGGREGATE_INTERFACE_NAME} INTERFACE 
        $<$<BOOL:${STTSERVER_ENABLE_SANITIZER_ADDRESS}>:WORKSPACE_CONFIG::AddressSanitizerInterface>
        $<$<BOOL:${STTSERVER_ENABLE_SANITIZER_UNDEFINED}>:WORKSPACE_CONFIG::UBSanInterface>
        $<$<BOOL:${STTSERVER_ENABLE_SANITIZER_MEMORY}>:WORKSPACE_CONFIG::MemorySanitizerInterface>
    )
endmacro()


# declare_optional_interface_library_lto()
macro(DECLARE_OPTIONAL_INTERFACE_LIBRARY_LTO)
    # Configure Interface Project for Link-Time/Interprocedural Optimization
    add_library(${LINK_TIME_OPT_INTERFACE_NAME} INTERFACE)
    add_library(WORKSPACE_CONFIG::LTO ALIAS ${LINK_TIME_OPT_INTERFACE_NAME})

    set_target_properties(${LINK_TIME_OPT_INTERFACE_NAME} PROPERTIES 
        INTERFACE_INTERPROCEDURAL_OPTIMIZATION "$<AND:
            $<BOOL:${ENABLE_LINK_TIME_OPTIMIZATION}>,
            $<BOOL:${LTO_SUPPORT_CHECK_RESULT}>
        >"
    )
    if(NOT LTO_SUPPORT_CHECK_RESULT)
        message(WARNING "IPO / LTO Not Supported:\nMessage:${LTO_SUPPORT_CHECK_OUTPUT}\n")
    endif()
endmacro()


# Project Configuration that should be used
# declare_optional_interface_default_project_configuration()
macro(DECLARE_OPTIONAL_INTERFACE_DEFAULT_PROJECT_CONFIGURATION)
    add_library(${PROJECT_CONFIG_INTERFACE_NAME} INTERFACE)
    add_library(WORKSPACE_CONFIG::ProjectDefaultConfig ALIAS ${PROJECT_CONFIG_INTERFACE_NAME})
    
    set(GCC_CLANG_WARNINGS
        -Wall 
        -Wextra 
        -Wshadow 
        -Wfloat-equal 
        -Wconversion 
        -Wformat=2 
        -pedantic 
        -pedantic-errors 
        -fstrict-aliasing
    )
    
    set(GCC_CLANG_DEBUG_ERROR
        $<$<CONFIG:Debug,RelWithDebInfo>:-Werror>
    )

    set(CXX_ONLY_WARNINGS
        -Wold-style-cast 
        -Wnon-virtual-dtor 
        -Woverloaded-virtual
    )

    set(C_ONLY_WARNINGS
        -Wmissing-prototypes -Wstrict-prototypes
    )

    set(MSVC_WARNINGS
        /W4 
        $<$<CONFIG:Debug,RelWithDebInfo>:/WX>
        $<$<COMPILE_LANGUAGE:CXX>:/permissive->
    )

    set(IS_GNU_OR_CLANG $<OR:$<CXX_COMPILER_ID:GNU>,$<CXX_COMPILER_ID:Clang>,$<CXX_COMPILER_ID:AppleClang>>)
    set(IS_MSVC         $<CXX_COMPILER_ID:MSVC>)
    set(IS_CXX          $<COMPILE_LANGUAGE:CXX>)
    set(IS_C            $<COMPILE_LANGUAGE:C>)


    target_link_libraries(${PROJECT_CONFIG_INTERFACE_NAME} INTERFACE
        WORKSPACE_CONFIG::Sanitizers
        WORKSPACE_CONFIG::LTO
    )

    target_compile_options(${PROJECT_CONFIG_INTERFACE_NAME} INTERFACE
        $<$<AND:${IS_GNU_OR_CLANG},${IS_C}>:
            ${GCC_CLANG_WARNINGS} ${GCC_CLANG_DEBUG_ERROR} ${C_ONLY_WARNINGS}
        >
        $<$<AND:${IS_GNU_OR_CLANG},${IS_CXX}>:
            ${GCC_CLANG_WARNINGS} ${GCC_CLANG_DEBUG_ERROR} ${CXX_ONLY_WARNINGS}
        >
        
        $<$<CXX_COMPILER_ID:Clang,AppleClang>:-fcolor-diagnostics>
        $<$<CXX_COMPILER_ID:GNU>:-fdiagnostics-color=always>

        # --- MSVC ---
        $<$<AND:${IS_MSVC},$<OR:${IS_C},${IS_CXX}>>:
            ${MSVC_WARNINGS}
        >
    )

    target_compile_features(${PROJECT_CONFIG_INTERFACE_NAME} INTERFACE 
        c_std_11 
        cxx_std_17
    )

    set_target_properties(${PROJECT_CONFIG_INTERFACE_NAME} PROPERTIES
        INTERFACE_CXX_STANDARD_REQUIRED      ON
        INTERFACE_CXX_EXTENSIONS             OFF
        INTERFACE_POSITION_INDEPENDENT_CODE  ON
        INTERFACE_CXX_VISIBILITY_PRESET      hidden
        INTERFACE_VISIBILITY_INLINES_HIDDEN  ON
    )
endmacro()
