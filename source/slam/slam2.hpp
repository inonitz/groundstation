#pragma once
#include <cstdlib>
#include <thread>
#include <atomic>
#include <memory>
#include <string>

// Stella VSLAM Core
#include <stella_vslam/system.h>
#include <stella_vslam/config.h>
#include <stella_vslam/data/landmark.h>
#include <stella_vslam/publish/map_publisher.h>

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/msg/point_field.hpp>
#include <sensor_msgs/point_cloud2_iterator.hpp>

#include <opencv2/core.hpp>
#include <opencv2/core/eigen.hpp>
#include <Eigen/Geometry>
#include <cv_bridge/cv_bridge.hpp>

#include "readerwriterqueue.h"


constexpr const char* kCameraImageTopic = "camera/stream";
constexpr const char* kSlamPoseTopic    = "slam/pose";
constexpr const char* kSlamActivePointCloudTopic = "slam/active_cloud_pts";
constexpr const char* kSlamLocalPointCloudTopic  = "slam/local_cloud_pts";


static std::string env_or_default(const char* name, const char* fallback) {
    const char* value = std::getenv(name);
    return (value != nullptr && value[0] != '\0') ? std::string{value} : std::string{fallback};
}


class SLAMNode : public rclcpp::Node {
private:
    using ImageType         = sensor_msgs::msg::Image;
    using ImageFrameType    = ImageType::ConstSharedPtr;
    using PoseType          = geometry_msgs::msg::PoseStamped;
    using PoseFrameType     = PoseType::ConstSharedPtr;
    using PointCloudType    = sensor_msgs::msg::PointCloud2;
    using PointCloudPtrType = PointCloudType::ConstSharedPtr;

    using SLAMLandmarkPtrType = std::shared_ptr<stella_vslam::data::landmark>;


    template<typename T>
    using SubscriptionPtr = typename rclcpp::Subscription<T>::SharedPtr;

    template<typename T>
    using PublisherPtr = typename rclcpp::Publisher<T>::SharedPtr;

