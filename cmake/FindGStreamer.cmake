cmake_minimum_required(VERSION 3.14)


macro(DEFINE_LIBRARY_FETCH_OF_GSTREAMER)
    if(NOT WIN32 AND NOT APPLE)
        # LINUX: Use native apt precompiled binaries
        find_package(PkgConfig REQUIRED)
        pkg_check_modules(GST REQUIRED 
            gstreamer-1.0 
            gstreamer-app-1.0 
            gstreamer-base-1.0 
            gstreamer-video-1.0 
            glib-2.0 
            gobject-2.0
        )
        
        add_library(gst_interface INTERFACE)
        add_library(GSTREAMER::gstreamer ALIAS gst_interface)
        
        target_link_libraries(gst_interface INTERFACE ${GST_LIBRARIES})
        target_include_directories(gst_interface INTERFACE ${GST_INCLUDE_DIRS})
        target_compile_options(gst_interface INTERFACE ${GST_CFLAGS_OTHER})

        # Linux does not need local deployment. System libraries are in the global PATH.
        function(target_deploy_gstreamer _target)
        endfunction()


    else()
        # WINDOWS / MACOS: Fetch Precompiled Binaries
        include(FetchContent)
        set(GST_VERSION "1.22.12")

        if(WIN32)
            set(GST_DEFAULT_URL 
                "https://gstreamer.freedesktop.org/data/pkg/windows/${GST_VERSION}/msvc/gstreamer-1.0-devel-msvc-x86_64-${GST_VERSION}.msi"
            )
        else()
            set(GST_DEFAULT_URL 
                "https://gstreamer.freedesktop.org/data/pkg/osx/${GST_VERSION}/gstreamer-1.0-devel-${GST_VERSION}-x86_64.pkg"
            )
        endif()

        FetchContent_Declare(
            gstreamer_binaries
            URL "${GST_DEFAULT_URL}"
            DOWNLOAD_EXTRACT_TIMESTAMP TRUE
        )

        FetchContent_GetProperties(gstreamer_binaries)
        if(NOT gstreamer_binaries_POPULATED)
            FetchContent_Populate(gstreamer_binaries)
        endif()

        set(GST_DIRECTORY ${gstreamer_binaries_SOURCE_DIR})
        set(GST_INTERFACE_LIBRARY_NAME gst_interface)
        set(GST_LINK_TARGETS)
        set(GST_EXPLICIT_BINARIES)
        set(GST_COMPONENTS gstreamer-1.0 gstapp-1.0 gstbase-1.0 gstvideo-1.0 glib-2.0 gobject-2.0)

        if(WIN32)
            foreach(LIB IN LISTS GST_COMPONENTS)
                add_library(gst_${LIB} UNKNOWN IMPORTED)
                set_target_properties(gst_${LIB} PROPERTIES
                    IMPORTED_LOCATION "${GST_DIRECTORY}/lib/${LIB}.lib"
                )
                list(APPEND GST_LINK_TARGETS gst_${LIB})
                # Track the runtime DLL for post-build deployment
                list(APPEND GST_EXPLICIT_BINARIES "${GST_DIRECTORY}/bin/${LIB}-0.dll")
            endforeach()
            set(GST_EXPLICIT_BINARIES ${GST_EXPLICIT_BINARIES} CACHE INTERNAL "GStreamer Windows DLLs")
        elseif(APPLE)
            foreach(LIB IN LISTS GST_COMPONENTS)
                add_library(gst_${LIB} SHARED IMPORTED)
                set_target_properties(gst_${LIB} PROPERTIES
                    IMPORTED_LOCATION "${GST_DIRECTORY}/lib/lib${LIB}.dylib"
                )
                list(APPEND GST_LINK_TARGETS gst_${LIB})
                # macOS runtime files
                list(APPEND GST_EXPLICIT_BINARIES "${GST_DIRECTORY}/lib/lib${LIB}.dylib")
            endforeach()
            set(GST_EXPLICIT_BINARIES ${GST_EXPLICIT_BINARIES} CACHE INTERNAL "GStreamer macOS Dylibs")
        endif()

        add_library(${GST_INTERFACE_LIBRARY_NAME} INTERFACE)
        add_library(GSTREAMER::gstreamer ALIAS ${GST_INTERFACE_LIBRARY_NAME})
        
        target_link_libraries(${GST_INTERFACE_LIBRARY_NAME} INTERFACE ${GST_LINK_TARGETS})
        target_include_directories(${GST_INTERFACE_LIBRARY_NAME} INTERFACE 
            "${GST_DIRECTORY}/include/gstreamer-1.0"
            "${GST_DIRECTORY}/include/glib-2.0"
            "${GST_DIRECTORY}/lib/glib-2.0/include"
        )

        # The actual deployment logic for Windows/macOS
        function(target_deploy_gstreamer _target)
            add_custom_command(TARGET ${_target} POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy_if_different 
                ${GST_EXPLICIT_BINARIES} $<TARGET_FILE_DIR:${_target}>
                VERBATIM
                COMMAND_EXPAND_LISTS
                COMMENT "Deploying GStreamer Binaries to $<TARGET_FILE_DIR:${_target}>"
            )
        endfunction()
    endif()
endmacro()