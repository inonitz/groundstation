#pragma once
#include <cv_bridge/cv_bridge.hpp>
#include <cstddef>
#include <vector>
#include "bumpalloc.hpp"

constexpr uint16_t    kMaxCharsPerModelResponse = 512;
constexpr const char* kCameraTopic = 
    "/world/default/model/x500_gimbal_0/link/camera_link/sensor/camera/image";
constexpr const char* kVLMTextTopic = 
    "/vlm/text";

class CvImageRingBuffer {
public:
    using ImgSharedPtr = cv_bridge::CvImageConstPtr;

    CvImageRingBuffer(const CvImageRingBuffer&)            = delete;
    CvImageRingBuffer& operator=(const CvImageRingBuffer&) = delete;
    CvImageRingBuffer(CvImageRingBuffer&&)                 = delete;
    CvImageRingBuffer& operator=(CvImageRingBuffer&&)      = delete;


    explicit CvImageRingBuffer(size_t capacity) 
        : 
        m_buffer(capacity), 
        m_capacity{capacity}, 
        m_head{0},
        m_count{0}
        {}


    void push(const ImgSharedPtr& img) {
        if (m_capacity == 0) {
            return; /* Guard against zero capacity */
        }

        m_buffer[m_head] = img;
        m_head = (m_head + 1) % m_capacity;
        m_count += (m_count < m_capacity);
        return;
    }

    ImgSharedPtr operator[](size_t index) const 
    {
        size_t actual_index = 0;
        if (index >= m_count) { /* Out of bounds */
            return nullptr;
        }
        
        /* If buffer not full, oldest is at index 0. */
        /* If full, oldest is at m_head. */
        actual_index = (m_count < m_capacity) ? index : (m_head + index) % m_capacity;
        return m_buffer[actual_index];
    }
    

    size_t size()     const { return m_count; }
    size_t capacity() const { return m_capacity; }

private:
    std::vector<ImgSharedPtr> m_buffer;
    size_t                    m_capacity;
    size_t                    m_head;
    size_t                    m_count;
};


struct FrameData {
    CvImageRingBuffer::ImgSharedPtr m_img;
    std::string_view                m_text;
    uint64_t                        m_timestampNs;

    FrameData(const FrameData&)            = delete;
    FrameData& operator=(const FrameData&) = delete;
};

struct Checkpoint {
    std::vector<uint32_t> m_frameIndices;
    std::string_view      m_modelOutput;
};

struct HistoryBuffer {
    CvImageRingBuffer       m_imgs;
    AtomicBumpAllocator     m_textAlloc;
    std::vector<FrameData>  m_frames;
    std::vector<Checkpoint> m_checkpoints;
    uint32_t                m_frameCount;


    HistoryBuffer(const HistoryBuffer&)            = delete;
    HistoryBuffer& operator=(const HistoryBuffer&) = delete;
    HistoryBuffer(HistoryBuffer&&)                 = delete;
    HistoryBuffer& operator=(HistoryBuffer&&)      = delete;

    explicit HistoryBuffer(uint32_t maxFrames) :
        m_imgs(maxFrames),
        m_textAlloc(kMaxCharsPerModelResponse * maxFrames),
        m_frames(maxFrames),
        m_checkpoints(),
        m_frameCount(maxFrames)
        {}

};