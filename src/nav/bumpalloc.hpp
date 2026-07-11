#include <atomic>
#include <cstddef>
#include <memory>
#include <thread>
#include <new>


class AtomicBumpAllocator {
public:
    AtomicBumpAllocator(const AtomicBumpAllocator&) = delete;
    AtomicBumpAllocator& operator=(const AtomicBumpAllocator&) = delete;
    AtomicBumpAllocator(AtomicBumpAllocator&&) = delete;
    AtomicBumpAllocator& operator=(AtomicBumpAllocator&&) = delete;

    explicit AtomicBumpAllocator(size_t size) 
        : 
        m_buffer(new std::byte[size]), 
        m_capacity{size},
        m_offset{0},
        m_active_allocations{0},
        m_resetting{false}
        {}


    void* allocate(size_t size, size_t alignment = kCacheLineSizeBytes) 
    {
        size_t current_offset = 0;
        size_t new_offset     = 0;
        void*  aligned_ptr    = nullptr;
        size_t leftoverSpace  = 0;
        void*  curr_ptr       = nullptr;
        const auto kl_notifyStartOfAllocation = [&cnt = this->m_active_allocations]() {
            cnt.fetch_add(1, std::memory_order_seq_cst);
            return;
        };
        const auto kl_notifyStopOfAllocation = [&cnt = this->m_active_allocations]() {
            cnt.fetch_sub(1, std::memory_order_release);
            return;
        };


        if (alignment == 0 || (alignment & (alignment - 1)) != 0) {
            return nullptr; /* Ensure Alignment is power of 2 */
        }

        /* Bump Allocator is actively being reset. Wait until finished. */
        while (m_resetting.load(std::memory_order_acquire)) {
            std::this_thread::yield();
        }


        kl_notifyStartOfAllocation();
        if (m_resetting.load(std::memory_order_acquire)) {
            /* We are resetting again. We just fail allocation. */
            kl_notifyStopOfAllocation();
            return nullptr;
        }


        current_offset = m_offset.load(std::memory_order_relaxed);
        do {
            if (current_offset > m_capacity) {
                kl_notifyStopOfAllocation();
                return nullptr; /* One thread already bumped offset past the capacity */
            }

            curr_ptr      = m_buffer.get() + current_offset;
            leftoverSpace = m_capacity - current_offset;
            /* aligns the pointer for us, if doesn't succeed -> nullptr */
            aligned_ptr = std::align(alignment, size, curr_ptr, leftoverSpace);
            if (aligned_ptr == nullptr) {
                kl_notifyStopOfAllocation();
                return nullptr; /* Not enough space */
            }

            /* Calculate updated offset using the aligned pointer */
            new_offset = static_cast<std::byte*>(aligned_ptr) - m_buffer.get() + size;

        } while (!m_offset.compare_exchange_weak(
            current_offset, 
            new_offset, 
            std::memory_order_acq_rel, 
            std::memory_order_relaxed
        ));


        /* We stopped allocation, we notify of this */
        kl_notifyStopOfAllocation();
        return aligned_ptr;
    }


    void reset() {
        m_resetting.store(true, std::memory_order_seq_cst);

        while (m_active_allocations.load(std::memory_order_acquire) > 0) {
            std::this_thread::yield();
        }

        m_offset.store(0, std::memory_order_release);
        m_resetting.store(false, std::memory_order_release);
        return;
    }

private:
#ifdef __cpp_lib_hardware_interference_size
    static constexpr size_t kCacheLineSizeBytes = 
        std::hardware_destructive_interference_size;
#else
    static constexpr size_t kCacheLineSizeBytes = 64; 
#endif

private:
    std::unique_ptr<std::byte[]> m_buffer;
    size_t                       m_capacity;
    std::atomic<size_t>          m_offset;
    std::atomic<size_t>          m_active_allocations;
    std::atomic<bool>            m_resetting;
};