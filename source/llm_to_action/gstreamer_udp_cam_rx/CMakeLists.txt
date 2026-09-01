# ---------------------------------------------------------------------------
# GStreamer camera receiver node (UDP: PX4/Tello, TCP: DJI -- selected at runtime).
# ---------------------------------------------------------------------------
set(GSTREAMER_RECEIVER_NAME_POSTFIX gstreamer_rx)
set(GSTREAMER_RECEIVER_SOURCES
    rx_node.cpp
    rx_node.hpp
    rx_node_base.hpp
)

define_ros2_node(${GSTREAMER_RECEIVER_NAME_POSTFIX} "${GSTREAMER_RECEIVER_SOURCES}")
ros2_node_add_library(${GSTREAMER_RECEIVER_NAME_POSTFIX}
    util_base_header
    GSTREAMER::gstreamer
    sensor_msgs::sensor_msgs__rosidl_typesupport_cpp
)
target_deploy_gstreamer(${PROJECT_NAME}_${GSTREAMER_RECEIVER_NAME_POSTFIX})
