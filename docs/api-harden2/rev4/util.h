/*
 * util.h -- harden2 API v2.3 (2026-09-24). Module util/: standalone helpers that
 * several modules share (owner ruling 2026-09-23: a helper used by more than one module
 * lives here).
 *
 * guarded.py holds the ONLY try/except blocks around third-party calls: ONE per failure
 * domain (HTTP, JSON, filesystem, asyncio streams). Each turns the throw into a status.
 * The one other catch in the app is runtime/fatal.py's crash-path cleanup loop.
 *  */
#ifndef __HARDEN2_API_UTIL_H__
#define __HARDEN2_API_UTIL_H__
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/* ---- OS primitives: the ONLY opaque types in these headers (python: threading.Lock,
 * threading.Event, threading.Condition, threading.Thread, queue.Queue). Every other
 * struct shows
 * its data members: each member is one attribute of the Python class named beside it. */
typedef struct OsLock OsLock;
typedef struct OsEvent OsEvent;
typedef struct OsCondition OsCondition;
typedef struct OsThread OsThread;
typedef struct OsQueue OsQueue;

/* ---- guarded third-party calls (guarded.py) ---- */
/*
 * @code:
 *     the HTTP status of ANY reply; 0 = no reply
 * @body:
 *     caller-owned buffer
 * @error:
 *     why there was no reply
 */
typedef struct {
	int32_t code;
	char*   body;
	size_t  bodyLen;
	char    error[128];
} UtilHttpReply;

/* false = no usable reply (refused, reset, ...) */
bool UtilHttpRequest(
	const char* host,
	uint16_t port,
	const char* method,
	const char* path,
	const void* body,
	size_t len,
	const char* const* headers,
	float timeoutS,
	UtilHttpReply* out
);
/* THIRD-PARTY: a parsed JSON value (a Python dict or list) */
typedef struct UtilJson UtilJson;
bool UtilParseJson(const char* text, UtilJson** out);   /* false = not JSON */
/* tmp + rename */
bool UtilAtomicWrite(const char* path, const void* data, size_t len);
bool UtilAppendLine(const char* path, const char* line);   /* fsynced */
bool UtilRename(const char* src, const char* dst);
/* THIRD-PARTY: one asyncio TCP stream (reader, writer) */
typedef struct UtilStream UtilStream;
bool UtilStreamReadLine(UtilStream* s, char* line, size_t cap);   /* false = peer left */

/* ---- net.py ---- */
extern const char* const kUtilJsonHeaders[];   /* {"Content-Type", "application/json"}   */
bool UtilPortOpen(const char* numericIp, uint16_t port, float timeoutS);   /* no throw */

/* ---- process.py ---- */
/* ours + the native lib folder */
const char** UtilNativeEnv(const char* const* extra);
bool         UtilWaitExit(int32_t pid, float timeoutS);   /* poll, never throws */

/* ---- hebrew.py ---- */
extern const char* const kUtilHebrewRange;              /* for a regex character class */
bool UtilIsHebrew(uint32_t codepoint);
/* עשרים וחמישה -> 25 */
void UtilHebnumToDigits(const char* in, char* out, size_t cap);

/* ---- mission.py ---- */
void UtilStepText(const char* stepJson, char* out, size_t cap);   /* "fly_by dz=5.0" */

/* ---- box overlap math (boxes.py; used by sam3/ and perception2/). A box: x1, y1, x2,
 * y2 ---- */
float BoxArea(const float* b);   /* 0 for an inverted box */
float BoxIntersection(const float* a, const float* b);
float BoxIou(const float* a, const float* b);
float BoxInside(const float* a, const float* b);   /* the share of a that lies in b */

#endif /* __HARDEN2_API_UTIL_H__ */
