#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <gst/gst.h>
#include <gst/video/video.h> 
#include <gst/app/gstappsink.h>
#include <chrono>


class GstReceiverNode : public rclcpp::Node {
public:
    GstReceiverNode() : Node("gst_receiver_node") {
        // Initialize GStreamer core
        gst_init(nullptr, nullptr);

        m_publisher = this->create_publisher<sensor_msgs::msg::Image>("camera/stream", 10);

        // Low-latency receiving pipeline matching the Gazebo source configuration
        std::string pipeline_str = 
            "udpsrc port=11111 caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=H264\" ! "
            "rtph264depay ! "
            "avdec_h264 ! "
            "videoconvert ! "
            "video/x-raw, format=BGR ! "
            "appsink name=mysink emit-signals=true max-buffers=1 drop=true";

        m_pipeline = gst_parse_launch(pipeline_str.c_str(), nullptr);
        GstElement* sink = gst_bin_get_by_name(GST_BIN(m_pipeline), "mysink");

        // Connect the new-sample signal to our callback processing layer
        g_signal_connect(sink, "new-sample", G_CALLBACK(OnNewSampleThunk), this);
        gst_object_unref(sink);

        // Transition pipeline to execution state
        gst_element_set_state(m_pipeline, GST_STATE_PLAYING);
        RCLCPP_INFO(this->get_logger(), "GStreamer Receiver Node Active. Listening on port 11111...");
        return;
    }

    ~GstReceiverNode() override {
        if (m_pipeline) {
            gst_element_set_state(m_pipeline, GST_STATE_NULL);
            gst_object_unref(m_pipeline);
        }
        return;
    }


private:
    static GstFlowReturn OnNewSampleThunk(GstAppSink* sink, gpointer user_data) {
        return static_cast<GstReceiverNode*>(user_data)->OnNewSample(sink);
    }

    GstFlowReturn OnNewSample(GstAppSink* sink) {
        GstSample*   sample = nullptr;
        GstBuffer*   buffer = nullptr;
        GstCaps*     caps   = nullptr;
        GstVideoInfo info;
        GstMapInfo   map;
        sensor_msgs::msg::Image msg;

        sample = gst_app_sink_pull_sample(sink);
        if (!sample) {
            return GST_FLOW_OK;
        }

        buffer = gst_sample_get_buffer(sample);
        caps   = gst_sample_get_caps(sample);
        if (!gst_video_info_from_caps(&info, caps)) {
            RCLCPP_ERROR(this->get_logger(), "Failed to parse GstCaps");
            gst_sample_unref(sample);
            return GST_FLOW_ERROR;
        }

        if (!gst_buffer_map(buffer, &map, GST_MAP_READ)) {
            RCLCPP_ERROR(this->get_logger(), "Failed to map GstBuffer");
            gst_sample_unref(sample);
            return GST_FLOW_ERROR;
        }

        /* Populate the message with all data gathered */
        msg.header.stamp    = this->now();
        msg.header.frame_id = "camera_link";
        msg.height          = info.height;
        msg.width           = info.width;
        msg.is_bigendian    = false;
        msg.step            = info.stride[0];
        switch (GST_VIDEO_INFO_FORMAT(&info)) {
            case GST_VIDEO_FORMAT_BGR:
            msg.encoding = "bgr8";
            break;
            case GST_VIDEO_FORMAT_RGB:
            msg.encoding = "rgb8";
            break;
            case GST_VIDEO_FORMAT_GRAY8:
            msg.encoding = "mono8";
            break;
            default:
            msg.encoding = "unknown";
            RCLCPP_WARN(this->get_logger(), "Unknown format mapped.");
            break;
        }


        msg.data.assign(map.data, map.data + map.size);
        m_publisher->publish(msg);

        gst_buffer_unmap(buffer, &map);
        gst_sample_unref(sample);
        return GST_FLOW_OK;
    }


private:
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr m_publisher;
    GstElement* m_pipeline = nullptr;
};

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    auto node = std::make_shared<GstReceiverNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}