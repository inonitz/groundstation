#include "async_key.hpp"
#include <cstdarg>
#include <cstdio>


#if defined(UTIL2_OS_LINUX) /* __WSL__ is compile-time defined using cmake */
#	include <regex>
#	include <fstream>
#	include <fcntl.h>
#	include <unistd.h>
#endif
#if defined(UTIL2_OS_LINUX) && defined(__WSL__)
#	include <X11/Xlib.h>
#	include <X11/keysym.h>
#	include <X11/extensions/XInput2.h>
#	include <sys/select.h>
#	include <cstring>
#endif

std::atomic_flag AsyncKeyHook::s_instanceGuard = ATOMIC_FLAG_INIT;
AsyncKeyHook* AsyncKeyHook::s_instance = nullptr;

bool AsyncKeyHook::create() {
	bool expected = false;
	if (!m_running.compare_exchange_strong(expected, true)) {
		return true; // already running
	}

	if (s_instanceGuard.test_and_set()) {
        m_running = false;
        return false; // Instance already exists
    }


	m_exit     = false;
	s_instance = this;
	m_startupComplete = false;
	m_startupSuccess = false;
	m_producer = std::thread(&AsyncKeyHook::producerThread, this);
	m_consumer = std::thread(&AsyncKeyHook::consumerThread, this);
	{
		std::unique_lock<std::mutex> lock(m_queueMtx);
		m_cv.wait(lock, [this]() { return m_startupComplete.load(); });
	}

	if (!m_startupSuccess) { 
		destroy();
		return false;
	}


	return true;
}

void AsyncKeyHook::destroy() {
	if (!m_running.exchange(false)) {
		return; // not running
	}

	m_exit = true;
	m_cv.notify_all();

#if defined(UTIL2_OS_WINDOWS)
	// Wake the consumer, then unblock the producer's GetMessage loop.
	if (m_consumer.joinable())
		m_consumer.join();
	if (m_producerID.load() != 0xFFFFFFFFu) {
		PostThreadMessage(m_producerID.load(), WM_QUIT, 0, 0);
	}
	if (m_producer.joinable())
		m_producer.join();

#elif defined(UTIL2_OS_LINUX)
	// Closing the fd causes read() to return with an error, unblocking the producer.
	if (m_fd != -1) {
		::close(m_fd);
		m_fd = -1;
	}
	if (m_consumer.joinable())
		m_consumer.join();
	if (m_producer.joinable())
		m_producer.join();
#endif

	{
		std::lock_guard<std::mutex> lock(m_queueMtx);
		std::queue<KeyMessage>      empty;
		std::swap(m_keyQueue, empty);
	}

	if (s_instance == this) {
		s_instance = nullptr;
		s_instanceGuard.clear();
	}
	return;
}

void AsyncKeyHook::bindKey(KeyCodeEnum key, Callback cb) {
	std::lock_guard<std::mutex> lock(m_bindingsMtx);
	m_bindings[key] = std::move(cb);
	return;
}

void AsyncKeyHook::unbindKey(KeyCodeEnum key) {
	std::lock_guard<std::mutex> lock(m_bindingsMtx);
	m_bindings.erase(key);
	return;
}

void AsyncKeyHook::dispatch(KeyCodeEnum key, KeyAction pressType) {
	Callback cb    = nullptr;
	Callback anycb = nullptr;
	{
		std::lock_guard<std::mutex> lock(m_bindingsMtx);
		auto it    = m_bindings.find(key);
		auto anyit = m_bindings.find(KeyCodeEnum::Any);
		if (it == m_bindings.end() && anyit == m_bindings.end()) {
			return;
		}

		// copy, so we don't hold the mutex during the call
		cb 	  = (it != m_bindings.end())    ? it->second    : nullptr;
		anycb = (anyit != m_bindings.end()) ? anyit->second : nullptr;
	}
	if (cb) {
		cb(key, pressType);
    }
	if(anycb) {
		anycb(key, pressType);
	}
    return;
}


// =========================================================================
// Windows implementation
// =========================================================================
#if defined(UTIL2_OS_WINDOWS)


