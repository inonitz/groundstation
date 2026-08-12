#include "rx_node.hpp"
#include "gstreamer_gz_udp_tx/gazebo_cam_plugin_base.hpp"  /* kSitlUdpCamPort (sim camera transport). */
#include "tello_backend/tello_backend_base.hpp"           /* kTelloVideoPort (Tello's own source of truth). */
#include <gst/app/gstappsink.h>
#include <gst/video/video.h>


using namespace std::chrono_literals;


GstReceiverNode::GstReceiverNode(bool bUseTelloPipeline) : Node("gst_receiver_node") {
    gst_init(nullptr, nullptr);

    m_pubCamFrames = this->create_publisher<UDPCamMsgType>(kOutUDPCameraRawFrameTopic, 10);

    /* 
        max-buffers=1 & drop=true: 
            Creates a size-1 circular queue. 
            Drops stale frames if Receiving is slow.
        sync=false: 
            Disables GStreamer's internal wall-clock pacing. 
            Forces frames to pass through instantly regardless of their timestamp.
    */ 
    /* The real Tello sends raw H.264 over UDP with no RTP framing, so it parses NAL
       units with h264parse and has no rtph264depay stage. Gazebo's simulated camera
       sends RTP-framed H.264 and must be depayloaded first. Everything from avdec_h264
       onward is identical, so only the source+depay stage differs between the two. */
    /* Port owned by whichever backend feeds this pipeline: the Tello backend fixes video at 11111
       (kTelloVideoPort); the gz sim transport uses kSitlUdpCamPort. Split lets SITL and a real
       Tello share a host without both binding 11111. */
    const u16 kRxCamPort = bUseTelloPipeline ? kTelloVideoPort : kSitlUdpCamPort;
    const std::string kSourceStage = bUseTelloPipeline
        ? "udpsrc port=" + std::to_string(kRxCamPort) + " ! h264parse ! "
        : "udpsrc port=" + std::to_string(kRxCamPort) + " caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=H264\" ! "
          "rtph264depay ! ";
    const std::string kRxPipelineStr = kSourceStage +
        "avdec_h264 ! videoconvert ! video/x-raw, format=BGR ! "
        "appsink name=" + kOutUDPCameraGstSinkName + " max-buffers=1 drop=true sync=false";

    m_pipeline = gst_parse_launch(kRxPipelineStr.c_str(), nullptr);
    m_sink     = gst_bin_get_by_name(GST_BIN(m_pipeline), kOutUDPCameraGstSinkName);
    m_bus      = gst_element_get_bus(m_pipeline);
    gst_element_set_state(m_pipeline, GST_STATE_PLAYING);

    /* Timer 1: Poll appsink directly on ROS 2 thread (100 Hz) */
    m_pull_timer = this->create_wall_timer(10ms, 
        std::bind(&GstReceiverNode::PollSampleCb, this)
    );

    /* Timer 2: Poll GStreamer bus for fatal disconnects (10 Hz) */
    m_bus_timer = this->create_wall_timer(100ms, 
        std::bind(&GstReceiverNode::PollBusCb, this)
    );

    RCLCPP_INFO(this->get_logger(), "GStreamer Receiver Node Active (%s pipeline). Dual-timer polling on port %u.",
        bUseTelloPipeline ? "Tello raw-H264" : "PX4/Gazebo RTP", kRxCamPort);
}


GstReceiverNode::~GstReceiverNode() {
    if (m_bus) gst_object_unref(m_bus);
    if (m_sink) gst_object_unref(m_sink);
    if (m_pipeline) {
        gst_element_set_state(m_pipeline, GST_STATE_NULL);
        gst_object_unref(m_pipeline);
    }
    return;
}


