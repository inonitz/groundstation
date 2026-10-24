/*
 * keys.h -- harden2 API rev3 DRAFT (2026-10-02; split from app.h, owner HDR1). Module keys/
 * (keys/keys.py): the global keys. The keyboard hook (a native process) publishes every key
 * press and release on a ROS2 topic; Keys turns each into one callback. Keys knows nothing
 * about the drone, the screen or vision: the app gives it the two callbacks.
 */
#ifndef __HARDEN2_API_KEYS_H__
#define __HARDEN2_API_KEYS_H__
#include "runtime.h"

/* The key codes that act (config/constants.py; evdev codes). Every other key does nothing:
 * letters are typed in other windows (owner 2026-09-23). */
enum {
	kQuitKeyCode       = 59,              /* F1: quit the app                                */
	kClearKeyCode      = 60,              /* F2: clear the highlights                        */
	kKillKeyCode       = 62,              /* F4: toggle manual mode (the kill key)           */
	kPushToTalkKeyCode = 63               /* F5: hold to talk; its RELEASE starts the timing */
};

typedef void (*KeyFn)(int32_t evdevCode);
typedef struct Keys {                     /* python: keys.keys.Keys                          */
	KeyFn            onKey;               /* called on every key PRESS                       */
	KeyFn            onRelease;           /* called on every key RELEASE; may be NULL        */
	RosSubscription* sub;                 /* the hook's topic, on its own node and thread    */
} Keys;

Keys*      KeysCreate(KeyFn onKey, KeyFn onRelease);
void       KeysClose(Keys* k);
SupProcess KeysProcess(const char* logDir);   /* the keyboard hook: ALWAYS started (F4 needs it) */

#endif /* __HARDEN2_API_KEYS_H__ */