BOOL AsyncKeyHook::getErrorMessage(DWORD dwErrorCode, LPTSTR pBuffer, DWORD cchBufferLength) {
	if (cchBufferLength == 0)
		return FALSE;
	DWORD cchMsg = FormatMessage(
	    FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
	    nullptr,
	    dwErrorCode,
	    MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
	    pBuffer,
	    cchBufferLength,
	    nullptr
	);
	return cchMsg > 0;
}


// #if defined(UTIL2_COMPILER_CLANG) || defined(UTIL2_COMPILER_GCC) || defined(__MINGW64__)
// __attribute__((format(printf, 1, 2)))
// #endif
void AsyncKeyHook::printLastError(const char* format, ...) {
	va_list arg_list;
	va_start(arg_list, format);
	vfprintf(stderr, format, arg_list);
	va_end(arg_list);

	thread_local TCHAR errBuf[1024] = {0};
	DWORD        errCode      = GetLastError();
	BOOL         status       = getErrorMessage(errCode, errBuf, 1024);
	fprintf(stderr, "    Optional System Message (Windows errCode=%lu): %s\n", static_cast<unsigned long>(errCode), status ? errBuf : "None");
}

LRESULT CALLBACK AsyncKeyHook::keyboardCallback(int nCode, WPARAM wParam, LPARAM lParam) {
    AsyncKeyHook* self = s_instance;
	KeyAction action = 
		(wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN) ? KeyAction::PRESSED
		:
		(wParam == WM_KEYUP || wParam == WM_SYSKEYUP) ? KeyAction::RELEASED
		:
		KeyAction::UNKNOWN;
    
    if (self && nCode == HC_ACTION && 
		( (action == KeyAction::PRESSED) || (action == KeyAction::RELEASED) )
	) {
        auto* kb = reinterpret_cast<KBDLLHOOKSTRUCT*>(lParam);
		{
			std::lock_guard<std::mutex> lock(self->m_queueMtx);
			self->m_keyQueue.push(KeyMessage{
				kb->vkCode, 
				static_cast<std::uint16_t>(action),
				static_cast<std::uint16_t>(wParam)
			});
		}
		self->m_cv.notify_one();
    }
    
    return CallNextHookEx(nullptr, nCode, wParam, lParam);
}

void AsyncKeyHook::producerThread() {
	m_keyHook = SetWindowsHookEx(
		WH_KEYBOARD_LL,
		&AsyncKeyHook::keyboardCallback,
		GetModuleHandle(nullptr),
		0
	);
	if (m_keyHook == nullptr) {
		printLastError("Error hooking low-level keyboard hook\n");
        m_startupSuccess  = false;
        m_startupComplete = true;
		m_exit = true;
		m_cv.notify_all();
		return;
	}

	m_startupSuccess  = true;
	m_startupComplete = true;
	m_cv.notify_all();
	m_producerID = GetCurrentThreadId();

	MSG msg;
	while (GetMessage(&msg, nullptr, 0, 0)) {
		TranslateMessage(&msg);
		DispatchMessage(&msg);
	}

	if (!UnhookWindowsHookEx(m_keyHook)) {
		fprintf(stderr, "Error unhooking low-level keyboard hook\n");
	}
	m_keyHook = nullptr;
	return;
}

void AsyncKeyHook::consumerThread() {
	m_consumerID = GetCurrentThreadId();

	while (!m_exit) {
		KeyMessage km;
		{
			std::unique_lock<std::mutex> lock(m_queueMtx);
			m_cv.wait(lock, [this]() {
				return !m_keyQueue.empty() || m_exit.load();
			});
			if (m_exit.load() && m_keyQueue.empty())
				break;

			km = m_keyQueue.front();
			m_keyQueue.pop();
		}
		dispatch(
			static_cast<KeyCodeEnum>(km.m_virtualKey),
			static_cast<KeyAction>(km.m_action)
		);
	}
	return;
}


// =========================================================================
// Linux implementation
// =========================================================================
#elif defined(UTIL2_OS_LINUX)
#	if !defined(__WSL__) /* Will be most common */


