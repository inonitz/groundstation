# ---------------------------------------------------------------------------
# PX4 offboard control mode node.
# ---------------------------------------------------------------------------
set(OFFBOARD_CONTROL_MODE_NAME_POSTFIX offboard_mode)
set(OFFBOARD_CONTROL_NODE_SOURCES
    px4_offboard_node_base.hpp
    px4_offboard_node.hpp
    px4_offboard_node.cpp
)

define_ros2_node(${OFFBOARD_CONTROL_MODE_NAME_POSTFIX} "${OFFBOARD_CONTROL_NODE_SOURCES}")
ros2_node_add_library(${OFFBOARD_CONTROL_MODE_NAME_POSTFIX}
    util_base_header
    px4_msgs::px4_msgs__rosidl_typesupport_cpp
)
ros2_node_add_include_directory(${OFFBOARD_CONTROL_MODE_NAME_POSTFIX}
    "$<$<BOOL:${IS_WSL_ENV}>:${X11_INCLUDE_DIR}>"
)
