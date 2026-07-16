#include <iostream>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <chrono>

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp> // Added for cv::resize

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <cv_bridge/cv_bridge.hpp>

#include <httplib.h>
#include <nlohmann/json.hpp>
#include <base64.h>


// Fix #3: Downscale frame before JPEG/Base64 encoding to slash CPU latency
std::string mat_to_base64(const cv::Mat& image) {
    if (image.empty()) return "";
    
    // cv::Mat resized;
    // cv::resize(image, resized, cv::Size(512, 512), 0, 0, cv::INTER_LINEAR);

    std::vector<uchar> buffer;
    std::vector<int> params = {cv::IMWRITE_JPEG_QUALITY, 80};
    cv::imencode(".jpg", image, buffer, params);
    return base64_encode(buffer.data(), buffer.size());
}


class VLMNavNode : public rclcpp::Node {
public:
    VLMNavNode() : Node("vlmnav_node"), m_running(true), m_frame_ready(false) {
        // Fix #2: Exact topic string from simenv.sh SITL bridge
        m_subImg = this->create_subscription<sensor_msgs::msg::Image>(
            "/world/default/model/x500_gimbal_0/link/camera_link/sensor/camera/image", 10, 
            std::bind(&VLMNavNode::image_callback, this, std::placeholders::_1)
        );

        m_inference_thread = std::thread(&VLMNavNode::inference_worker, this);
        RCLCPP_INFO(this->get_logger(), "VLMNav Node Started. Listening to Gazebo bridge...");
    }

    ~VLMNavNode() {
        m_running = false;
        m_cv.notify_all();
        if (m_inference_thread.joinable()) {
            m_inference_thread.join();
        }
    }

private:
    void image_callback(const sensor_msgs::msg::Image::SharedPtr msg) {
        try {
            cv::Mat frame = cv_bridge::toCvCopy(msg, "bgr8")->image;
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                m_latest_frame = frame.clone();
                m_frame_ready = true;
            }
            m_cv.notify_one();
        } catch (cv_bridge::Exception& e) {
            RCLCPP_ERROR(this->get_logger(), "cv_bridge exception: %s", e.what());
        }
    }

    void inference_worker() {
        while (m_running) {
            cv::Mat frame_to_process;
            {
                std::unique_lock<std::mutex> lock(m_mutex);
                m_cv.wait(lock, [this]{ return m_frame_ready || !m_running; });
                if (!m_running) break;
                
                frame_to_process = m_latest_frame.clone();
                m_frame_ready = false;
            }

            httplib::Client cli("127.0.0.1", 8080);
            cli.set_read_timeout(15, 0); 

            std::string b64_image = mat_to_base64(frame_to_process);

            nlohmann::json payload;
            payload["messages"] = nlohmann::json::array({
                {{"role", "system"}, {"content", "You are a direct automation tool. Output only the requested answer."}},
                {{"role", "user"}, {"content", {
                    {{"type", "text"}, {"text", "Describe this camera frame."}},
                    {{"type", "image_url"}, {"image_url", {{"url", "data:image/jpeg;base64," + b64_image}}}}
                }}}
            });
            payload["temperature"] = 0.1;
            payload["max_tokens"] = 128;

            auto start_time = std::chrono::steady_clock::now();
            auto res = cli.Post("/v1/chat/completions", payload.dump(), "application/json");
            auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start_time).count();

            if (res && res->status == 200) {
                nlohmann::json response_json = nlohmann::json::parse(res->body);
                RCLCPP_INFO(this->get_logger(), "[VLM Response]: %s", response_json["choices"][0]["message"]["content"].get<std::string>().c_str());
                RCLCPP_INFO(this->get_logger(), "[Inference Time]: %ld ms", duration);
            } else {
                RCLCPP_ERROR(this->get_logger(), "HTTP Error: %s", (res ? std::to_string(res->status).c_str() : "Host unreachable"));
            }
        }
    }

    rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr m_subImg;
    std::thread m_inference_thread;
    std::mutex m_mutex;
    std::condition_variable m_cv;
    cv::Mat m_latest_frame;
    bool m_frame_ready;
    bool m_running;
};


