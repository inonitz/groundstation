#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <gst/gst.h>
#include <gst/video/video.h> 
#include <gst/app/gstappsink.h>
#include <chrono>


using namespace std::chrono_literals;


class GstReceiverNode : public rclcpp::Node {
public:
    GstReceiverNode() : Node("gst_receiver_node") {
        gst_init(nullptr, nullptr);

        m_publisher = this->create_publisher<sensor_msgs::msg::Image>(cameraTopic(), 10);

        /* 
            max-buffers=1 & drop=true: 
                Creates a size-1 circular queue. 
                Drops stale frames if Receiving is slow.
            sync=false: 
                Disables GStreamer's internal wall-clock pacing. 
                Forces frames to pass through instantly regardless of their timestamp.
        */ 
        std::string pipeline_str = 
            "udpsrc port=11111 caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=H264\" ! "
            "rtph264depay ! avdec_h264 ! videoconvert ! video/x-raw, format=BGR ! "
            "appsink name=mysink max-buffers=1 drop=true sync=false";

        m_pipeline = gst_parse_launch(pipeline_str.c_str(), nullptr);
        m_sink     = gst_bin_get_by_name(GST_BIN(m_pipeline), "mysink");
        m_bus      = gst_element_get_bus(m_pipeline);
        gst_element_set_state(m_pipeline, GST_STATE_PLAYING);

        // Timer 1: Poll appsink directly on ROS 2 thread (100 Hz)
        m_pull_timer = this->create_wall_timer(10ms, 
            std::bind(&GstReceiverNode::PollSampleCb, this)
        );

        // Timer 2: Poll GStreamer bus for fatal disconnects (10 Hz)
        m_bus_timer = this->create_wall_timer(100ms, 
            std::bind(&GstReceiverNode::PollBusCb, this)
        );

        RCLCPP_INFO(this->get_logger(), "GStreamer Receiver Node Active. Dual-timer polling on port 11111.");
    }

    ~GstReceiverNode() override {
        if (m_bus) gst_object_unref(m_bus);
        if (m_sink) gst_object_unref(m_sink);
        if (m_pipeline) {
            gst_element_set_state(m_pipeline, GST_STATE_NULL);
            gst_object_unref(m_pipeline);
        }
        return;
    }

private:
    void PollSampleCb() {
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

        msg.header.frame_id = frameId();
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
        m_publisher->publish(msg);


        gst_buffer_unmap(buffer, &map);
        gst_sample_unref(sample);
        return;
    }


    void PollBusCb() {
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

private:
    constexpr const char* frameId()     { return "camera_link"; }
    constexpr const char* cameraTopic() { return "camera/stream"; }

private:
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr m_publisher;
    rclcpp::TimerBase::SharedPtr                          m_pull_timer;
    rclcpp::TimerBase::SharedPtr                          m_bus_timer;
    GstElement* m_pipeline = nullptr;
    GstElement* m_sink = nullptr;
    GstBus*     m_bus = nullptr;
};


int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    auto node = std::make_shared<GstReceiverNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}