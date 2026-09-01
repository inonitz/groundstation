# ---------------------------------------------------------------------------
# Keyboard hook node. On WSL it links X11 for global key capture.
# ---------------------------------------------------------------------------
set(KEYBOARD_NODE_NAME_POSTFIX keyboard_hook)
set(KEYBOARD_NODE_SOURCES
    async_key.hpp
    async_key.cpp
    key_codes.hpp
    key_codes.cpp
    keyboard_node.hpp
    keyboard_node.cpp
    keyboard_node_base.hpp
)

define_ros2_node(${KEYBOARD_NODE_NAME_POSTFIX} "${KEYBOARD_NODE_SOURCES}")
ros2_node_add_library(${KEYBOARD_NODE_NAME_POSTFIX}
    "$<$<BOOL:${IS_WSL_ENV}>:${X11_LIBRARIES};${X11_Xi_LIB}>"
    util_base_header
)
ros2_node_add_include_directory(${KEYBOARD_NODE_NAME_POSTFIX}
    "$<$<BOOL:${IS_WSL_ENV}>:${X11_INCLUDE_DIR}>"
)
