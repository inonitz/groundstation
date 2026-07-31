#include <rclcpp/rclcpp.hpp>
#include <sttserv/audio2.hpp>
#include <sttserv/backend.hpp>
#include "keyboard/keyboard_node_base.hpp"
#include "keyboard/key_codes.hpp"
#include "asr_node_base.hpp"
#include "util/base.hpp"
#include <thread>
#include <atomic>
#include <cstring>


class ASRStandaloneNode : public rclcpp::Node {
public:
    ASRStandaloneNode(int argc, char** argv) : Node("asr_standalone_node") {
        m_pubText = this->create_publisher<ASRTextType>(kOutASRServerTranscriptionTopic, 10);


        CommandLineArguments args{};
        if(!parse_commandline_args(argc, argv, args)) {
            RCLCPP_ERROR(this->get_logger(), "Command-Line Argument Parsing failed");
            return;
        }
        if (!m_backend.create(args)) {
            RCLCPP_ERROR(this->get_logger(), "Backend failed");
            return;
        }


        // Init Audio
        if (!m_audioMan.createContext()) {
            RCLCPP_ERROR(this->get_logger(), "Audio Driver Context failed");
        }
        if(!m_audioMan.selectDevicesAndFinalize(this, captureCallbackProducer, 1, 1, 16000, 
            static_cast<uint8_t>(args.capture_id == -1 ? 0xFF : args.capture_id), 
            static_cast<uint8_t>(args.playback_id == -1 ? 0xFF : args.playback_id)
        )) {
            RCLCPP_ERROR(this->get_logger(), "Audio Driver Finalization failed");
        }
        if(!m_audioMan.start()) {
            RCLCPP_ERROR(this->get_logger(), "Audio Initialization failed");
        }


        m_subKey = this->create_subscription<KeyboardRawInputType>(
            kOutKeyboardRawTopic, 
            10,
            [this](const KeyboardRawInputType::SharedPtr msg) {
                if (msg->data.size() < 2) { 
                    return;
                }

                auto key = static_cast<KeyCodeEnum>(msg->data[0]);
                auto action = static_cast<KeyAction>(msg->data[1]);

                /* Early Exit - We Listen to the Key H for recording */
                if (key != KeyCodeEnum::H) {
                    return;
                }


                if (action == KeyAction::PRESSED) {
                    RCLCPP_INFO(this->get_logger(), "[KEY] Key H PRESSED. Recording started.");
                    m_isRecording = true;
                    m_recordTimeMs = static_cast<uint64_t>(this->now().nanoseconds());

                } else if (action == KeyAction::RELEASED) {
                    m_recordTimeMs = static_cast<uint64_t>(this->now().nanoseconds()) - m_recordTimeMs;
                    m_recordTimeMs = (m_recordTimeMs / 1000'000) + ((m_recordTimeMs % 1000'000) > 0);

                    RCLCPP_INFO(this->get_logger(), 
                        "[KEY] Key H RELEASED. Recording stopped (%lu ms). Triggering worker.", 
                        m_recordTimeMs
                    );
                    {
                        std::lock_guard<std::mutex> lock(m_processMtx);
                        m_isRecording = false;
                        m_audioDataReady = true;
                    }
                    m_processCV.notify_one();
                }

                return;
            }
        );


        m_worker = std::thread(&ASRStandaloneNode::audioProcessingConsumerThread, this);
        return;
    }


    ~ASRStandaloneNode() {
        m_exit = true;
        m_isRecording = false;
        m_processCV.notify_all();
        if (m_worker.joinable()) {
            m_worker.join();
        }
        m_audioMan.stop();
        m_audioMan.destroy();
        m_backend.destroy();
        return;
    }

private:
    // Static callback passed to miniaudio. User data is 'this'.
    static void captureCallbackProducer(
        ma_device*  pDevice, 
        void*       pOutput, 
        const void* pInput, 
        ma_uint32   frameCount
    );

    void audioProcessingConsumerThread();
    void parse_msg_for_drone_topics(std::string const& result);


private:
    PublisherPtr<ASRTextType>           m_pubText;
    SubscriberPtr<KeyboardRawInputType> m_subKey;
    TimerSharedPtr                      m_timer;
    
    ModelBackend            m_backend;
    AudioManager2           m_audioMan;
    
    std::atomic<bool>       m_isRecording{false};
    std::atomic<bool>       m_exit{false};
    std::atomic<bool>       m_audioDataReady{false};
    uint64_t                m_recordTimeMs{0};
    std::thread             m_worker;
    std::mutex              m_processMtx;
    std::condition_variable m_processCV;

    std::mutex              m_modifyMtx;
};
