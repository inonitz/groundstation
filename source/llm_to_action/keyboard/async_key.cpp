#include "async_key.hpp"
#include <cstdarg>
#include <cstdio>


#if defined(UTIL2_OS_LINUX) && !defined(__WSL__) /* __WSL__ is compile-time defined using cmake */
#	define ASYNC_KEY_OS_LINUX
#	include <regex>
#	include <fstream>
#	include <fcntl.h>
#	include <unistd.h>
#	include <sys/poll.h>
#	include <sys/eventfd.h>
#	include <sys/ioctl.h>
#endif
#if defined(UTIL2_OS_LINUX) && defined(__WSL__)
#	define ASYNC_KEY_OS_LINUX_WSL
#	include <X11/Xlib.h>
#	include <X11/keysym.h>
#	include <X11/extensions/XInput2.h>
#	include <sys/select.h>
#	include <cstring>
#endif

std::atomic_flag 		   AsyncKeyHook::s_instanceGuard = ATOMIC_FLAG_INIT;
std::atomic<AsyncKeyHook*> AsyncKeyHook::s_instance = nullptr;


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
	// Wake the consumer, then unblock the producer's GetMessage loop
	if (m_keyHook) {
		HHOOK _ = m_keyHook;
		m_keyHook = nullptr; // Prevent producerThread from unhooking again
		if(!UnhookWindowsHookEx(_)) {
			printLastError(
				"[HOOK_DBG] Failed to unhook m_keyHook using UnhookWindowsHookEx\n"
			);
		}
	}
	if (m_consumer.joinable())
		m_consumer.join();
	if (m_producerID.load() != 0xFFFFFFFFu) {
		PostThreadMessage(m_producerID.load(), WM_QUIT, 0, 0);
	}
	if (m_producer.joinable())
		m_producer.join();

#elif defined(UTIL2_OS_LINUX)
	/* 
		fd[0] is an event signal for producerThread to exit. 
		Because ::poll() is blocking, we need to somehow manually exit from it.
		Writing to fd[0] causes the thread to wake up once again, handling the exit gracefully.
	*/
	if(m_wakeupFd.load() != -1) {
		const uint64_t kWakeSignal = 1;
		write(m_wakeupFd.load(), &kWakeSignal, sizeof(uint64_t));
	}
	/* Let each thread handle its own cleanup */
	if (m_consumer.joinable())
		m_consumer.join();
	if (m_producer.joinable())
		m_producer.join();


	for(auto& fd : m_fds) {
		if(fd != -1) {
			::close(fd);
			fd = -1;
		}
	}
	m_fds.clear();
	::close(m_wakeupFd.load());
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
	fprintf(stderr, "[HOOK_DBG] Bound KeyCode: %d\n", static_cast<int>(key));
	return;
}

void AsyncKeyHook::unbindKey(KeyCodeEnum key) {
	std::lock_guard<std::mutex> lock(m_bindingsMtx);
	m_bindings.erase(key);
	return;
}

