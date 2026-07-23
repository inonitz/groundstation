#include "ros2_caminfer.hpp"
#include "spsc_ringbuffer.hpp"
#include "llamaclient.hpp"
#include <chrono>
#include <cv_bridge/cv_bridge.hpp>
#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <base64.h>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/subscription.hpp>
#include <rclcpp/strategies/message_pool_memory_strategy.hpp>
#include <std_msgs/msg/string.hpp>
#include <sensor_msgs/msg/image.hpp>


// class VLMNavNode : public rclcpp::Node {
// public:
//     VLMNavNode() : Node("vlmnav_node"), m_running(true), m_frame_ready(false) {
//         m_subImg = this->create_subscription<sensor_msgs::msg::Image>(kCameraTopic, 10, 
//             std::bind(&VLMNavNode::image_callback, this, std::placeholders::_1)
//         );

//         m_inference_thread = std::thread(&VLMNavNode::inference_worker, this);
//         RCLCPP_INFO(this->get_logger(), "VLMNav Node Started. Listening to Gazebo bridge...");
//     }

//     ~VLMNavNode() {
//         m_running = false;
//         m_cv.notify_all();
//         if (m_inference_thread.joinable()) {
//             m_inference_thread.join();
//         }
//     }

// private:
//     void image_callback(const sensor_msgs::msg::Image::SharedPtr msg) {
//         try {
//             cv_bridge::CvImageConstPtr shared_frame = cv_bridge::toCvShare(msg, "bgr8");
//             {
//                 std::lock_guard<std::mutex> lock(m_mutex);
//                 m_latest_frame = shared_frame.clone();
//                 m_frame_ready = true;
//             }
//             m_cv.notify_one();
//         } catch (cv_bridge::Exception& e) {
//             RCLCPP_ERROR(this->get_logger(), "cv_bridge exception: %s", e.what());
//         }
//     }

//     void inference_worker() {
//         while (m_running) {
//             cv::Mat frame_to_process;
//             {
//                 std::unique_lock<std::mutex> lock(m_mutex);
//                 m_cv.wait(lock, [this]{ return m_frame_ready || !m_running; });
//                 if (!m_running) break;
                
//                 frame_to_process = m_latest_frame.clone();
//                 m_frame_ready = false;
//             }

//             httplib::Client cli("127.0.0.1", 8080);
//             cli.set_read_timeout(15, 0); 

//             std::string b64_image = mat_to_base64(frame_to_process);

//             nlohmann::json payload;
//             payload["messages"] = nlohmann::json::array({
//                 {{"role", "system"}, {"content", "You are a direct automation tool. Output only the requested answer."}},
//                 {{"role", "user"}, {"content", {
//                     {{"type", "text"}, {"text", "Describe this camera frame."}},
//                     {{"type", "image_url"}, {"image_url", {{"url", "data:image/jpeg;base64," + b64_image}}}}
//                 }}}
//             });
//             payload["temperature"] = 0.1;
//             payload["max_tokens"] = 128;

//             auto start_time = std::chrono::steady_clock::now();
//             auto res = cli.Post("/v1/chat/completions", payload.dump(), "application/json");
//             auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start_time).count();

//             if (res && res->status == 200) {
//                 nlohmann::json response_json = nlohmann::json::parse(res->body);
//                 RCLCPP_INFO(this->get_logger(), "[VLM Response]: %s", response_json["choices"][0]["message"]["content"].get<std::string>().c_str());
//                 RCLCPP_INFO(this->get_logger(), "[Inference Time]: %ld ms", duration);
//             } else {
//                 RCLCPP_ERROR(this->get_logger(), "HTTP Error: %s", (res ? std::to_string(res->status).c_str() : "Host unreachable"));
//             }
//         }
//     }

//     rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr m_subImg;
//     std::thread m_inference_thread;
//     std::mutex m_mutex;
//     std::condition_variable m_cv;
//     cv::Mat m_latest_frame;
//     bool m_frame_ready;
//     bool m_running;
// };