bool AsyncKeyHook::findDeviceProcKeyboardPath(std::string& out) {
	std::ifstream file("/proc/bus/input/devices");
	if (!file.is_open()) {
		perror("Error opening '/proc/bus/input/devices' (need sudo or correct permissions)");
		return false;
	}

	std::string line, handlers;
	bool        isKeyboard = false;

	while (std::getline(file, line)) {
		if (line.find("EV=120013") != std::string::npos)
			isKeyboard = true;
		if (line.find("Handlers=") != std::string::npos)
			handlers = line;

		if (line.empty()) {
			if (isKeyboard) {
				std::regex  re("event[0-9]+");
				std::smatch match;
				if (std::regex_search(handlers, match, re)) {
					out = "/dev/input/" + match.str();
					return true;
				}
			}
			isKeyboard = false;
			handlers.clear();
		}
	}
	return false;
}

void AsyncKeyHook::producerThread() {
    constexpr ssize_t onErrorBytesRead = -1;
    std::string devicePath;
    struct input_event ev{};
    ssize_t bytesRead     = 0;
    bool 	relevantEvent = false;

    if (!findDeviceProcKeyboardPath(devicePath)) {
        fprintf(stderr, "Couldn't find the keyboard event device\n");
        {
            std::lock_guard<std::mutex> lock(m_queueMtx);
            m_startupSuccess  = false;
            m_startupComplete = true;
        }
        m_cv.notify_all();
        return;
    }

    m_fd = ::open(devicePath.c_str(), O_RDONLY);
    if (m_fd == -1) {
        perror("Cannot open input device");
        {
            std::lock_guard<std::mutex> lock(m_queueMtx);
            m_startupSuccess  = false;
            m_startupComplete = true;
        }
        m_cv.notify_all();
        return;
    }

	std::unique_lock<std::mutex> lock(m_queueMtx);
	m_startupSuccess  = true;
	m_startupComplete = true;
	lock.unlock();
    m_cv.notify_all();

    while (!m_exit) {
        bytesRead = ::read(m_fd, &ev, sizeof(ev));
        if (bytesRead == onErrorBytesRead)
            break;

        relevantEvent = (ev.type == EV_KEY) && (ev.value > -1 && ev.value < 3);
        if (relevantEvent) {
            {
                std::lock_guard<std::mutex> lock(m_queueMtx);
                m_keyQueue.push(KeyMessage{ev.code, static_cast<std::uint8_t>(ev.value), 0});
            }
            m_cv.notify_one();
        }
    }

    if (m_fd != -1) {
        ::close(m_fd);
        m_fd = -1;
    }
    return;
}