void AsyncKeyHook::dispatch(KeyCodeEnum key, KeyAction pressType) {
	fprintf(stderr, "[HOOK_DBG] Dispatching KeyCode: %d, Action: %d\n", 
		static_cast<int>(key), 
		static_cast<int>(pressType)
	);
	Callback cb    = nullptr;
	Callback anycb = nullptr;
	{
		std::lock_guard<std::mutex> lock(m_bindingsMtx);
		auto it    = m_bindings.find(key);
		auto anyit = m_bindings.find(KeyCodeEnum::Any);
		if (it == m_bindings.end() && anyit == m_bindings.end()) {
			fprintf(stderr, "[HOOK_DBG] KeyCode %d NOT BOUND -> Dropping event\n", 
				static_cast<int>(key)
			);
			return;
		}

		// copy, so we don't hold the mutex during the call
		cb 	  = (it != m_bindings.end())    ? it->second    : nullptr;
		anycb = (anyit != m_bindings.end()) ? anyit->second : nullptr;
	}
	fprintf(stderr, "[HOOK_DBG] Invoking Callback for KeyCode %d...\n", 
		static_cast<int>(key)
	);
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
		{
			std::lock_guard<std::mutex> lock(m_queueMtx);
        	m_startupSuccess  = false;
        	m_startupComplete = true;
		}
		m_exit = true;
		m_cv.notify_all();
		return;
	}


	{
		std::lock_guard<std::mutex> lock(m_queueMtx);
		m_startupSuccess  = true;
		m_startupComplete = true;
	}
	m_cv.notify_all();
	m_producerID = GetCurrentThreadId();

	MSG msg;
	while (GetMessage(&msg, nullptr, 0, 0)) {
		TranslateMessage(&msg);
		DispatchMessage(&msg);
	}

	if (m_keyHook != nullptr && !UnhookWindowsHookEx(m_keyHook)) {
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


bool AsyncKeyHook::findAllKeyboardDeviceInfo(std::vector<KeyboardDeviceInfo>& kbInfo) {
    std::ifstream file("/proc/bus/input/devices");
    if (!file.is_open()) {
		return false;
	}
    std::string line, name, path;
    bool isKb = false;

    while (std::getline(file, line)) {
        if (line.find("Name=") != std::string::npos) name = line;
        if (line.find("Handlers=") != std::string::npos) {
			if (line.find("kbd") != std::string::npos) { 
				isKb = true;
			}

            std::smatch m;
            if (std::regex_search(line, m, std::regex("event[0-9]+"))) {
                path = "/dev/input/" + m.str();
            }
        }
        
        /* Blank line means end of device block https://www.kernel.org/doc/html/latest/input/input.html */
        if (line.empty()) {
            if (isKb && !path.empty()) { 
				kbInfo.push_back({name, path}); 
			}
			/* Reset for next block */
            isKb = false; 
			name.clear(); 
			path.clear(); 
        }
    }
    return !kbInfo.empty();
}


/* Great Documentation here: https://www.linuxjournal.com/article/6429 */
constexpr std::size_t kBitsPerByte = 8;
constexpr std::size_t kBitsPerQWord = sizeof(std::uint64_t) * kBitsPerByte;
constexpr std::size_t kQWordMask    = kBitsPerQWord - 1;

inline bool testBit(int bit, const std::vector<std::uint64_t>& array) {
    return (array[bit / kBitsPerQWord] & (1ULL << (bit & kQWordMask))) != 0;
}

inline bool isActuallyKeyboard(int32_t fd) {
    constexpr uint32_t evWords = (EV_MAX / kBitsPerQWord) + 1;
    constexpr uint32_t keyWords = (KEY_MAX / kBitsPerQWord) + 1;

    std::vector<std::uint64_t> evBitmask(evWords, 0);
    std::vector<std::uint64_t> keyBitmask(keyWords, 0);

    if (ioctl(fd, 
		EVIOCGBIT(0, evBitmask.size() * sizeof(std::uint64_t)), 
		evBitmask.data()
	) < 0) {
        return false;
    }
    
    if (!testBit(EV_KEY, evBitmask)) { /* Check if the device supports key movements */
        return false;
    }
	
    if (testBit(EV_REL, evBitmask)) { /* check if device supports relative movement (i.e. mouse) */
        return false; 
    }

    if (ioctl(fd, 
		EVIOCGBIT(EV_KEY, keyBitmask.size() * sizeof(std::uint64_t)), 
		keyBitmask.data()
	) < 0) {
        return false;
    }

    return testBit(KEY_A, keyBitmask) 
		|| testBit(KEY_SPACE, keyBitmask) 
		|| testBit(KEY_ENTER, keyBitmask);
}

void AsyncKeyHook::producerThread() {
    constexpr ssize_t kOnErrFlag = 0;
    std::vector<KeyboardDeviceInfo> kbDevInfoBuf;
	std::vector<pollfd> 		    pollFdBuf;
    struct input_event ev{};
	bool kExitSignalRecv	= false;
	bool kDevDisconnectRecv = false;
	bool kNoEventsRecv 		= false;
    ssize_t bytesRead  = 0;
    bool relevantEvent = false;


	if(!findAllKeyboardDeviceInfo(kbDevInfoBuf)) {
		fprintf(stderr, 
			"[HOOK_DBG] Producer aborted: Device path lookup failed - event device not found\n"
		);
        {
            std::lock_guard<std::mutex> lock(m_queueMtx);
            m_startupSuccess  = false;
            m_startupComplete = true;
        }
        m_cv.notify_all();
        return;
    }


	/* eventfd is crucial for waking up from the ::poll() call below incase of requested-exit */
	m_wakeupFd.store(eventfd(0, EFD_NONBLOCK));
	if (m_wakeupFd.load() == -1) {
        perror("[HOOK_DBG] Failed to create eventfd\n");
        {
            std::lock_guard<std::mutex> lock(m_queueMtx);
            m_startupSuccess  = false;
            m_startupComplete = true;
        }
        m_cv.notify_all();
        return;
    }


	m_fds.clear();
	for (const auto& dev : kbDevInfoBuf) {
		FileDescriptor fd = ::open(dev.path.c_str(), O_RDONLY);
		
		fprintf(stderr, "[HOOK_DBG] ::open(%s) fd = %d (errno: %d)\n", 
			dev.path.c_str(), 
			fd,
			errno
		);
		if(fd != -1 && isActuallyKeyboard(fd)) {
			m_fds.push_back(fd);
		} else if(fd == -1) {
			fprintf(stderr, "[HOOK_DBG] Cannot open input device %d", fd);
			{
				/* trigger init failure inside create() */
				std::lock_guard<std::mutex> lock(m_queueMtx);
				m_startupSuccess  = false;
				m_startupComplete = true;
			}
			m_cv.notify_all();
			return;
		}	
	}


	/* Signal to create() that initialization was successfull. */
	std::unique_lock<std::mutex> lock(m_queueMtx);
	m_startupSuccess  = true;
	m_startupComplete = true;
	lock.unlock();
    m_cv.notify_all();


	/* Prepare file-descriptor buffer for all detected keyboards & exit-notifier */
	pollFdBuf.push_back({m_wakeupFd.load(), POLLIN, 0});
	for(const auto& fd : m_fds) {
		pollFdBuf.push_back({fd, POLLIN, 0});
	}

	while (!m_exit) {
		int ret = ::poll(pollFdBuf.data(), pollFdBuf.size(), -1);
		if (ret < kOnErrFlag) { /* 0 = no event detected. -1 = errors */
			perror("[HOOK_DBG] Polling Error\n");
			break;
		}

		for (const auto& pfd : pollFdBuf) {
			/* Wake signal received from destroy() via eventfd: https://man7.org/linux/man-pages/man2/eventfd.2.html */
			kExitSignalRecv    = (pfd.fd == m_wakeupFd.load() && (pfd.revents & POLLIN) );
			kDevDisconnectRecv = (pfd.revents & (POLLERR | POLLHUP | POLLNVAL) );
			kNoEventsRecv      = (pfd.revents & POLLIN) == 0;
			if (kExitSignalRecv || kDevDisconnectRecv) {
				if(kExitSignalRecv) {
					fprintf(stderr, "[HOOK_DBG] Received Exit Signal. Terminating.\n");
				}
				if(kDevDisconnectRecv) {
					fprintf(stderr, "[HOOK_DBG] Device disconnected. Terminating.\n");
				}
				m_exit = true;
				break;
			}
			if(kNoEventsRecv) {
				continue;
			}

			/* https://man7.org/linux/man-pages/man2/read.2.html */
			bytesRead = ::read(pfd.fd, &ev, sizeof(ev));
			if(bytesRead <= kOnErrFlag) {
				fprintf(stderr, "[HOOK_DBG] Couldn't read from device %d. Skipping\n",
					pfd.fd
				);
				continue;
			}


			fprintf(stderr, "[HOOK_DBG] RAW READ -> Type: 0x%04x, Code: %d, Value: %d\n", 
				ev.type, 
				ev.code, 
				ev.value
			);
			relevantEvent = (ev.type == EV_KEY) && (ev.value > -1 && ev.value < 3);
			if (relevantEvent) {
				{
					std::lock_guard<std::mutex> lock(m_queueMtx);
					m_keyQueue.push(KeyMessage{ev.code, static_cast<std::uint8_t>(ev.value), 0});
					fprintf(stderr, "[HOOK_DBG] Pushed to queue. Queue size: %zu\n", 
						m_keyQueue.size()
					);
				}
				m_cv.notify_one();
			}

		}
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
    XEvent 			incomingX11Event;
    XIRawEvent* 	rawKeyEventData;
    bool isGenericEvent 	   = false;
	bool isFromXInputExtension = false;
	bool hasEventData 		   = false;
	bool isKeyPress 		   = false;
	bool isKeyRelease 		   = false;
    std::uint16_t linuxEvDevKeyCode;
	std::vector<pollfd> pollFds;


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
	
    if (!XQueryExtension(x11DisplayConnection, 
		"XInputExtension", 
		&xinExtOpcode, 
		&xInFirstEventCode, 
		&xInFirstErrCode)
	) {
        perror("X11: XInput extension not available.\n");
        {
            std::lock_guard<std::mutex> lock(m_queueMtx);
            m_startupSuccess  = false;
            m_startupComplete = true;
        }
        m_cv.notify_all();
        XCloseDisplay(x11DisplayConnection);
        return;
    }

	/* Same trick from the normal linux version of the code */
	m_wakeupFd.store(eventfd(0, EFD_NONBLOCK));
	if (m_wakeupFd.load() == -1) {
        perror("[HOOK_DBG] Failed to create eventfd\n");
        {
            std::lock_guard<std::mutex> lock(m_queueMtx);
            m_startupSuccess  = false;
            m_startupComplete = true;
        }
        m_cv.notify_all();
        return;
    }


	/* We finally finished state initialization */
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

	pollFds.clear();
	pollFds.push_back({m_wakeupFd.load(), POLLIN, 0});
	pollFds.push_back({ConnectionNumber(x11DisplayConnection) , POLLIN, 0});
    while (!m_exit) {
		auto ret = ::poll(pollFds.data(), pollFds.size(), -1);
		if (ret < 0) { /* 0 = no event detected. -1 = errors */
			perror("[HOOK_DBG] Polling Error\n");
			break;
		}

		if( (pollFds[0].revents & POLLIN) ) {
			m_exit = true;
			break;
		}

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
