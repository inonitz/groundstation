#ifndef __ASYNCHRONOUS_KEY_LOGGING_CLASS_DEFINITION_HEADER__
#define __ASYNCHRONOUS_KEY_LOGGING_CLASS_DEFINITION_HEADER__
#include "key_codes.hpp"
#include <atomic>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <queue>
#include <thread>
#include <unordered_map>


#if defined(UTIL2_OS_WINDOWS)
#   define WIN32_LEAN_AND_MEAN
#   include <Windows.h>
#   undef WIN32_LEAN_AND_MEAN
#elif defined(UTIL2_OS_LINUX)
#   include <string>
#endif


class AsyncKeyHook {
public:
    using Callback = std::function<void(KeyCodeEnum, KeyAction)>;

#if defined(UTIL2_OS_WINDOWS)
    using ThreadID = DWORD;
#elif defined(UTIL2_OS_LINUX)
    using ThreadID = std::uint32_t;
#endif

    AsyncKeyHook() = default;
    ~AsyncKeyHook() {
        destroy();
        return;
    }

    // non-copyable, non-movable (holds threads and a global hook)
    AsyncKeyHook(const AsyncKeyHook&)            = delete;
    AsyncKeyHook& operator=(const AsyncKeyHook&) = delete;
    AsyncKeyHook(AsyncKeyHook&&)                 = delete;
    AsyncKeyHook& operator=(AsyncKeyHook&&)      = delete;

    // Start producer/consumer threads and install the OS-level keyboard hook.
    // Returns true on success.
    bool create();

    // Stop threads, uninstall hook and release resources.
    void destroy();

    // Register a callback invoked (on the consumer thread) when `key` is pressed.
    // Replaces any existing callback for the same key.
    void bindKey(KeyCodeEnum key, Callback cb);

    // Remove a previously registered callback (no-op if not bound).
    void unbindKey(KeyCodeEnum key);


private:
    struct KeyMessage { /* Both Representations Fit Into Registers (On x86_64 atleast...) */
#if defined(UTIL2_OS_WINDOWS)
        std::uint32_t m_virtualKey;
        std::uint16_t m_action;
        std::uint16_t m_wParam; /* Low-Level Windows Bit Pattern */
#elif defined(UTIL2_OS_LINUX)
        std::uint16_t m_keyCode;
        std::uint8_t  m_action;
        std::uint8_t  m_reserved; /* Padding to 4 bytes */
#endif
    };

    void producerThread();
    void consumerThread();
    void dispatch(KeyCodeEnum key, KeyAction pressType);

#if defined(UTIL2_OS_WINDOWS)
    static LRESULT CALLBACK keyboardCallback(int nCode, WPARAM wParam, LPARAM lParam);
    static BOOL getErrorMessage(DWORD dwErrorCode, LPTSTR pBuffer, DWORD cchBufferLength);
    static void printLastError(const char* format, ...);
#elif defined(UTIL2_OS_LINUX)
    static bool findDeviceProcKeyboardPath(std::string& out);
#endif

    // Singleton pointer used from the Windows low-level hook callback,
    // which has a C-style signature without user-data.
    static AsyncKeyHook* s_instance;
    static std::atomic_flag s_instanceGuard;

    std::thread             m_producer;
    std::thread             m_consumer;
    std::queue<KeyMessage>  m_keyQueue;
    std::mutex              m_queueMtx;
    std::condition_variable m_cv;
    std::atomic<bool>       m_exit{false};
    std::atomic<bool>       m_running{false};
    std::atomic<bool>       m_startupSuccess{false};
    std::atomic<bool>       m_startupComplete{false};
    std::atomic<ThreadID>   m_producerID{0xFFFFFFFF};
    std::atomic<ThreadID>   m_consumerID{0xFFFFFFFF};

    std::mutex                            m_bindingsMtx;
    std::unordered_map<KeyCodeEnum, Callback> m_bindings;

#if defined(UTIL2_OS_WINDOWS)
    HHOOK m_keyHook{nullptr};
#elif defined(UTIL2_OS_LINUX)
    int   m_fd{-1};
#endif
};


#endif /* __ASYNCHRONOUS_KEY_LOGGING_CLASS_DEFINITION_HEADER__ */
