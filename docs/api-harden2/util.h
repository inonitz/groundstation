/*
 * util.h -- harden2 API v2.3 (2026-09-24). Module util/: standalone helpers that several
 * modules share (owner ruling 2026-09-23: a helper used by more than one module lives here).
 *
 * guarded.py holds the ONLY try/except blocks around third-party calls: ONE per failure
 * domain (HTTP, JSON, filesystem, asyncio streams). Each turns the throw into a status.
 * The one other catch in the app is system/fatal.py's crash-path cleanup loop.
 */
#ifndef __HARDEN2_API_UTIL_H__
#define __HARDEN2_API_UTIL_H__
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/* ---- guarded third-party calls (guarded.py) ---- */
typedef struct {
	int32_t code;                         /* the HTTP status of ANY reply; 0 = no reply     */
	char*   body;                         /* caller-owned buffer                             */
	size_t  bodyLen;
	char    error[128];                   /* why there was no reply                          */
} UtilHttpReply;
bool UtilHttpRequest(const char* host, uint16_t port, const char* method, const char* path,
	const void* body, size_t len, const char* const* headers, float timeoutS,
	UtilHttpReply* out);                  /* false = no usable reply (refused, reset, ...)  */
typedef struct UtilJson UtilJson;         /* an opaque parsed document                       */
bool UtilParseJson(const char* text, UtilJson** out);            /* false = not JSON      */
bool UtilAtomicWrite(const char* path, const void* data, size_t len);  /* tmp + rename  */
bool UtilAppendLine(const char* path, const char* line);        /* fsynced              */
bool UtilRename(const char* src, const char* dst);
typedef struct UtilStream UtilStream;     /* one asyncio TCP stream                          */
bool UtilStreamReadLine(UtilStream* s, char* line, size_t cap);  /* false = peer left    */

/* ---- net.py ---- */
extern const char* const kUtilJsonHeaders[];   /* {"Content-Type", "application/json"}   */
bool UtilPortOpen(const char* numericIp, uint16_t port, float timeoutS);   /* no throw  */

/* ---- process.py ---- */
const char** UtilNativeEnv(const char* const* extra);   /* ours + the native lib folder */
bool UtilWaitExit(int32_t pid, float timeoutS);         /* poll, never throws           */

/* ---- hebrew.py ---- */
extern const char* const kUtilHebrewRange;              /* for a regex character class */
bool UtilIsHebrew(uint32_t codepoint);
void UtilHebnumToDigits(const char* in, char* out, size_t cap);   /* עשרים וחמישה -> 25 */

/* ---- mission.py ---- */
void UtilStepText(const char* stepJson, char* out, size_t cap);   /* "fly_by dz=5.0"    */

#endif /* __HARDEN2_API_UTIL_H__ */
