#include "asr_node.hpp"
#include <sttserv/wav_writer.hpp>


// static float get_transcription_confidence(struct parakeet_context* ctx);

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<ASRStandaloneNode>(argc, argv));
    rclcpp::shutdown();
    return 0;
}



// Static callback passed to miniaudio. User data is 'this'.
void ASRStandaloneNode::captureCallbackProducer(
    ma_device*     pDevice, 
    __unused void* pOutput, 
    const void*    pInput, 
    ma_uint32      frameCount
) {
    auto* node = static_cast<ASRStandaloneNode*>(pDevice->pUserData);

    // --- DIRECT LOOPBACK ---
    // if (pOutput != nullptr && pInput != nullptr) {
    //     // Copy raw PCM directly to playback buffer.
    //     // Assumes ma_format_f32 and matching capture/playback channels.
    //     std::memcpy(pOutput, pInput, frameCount * pDevice->capture.channels * sizeof(float));
    // }
    // if (pInput != nullptr) {
    //     float max_val = 0.0f;
    //     const float* in_f = static_cast<const float*>(pInput);
    //     ma_uint32 total_samples = frameCount * pDevice->capture.channels;
        
    //     for (ma_uint32 i = 0; i < total_samples; ++i) {
    //         float abs_val = in_f[i] < 0 ? -in_f[i] : in_f[i];
    //         if (abs_val > max_val) max_val = abs_val;
    //     }
        
    //     if (max_val == 0.0f) {
    //         RCLCPP_INFO(node->get_logger(), "[DEBUG] SILENT BLOCK (0.0)\n");
    //     } else {
    //         RCLCPP_INFO(node->get_logger(), "[DEBUG] Audio Amplitude: %f\n", max_val);
    //     }
    // }


    if (!node->m_isRecording.load() || !pInput) return;

    ma_uint32 framesToWrite = frameCount;
    void* pWriteBuffer = nullptr;
    
    // Write to AudioManager's Native Ring Buffer
    ma_pcm_rb_acquire_write(node->m_audioMan.ringBufferHandle(), &framesToWrite, &pWriteBuffer);
    
    if (framesToWrite > 0) {
        std::memcpy(pWriteBuffer, pInput, framesToWrite * sizeof(float));
        ma_pcm_rb_commit_write(node->m_audioMan.ringBufferHandle(), framesToWrite);
    }
}


void ASRStandaloneNode::parse_msg_for_drone_topics(std::string const& text) {
    // bool doArm = false;
    // bool newArm = false;
    // bool doTwist = false;
    // float lx = 0.0f;
    // float ly = 0.0f;
    // float lz = 0.0f;
    // float az = 0.0f;

    // std::string s = text;
    // std::transform(s.begin(), s.end(), s.begin(), ::tolower);

    // // If detected Stop/Halt, we flag it and skip the directional logic.
    // if(s.find("stop") != std::string::npos || s.find("halt") != std::string::npos) {
    //     doTwist = true; // trigger twist with 0 velocity
    // } 
    // else {
    //     if(s.find("disarm") != std::string::npos || s.find("land") != std::string::npos) {
    //         doArm = true; newArm = false;
    //     } 
    //     else if(
    //         s.find("arm") != std::string::npos 
    //         || s.find("um") != std::string::npos 
    //         || s.find("takeoff") != std::string::npos
    //         || s.find("take off") != std::string::npos
    //     ) {
    //         doArm = true; newArm = true;
    //     } 
    //     else if (s.find("go forward") != std::string::npos) {
    //         lx = 1.0f; doTwist = true;
    //     } 
    //     else if (s.find("go backward") != std::string::npos || s.find("go back") != std::string::npos) {
    //         lx = -1.0f; doTwist = true;
    //     } 
    //     else if (s.find("go left") != std::string::npos) {
    //         ly = 1.0f; doTwist = true;
    //     } 
    //     else if (s.find("go right") != std::string::npos || s.find("go write") != std::string::npos) {
    //         ly = -1.0f; doTwist = true;
    //     } 
    //     else if (s.find("go up") != std::string::npos || s.find("ascend") != std::string::npos) {
    //         lz = 1.0f; doTwist = true;
    //     } 
    //     else if (s.find("go down") != std::string::npos || s.find("descend") != std::string::npos) {
    //         lz = -1.0f; doTwist = true;
    //     } 
    //     else if (s.find("rotate counter clockwise") != std::string::npos || s.find("rotate left") != std::string::npos) {
    //         az = 1.0f; doTwist = true;
    //     } 
    //     else if (s.find("rotate clockwise") != std::string::npos || s.find("rotate right") != std::string::npos) {
    //         az = -1.0f; doTwist = true;
    //     }
    // }

    // // 3. Mutex protected update
    // {
    //     std::lock_guard<std::mutex> lock(m_modifyMtx);
        
    //     if (doTwist) {
    //         m_velcmd.linear.x = lx;
    //         m_velcmd.linear.y = ly;
    //         m_velcmd.linear.z = lz;
    //         m_velcmd.angular.x = 0.0f;
    //         m_velcmd.angular.y = 0.0f;
    //         m_velcmd.angular.z = az;
    //     }
        
    //     if (doArm) {
    //         m_armState.data = newArm;
    //     }
    // }

    // if(doArm) {
    //     m_pubArmState->publish(m_armState);
    // }
    return;
}


