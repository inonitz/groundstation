#pragma once
#include <atomic>
#include <util2/time.hpp>
#include "audio2.hpp"
#include "async_key.hpp"
#include "backend.hpp"
#include "wav_writer.hpp"


#if defined(ENABLE_PROFILING)
#   undef ENABLE_PROFILING
#   define ENABLE_PROFILING 0
#endif


#if defined(TRACY_ENABLE) & defined(ENABLE_PROFILING) && ENABLE_PROFILING == 1
#   ifndef __profile
#       define __profile(...) { __VA_ARGS__ }
#   endif
#else
#   ifndef __profile
#       define __profile(...) {}
#   endif
#endif


struct ProgramContext 
{
    using signalCV = std::condition_variable;
    using signalMtx = std::mutex;

    std::thread m_readThread;
    std::thread m_processingThread;
    
    signalMtx         m_exitLock;
    std::atomic<bool> m_exit = false;
    signalCV          m_exitSignal;

    signalMtx            m_selectDeviceLock;
    std::atomic<uint8_t> m_devicesSelected = 0;
    signalCV             m_deviceSelectionCV;

    std::atomic<bool> m_audioDataReady = false;
    signalCV          m_audioCV;
    signalMtx         m_audioLock;

    std::atomic<bool> m_inferenceBufReady = false;
    signalCV          m_inferenceCV;
    signalMtx         m_inferenceLock;

    std::atomic<bool> m_startStopFlag = false;

    std::atomic<uint32_t> m_produced  = 0;
    std::atomic<uint32_t> m_dropped   = 0;
    std::atomic<uint32_t> m_consumed  = 0;
    std::atomic<uint32_t> m_processed = 0;

    std::atomic<bool>    m_recordTimerFlag;
    std::atomic<bool>    m_processingTimerFlag;
    util2::Time::Timer<> m_recordTime;
    util2::Time::Timer<> m_processingTime;
    util2::Time::Timer<> m_whisperTime;
    util2::Time::Timer<> m_loggingTime;

    util2::Time::Timer<>& mr_startPTT_Till_ReleasePTT   = m_recordTime;
    util2::Time::Timer<>& mr_ReleasePTT_Till_EndOfInfer = m_processingTime;
    util2::Time::Timer<>& mr_Start_Till_EndOfInfer      = m_whisperTime;

    WavWriter        m_micToFile;
    AudioManager2    m_audioMan;
    uint32_t         m_resampleBufferSize;
    uint32_t         m_inferenceBufferSize;
    std::vector<f32> m_resampleBuffer;
    std::vector<f32> m_inferenceBuf;
    std::vector<f32> m_inferSliceBuf;
    inferenceResultBuffer m_inferResult;

    AsyncKeyHook     m_keyListener;
    ModelBackend     m_backend;
};


void audioCaptureCallbackProducer(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount);
void audioProcessCallbackConsumer();
void audioInferenceWorker();
int  main(int argc, char* argv[]);
