#pragma once
#include <thread>
#include <atomic>
#include <memory>
#include <string>

// Stella VSLAM Core
#include <stella_vslam/system.h>
#include <stella_vslam/config.h>
#include <stella_vslam/publish/map_publisher.h>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>

#include <opencv2/core.hpp>
#include <opencv2/core/eigen.hpp>
#include <Eigen/Geometry>
#include <cv_bridge/cv_bridge.hpp>

#include "readerwriterqueue.h"


constexpr const char* kCameraImageTopic = "camera/stream";
constexpr const char* kSlamPoseTopic    = "slam/pose";


class SLAMNode : public rclcpp::Node {
private:
    using ImageType      = sensor_msgs::msg::Image;
    using ImageFrameType = ImageType::ConstSharedPtr;
    using PoseType       = geometry_msgs::msg::PoseStamped;
    using PoseFrameType  = PoseType::ConstSharedPtr;

    template<typename T>
    using SubscriptionPtr = typename rclcpp::Subscription<T>::SharedPtr;

    template<typename T>
    using PublisherPtr = typename rclcpp::Publisher<T>::SharedPtr;

    template<typename T>
    using SPSC_Queue = moodycamel::ReaderWriterQueue<T>;

public:
    SLAMNode() : Node("stella_vslam_node") 
    {
        // Stella VSLAM requires a YAML config and a pre-trained ORB vocabulary
        constexpr const char* kConfigPath = "/root/groundstation/dependencies/stella_config.yaml";
        constexpr const char* kVocabPath  = "/root/groundstation/dependencies/orb_vocab.fbow";

        /* Init Subscription */
        m_subImg = this->create_subscription<ImageType>(
            kCameraImageTopic, 60,
            std::bind(&SLAMNode::imageCallback, this, std::placeholders::_1)
        );
        m_pubPose = this->create_publisher<PoseType>(
            kSlamPoseTopic, 10
        );

        /* Init Stella VSLAM System */
        auto cfg = std::make_shared<stella_vslam::config>(kConfigPath);
        m_slamSystem = std::make_shared<stella_vslam::system>(cfg, kVocabPath);
        
        m_slamSystem->startup();

        m_slamThread = std::thread(&SLAMNode::slamWorkerThread, this);
        RCLCPP_INFO(this->get_logger(), "Stella VSLAM Node Active. CPU Tracking initialized.");
    }

    ~SLAMNode() {
        m_exitSlam = true;
        if (m_slamThread.joinable()) {
            m_slamThread.join();
        }
        if (m_slamSystem) {
            m_slamSystem->shutdown();
        }
    }


private:
    void imageCallback(const ImageFrameType& msg) {
        ImageFrameType trash;
        while (!m_imgData.try_enqueue(msg)) {
            m_imgData.try_dequeue(trash); 
            RCLCPP_WARN(this->get_logger(), "Queue Full. Dropping OLDEST frame.");
        }
    }

    void slamWorkerThread() {
        ImageFrameType pendingImg;
        double timestamp = 0;

        while (rclcpp::ok() && !m_exitSlam.load()) {
            if (m_imgData.try_dequeue(pendingImg)) {
                
                timestamp = pendingImg->header.stamp.sec;
                timestamp += 1e-9 * static_cast<double>(pendingImg->header.stamp.nanosec);

                // 2. Convert ROS Image to OpenCV Mat
                auto cv_ptr = cv_bridge::toCvShare(pendingImg, sensor_msgs::image_encodings::MONO8);

                // 3. Feed directly to CPU Tracker (No IMU needed)
                // Third argument is an empty mask
                m_slamSystem->feed_monocular_frame(cv_ptr->image, timestamp, cv::Mat{});
                publish_rviz_pose();
            } else {
                std::this_thread::sleep_for(std::chrono::milliseconds(20));
            }
        }
    }


    void publish_rviz_pose() {
        stella_vslam::Mat44_t  cam_pose_cw;
        Eigen::Matrix3d        R_cw;
        Eigen::Vector3d        t_cw;
        Eigen::Matrix3d        R_wc;
        Eigen::Vector3d        t_wc;
        Eigen::Quaterniond     q;
        PoseType               msg;

        cam_pose_cw = m_slamSystem->get_map_publisher()->get_current_cam_pose();
        if (m_slamSystem->tracker_is_paused()) {
            return;
        }

        R_cw = cam_pose_cw.block<3, 3>(0, 0);
        t_cw = cam_pose_cw.block<3, 1>(0, 3);
        R_wc = R_cw.transpose();
        t_wc = -R_wc * t_cw;
        q = Eigen::Quaterniond(R_wc);

        msg.header.stamp       = this->now();
        msg.header.frame_id    = "map"; 
        msg.pose.position.x    = t_wc.x();
        msg.pose.position.y    = t_wc.y();
        msg.pose.position.z    = t_wc.z();
        msg.pose.orientation.x = q.x();
        msg.pose.orientation.y = q.y();
        msg.pose.orientation.z = q.z();
        msg.pose.orientation.w = q.w();
        m_pubPose->publish(msg);
        return;
    }

private:
    SubscriptionPtr<ImageType>             m_subImg;
    SPSC_Queue<ImageFrameType>             m_imgData{60};
    PublisherPtr<PoseType>                 m_pubPose;
    std::thread                            m_slamThread;
    std::atomic<bool>                      m_exitSlam{false};    
    std::shared_ptr<stella_vslam::system>  m_slamSystem;
};