#include <iostream>
#include <vector>
#include <string>
#include <opencv/core.hpp>
#include <opencv/imgcodecs.hpp>
#include <httplib.h>
#include <nlohmann/json.hpp>
#include <base64.h>


std::string mat_to_base64(const cv::Mat& image) {
    if (image.empty()) return "";
    
    std::vector<uchar> buffer;
    std::vector<int> params = {cv::IMWRITE_JPEG_QUALITY, 85};
    cv::imencode(".jpg", image, buffer, params);

    return base64_encode(buffer.data(), buffer.size());
}


int main() {
    std::cout << "VLMNav Workspace Initialized." << std::endl;

    // 1. Create dummy image (replace with camera logic later)
    // cv::VideoCapture videocap{};
    cv::Mat frame(480, 640, CV_8UC3, cv::Scalar(0, 0, 255)); 
    
    // 2. Encode to Base64
    std::string b64_image = mat_to_base64(frame);

    // 3. Build Payload
    nlohmann::json payload;
    payload["messages"] = nlohmann::json::array({
        {
            {"role", "system"},
            {"content", "You are a direct automation tool. Output only the requested answer. Do not include introductions, pleasantries, or explanations."}
        },
        {
            {"role", "user"},
            {"content", 
                {
                    {{"type", "text"}, {"text", "Describe this camera frame."}},
                    {{"type", "image_url"}, {"image_url", {{"url", "data:image/jpeg;base64," + b64_image}}}}
                }
            }
        }
    });

    payload["temperature"] = 0.1;
    payload["max_tokens"] = 256;
    payload["stop"] = nlohmann::json::array({"\n", "User:", "<|im_end|>"});


    // 4. Dispatch Request with Timestamps
    httplib::Client cli("localhost", 8080);

    auto start_time = std::chrono::steady_clock::now();
    auto res = cli.Post("/v1/chat/completions", payload.dump(), "application/json");
    auto end_time = std::chrono::steady_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time).count();

    // 5. Handle Response
    if (res && res->status == 200) {
        nlohmann::json response_json = nlohmann::json::parse(res->body);
        std::cout << "\n[Llama-Server Response]:\n" << response_json["choices"][0]["message"]["content"].get<std::string>() << std::endl;
        std::cout << "\n[Inference Time]: " << duration << " ms" << std::endl;
    } else {
        std::cerr << "HTTP Error: " << (res ? std::to_string(res->status) : "Host unreachable") << std::endl;
        std::cerr << "[Failed Attempt Duration]: " << duration << " ms" << std::endl;
    }
    return 0;
}