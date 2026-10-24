/*
 * keys.h -- harden2 API rev4 DRAFT (2026-10-02; split from app.h, owner HDR1). Module
 * keys/ (keys/keys.py): the global keys. The keyboard hook (a native process) publishes
 * every key press and release on a ROS2 topic; Keys turns each into one callback. Keys
 * knows nothing about the drone, the screen or vision: the app gives it the two
 * callbacks.
 *  */
#ifndef __HARDEN2_API_KEYS_H__
#define __HARDEN2_API_KEYS_H__
#include "runtime.h"

/* The key codes that act (config/constants.py; evdev codes). Every other key does
 * nothing: letters are typed in other windows (owner 2026-09-23). */
/*
 * @kPushToTalkKeyCode:
 *     F5: hold to talk; its RELEASE starts the timing
 */
enum {
	kQuitKeyCode = 59,
	kClearKeyCode = 60,
	kKillKeyCode = 62,
	kPushToTalkKeyCode = 63
};

typedef void (*KeyFn)(int32_t evdevCode);
/* python: keys.keys.Keys */
/*
 * @onKey:
 *     called on every key PRESS
 * @onRelease:
 *     called on every key RELEASE; may be NULL
 * @sub:
 *     the hook's topic, on its own node and thread
 */
typedef struct Keys {
	KeyFn            onKey;
	KeyFn            onRelease;
	RosSubscription* sub;
} Keys;

Keys* KeysCreate(KeyFn onKey, KeyFn onRelease);
void  KeysClose(Keys* k);
/* the keyboard hook: ALWAYS started (F4 needs it) */
ProcessSpec KeysProcess(const char* logDir);

#endif /* __HARDEN2_API_KEYS_H__ */
