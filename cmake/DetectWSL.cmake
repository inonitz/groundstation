cmake_minimum_required(VERSION 3.16)


function(detect_wsl_env OUTPUT_VAR)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        set(KERNEL_VERSION "NONE")

        # Read kernel release string. https://man7.org/linux/man-pages/man1/uname.1.html
        execute_process(
            COMMAND uname -r 
            OUTPUT_VARIABLE KERNEL_VERSION 
            OUTPUT_STRIP_TRAILING_WHITESPACE
        )

        string(TOLOWER ${KERNEL_VERSION} KERNEL_VERSION_LOWERCASE)
        if(KERNEL_VERSION_LOWERCASE MATCHES "microsoft" OR KERNEL_VERSION_LOWERCASE MATCHES "wsl2")
            message(WARNING "Detected WSL2 environment")
            set(${OUTPUT_VAR} TRUE PARENT_SCOPE)
        else()
            message(WARNING "Detected Native Linux environment")
            set(${OUTPUT_VAR} FALSE PARENT_SCOPE)
        endif()
    else()
        message(WARNING "Detected Non-Linux environment")
        set(${OUTPUT_VAR} FALSE)
    endif()
endfunction()


set(GLOBAL_WORKSPACE_LINUX_IS_WSL
)
detect_wsl_env(GLOBAL_WORKSPACE_LINUX_IS_WSL)
