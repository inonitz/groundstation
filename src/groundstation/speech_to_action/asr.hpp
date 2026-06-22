#include "base.hpp"
#include "key_codes.hpp"
#include <sttserv/backend.hpp>
#include <string>


constexpr const char* kOutASRServerTranscriptionTopic = "/asr_server/transcribe";
using ASRTextType = std_msgs::msg::String;



class ASRKeyboardTrigger : public rclcpp::Node {
public:
    ASRKeyboardTrigger() : Node("asr_keyboard_trigger") {
        m_pubText = this->create_publisher<ASRTextType>(
            kOutASRServerTranscriptionTopic, 
            10
        );
        
        // Initialize STT Backend
        CommandLineArguments args;
        if (!createBackend(&args, nullptr, &m_modelContext, nullptr)) {
            RCLCPP_ERROR(this->get_logger(), "Backend creation failed!");
            return;
        }

        m_subKeyInput = this->create_subscription<std_msgs::msg::Int32MultiArray>(
            kPx4KeyboardRawTopic, 
            10,
            [this](const Px4KeyboardRawInputType::SharedPtr msg) {
                if (msg->data.size() < 2) return;

                auto key    = static_cast<KeyCode>(msg->data[0]);
                auto action = static_cast<KeyAction>(msg->data[1]);

                if (key == KeyCode::Space && action == KeyAction::PRESSED) {
                    RCLCPP_INFO(this->get_logger(), "Space received. Transcribing...");
                    
                    BackendTranscriptionResult result_buf = {0};
                    m_modelContext.transcribe(const f32 *pcm, size_t frames, u32 duration_ms, u32 sample_rate)
                    if (transcribe(&result_buf)) {
                        ASRTextType out_msg;
                        out_msg.data = std::string(result_buf);
                        m_pubText->publish(out_msg);
                    } else {
                        RCLCPP_ERROR(this->get_logger(), "Transcription failed.");
                    }
                }
            }
        );
    }


    ~ASRKeyboardTrigger() {
        if (m_modelContext.m_state.parakeet) {
            m_modelContext.destroy();
        }
        return;
    }

private:
    PublisherPtr<ASRTextType>              m_pubText;
    SubscriberPtr<Px4KeyboardRawInputType> m_subKeyInput;
    ModelBackend                           m_modelContext;
};
