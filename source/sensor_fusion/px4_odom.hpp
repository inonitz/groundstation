#pragma once
#include <thread>
#include <atomic>
#include <open_vins/core/VioManager.h>
#include <open_vins/state/State.h>

#include <px4_msgs/msg/sensor_combined.hpp>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/point_cloud2_iterator.hpp>

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <cv_bridge/cv_bridge.hpp>

#include "readerwriterqueue.h"


constexpr const char* kCameraImageTopic    = "camera/stream";
constexpr const char* kSensorCombinedTopic = "/fmu/out/sensor_combined";
constexpr const char* kOutPointCloudPersistentTopic = "/slam/point_cloud/persistent";
constexpr const char* kOutPointCloudTransientTopic  = "/slam/point_cloud/transient";


class SLAMNode : public rclcpp::Node {
private:
    using ImageType          = sensor_msgs::msg::Image;
    using SensorCombinedType = px4_msgs::msg::SensorCombined;
    using ImageFrameType = ImageType::ConstSharedPtr;
    using IMUFrameType   = SensorCombinedType::ConstSharedPtr;
    using PointCloudType = sensor_msgs::msg::PointCloud2;

    template<typename T>
    using SubscriptionPtr = typename rclcpp::Subscription<T>::SharedPtr;
    
    template<typename T>
    using PublisherPtr = typename rclcpp::Publisher<T>::SharedPtr;

    template<typename T>
    using SPSC_Queue = moodycamel::ReaderWriterQueue<T>;

public:
    SLAMNode() : Node("slam_openvins_node") 
    {
        ov_msckf::VioManagerOptions options{};

        /* Init Subscriptions & Point-Cloud Publisher */
        m_subImuCombined = this->create_subscription<SensorCombinedType>(
            kSensorCombinedTopic, 400,
            std::bind(&SLAMNode::imuCallback, this, std::placeholders::_1)
        );
        m_subImg = this->create_subscription<ImageType>(
            kCameraImageTopic, 60,
            std::bind(&SLAMNode::imageCallback, this, std::placeholders::_1)
        );
        m_pubSlamPointCloud = this->create_publisher<PointCloudType>(kOutPointCloudPersistentTopic, 10);
        m_pubMsckfPointCloud = this->create_publisher<PointCloudType>(kOutPointCloudTransientTopic, 10);

        /* Init OpenVINS */
        options.print_and_load_estimator();
        m_vioManager = std::make_unique<ov_msckf::VioManager>(options);


        m_slamThread = std::thread(&SLAMNode::slamWorkerThread, this);
        RCLCPP_INFO(this->get_logger(), "OpenVINS SLAM Node Active.");
        return;
    }

    ~SLAMNode() {
        m_exitSlam = true;
        if (m_slamThread.joinable()) {
            m_slamThread.join();
        }
        return;
    }

private:
    void imuCallback(const IMUFrameType& msg) {
        IMUFrameType trash;
        while (!m_imuData.try_enqueue(msg)) {
            m_imuData.try_dequeue(trash); 
            RCLCPP_WARN(this->get_logger(), "Queue Full. Dropping OLDEST frame.");
        }
        return;
    }

    void imageCallback(const ImageFrameType& msg) {
        ImageFrameType trash;

        while (!m_imgData.try_enqueue(msg)) {
            m_imgData.try_dequeue(trash); 
            RCLCPP_WARN(this->get_logger(), "Queue Full. Dropping OLDEST frame.");
        }
        return;
    }


