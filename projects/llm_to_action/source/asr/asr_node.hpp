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
        std::vector<std::string> sttservPassthroughArgs;   // owns the flag strings; must outlive the backend parse
        std::vector<char*> sttservArgv;                    // argv view the backend parser will read
        CommandLineArguments backendArgs{};

        m_pubText = this->create_publisher<ASRTextType>(kOutASRServerTranscriptionTopic, 10);
        if (!parseCommandlineArguments(
            argc, 
            argv, 
            m_recordAudioClips, 
            m_recordFolderPath, 
            sttservPassthroughArgs
        )) {
            RCLCPP_ERROR(this->get_logger(), "Command-Line Argument Parsing failed (ROS2 Node)");
            return;
        }

        sttservArgv.reserve(sttservPassthroughArgs.size() + 1);
        sttservArgv.push_back(argv[0]);
        for (std::string& backendFlag : sttservPassthroughArgs) {
            sttservArgv.push_back(const_cast<char*>(backendFlag.c_str()));
        }
        if (!parse_commandline_args(
            static_cast<int>(sttservArgv.size()), 
            sttservArgv.data(), 
            backendArgs
        )) {
            RCLCPP_ERROR(this->get_logger(), "Command-Line Argument Parsing failed (ASR Backend)");
            return;
        }

        if (!m_backend.create(backendArgs)) {
            RCLCPP_ERROR(this->get_logger(), "ASR Backend creation failed");
            return;
        }



        // Init Audio
        if (!m_audioMan.createContext()) {
            RCLCPP_ERROR(this->get_logger(), "Audio Driver Context failed");
        }
        if(!m_audioMan.selectDevicesAndFinalize(this, captureCallbackProducer, 1, 1, 16000, 
            static_cast<uint8_t>(backendArgs.capture_id == -1 ? 0xFF : backendArgs.capture_id), 
            static_cast<uint8_t>(backendArgs.playback_id == -1 ? 0xFF : backendArgs.playback_id)
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
                static const char* skPushToTalkKeyBindStr = keyCodeToString(kPushToTalkKeyBind);
                if (msg->data.size() < 2) { 
                    return;
                }

                auto key = static_cast<KeyCodeEnum>(msg->data[0]);
                auto action = static_cast<KeyAction>(msg->data[1]);

                /* Early Exit - We Listen to the Key H for recording */
                if (key != kPushToTalkKeyBind) {
                    return;
                }


                /* TOGGLE: first keypress starts recording, the next press stops + transcribes.
                   No holding. RELEASED is ignored here, REPEATED (auto-repeat) is already filtered. */
                if (action != KeyAction::PRESSED) {
                    return;
                }

                if (!m_isRecording) {
                    /* START. The producer only writes while m_isRecording, so the buffer is already
                       empty here -- nothing to drain (the consumer flushes after each utterance). */
                    m_isRecording = true;
                    m_recordTimeMs = static_cast<uint64_t>(this->now().nanoseconds());
                    RCLCPP_INFO(this->get_logger(), 
                        "[KEY] %s -> recording ON (press %s again to stop).", 
                        skPushToTalkKeyBindStr, 
                        skPushToTalkKeyBindStr
                    );
                } else {
                    /* STOP. Compute held duration and wake the consumer to transcribe. */
                    m_recordTimeMs = static_cast<uint64_t>(this->now().nanoseconds()) - m_recordTimeMs;
                    m_recordTimeMs = (m_recordTimeMs / 1000'000) + ((m_recordTimeMs % 1000'000) > 0);
                    RCLCPP_INFO(this->get_logger(), "[KEY] %s -> recording OFF (%lu ms). Transcribing.",
                        skPushToTalkKeyBindStr,
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
    static constexpr KeyCodeEnum kPushToTalkKeyBind = KeyCodeEnum::F5;

    // Static callback passed to miniaudio. User data is 'this'.
    static void captureCallbackProducer(
        ma_device*  pDevice, 
        void*       pOutput, 
        const void* pInput, 
        ma_uint32   frameCount
    );

    bool parseCommandlineArguments(int argc, char** argv,
        bool&                     outShouldRecordAudioClips,
        std::string&              outAudioClipDestFolder,
        std::vector<std::string>& outSttservPassthroughArgs
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
    std::string             m_recordFolderPath;
    std::atomic<uint32_t>   m_audioClipIndex{0}; 
    bool                    m_recordAudioClips{false};

    std::thread             m_worker;
    std::mutex              m_processMtx;
    std::condition_variable m_processCV;

    std::mutex              m_modifyMtx;
};
