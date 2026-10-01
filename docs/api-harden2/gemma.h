/*
 * gemma.h -- harden2 API v2.4 (2026-09-26). Module gemma/: Gemma's process (ONE spec for
 * the app and the benches, owner ruling 2026-09-23) and the ONE client. It holds no task
 * code: the recognizer's and perception's prompts stay with them.
 */
#ifndef __HARDEN2_API_GEMMA_H__
#define __HARDEN2_API_GEMMA_H__
#include "runtime.h"

/* The supervised llama-server: a laptop part (3 restarts, then die). A bench passes its
 * own port so it never collides with the app's. */
/* @warmUp: NULL, or one request run once /health answers, before the row turns UP (owner
 * L1: the app passes the recognizer's warm-up plan; a restart warms again). */
SupProcess GemmaProcess(const char* logDir, uint16_t port, bool thinking, void (*warmUp)(void));

typedef struct Gemma Gemma;
typedef struct Perf Perf;
Gemma* GemmaCreate(uint16_t port, Perf* perf);   /* perf: a "gemma" record per request */
void   GemmaClose(Gemma* g);
/* true = reply filled. false = no answer, timeout, or a malformed body: the CALLER reports
 * it ("gemma-failed"), never as "the user said something invalid". Thread-safe. */
/* @label: the name in the "gemma" perf record ("plan", "vision", ...). */
bool GemmaRequest(Gemma* g, const char* messagesJson, const char* grammar,
	uint32_t maxTokens, float timeoutS, const char* label, char* reply, size_t cap);

#endif /* __HARDEN2_API_GEMMA_H__ */
