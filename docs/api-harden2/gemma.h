/*
 * gemma.h -- harden2 API v2.3 (2026-09-24). Module gemma/: Gemma's process (ONE spec for
 * the app and the benches, owner ruling 2026-09-23) and the ONE client. It holds no task
 * code: the recognizer's and perception's prompts stay with them.
 */
#ifndef __HARDEN2_API_GEMMA_H__
#define __HARDEN2_API_GEMMA_H__
#include "system.h"

/* The supervised llama-server: a laptop part (3 restarts, then die). A bench passes its
 * own port so it never collides with the app's. */
SupProcess GemmaProcess(const char* logDir, uint16_t port, bool thinking);

typedef struct Gemma Gemma;
Gemma* GemmaCreate(uint16_t port);
void   GemmaClose(Gemma* g);
/* true = reply filled. false = no answer, timeout, or a malformed body: the CALLER reports
 * it ("gemma-failed"), never as "the user said something invalid". Thread-safe. */
bool GemmaRequest(Gemma* g, const char* messagesJson, const char* grammar,
	uint32_t maxTokens, float timeoutS, char* reply, size_t cap);

#endif /* __HARDEN2_API_GEMMA_H__ */
