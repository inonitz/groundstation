#include "rx_node.hpp"
#include "gstreamer_gz_udp_tx/gazebo_cam_plugin_base.hpp"  /* kSitlUdpCamPort (sim camera transport). */
#include "tello_backend/tello_backend_base.hpp"           /* kTelloVideoPort (Tello's own source of truth). */
#include "dji_backend/dji_backend_base.hpp"               /* kDjiVideoPort (VideoTcpServer stream port).    */
#include <gst/app/gstappsink.h>
#include <gst/video/video.h>


using namespace std::chrono_literals;


GstReceiverNode::GstReceiverNode(BackendType backend, std::string djiHost) : Node("gst_receiver_node") {
    gst_init(nullptr, nullptr);

    m_pubCamFrames = this->create_publisher<CameraPipelineMsgType>(kOutCameraPipelineRawFrameTopic, 10);

    /* 
        max-buffers=1 & drop=true: 
            Creates a size-1 circular queue. 
            Drops stale frames if Receiving is slow.
        sync=false: 
            Disables GStreamer's internal wall-clock pacing. 
            Forces frames to pass through instantly regardless of their timestamp.
    */ 
    /* Only the SOURCE+DECODE prefix depends on the backend; the raw-video tail, the
       appsink pull, and the bus poll are identical for all three. So we pick the
       prefix ONCE here and share everything downstream -- no per-frame branch, no
       duplicated node. (Runtime switch, not a template: gstreamer_rx is one binary
       shared by every backend, the prefix is chosen at init, and gst_parse_launch
       builds the graph from a string anyway -- so a compile-time specialisation
       would remove a single init switch for no runtime gain.)
         TELLO : raw H.264 over UDP (no RTP), parse -> decode. Fixed at kTelloVideoPort.
         PX4/gz: RTP-framed H.264 over UDP, depayload -> decode. kSitlUdpCamPort.
         DJI   : raw H.264/H.265 over TCP from the phone app (VideoTcpServer, which
                 LISTENS on kDjiVideoPort); we connect in. decodebin auto-selects
                 H.264 vs H.265, so the one node handles either without being told. */
    std::string kDecodeStage;
    const char* kLabel = "PX4/Gazebo RTP/UDP";
    switch (backend) {
        case BackendType::TELLO:
            kDecodeStage = "udpsrc port=" + std::to_string(kTelloVideoPort) +
                           " ! h264parse ! avdec_h264 ! ";
            kLabel = "Tello raw-H264/UDP";
            break;
        case BackendType::DJI:
            kDecodeStage = "tcpclientsrc host=" + djiHost + " port=" + std::to_string(kDjiVideoPort) +
                           " ! h264parse ! avdec_h264 max-threads=1 output-corrupt=false ! ";  /* explicit H.264 low-latency: no decodebin queue, no frame-threading delay */
            kLabel = "DJI H264/TCP (low-latency)";
            break;
        case BackendType::PX4:
            kDecodeStage = "udpsrc port=" + std::to_string(kSitlUdpCamPort) +
                           " caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=H264\" ! "
                           "rtph264depay ! avdec_h264 ! ";
            break;
    }
    const std::string kRxPipelineStr = kDecodeStage +
        "videoconvert ! video/x-raw, format=BGR ! "
        "appsink name=" + kOutCameraPipelineGstSinkName + " max-buffers=1 drop=true sync=false";

    m_pipeline = gst_parse_launch(kRxPipelineStr.c_str(), nullptr);
    m_sink     = gst_bin_get_by_name(GST_BIN(m_pipeline), kOutCameraPipelineGstSinkName);
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

    RCLCPP_INFO(this->get_logger(), "GStreamer Receiver Node Active (%s pipeline).", kLabel);
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

    msg.header.frame_id = kOutCameraPipelineRawFrameID;
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

    /* Backend selects the pipeline source at RUNTIME (gstreamer_rx is one binary
       shared by every backend; no FMU_BACKEND_* reaches this target). Default is
       PX4/Gazebo so the no-flag SITL path is unchanged.
         --tello        real Tello (raw H.264 / UDP)
         --dji [host]   DJI phone-app video (TCP); host defaults to the mock 127.0.0.1 */
    BackendType  backend = BackendType::PX4;
    std::string djiHost = "127.0.0.1";
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--tello") {
            backend = BackendType::TELLO;
        } else if (arg == "--dji") {
            backend = BackendType::DJI;
            if (i + 1 < argc && argv[i + 1][0] != '-') djiHost = argv[++i];   /* optional host */
        }
    }

    auto node = std::make_shared<GstReceiverNode>(backend, djiHost);
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
