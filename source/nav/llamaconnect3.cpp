#include "llamaconnect3.hpp"
#include "llamaclient.hpp"
#include <chrono>
#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <base64.h>


std::string mat_to_base64(const cv::Mat& image);


int main()
{
    const cv::Mat frame(1280, 720, CV_8UC3, cv::Scalar(255, 0, 128));
    
    
    llamaConnection cli{};  
    std::string     b64_image = mat_to_base64(frame);


    cli.create("You are a direct automation tool. Output only the requested answer.",
        0.2,
        256
    );

    auto result = cli.send("", "Describe this camera frame", b64_image);
    if(result.has_value()) {
        const auto k_start_time = std::chrono::steady_clock::now();
        
        const auto& res = result->get();
        if(res && res->status == 200) {
            nlohmann::json response_json = nlohmann::json::parse(res->body);
            fprintf(stdout, "[VLM Response]: %s\n", 
                response_json["choices"][0]["message"]["content"].get<std::string>().c_str()
            );
            // fprintf(stdout, "[Inference Time]: %ld ms\n", duration);
        } else {
            fprintf(stdout, "HTTP Error: %s\n", (res ? std::to_string(res->status).c_str() : "Host unreachable"));
        }
        
        const auto k_stop_time = std::chrono::steady_clock::now();
        fprintf(stdout, "[End-To-End Inference Time]: %ld ms\n", 
            std::chrono::duration_cast<std::chrono::milliseconds>(k_stop_time - k_start_time).count()
        );
    }


    cli.destroy();
    return 0;
}


std::string mat_to_base64(const cv::Mat& image) {
    if (image.empty()) return "";
    
    // cv::Mat resized;
    // cv::resize(image, resized, cv::Size(512, 512), 0, 0, cv::INTER_LINEAR);

    std::vector<uchar> buffer;
    std::vector<int> params = {cv::IMWRITE_JPEG_QUALITY, 80};
    cv::imencode(".jpg", image, buffer, params);
    return base64_encode(buffer.data(), buffer.size());
}


