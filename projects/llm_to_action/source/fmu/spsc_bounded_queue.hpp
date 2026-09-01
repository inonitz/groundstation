#pragma once
#include <atomic>
#include <utility>
#include <type_traits>
#include <memory>
#include <cstring>



/* Compiler ABI fallback for cache line */
#ifdef __cpp_lib_hardware_interference_size
    inline constexpr size_t kCacheLineBytes = std::hardware_destructive_interference_size;
#else
    inline constexpr size_t kCacheLineBytes = 64;
#endif


template<typename T> 
struct ContentionFreeAtomic {
    alignas(kCacheLineBytes) std::atomic<T> m_data;
};


template <typename T>
class LockFreeSpscBufferedQueue {
public:
    LockFreeSpscBufferedQueue(const LockFreeSpscBufferedQueue&) = delete;
    LockFreeSpscBufferedQueue& operator=(const LockFreeSpscBufferedQueue&) = delete;
    LockFreeSpscBufferedQueue(LockFreeSpscBufferedQueue&&) = delete;
    LockFreeSpscBufferedQueue& operator=(LockFreeSpscBufferedQueue&&) = delete;

    LockFreeSpscBufferedQueue() : m_buf(nullptr), m_cap(0) {}
    ~LockFreeSpscBufferedQueue() {
        if (m_buf != nullptr) {
            destroy();
        }
        return;
    }


    inline bool create(size_t size) {
        m_cap  = size;
        m_buf  = m_alloc.allocate(m_cap);
        m_init = std::make_unique<bool[]>(m_cap);
        return (m_buf != nullptr) && (m_init != nullptr);
    }

    inline void destroy() {
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


    bool pop() {
        /* 
            If you manage the memory of each ringbuffer member,
            you may not want the out_item in the first place.
        */
        size_t current_tail = m_tail.load(std::memory_order_relaxed); 
        size_t current_head = m_head.load(std::memory_order_acquire); 
        
        if (current_tail == current_head) {
            return false; 
        }

        if constexpr (!std::is_trivially_copyable_v<T>) {
            m_buf[current_tail].~T();     // Explicit destructor
            m_init[current_tail] = false; // Mark as uninitialized
        }

        m_tail.store((current_tail + 1) % m_cap, std::memory_order_release);
        return true;
    }



    T* checkout() {
        size_t current_head = m_head.load(std::memory_order_relaxed);
        size_t current_tail = m_tail.load(std::memory_order_acquire);
        size_t next_head = (current_head + 1) % m_cap;

        if (next_head == current_tail) {
            return nullptr;
        }
        
        return &m_buf[current_head];
    }

    void commit() {
        size_t current_head = m_head.load(std::memory_order_relaxed);
        size_t next_head    = (current_head + 1) % m_cap;

        m_init[current_head] = true; /* Mark as initialized */
        m_head.store(next_head, std::memory_order_release);
    }
    
public:
    alignas(kCacheLineBytes) std::atomic<size_t> m_head{0};
    alignas(kCacheLineBytes) std::atomic<size_t> m_tail{0};
    size_t                                       m_cap;
    T*                                           m_buf;
    std::unique_ptr<bool[]>                      m_init;
    std::allocator<T>                            m_alloc;
};
