/* llama_server.h -- the app's one llama-server process (Gemma 4 E4B) and its client:
 * the process's spec, and the chat requests, one slot per caller.
 * Rulings: PROC2, OWN1, REC1, RUN9, RVW4, RVW5, SYS1, TEL4, PHN1; D1 to D4, D8. */
#ifndef __HARDEN2_LLAMA_SERVER_H__
#define __HARDEN2_LLAMA_SERVER_H__

#include <stdbool.h>
#include <stdint.h>

#include "record_field.h"
#include "record_span.h"
#include "monotonic_clock.h"
#include "recorder.h"
#include "runtime.h"

/* ============================ 1. the process =============================== */

enum {
	kLlamaServerSlots = 9,
	kLlamaServerArgvMax = 32,
	kLlamaServerEnvMax = 2,
	kLlamaServerNumberBytes = 128,
	kLlamaServerSocketPathBytes = 108,
	kLlamaServerPathBytes = 4096
};

#define LLAMA_SERVER_NAME              "llama"
#define LLAMA_SERVER_SOCKET_FILE       "llama.sock"
#define LLAMA_SERVER_READY_TIMEOUT_NS  UINT64_C(240000000000)
#define LLAMA_SERVER_RETRY_DELAY_NS    UINT64_C(2000000000)
#define LLAMA_SERVER_GRACE_NS          UINT64_C(10000000000)

/* SIGINT; SIGINT again after 2 s (a request in flight ignores the first); the kill after
 * 10 s, logged */
extern const ProcessStopPolicy kLlamaServerStopPolicy;

/* -np kLlamaServerSlots --kv-unified -c m_contextTokens (8192): a slot per caller, the
 * pool of 8 vision jobs plus the one planner, in one shared KV pool (D2); the values of
 * the command line, every one from config but m_socketPath; thinking is
 * always off (--jinja, --chat-template-kwargs {"enable_thinking":false},
 * --reasoning-budget 0); the KV cache keeps its default type; --image-min-tokens is
 * never passed; --cache-ram m_cacheRamMib bounds the prompt cache in host RAM; --host
 * m_socketPath, a Unix domain socket in the session folder (D4): no TCP port
 * @m_socketPath: <sessionDir>/llama.sock; a longer path than sun_path holds is our bug,
 *                and LlamaServerSettingsFromConfig dies at start */
typedef struct {
	const char* m_binaryPath;
	const char* m_nativeBinDir;
	const char* m_modelPath;
	const char* m_mmprojPath;
	const char* m_device;
	uint32_t    m_gpuLayers;
	uint32_t    m_contextTokens;
	uint32_t    m_threads;
	uint32_t    m_cacheRamMib;
	char        m_socketPath[kLlamaServerSocketPathBytes];
} LlamaServerSettings;

/* the strings the spec points to; the supervisor copies argv and env at Create; the
 * app holds this until SupervisorDestroy, since the probe's context points into it */
typedef struct {
	LlamaServerSettings m_settings;
	const char*         m_argv[kLlamaServerArgvMax];
	const char*         m_env[kLlamaServerEnvMax];
	char                m_numbers[kLlamaServerNumberBytes];
	char                m_libraryPath[kLlamaServerPathBytes];
	char                m_logPath[kLlamaServerPathBytes];
} LlamaServerSpecText;

LlamaServerSettings LlamaServerSettingsFromConfig(const char* sessionDir);

/* pure: fills text and returns the spec; launches nothing (RUN9). The name "llama"; the
 * probe LlamaServerHealthProbe; 240 s to ready; kLlamaServerStopPolicy;
 * BUDGET_SPENT_DIE; the log <logDir>/proc-llama.log; the socket file removed before
 * each launch (carried to runtime: ProcessSpec.m_removeBeforeLaunch) */
ProcessSpec LlamaServerProcessSpec(
	const LlamaServerSettings* settings,
	const char* logDir,
	LlamaServerSpecText* text
);

/* GET /health on a new connection to m_socketPath, under
 * SUPERVISOR_READY_PROBE_CALL_NS: 200 is true; 503 (the model loads), no socket, a
 * refused connection and a timeout are false; ctx is the LlamaServerSpecText */
bool LlamaServerHealthProbe(void* ctx);

/* ============================ 2. the client ================================ */

/* a reply longer than kLlamaReplyTextBytes is LLAMA_INVALID_REPLY, never cut */
enum {
	kLlamaReplyTextBytes = 16384
};

