#pragma once
#include "util/base.hpp"
#include "gstreamer_udp_cam_rx/rx_node_base.hpp"
#include <sensor_msgs/msg/image.hpp>
#include <readerwriterqueue.h>


using namespace std::chrono_literals;


class SlowLoopNavigatorNode : public rclcpp::Node {
public:
    SlowLoopNavigatorNode(int argc, char** argv) : Node("high_level_navigation_node") {
        m_subImg = this->create_subscription<UDPCamMsgType>(kOutUDPCameraRawFrameTopic, 10,
            std::bind(&SlowLoopNavigatorNode::imgCallback, this, std::placeholders::_1)
        );

        m_vlmTimer = this->create_wall_timer(kVLMUpdateRate(), 
            std::bind(&SlowLoopNavigatorNode::timerCallback, this)
        );

        // m_imgQueue.
        RCLCPP_INFO(this->get_logger(), "Slow-Navigation Node Active.");
        return;
    }

private:
    constexpr std::chrono::milliseconds kVLMUpdateRate() const {
        return 1000ms / 4;
    }


private:
    /* Update Rate is Camera Topics' */
    void imgCallback(khUDPCamMsgType msg)
    {
        auto cond = m_imgQueue.try_enqueue(msg); 
        if(!cond) {
            (void(0)); /* Placeholder */
        }
        return;
    }

    /* Update Rate is 5Hz */
    void timerCallback()
    {
        khUDPCamMsgType res;
        if(m_imgQueue.try_dequeue(res)) {

        }
        return;
    }


private:
    using spsc_queue = moodycamel::ReaderWriterQueue<khUDPCamMsgType, sizeof(khUDPCamMsgType)>;
    SubscriberPtr<UDPCamMsgType> m_subImg;
    TimerSharedPtr               m_vlmTimer;
    spsc_queue                   m_imgQueue;
    
};