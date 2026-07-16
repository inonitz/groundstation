#pragma once
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include "spsc_bounded_queue.hpp"
#include "readerwriterqueue.h"
#include <chrono>


using namespace std::chrono_literals;


class SlowLoopNavigatorNode : public rclcpp::Node {
public:
    SlowLoopNavigatorNode(int argc, char** argv) : Node("high_level_navigation_node") {
        m_subImg = this->create_subscription<sensor_msgs::msg::Image>(kCameraTopic(), 10,
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
    using imgMsgBase = sensor_msgs::msg::Image;
    using imgMsgPtr  = sensor_msgs::msg::Image::SharedPtr;
    using kImgMsgPtr = sensor_msgs::msg::Image::ConstSharedPtr;


    constexpr const char*               kCameraTopic()   const { return "camera/stream"; }
    constexpr std::chrono::milliseconds kVLMUpdateRate() const {
        return 1000ms / 4;
    }


private:
    /* Update Rate is Camera Topics' */
    void imgCallback(kImgMsgPtr msg)
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
        kImgMsgPtr res;
        if(m_imgQueue.try_dequeue(res)) {

        }
        return;
    }


private:
    using spsc_queue = moodycamel::ReaderWriterQueue<kImgMsgPtr, sizeof(kImgMsgPtr)>;
    rclcpp::Subscription<imgMsgBase>::SharedPtr m_subImg;
    rclcpp::TimerBase::SharedPtr                m_vlmTimer;
    spsc_queue                                  m_imgQueue;
    
};