void GstReceiverNode::PollSampleCb() {
    GstSample* sample = nullptr;
    GstBuffer* buffer = nullptr;
    GstCaps* caps = nullptr;
    GstVideoInfo info;
    GstMapInfo map;
    sensor_msgs::msg::Image msg;
    guint64 presentTimestamp = 0;

    // Non-blocking attempt to pull frame. Timeout = 0.
    sample = gst_app_sink_try_pull_sample(GST_APP_SINK(m_sink), 0);
    if (!sample) {
        return;
    }

    buffer = gst_sample_get_buffer(sample);
    caps = gst_sample_get_caps(sample);

    if (!gst_video_info_from_caps(&info, caps)) {
        RCLCPP_ERROR(this->get_logger(), "Failed to parse GstCaps");
        gst_sample_unref(sample);
        return;
    }

    if (!gst_buffer_map(buffer, &map, GST_MAP_READ)) {
        RCLCPP_ERROR(this->get_logger(), "Failed to map GstBuffer");
        gst_sample_unref(sample);
        return;
    }

    presentTimestamp = GST_BUFFER_PTS(buffer);
    if (GST_CLOCK_TIME_IS_VALID(presentTimestamp) && presentTimestamp > 0) {
        // Reconstruct the ROS 2 timestamp using the exact simulation math.
        msg.header.stamp.sec = presentTimestamp / 1000000000ULL;
        msg.header.stamp.nanosec = presentTimestamp % 1000000000ULL;
    } else {
        /*  Physical drones fallback: streams raw UDP without embedded timestamps. 
            If PTS is 0/invalid, we must use the current ROS wall-clock.
        */
        msg.header.stamp = this->now();
    }

    msg.header.frame_id = kOutUDPCameraRawFrameID;
    msg.height = info.height;
    msg.width = info.width;
    msg.is_bigendian = false;
    msg.step = info.stride[0];

    switch (GST_VIDEO_INFO_FORMAT(&info)) {
        case GST_VIDEO_FORMAT_BGR:   msg.encoding = "bgr8"; break;
        case GST_VIDEO_FORMAT_RGB:   msg.encoding = "rgb8"; break;
        case GST_VIDEO_FORMAT_GRAY8: msg.encoding = "mono8"; break;
        default:                     msg.encoding = "unknown";
    }

    msg.data.assign(map.data, map.data + map.size);
    m_pubCamFrames->publish(msg);


    gst_buffer_unmap(buffer, &map);
    gst_sample_unref(sample);
    return;
}


void GstReceiverNode::PollBusCb() {
    GstMessage* msg = nullptr;
    GError*     err = nullptr;
    gchar*      debug_info = nullptr;
    GstState    old_state, new_state, pending;
    gint        percent;

    // Use a while loop to drain the bus entirely per call
    while (  (msg = gst_bus_timed_pop_filtered(m_bus, 0, 
        static_cast<GstMessageType>(
            GST_MESSAGE_ERROR 
            | GST_MESSAGE_EOS 
            | GST_MESSAGE_STATE_CHANGED
            | GST_MESSAGE_WARNING 
            | GST_MESSAGE_BUFFERING
        )
        ))
    ) {
        switch (GST_MESSAGE_TYPE(msg)) {
            case GST_MESSAGE_ERROR:
                gst_message_parse_error(msg, &err, &debug_info);
                RCLCPP_ERROR(this->get_logger(), "Error: %s", err->message);
                g_clear_error(&err);
                g_free(debug_info);
                break;
            case GST_MESSAGE_WARNING:
                gst_message_parse_warning(msg, &err, &debug_info);
                RCLCPP_WARN(this->get_logger(), "Warning: %s", err->message);
                g_clear_error(&err);
                g_free(debug_info);
                break;
            case GST_MESSAGE_STATE_CHANGED:
                gst_message_parse_state_changed(msg, &old_state, &new_state, &pending);
                RCLCPP_INFO(this->get_logger(), "State: %s -> %s", 
                    gst_element_state_get_name(old_state), 
                    gst_element_state_get_name(new_state)
                );
                break;
            case GST_MESSAGE_BUFFERING:
                gst_message_parse_buffering(msg, &percent);
                if (percent < 100) {
                    RCLCPP_WARN(this->get_logger(), "Network Buffering: %d%%", percent);
                }
                break;
            case GST_MESSAGE_EOS:
                RCLCPP_INFO(this->get_logger(), "End of stream reached");
                break;
            default:
                break;
        }
        gst_message_unref(msg);
    }


    return;
}




int main(int argc, char** argv) {
    rclcpp::init(argc, argv);

    /* --tello selects the raw-H.264 pipeline for the real drone; absent = the RTP
       pipeline for Gazebo SITL, so the default (no-flag) path is unchanged. This is a
       runtime flag, not a compile-time #if, because gstreamer_rx is one binary shared
       by both backends -- no FMU_BACKEND_* definitions reach this target. */
    bool bUseTelloPipeline = false;
    for (int i = 1; i < argc; ++i) {
        if (std::string(argv[i]) == "--tello") {
            bUseTelloPipeline = true;
        }
    }

    auto node = std::make_shared<GstReceiverNode>(bUseTelloPipeline);
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