class VLMNavNode2 : public rclcpp::Node {
public:
    static constexpr size_t kQoSHistoryDepth = 10;
    static constexpr uint32_t kMillisecondsInSecond  = 1000;
    static constexpr uint32_t kCameraFramesPerSecond = 2;
    static constexpr uint32_t kMaxSecondsToRecord    = 60 * 10;

    using Ros2ImgType = sensor_msgs::msg::Image;
    using CvImgType = cv_bridge::CvImage;

    using Ros2ImgSharedPtr = Ros2ImgType::SharedPtr;
    using CvImgSharedPtr   = CvImgType::ConstPtr;

    VLMNavNode2() : 
        Node("vlmnav_node"),
        m_lastFrames(2 * kCameraFramesPerSecond),
        m_modelHistory(kMaxSecondsToRecord * kCameraFramesPerSecond)
        {
            rclcpp::QoS qos(kQoSHistoryDepth);

            // 2. Create the Memory Pool Strategy
            // This pre-allocates exactly 'history_depth' number of Image messages.
            auto memory_strategy = std::make_shared<
                rclcpp::strategies::message_pool_memory_strategy::MessagePoolMemoryStrategy<
                    sensor_msgs::msg::Image, kQoSHistoryDepth>
                    >();

            // 3. Set up default subscription options
            rclcpp::SubscriptionOptions options{};

            m_subImg = this->create_subscription<Ros2ImgType>(
                kCameraTopic,
                qos,
                std::bind(&VLMNavNode2::image_callback, this, std::placeholders::_1),
                options,
                memory_strategy // Injecting the ring buffer pool here
            );

            m_pubText = this->create_publisher<std_msgs::msg::String>(
                kVLMTextTopic, 10
            );
            m_timer = this->create_wall_timer(
                std::chrono::milliseconds(kMillisecondsInSecond / kCameraFramesPerSecond), 
                std::bind(&VLMNavNode2::timerCallback, this)
            );
            
            m_inference_thread = std::thread(&VLMNavNode::inference_worker, this);
            RCLCPP_INFO(this->get_logger(), "VLMNav Node Started. Listening to Gazebo bridge...");
        }

    ~VLMNavNode2() {
        m_running = false;
        m_cv.notify_all();
        if (m_inference_thread.joinable()) {
            m_inference_thread.join();
        }
    }

private:
    void timerCallback() {
        {
            std::unique_lock<std::mutex> lock(m_frameLock);
            m_modelHistory.m_imgs.push(cv_bridge::toCvShare(m_latestFrame));
        }

        m_modelHistory.
        return;
    }

    void image_callback(Ros2ImgSharedPtr imgaddr) {
        m_lastFrames.push(imgaddr);
        return;
    }
    // void timerCallback() {
    //     std_msgs::msg::String _ = m_velcmd;

    //     RCLCPP_DEBUG(this->get_logger(), 
    //         "Keyboard Timer Tick -> Pub Twist (Linear X: %.1f, Z: %.1f)", 
    //         _.linear.x, 
    //         _.linear.z
    //     );
    //     m_pubTwist->publish(_);
    // }


    template<typename T> using PublisherPtr  = typename rclcpp::Publisher<T>::SharedPtr;
    template<typename T> using SubscriberPtr = typename rclcpp::Subscription<T>::SharedPtr;

    SubscriberPtr<sensor_msgs::msg::Image>  m_subImg;
    PublisherPtr<std_msgs::msg::String>     m_pubText;
    rclcpp::TimerBase::SharedPtr            m_timer;
    LockFreeSpscDropQueue<Ros2ImgSharedPtr> m_lastFrames; /* Updates 60Hz */
    HistoryBuffer                           m_modelHistory;
    // PublisherPtr<ASRTextTwistType>         m_pubTwist;
    // PublisherPtr<ASRArmType>               m_pubArmState;
    // SubscriberPtr<Px4KeyboardRawInputType> m_subKey;
};


int main(int argc, char* argv[]) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<VLMNavNode2>());
    rclcpp::shutdown();
    return 0;
}
