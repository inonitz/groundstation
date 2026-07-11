#pragma once

#include <atomic>
#include <utility>
#include <type_traits>
#include <memory>
#include <cstring>

// Compiler ABI fallback for cache line
#ifdef __cpp_lib_hardware_interference_size
    inline constexpr size_t kCacheLineBytes = std::hardware_destructive_interference_size;
#else
    inline constexpr size_t kCacheLineBytes = 64;
#endif

template <typename T>
class LockFreeSpscDropQueue {
public:
    LockFreeSpscDropQueue(const LockFreeSpscDropQueue&) = delete;
    LockFreeSpscDropQueue& operator=(const LockFreeSpscDropQueue&) = delete;
    LockFreeSpscDropQueue(LockFreeSpscDropQueue&&) = delete;
    LockFreeSpscDropQueue& operator=(LockFreeSpscDropQueue&&) = delete;

    explicit LockFreeSpscDropQueue(size_t size) 
        : 
        m_cap(size + 1), 
        m_buf(m_alloc.allocate(m_cap)),
        m_init(std::make_unique<bool[]>(m_cap)) // Zero-initialized to false
    {}

    ~LockFreeSpscDropQueue() {
        if constexpr (!std::is_trivially_copyable_v<T>) {
            // Safely iterate over the bitset to destroy only active items
            for (size_t i = 0; i < m_cap; ++i) {
                if (m_init[i]) {
                    m_buf[i].~T();
                }
            }
        }
        m_alloc.deallocate(m_buf, m_cap);
    }

    template <typename U> 
    bool push(U&& item) {
        size_t current_head = m_head.load(std::memory_order_relaxed);
        size_t next_head    = (current_head + 1) % m_cap;
        size_t current_tail = m_tail.load(std::memory_order_acquire);

        if (next_head == current_tail) {
            return false; 
        }

        if constexpr (std::is_trivially_copyable_v<T>) {
            std::memcpy(&m_buf[current_head], &item, sizeof(T));
        } else {
            if (m_init[current_head]) {
                m_buf[current_head].~T();
            }
            ::new ( static_cast<void*>(&m_buf[current_head]) ) T(std::forward<U>(item));
            m_init[current_head] = true; // Mark as initialized
        }

        m_head.store(next_head, std::memory_order_release);
        return true;
    }

    bool pop(T& out_item) {
        size_t current_tail = m_tail.load(std::memory_order_relaxed); 
        size_t current_head = m_head.load(std::memory_order_acquire); 
        
        if (current_tail == current_head) {
            return false; 
        }

        if constexpr (std::is_trivially_copyable_v<T>) {
            out_item = m_buf[current_tail];
        } else {
            out_item = std::move(m_buf[current_tail]);
            m_buf[current_tail].~T(); // Explicit destructor
            m_init[current_tail] = false; // Mark as uninitialized
        }

        m_tail.store((current_tail + 1) % m_cap, std::memory_order_release);
        return true;
    }

private:
    std::allocator<T>       m_alloc;
    T* const                m_buf;
    const size_t            m_cap;
    std::unique_ptr<bool[]> m_init; // Replaces missing m_init reference

    alignas(kCacheLineBytes) std::atomic<size_t> m_head{0};
    alignas(kCacheLineBytes) std::atomic<size_t> m_tail{0};
};