    template<typename T>
    using SPSC_Queue = moodycamel::ReaderWriterQueue<T>;

public:
    SLAMNode() : Node("stella_vslam_node") 
    {
        // Stella VSLAM requires a YAML config and a pre-trained ORB vocabulary.
        // Paths default to the primary checkout, but STELLA_CONFIG_PATH /
        // STELLA_VOCAB_PATH override them so a worktree or a relocated
        // checkout does not silently load the wrong config.
        const std::string kConfigPath = env_or_default("STELLA_CONFIG_PATH", "/root/groundstation/dependencies/stella_config.yaml");
        const std::string kVocabPath  = env_or_default("STELLA_VOCAB_PATH",  "/root/groundstation/dependencies/orb_vocab.fbow");
        RCLCPP_INFO(this->get_logger(), "stella config=%s vocab=%s", kConfigPath.c_str(), kVocabPath.c_str());

        /* Init Subscription */
        m_subImg = this->create_subscription<ImageType>(
            kCameraImageTopic, 60,
            std::bind(&SLAMNode::imageCallback, this, std::placeholders::_1)
        );
        m_pubPose = this->create_publisher<PoseType>(
            kSlamPoseTopic, 10
        );
        m_pubActivePoints = this->create_publisher<PointCloudType>(
            kSlamActivePointCloudTopic, 10
        );
        m_pubLocalPoints = this->create_publisher<PointCloudType>(
            kSlamLocalPointCloudTopic, 10
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
            if(m_imgData.try_dequeue(pendingImg) == false) {
                std::this_thread::sleep_for(std::chrono::milliseconds(20));
                continue;
            }

            timestamp = pendingImg->header.stamp.sec;
            timestamp += 1e-9 * static_cast<double>(pendingImg->header.stamp.nanosec);
            try {
                auto cv_ptr = cv_bridge::toCvShare(pendingImg, sensor_msgs::image_encodings::BGR8);
                m_slamSystem->feed_monocular_frame(cv_ptr->image, timestamp, cv::Mat{});
                publish_rviz_pose();
                publish_global_point_cloud();

            } catch (const cv_bridge::Exception& e) {
                RCLCPP_ERROR(this->get_logger(), "cv_bridge conversion exception: %s", e.what());
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


    void publish_global_point_cloud()
    {
        PointCloudType pcl_global;
        PointCloudType pcl_local;
        sensor_msgs::PointCloud2Modifier mod_gbl(pcl_global);
        sensor_msgs::PointCloud2Modifier mod_lcl(pcl_local);
        std::set<SLAMLandmarkPtrType> tmp_local_cloud;
        std::vector<uint32_t> activeIndicesGlobal;
        std::vector<uint32_t> activeIndicesLocal;


        m_slamSystem->get_map_publisher()->get_landmarks(
            m_globalCloud,
            tmp_local_cloud
        );
        m_localCloud.assign(tmp_local_cloud.begin(), tmp_local_cloud.end());


        activeIndicesGlobal.reserve(m_globalCloud.size());
        for(uint32_t i = 0; i < m_globalCloud.size(); ++i) {
            if(m_globalCloud[i] == nullptr) {
                continue;
            }
            if(m_globalCloud[i]->will_be_erased()) {
                continue;
            }
            activeIndicesGlobal.push_back(i);
        }
        
        activeIndicesLocal.reserve(m_localCloud.size());
        for(uint32_t i = 0; i < m_localCloud.size(); ++i) {
            if(m_localCloud[i] == nullptr) {
                continue;
            }
            if(m_localCloud[i]->will_be_erased()) {
                continue;
            }
            activeIndicesLocal.push_back(i);
        }


        mod_gbl.setPointCloud2Fields(
            3,
            "x", 1, sensor_msgs::msg::PointField::FLOAT32,
            "y", 1, sensor_msgs::msg::PointField::FLOAT32,
            "z", 1, sensor_msgs::msg::PointField::FLOAT32
        );
        mod_gbl.resize(activeIndicesGlobal.size());
        pcl_global.header          = std_msgs::msg::Header{};
        pcl_global.header.stamp    = this->now();
        pcl_global.header.frame_id = "map";
        pcl_global.height          = 1;
        pcl_global.width           = activeIndicesGlobal.size();
        pcl_global.is_dense        = true;
        
        sensor_msgs::PointCloud2Iterator<float> iterX_gbl(pcl_global, "x");
        sensor_msgs::PointCloud2Iterator<float> iterY_gbl(pcl_global, "y");
        sensor_msgs::PointCloud2Iterator<float> iterZ_gbl(pcl_global, "z");
        for(auto& idx : activeIndicesGlobal) {
            const auto& pos = m_globalCloud[idx]->get_pos_in_world();
            *iterX_gbl = static_cast<float>(pos.x());
            *iterY_gbl = static_cast<float>(pos.y());
            *iterZ_gbl = static_cast<float>(pos.z());
            ++iterX_gbl;
            ++iterY_gbl;
            ++iterZ_gbl;
        }
        
        
        mod_lcl.setPointCloud2Fields(
            3,
            "x", 1, sensor_msgs::msg::PointField::FLOAT32,
            "y", 1, sensor_msgs::msg::PointField::FLOAT32,
            "z", 1, sensor_msgs::msg::PointField::FLOAT32
        );
        mod_lcl.resize(activeIndicesLocal.size());
        pcl_local.header          = std_msgs::msg::Header{};
        pcl_local.header.stamp    = this->now();
        pcl_local.header.frame_id = "map";
        pcl_local.height          = 1;
        pcl_local.width           = activeIndicesLocal.size();
        pcl_local.is_dense        = true;
        
        sensor_msgs::PointCloud2Iterator<float> iterX_lcl(pcl_local, "x");
        sensor_msgs::PointCloud2Iterator<float> iterY_lcl(pcl_local, "y");
        sensor_msgs::PointCloud2Iterator<float> iterZ_lcl(pcl_local, "z");
        for(auto& idx : activeIndicesLocal) {
            const auto& pos = m_localCloud[idx]->get_pos_in_world();
            *iterX_lcl = static_cast<float>(pos.x());
            *iterY_lcl = static_cast<float>(pos.y());
            *iterZ_lcl = static_cast<float>(pos.z());
            ++iterX_lcl;
            ++iterY_lcl;
            ++iterZ_lcl;
        }


        m_pubActivePoints->publish(pcl_global);
        m_pubLocalPoints->publish(pcl_local);
        return;
    }

private:
    SubscriptionPtr<ImageType>             m_subImg;
    SPSC_Queue<ImageFrameType>             m_imgData{60};
    PublisherPtr<PoseType>                 m_pubPose;
    PublisherPtr<PointCloudType>           m_pubActivePoints;
    PublisherPtr<PointCloudType>           m_pubLocalPoints;

    std::thread                            m_slamThread;
    std::atomic<bool>                      m_exitSlam{false};    
    std::shared_ptr<stella_vslam::system>  m_slamSystem;
    std::vector<SLAMLandmarkPtrType>       m_globalCloud;
    std::vector<SLAMLandmarkPtrType>       m_localCloud;
};