int main(int argc, char* argv[]) {
    rclcpp::init(argc, argv);
    // rclcpp::spin(std::make_shared<VLMNavNode>());

    auto log = rclcpp::get_logger("ugabuga");
    httplib::Client cli("127.0.0.1", 8080);
    // cli.set_read_timeout(15, 0); 

    // while (true) {
    //     auto res = cli.Get("/health");
    //     if (res) {
    //         if (res->status == 200) {
    //             RCLCPP_INFO(log, "Server ready!");
    //             break;
    //         }
    //         RCLCPP_INFO(log, "Server replied but not 200. Status: %d, Body: %s", res->status, res->body.c_str());
    //     } else {
    //         RCLCPP_ERROR(log, "Network error enum: %d", res.error());
    //     }
    //     std::this_thread::sleep_for(std::chrono::seconds(1));
    // }


    const cv::Mat frame(480, 640, CV_8UC3, cv::Scalar(0, 0, 255));
    nlohmann::json payload;
    httplib::Headers headers = {
        {"Origin", "http://127.0.0.1"} 
    };
    std::string b64_image = mat_to_base64(frame);


    payload["messages"] = nlohmann::json::array({
        {{"role", "system"}, {"content", "You are a direct automation tool. Output only the requested answer."}},
        {{"role", "user"}, {"content", {
            {{"type", "text"}, {"text", "Describe this camera frame."}},
            {{"type", "image_url"}, {"image_url", {{"url", "data:image/jpeg;base64," + b64_image}}}}
        }}}
    });
    payload["temperature"] = 0.1;
    payload["max_tokens"] = 128;

    auto start_time = std::chrono::steady_clock::now();
    auto res = cli.Post("/v1/chat/completions", headers, payload.dump(), "application/json");
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start_time).count();

    if (res && res->status == 200) {
        nlohmann::json response_json = nlohmann::json::parse(res->body);
        RCLCPP_INFO(log, "[VLM Response]: %s", response_json["choices"][0]["message"]["content"].get<std::string>().c_str());
        RCLCPP_INFO(log, "[Inference Time]: %ld ms", duration);
    } else {
        RCLCPP_ERROR(log, "HTTP Error: %s", (res ? std::to_string(res->status).c_str() : "Host unreachable"));
    }


    rclcpp::shutdown();
    return 0;
}


// int main(int argc, char* argv[]) {
//     rclcpp::init(argc, argv);
//     // rclcpp::spin(std::make_shared<VLMNavNode>());

//     auto log = rclcpp::get_logger("ugabuga");
//     int sock = socket(AF_INET, SOCK_STREAM, 0);
//     struct sockaddr_in addr;
//     addr.sin_family = AF_INET;
//     addr.sin_port = htons(8080);
//     inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

//     if (connect(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
//         perror("Raw socket connect failed");
//     } else {
//         printf("Raw socket connected successfully!\n");
//     }
//     close(sock);


//     rclcpp::shutdown();
//     return 0;
// }

// int main() {
//     // 1. Force IP, No DNS
//     // httplib::Client cli("http://127.0.0.1:8080"); 
//     httplib::Client cli("127.0.0.1", 8080);
//     cli.set_read_timeout(10, 0);
//     auto res = cli.Get("/health");

//     if (res) {
//         std::cout << "Status: " << res->status << std::endl;
//         std::cout << "Body: " << res->body << std::endl;
//     } else {
//         auto err = res.error();
//         std::cout << "Error code: " << (int)err << std::endl;
//         // Print the ACTUAL Linux OS Error:
//         std::cout << "POSIX errno: " << strerror(errno) << " (" << errno << ")" << std::endl;
//     }
//     return 0;
// }


// int main() {
//     httplib::Client cli("127.0.0.1", 8080);
    
//     // 5 second timeout. Do not hang forever.
//     cli.set_connection_timeout(5, 0); 

//     httplib::Headers headers = {
//         {"Origin", "http://127.0.0.1"} 
//     };

//     std::string body = R"({"messages": [{"role": "user", "content": "Hello"}]})";

//     auto res = cli.Post("/v1/chat/completions", headers, body, "application/json");

//     if (!res) {
//         // Network error (Server down, timeout, etc)
//         std::cerr << "Network Error: " << httplib::to_string(res.error()) << std::endl;
//         return 1;
//     }

//     if (res->status != 200) {
//         // HTTP error (400, 404, 500, etc)
//         std::cerr << "HTTP Error Status: " << res->status << std::endl;
//         std::cerr << "Error Body: " << res->body << std::endl;
//         return 1;
//     }

//     // Success
//     std::cout << "Response:\n" << res->body << std::endl;

//     return 0;
// }