#	else /* We're inside Windows-Subsystem for Linux. */
void AsyncKeyHook::producerThread() {
    Display* 		x11DisplayConnection;
    int 			xinExtOpcode;
    int 			xInFirstEventCode;
    int 			xInFirstErrCode;
    int 			x11ConnFd;
    Window 			x11RootWin;
    XIEventMask 	xInpDevEventMasks[1];
    unsigned char   rawKeyEventBitmask[XIMaskLen(XI_LASTEVENT)];
    struct timeval  selectPollingTimeout;
    fd_set 			x11SocketFDSet;
    XEvent 			incomingX11Event;
    XIRawEvent* 	rawKeyEventData;
    bool isGenericEvent 	   = false;
	bool isFromXInputExtension = false;
	bool hasEventData 		   = false;
	bool isKeyPress 		   = false;
	bool isKeyRelease 		   = false;
    std::uint16_t linuxEvDevKeyCode;


    x11DisplayConnection = XOpenDisplay(NULL);
    if (!x11DisplayConnection) {
        fprintf(stderr, "WSL2/X11: Cannot open display.\n");
        {
            std::lock_guard<std::mutex> lock(m_queueMtx);
            m_startupSuccess  = false;
            m_startupComplete = true;
        }
        m_cv.notify_all();
        return;
    }
	
    if (!XQueryExtension(x11DisplayConnection, "XInputExtension", &xinExtOpcode, &xInFirstEventCode, &xInFirstErrCode)) {
        fprintf(stderr, "X11: XInput extension not available.\n");
        {
            std::lock_guard<std::mutex> lock(m_queueMtx);
            m_startupSuccess  = false;
            m_startupComplete = true;
        }
        m_cv.notify_all();
        XCloseDisplay(x11DisplayConnection);
        return;
    }

    {
        std::lock_guard<std::mutex> lock(m_queueMtx);
        m_startupSuccess  = true;
        m_startupComplete = true;
    }
    m_cv.notify_all();

    x11RootWin = DefaultRootWindow(x11DisplayConnection);
    std::memset(rawKeyEventBitmask, 0, sizeof(rawKeyEventBitmask));

    xInpDevEventMasks[0].deviceid = XIAllMasterDevices;
    xInpDevEventMasks[0].mask_len = sizeof(rawKeyEventBitmask);
    xInpDevEventMasks[0].mask = rawKeyEventBitmask;

    XISetMask(rawKeyEventBitmask, XI_RawKeyPress);
    XISetMask(rawKeyEventBitmask, XI_RawKeyRelease);

    XISelectEvents(x11DisplayConnection, x11RootWin, xInpDevEventMasks, 1);
    XSync(x11DisplayConnection, False);

    x11ConnFd = ConnectionNumber(x11DisplayConnection);
    while (!m_exit) {
        selectPollingTimeout.tv_sec = 0;
        selectPollingTimeout.tv_usec = 100000;

        FD_ZERO(&x11SocketFDSet);
        FD_SET(x11ConnFd, &x11SocketFDSet);

        select(x11ConnFd + 1, &x11SocketFDSet, NULL, NULL, &selectPollingTimeout);
        while (XPending(x11DisplayConnection)) {
            XNextEvent(x11DisplayConnection, &incomingX11Event); 

            isGenericEvent 		  = (incomingX11Event.xcookie.type == GenericEvent);
            isFromXInputExtension = (incomingX11Event.xcookie.extension == xinExtOpcode);
            if (!isGenericEvent || !isFromXInputExtension) {
                continue;
            }

            hasEventData = XGetEventData(x11DisplayConnection, &incomingX11Event.xcookie);
            if (!hasEventData) {
                continue;
            }

            isKeyPress  = (incomingX11Event.xcookie.evtype == XI_RawKeyPress);
            isKeyRelease = (incomingX11Event.xcookie.evtype == XI_RawKeyRelease);
            if (!isKeyPress && !isKeyRelease) {
                XFreeEventData(x11DisplayConnection, &incomingX11Event.xcookie);
                continue;
            }

            rawKeyEventData   = static_cast<XIRawEvent*>(incomingX11Event.xcookie.data);
            linuxEvDevKeyCode = static_cast<std::uint16_t>(rawKeyEventData->detail - 8);
            {
                std::lock_guard<std::mutex> lock(m_queueMtx);
                m_keyQueue.push(KeyMessage{
                    linuxEvDevKeyCode, 
                    static_cast<std::uint8_t>(isKeyPress ? KeyAction::PRESSED : KeyAction::RELEASED), 
                    0
                });
            }
            m_cv.notify_one();

            XFreeEventData(x11DisplayConnection, &incomingX11Event.xcookie);
        }
    }

    XCloseDisplay(x11DisplayConnection);
    return;
}
#	endif /* If defined(__WSL__) */


void AsyncKeyHook::consumerThread() {
	while (!m_exit) {
		KeyMessage km;
		{
			std::unique_lock<std::mutex> lock(m_queueMtx);
			m_cv.wait(lock, [this]() {
				return !m_keyQueue.empty() || m_exit.load();
			});
			if (m_exit.load() && m_keyQueue.empty())
				break;

			km = m_keyQueue.front();
			m_keyQueue.pop();
		}
		dispatch(
			static_cast<KeyCodeEnum>(km.m_keyCode),
			static_cast<KeyAction>(km.m_action)
		);
	}


	return;
}


#endif // Platform-specific code
