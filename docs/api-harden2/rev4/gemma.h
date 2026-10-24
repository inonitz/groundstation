/*
 * gemma.h -- harden2 API rev4 DRAFT (2026-10-02). Module gemma/: the ONE Gemma of the
 * app. The app starts ONE llama-server, ONCE, and gets ONE handle. The recognizer and
 * the vision system both get that same handle. Nobody "creates" Gemma a second time and
 * nobody "closes" it: the supervisor stops the server with every other process.
 *  */
#ifndef __HARDEN2_API_GEMMA_H__
#define __HARDEN2_API_GEMMA_H__
#include "runtime.h"

/*
 * @server:
 *     the supervised llama-server; NULL when attached
 * @port:
 *     it answers on 127.0.0.1:port
 */
typedef struct Gemma {
	Process* server;
	uint16_t port;
} Gemma;

/* Called ONCE by the app at start: launches the server under the supervisor. */
Gemma* GemmaStartServer(Supervisor* s, const char* logDir, uint16_t port, bool thinking);
/* A benchmark only: use a server that is already running on `port`; nothing is
 *     launched. */
Gemma* GemmaAttach(uint16_t port);
/* llama-server's own times for one request */
typedef struct {
	uint32_t cachedTokens;
	uint32_t promptTokens;
	uint32_t answerTokens;
	float    promptMs;
	float    answerMs;
} GemmaTimings;

/* One chat request. false = no answer, a timeout, or a reply that is not valid: the
 * CALLER reports "gemma failed"; it is never "the user said something invalid".
 * Thread-safe. */
bool GemmaRequest(
	Gemma* g,
	const char* messagesJson,
	const char* grammar,
	uint32_t maxTokens,
	float timeoutS,
	char* reply,
	size_t cap,
	GemmaTimings* timings
);
#endif