/* how one request ended; every value but LLAMA_OK is a false return
 * @LLAMA_REFUSED:
 *     no server listens on the socket (no file, or a stale one): down or relaunching
 * @LLAMA_LOADING:
 *     HTTP 503: the server listens and its model still loads
 * @LLAMA_CLOSED:
 *     the connection closed before the reply: the server stopped or crashed
 * @LLAMA_TIMEOUT:
 *     no reply within m_timeoutNs; the client closed the socket; the server cancels
 *     the task within 1 s
 * @LLAMA_CUT:
 *     HTTP 200 with finish_reason "length": the reply stopped at m_maxTokens or at
 *     the context's end
 * @LLAMA_HTTP_ERROR:
 *     any other HTTP status in m_httpStatus
 * @LLAMA_INVALID_REPLY:
 *     not JSON; no string at choices[0].message.content; longer than
 *     kLlamaReplyTextBytes */
typedef enum {
	LLAMA_OK,
	LLAMA_REFUSED,
	LLAMA_LOADING,
	LLAMA_CLOSED,
	LLAMA_TIMEOUT,
	LLAMA_CUT,
	LLAMA_HTTP_ERROR,
	LLAMA_INVALID_REPLY
} LlamaResult;

/* one chat completion at temperature 0; an image is one content part of the caller's
 * messages, a data:image/jpeg;base64 URL
 * @m_messagesJson: the "messages" array as JSON text, built by the caller
 * @m_grammar:      a GBNF grammar, or NULL for none */
typedef struct {
	const char* m_messagesJson;
	const char* m_grammar;
	uint32_t    m_maxTokens;
	uint64_t    m_timeoutNs;
} LlamaRequest;

/* the server's own timings from the reply's "timings": cached, prompt and predicted
 * tokens; prompt and predicted ms; all zero when the reply has none */
typedef struct {
	uint32_t m_cachedTokens;
	uint32_t m_promptTokens;
	uint32_t m_predictedTokens;
	float    m_promptMs;
	float    m_predictedMs;
} LlamaTimings;

/* the caller's, filled by every request
 * @m_httpStatus: 0 when no HTTP reply came */
typedef struct {
	LlamaResult  m_result;
	int32_t      m_httpStatus;
	LlamaTimings m_timings;
	uint32_t     m_textBytes;
	char         m_text[kLlamaReplyTextBytes];
} LlamaReply;

/* the app owns it; no socket lives past a request: one connection per request; the
 * client never reads a status row: the reply is the truth
 * @m_warmRow: STARTING "cold" from LlamaClientCreate; then written only by
 *             LlamaClientWarmUp; read by the main thread */
typedef struct {
	char      m_socketPath[kLlamaServerSocketPathBytes];
	StatusRow m_warmRow;
} LlamaClient;

LlamaClient* LlamaClientCreate(const char* socketPath);
void LlamaClientDestroy(LlamaClient* c);   /* after every caller thread is joined */

/* any thread; the socket timeout is m_timeoutNs for each step; a reply arrives whole
 * at its end, so the wait is about m_timeoutNs; every caller has its own slot, so no
 * request waits for another (D2); it records nothing: the caller times it (PHN1) */
bool LlamaClientRequest(LlamaClient* c, const LlamaRequest* request, LlamaReply* reply);

/* at start, the app's start thread, after SupervisorWaitUntilReady; after every
 * relaunch, the recognizer worker, when the app puts it on that worker's queue (D1); the
 * request is the planner's warm sentence, built by the recognizer (REC1); the row:
 * STARTING "warming", then UP "warm" or FAILED with the result */
bool LlamaClientWarmUp(LlamaClient* c, const LlamaRequest* warmUp, LlamaReply* reply);

/* ========================= 3. the perf record (TEL4) ======================== */

/* OPEN 1 (P1): how a caller reaches the tracer. Now the caller's own pointer; the
 * client holds none (PHN1). The caller reads MonotonicNow() before and after
 * LlamaClientRequest. "llama_request" (RVW5): req (the caller's turn or job number),
 * label ("plan", "vision", "warmup"), ok, cn, pn, gn, pm, gm; the counts at most
 * m_contextTokens, the times in ms with one decimal; the longest payload 98 bytes */
void RecordLlamaRequest(
	MonotonicNs start,
	MonotonicNs end,
	uint32_t req,
	const char* label,
	bool ok,
	const LlamaTimings* timings
);

#endif
