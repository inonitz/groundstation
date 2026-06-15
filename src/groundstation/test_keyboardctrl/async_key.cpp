#include "async_key.hpp"
#include <cstdarg>
#include <cstdio>
#if defined(UTIL2_OS_LINUX)
#	include <regex>
#	include <fstream>
#	include <linux/input.h>
#	include <fcntl.h>
#	include <unistd.h>
#endif


AsyncKeyHook* AsyncKeyHook::s_instance = nullptr;

bool AsyncKeyHook::create() {
	bool expected = false;
	if (!m_running.compare_exchange_strong(expected, true)) {
		return true; // already running
	}

	m_exit     = false;
	s_instance = this;

	m_producer = std::thread(&AsyncKeyHook::producerThread, this);
	m_consumer = std::thread(&AsyncKeyHook::consumerThread, this);
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
	}
	return;
}

void AsyncKeyHook::bindKey(KeyCode key, Callback cb) {
	std::lock_guard<std::mutex> lock(m_bindingsMtx);
	m_bindings[key] = std::move(cb);
	return;
}

void AsyncKeyHook::unbindKey(KeyCode key) {
	std::lock_guard<std::mutex> lock(m_bindingsMtx);
	m_bindings.erase(key);
	return;
}

void AsyncKeyHook::dispatch(KeyCode key) {
	Callback cb    = nullptr;
	Callback anycb = nullptr;
	{
		std::lock_guard<std::mutex> lock(m_bindingsMtx);
		auto                        it    = m_bindings.find(key);
		auto 						anyit = m_bindings.find(KeyCode::Any);
		if (it == m_bindings.end() && anyit == m_bindings.end()) {
			return;
		}

		// copy, so we don't hold the mutex during the call
		cb 	  = (it != m_bindings.end())    ? it->second    : nullptr;
		anycb = (anyit != m_bindings.end()) ? anyit->second : nullptr;
	}
	if (cb) {
		cb(key);
    }
	if(anycb) {
		anycb(key);
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

	static TCHAR errBuf[1024] = {0};
	DWORD        errCode      = GetLastError();
	BOOL         status       = getErrorMessage(errCode, errBuf, 1024);
	fprintf(stderr, "    Optional System Message (Windows errCode=%lu): %s\n", static_cast<unsigned long>(errCode), status ? errBuf : "None");
}

LRESULT CALLBACK AsyncKeyHook::keyboardCallback(int nCode, WPARAM wParam, LPARAM lParam) {
	AsyncKeyHook* self = s_instance;
	if (self && nCode == HC_ACTION &&
	    (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN)) {
		auto* kb = reinterpret_cast<KBDLLHOOKSTRUCT*>(lParam);
		{
			std::lock_guard<std::mutex> lock(self->m_queueMtx);
			self->m_keyQueue.push(KeyMessage{static_cast<std::uint16_t>(wParam), kb->vkCode});
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
		m_exit = true;
		m_cv.notify_all();
		return;
	}
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
		dispatch(static_cast<KeyCode>(km.m_virtualKey));
	}
	return;
}

// =========================================================================
// Linux implementation
// =========================================================================
#elif defined(UTIL2_OS_LINUX)

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
	std::string       devicePath;

	if (!findDeviceProcKeyboardPath(devicePath)) {
		fprintf(stderr, "Couldn't find the keyboard event device\n");
		m_exit = true;
		m_cv.notify_all();
		return;
	}

	m_fd = ::open(devicePath.c_str(), O_RDONLY);
	if (m_fd == -1) {
		perror("Cannot open input device");
		m_exit = true;
		m_cv.notify_all();
		return;
	}

	struct input_event ev;
	while (!m_exit) {
		ssize_t bytesRead = ::read(m_fd, &ev, sizeof(ev));
		if (bytesRead == onErrorBytesRead)
			break;

		if (ev.type == EV_KEY && ev.value == 1) {
			{
				std::lock_guard<std::mutex> lock(m_queueMtx);
				m_keyQueue.push(KeyMessage{static_cast<std::uint16_t>(ev.value), ev.code});
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
		dispatch(static_cast<KeyCode>(km.m_keyCode));
	}


	return;
}


#endif // Platform-specific code