void ASRStandaloneNode::audioProcessingConsumerThread() 
{
    uint32_t availableFrames = 0;

    RCLCPP_INFO(this->get_logger(), "[WORKER] Background loop entered.");
    while (rclcpp::ok() && !m_exit.load()) 
    {
        std::unique_lock<std::mutex> lock(m_processMtx);
        m_processCV.wait(lock, [this]() { return m_exit.load() || m_audioDataReady.load(); });
        if (m_exit.load()) { 
            break;
        }

        m_audioDataReady = false;
        lock.unlock();
        
        
        /* [NOTE]: AvailableFrames is supposed to be captured inside a loop, not a single if-statement */
        RCLCPP_INFO(this->get_logger(), "[WORKER] Woken up. Data ready. Processing...");
        availableFrames = ma_pcm_rb_available_read(m_audioMan.ringBufferHandle());
        // printf("[DEBUG] Available frames in RB: %u\n", availableFrames);
        if(!availableFrames) {
            RCLCPP_WARN(this->get_logger(), "[WORKER] Woke up but no frames available in ringbuffer.");
            continue;
        }

        /* Reject a momentary H tap. Too-brief PTT captures produce empty/garbage transcripts that the
           VLM then hallucinates a whole mission from ("go find some vegetation"). If the key was held
           for less than kMinRecordMs it is not speech -- discard the clip and publish nothing. */
        constexpr uint64_t kMinRecordMs = 200;
        if (m_recordTimeMs < kMinRecordMs) {
            RCLCPP_WARN(this->get_logger(),
                "[WORKER] H held only %lu ms (< %lu) -- momentary tap, ignoring (no transcription/publish).",
                (unsigned long)m_recordTimeMs, (unsigned long)kMinRecordMs);
            ma_pcm_rb_seek_read(m_audioMan.ringBufferHandle(),
                ma_pcm_rb_available_read(m_audioMan.ringBufferHandle()));   /* discard so the next PTT is clean. */
            continue;
        }
    
        // Drain the ENTIRE utterance. The ring buffer is circular, so acquire_read yields only the
        // contiguous span up to the wrap point -- the old single read dropped everything past the
        // wrap, giving intermittent empty/truncated transcripts (positional: depends where the write
        // cursor sits in the 10 s buffer). Loop until all availableFrames are consumed.
        std::vector<float> nativePcm;
        nativePcm.reserve(availableFrames);
        {
            ma_uint32 remaining = availableFrames;
            while (remaining > 0) {
                ma_uint32 chunk       = remaining;
                void*     pReadBuffer = nullptr;
                if (ma_pcm_rb_acquire_read(m_audioMan.ringBufferHandle(), &chunk, &pReadBuffer) != MA_SUCCESS || chunk == 0) {
                    break;
                }
                const float* in = static_cast<const float*>(pReadBuffer);
                nativePcm.insert(nativePcm.end(), in, in + chunk);
                ma_pcm_rb_commit_read(m_audioMan.ringBufferHandle(), chunk);
                remaining -= chunk;
            }
        }

        // Resample the FULL native buffer (native rate -> target), +1024 padding.
        ma_uint64 framesToRead64  = nativePcm.size();
        ma_uint64 framesToWrite64 = (framesToRead64 * m_audioMan.resampleRate()) / m_audioMan.nativeSampleRate() + 1024;
        std::vector<float> resampledBuf(framesToWrite64);
        ma_resampler_process_pcm_frames(
            m_audioMan.resamplerHandle(),
            nativePcm.data(),
            &framesToRead64,
            resampledBuf.data(),
            &framesToWrite64
        );

        // Pass resampled buffer to whisper/parakeet backend
        auto transcript_time_ns = this->now().nanoseconds();
        if (m_backend.transcribe(
                resampledBuf.data(), 
                framesToWrite64, 
                static_cast<uint32_t>(m_recordTimeMs), 
                16000
            ) == false
        ) {
            RCLCPP_ERROR(this->get_logger(), "[WORKER] Transcribe failed.");

        } else {
            transcript_time_ns = this->now().nanoseconds() - transcript_time_ns;
            inferenceResultBuffer result_buf;
            if (m_backend.result(result_buf)) {
                ASRTextType out_msg;
                out_msg.data = std::string(result_buf.data());
                m_pubText->publish(out_msg);

                // parse_msg_for_drone_topics(out_msg.data);

                // transcript_time_ns = transcript_time_ns / (1000 * 1000) + (transcript_time_ns % (1000 * 1000)) > 0;
                transcript_time_ns = ( transcript_time_ns / 1'000'000 ) + (transcript_time_ns % 1'000'000 > 0);
                // RCLCPP_INFO(this->get_logger(), "[WORKER] >>> TRANSCRIBED (%ld ms, cf=%3.3f): \"%s\"", 
                //     transcript_time_ns, 
                //     get_transcription_confidence(m_backend.m_state.parakeet->ctx),
                //     out_msg.data.c_str()
                // );
                RCLCPP_INFO(this->get_logger(), "[WORKER] >>> TRANSCRIBED (%ld ms): \"%s\"", 
                    transcript_time_ns, 
                    out_msg.data.c_str()
                );
                // WavWriter d{};
                // d.open("audio_transcript_" + std::to_string(m_recordTimeMs) + ".wav", 1, 16000);
                // d.write(resampledBuf.data(), framesToWrite64);
                // d.close();
                m_backend.print_timings();
            }
        }
        transcript_time_ns = 0;
    }


    RCLCPP_INFO(this->get_logger(), "[WORKER] Background loop thread exiting.");
    return;
}


// float get_transcription_confidence(struct parakeet_context* ctx) {
//     float sum = 0; int cnt = 0;
//     for (int s = 0; s < parakeet_full_n_segments(ctx); ++s) {
//         for (int t = 0; t < parakeet_full_n_tokens(ctx, s); ++t, ++cnt) {
//             sum += parakeet_full_get_token_data(ctx, s, t).plog;
//         }
//     }
//     return cnt == 0 ? 0.0f : std::exp(sum / static_cast<f32>(cnt));
// }