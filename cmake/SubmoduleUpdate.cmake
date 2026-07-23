cmake_minimum_required(VERSION 3.15)



# Taken from: https://cliutils.gitlab.io/modern-cmake/chapters/projects/submodule.html
function(UPDATE_SUBMODULES_ON_CMAKE_CONFIGURE SUBMODULE_CMAKE_TXT_PATH)
    find_package(Git QUIET)
    if(GIT_FOUND AND EXISTS "${PROJECT_SOURCE_DIR}/.git")
        # Update submodules as needed
        option(GIT_SUBMODULE "Check submodules during build" ON)
        if(GIT_SUBMODULE)
            message(STATUS "Submodule update") # see: https://stackoverflow.com/a/21195182
            execute_process(COMMAND ${GIT_EXECUTABLE} submodule update --init --recursive
                            WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
                            RESULT_VARIABLE GIT_SUBMOD_RESULT
            )
            if(NOT GIT_SUBMOD_RESULT EQUAL "0")
                message(FATAL_ERROR "git submodule update --init --recursive failed with ${GIT_SUBMOD_RESULT}, please checkout submodules")
            endif()
        endif()
    endif()

    if(NOT EXISTS ${PROJECT_SOURCE_DIR}/${SUBMODULE_CMAKE_TXT_PATH})
        message(${PROJECT_SOURCE_DIR}/${SUBMODULE_CMAKE_TXT_PATH})
        message(FATAL_ERROR "The submodules were not downloaded! GIT_SUBMODULE was turned off or failed. Please update submodules and try again.")
    endif()
endfunction()


# In the case where a submodule "X" has been updated remotely,
# and we want to reflect the changes in the project 
# (i.e point the submodule head to the latest commit)
#
#
# cd path/to/submodule
# git checkout "latest_commit_name"
# git pull origin "latest_commit_name"
#
# [NOTE]: call 'git remote -v' to make sure your remote fetch branch is actually named 'origin'