    void slamWorkerThread() {
        const auto k_convert_between_imu_types = [](
            const IMUFrameType& imuFrame, 
            ov_core::ImuData&   outFrame
        ) -> void {
            outFrame.timestamp = imuFrame->timestamp;
            outFrame.timestamp *= 1e-6;
            
            // Accelerometer
            outFrame.am = Eigen::Matrix<double, 3, 1>{
                imuFrame->accelerometer_m_s2[0],
                imuFrame->accelerometer_m_s2[1],
                imuFrame->accelerometer_m_s2[2]
            };

            // Gyroscope
            outFrame.wm = Eigen::Matrix<double, 3, 1>{
                imuFrame->gyro_rad[0],
                imuFrame->gyro_rad[1],
                imuFrame->gyro_rad[2]
            };
            return;
        };

        const auto k_convert_between_image_types = [](
            const ImageFrameType& imgFrame, 
            ov_core::CameraData&  outFrame
        ) -> void {
                outFrame.timestamp = imgFrame->header.stamp.sec;
                outFrame.timestamp += 1e-9 * static_cast<double>(
                    imgFrame->header.stamp.nanosec
                );
                outFrame.sensor_ids.push_back(0); // ID 0 for single camera

                auto cv_ptr = cv_bridge::toCvShare(imgFrame, sensor_msgs::image_encodings::MONO8);
                outFrame.images.push_back(cv_ptr->image);
                return;
        };

        const auto k_publish_features = [this](const rclcpp::Time& stamp) -> void {
            std::vector<Eigen::Vector3d> slam_feats = m_vioManager->get_features_SLAM();
            std::vector<Eigen::Vector3d> msckf_feats = m_vioManager->get_good_features_MSCKF();

            auto const k_build_cloud_msg = [&stamp](const std::vector<Eigen::Vector3d>& points) -> PointCloudType {
                PointCloudType msg;
                msg.header.stamp = stamp;
                msg.header.frame_id = "map"; // Ensure this matches your world/odom frame
                msg.height = 1;
                msg.width = points.size();
                msg.is_dense = true;

                if (points.empty()) return msg;

                sensor_msgs::PointCloud2Modifier modifier(msg);
                modifier.setPointCloud2FieldsByString(1, "xyz");
                modifier.resize(points.size());

                sensor_msgs::PointCloud2Iterator<float> iter_x(msg, "x");
                sensor_msgs::PointCloud2Iterator<float> iter_y(msg, "y");
                sensor_msgs::PointCloud2Iterator<float> iter_z(msg, "z");

                for (const auto& pt : points) { 
                    *iter_x = static_cast<float>(pt.x());
                    *iter_y = static_cast<float>(pt.y());
                    *iter_z = static_cast<float>(pt.z());
                    ++iter_x; ++iter_y; ++iter_z;
                }
                return msg;
            };

            // 2. Build and publish both independent point clouds
            m_pubSlamPointCloud->publish(k_build_cloud_msg(slam_feats));
            m_pubMsckfPointCloud->publish(k_build_cloud_msg(msckf_feats));
        };

        /* Actual Worker Thread Begin */
        IMUFrameType     pendingImu;
        ov_core::ImuData slamImu;
        ImageFrameType      pendingImg;
        ov_core::CameraData slamImg;
        while (rclcpp::ok() && !m_exitSlam.load()) {
            while(true 
                && m_imuData.peek() == nullptr 
                && m_imgData.peek() == nullptr
                && !m_exitSlam.load()
            ) {
                std::this_thread::sleep_for(std::chrono::milliseconds{2});
            }

            /* Feeding IMU Data is way faster and doesn't trigger Expensive Kalman Filters */
            while (m_imuData.try_dequeue(pendingImu) != false) {
                k_convert_between_imu_types(pendingImu, slamImu);
                m_vioManager->feed_measurement_imu(slamImu);
            }

            /* Pushing Image Data on the other hand, does trigger Kalman Filter updates */
            while (m_imgData.try_dequeue(pendingImg) != false) {
                k_convert_between_image_types(pendingImg, slamImg);
                m_vioManager->feed_measurement_camera(slamImg);
                slamImg.sensor_ids.resize(0);
                slamImg.images.resize(0);
            }

            k_publish_features(pendingImg->header.stamp);
        }


        return;
    }


private:
    SubscriptionPtr<SensorCombinedType>   m_subImuCombined;
    SubscriptionPtr<ImageType>            m_subImg;
    PublisherPtr<PointCloudType>          m_pubSlamPointCloud;
    PublisherPtr<PointCloudType>          m_pubMsckfPointCloud;
    SPSC_Queue<IMUFrameType>              m_imuData{400}; /* Expected Refresh Rate ~200Hz, Capture Twice as much */
    SPSC_Queue<ImageFrameType>            m_imgData{60}; /* Expected Refresh Rate ~30Hz, Capture Twice as much */
    std::thread                           m_slamThread;
    std::atomic<bool>                     m_exitSlam{false};
    std::unique_ptr<ov_msckf::VioManager> m_vioManager;
};