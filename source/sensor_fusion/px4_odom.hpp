#pragma once
#include <thread>
#include <atomic>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <px4_msgs/msg/vehicle_odometry.hpp>
#include <message_filters/subscriber.h>
#include <message_filters/synchronizer.h>
#include <message_filters/pass_through.h>
#include <message_filters/sync_policies/approximate_time.h>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include "readerwriterqueue.h"


constexpr const char* kCameraImageTopic   = "camera/stream";
constexpr const char* kRawOdometryTopic   = "/fmu/out/vehicle_odometry";
constexpr const char* kOutPointCloudTopic = "/slam/point_cloud";

struct SyncedFrame {
    sensor_msgs::msg::Image::ConstSharedPtr img;
    nav_msgs::msg::Odometry::ConstSharedPtr odom;
};


class SyncNode : public rclcpp::Node {
private:
    using ImageType       = sensor_msgs::msg::Image;
    using OdometryType    = nav_msgs::msg::Odometry;
    using RawOdometryType = px4_msgs::msg::VehicleOdometry;
    using PointCloudType = sensor_msgs::msg::PointCloud2;

    template<typename T>
    using MessageFilterSubscription = typename message_filters::Subscriber<T>;

    template<typename T>
    using MimickSubscriptionType = typename message_filters::PassThrough<T>;

    template<typename T>
    using SubscriptionPtr = typename rclcpp::Subscription<T>::SharedPtr;
    
    template<typename T>
    using PublisherPtr = typename rclcpp::Publisher<T>::SharedPtr;

    using SyncPolicyType = message_filters::sync_policies::ApproximateTime<
        sensor_msgs::msg::Image, nav_msgs::msg::Odometry>;

    using SyncType = message_filters::Synchronizer<SyncPolicyType>;

    using SPSC_FrameQueue = moodycamel::ReaderWriterQueue<SyncedFrame>;

public:
    SyncNode() : Node("sync_node") {
        rmw_qos_profile_t qos_profile = rmw_qos_profile_default;
        qos_profile.depth = 10;

        m_subImg.subscribe(this, kCameraImageTopic, qos_profile);
        m_subRawOdometry = this->create_subscription<RawOdometryType>(
            kRawOdometryTopic, rclcpp::SensorDataQoS(),
            std::bind(&SyncNode::rawOdomCallback, this, std::placeholders::_1)
        );
        m_pubPointCloud = this->create_publisher<PointCloudType>(kOutPointCloudTopic, 10);


        m_sync = std::make_shared<SyncType>(
            SyncPolicyType(10), 
            m_subImg, 
            m_subPassOdometry
        );
        m_sync->registerCallback(
            std::bind(&SyncNode::syncCallback, this, std::placeholders::_1, std::placeholders::_2)
        );


        m_slamThread = std::thread(&SyncNode::slamWorkerThread, this);
        RCLCPP_INFO(this->get_logger(), "ApproximateTime Synchronizer Active.");
        return;
    }

    ~SyncNode() {
        m_exitSlam = true;
        if (m_slamThread.joinable()) {
            m_slamThread.join();
        }
        return;
    }

private:
    void rawOdomCallback(const RawOdometryType::ConstSharedPtr& msg) {
        OdometryType ros_odom;
        
        uint64_t time_us = msg->timestamp;
        ros_odom.header.stamp.sec     = time_us / 1000000;
        ros_odom.header.stamp.nanosec = (time_us % 1000000) * 1000;
        ros_odom.header.frame_id      = "odom";
        ros_odom.child_frame_id       = "base_link";

        // NED to ENU coordinate frame transform
        ros_odom.pose.pose.position.x = msg->position[1];  // East
        ros_odom.pose.pose.position.y = msg->position[0];  // North
        ros_odom.pose.pose.position.z = -msg->position[2]; // Up

        // Hamilton Quaternion conversion
        ros_odom.pose.pose.orientation.w = msg->q[0];
        ros_odom.pose.pose.orientation.x = msg->q[1];
        ros_odom.pose.pose.orientation.y = -msg->q[2];
        ros_odom.pose.pose.orientation.z = -msg->q[3];

        // Linear velocity transform
        ros_odom.twist.twist.linear.x = msg->velocity[1];
        ros_odom.twist.twist.linear.y = msg->velocity[0];
        ros_odom.twist.twist.linear.z = -msg->velocity[2];

        // Angular velocities transform
        ros_odom.twist.twist.angular.x = msg->angular_velocity[0];
        ros_odom.twist.twist.angular.y = -msg->angular_velocity[1];
        ros_odom.twist.twist.angular.z = -msg->angular_velocity[2];

        auto ros_odom_ptr = std::make_shared<OdometryType>(ros_odom);
        m_subPassOdometry.add(ros_odom_ptr);
        return;
    }

    void syncCallback(
        const ImageType::ConstSharedPtr&    img_msg, 
        const OdometryType::ConstSharedPtr& odom_msg
    ) {
        RCLCPP_INFO(this->get_logger(), "Synced! Image: %d.%d | Odom: %d.%d", 
            img_msg->header.stamp.sec, img_msg->header.stamp.nanosec,
            odom_msg->header.stamp.sec, odom_msg->header.stamp.nanosec
        );

        // Inside syncCallback, replace the enqueue logic with this:
        SyncedFrame frame{img_msg, odom_msg};
        SyncedFrame trash;
        
        /* 
            I hate the fact that I have to push out elements to make way for new ones,
            But considering that I need to keep atomicity, I'm going to settle for this (for now).
            If I find a more optimal way to handle this, other than a fucking while-loop, I will.
        */
        while (!m_slamQueue.try_enqueue(frame)) {
            m_slamQueue.try_dequeue(trash); 
            RCLCPP_WARN(this->get_logger(), "Queue Full. Dropping OLDEST frame");
        }
        return;
    }


    void slamWorkerThread() {
        SyncedFrame frame;
        while (rclcpp::ok() && !m_exitSlam.load()) {
            if (m_slamQueue.try_dequeue(frame)) {
                RCLCPP_INFO(this->get_logger(), "[SLAM BLACK BOX] Processing Frame %d | Odom %d", 
                    frame.img->header.stamp.sec, frame.odom->header.stamp.sec);

                PointCloudType mock_pc;
                mock_pc.header.stamp = frame.img->header.stamp;
                mock_pc.header.frame_id = "map";
                m_pubPointCloud->publish(mock_pc);
            } else {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
        }
        return;
    }


private:
    MessageFilterSubscription<ImageType> m_subImg;
    MimickSubscriptionType<OdometryType> m_subPassOdometry;
    SubscriptionPtr<RawOdometryType>     m_subRawOdometry;
    PublisherPtr<PointCloudType>         m_pubPointCloud;
    std::shared_ptr<SyncType>            m_sync;
    SPSC_FrameQueue                      m_slamQueue{60};
    std::thread                          m_slamThread;
    std::atomic<bool>                    m_exitSlam{false};
};