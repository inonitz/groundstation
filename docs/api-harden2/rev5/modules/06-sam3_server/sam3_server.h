/* sam3_server.h -- the SAM3 detector process and its client: the process's spec, the
 * two messages on its Unix domain socket, and one detect request per call.
 * Rulings: T6, S1, S2, FB2, FB4, RVW3, RVW4, RVW5, SYS1, RUN9, RUN15, RUN16, LLM1, REV8,
 * PRF7, RCD1 to RCD4, TR17 (docs/spec-harden2-cleanup.md). */
#ifndef __HARDEN2_SAM3_SERVER_H__
#define __HARDEN2_SAM3_SERVER_H__

#include <assert.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>

#include "monotonic_clock.h"
#include "recorder.h"
#include "runtime.h"

/* ============================ 1. the process =============================== */

enum {
	kSam3ServerArgvMax = 16,
	kSam3ServerNumberBytes = 16,
	kSam3ServerSocketPathBytes = 108,
	kSam3ServerPathBytes = 4096
};

#define SAM3_SERVER_NAME              "sam3"
#define SAM3_SERVER_SOCKET_FILE       "sam3.sock"
#define SAM3_SERVER_READY_TIMEOUT_NS  UINT64_C(120000000000)
#define SAM3_SERVER_GRACE_NS          UINT64_C(10000000000)
#define SAM3_SERVER_SEND_TIMEOUT_NS   UINT64_C(1000000000)

/* SIGINT: the pass in flight is answered, then the process exits 0; no second signal;
 * the kill after 10 s, logged */
extern const ProcessStopPolicy kSam3ServerStopPolicy;

/* every value from config but the session's: m_python is the app's own interpreter,
 * m_projectDir is config.PROJECT_DIR, m_weightsDir is config.SAM3_NF4_DIR, m_framesFd
 * is FramebufferDescriptor()
 * @m_socketPath: <sessionDir>/sam3.sock; a longer path than sun_path holds is our bug,
 *                and Sam3ServerSettingsFromConfig dies at start */
typedef struct {
	const char* m_python;
	const char* m_projectDir;
	const char* m_weightsDir;
	const char* m_sessionDir;
	int32_t     m_framesFd;
	char        m_socketPath[kSam3ServerSocketPathBytes];
} Sam3ServerSettings;

/* the strings the spec points to; the app holds this until SupervisorDestroy, since the
 * probe's context points into it */
typedef struct {
	Sam3ServerSettings m_settings;
	const char*        m_argv[kSam3ServerArgvMax];
	const char*        m_env[2];
	int32_t            m_passFds[1];
	char               m_framesFdText[kSam3ServerNumberBytes];
	char               m_pythonPathEntry[kSam3ServerPathBytes];
	char               m_logPath[kSam3ServerPathBytes];
} Sam3ServerSpecText;

Sam3ServerSettings Sam3ServerSettingsFromConfig(
	const char* sessionDir,
	int32_t framesFd
);

/* pure: fills text and returns the spec; launches nothing (RUN9). argv: m_python -m
 * sam3.server --session --socket --frames-fd --weights; one env addition,
 * PYTHONPATH=m_projectDir (RUN16), so the launch needs no working folder; m_passFds the
 * frame block's memfd (RUN15); Sam3ServerConnectProbe; 120 s to ready;
 * kSam3ServerStopPolicy; BUDGET_SPENT_DIE; the log <logDir>/proc-sam3.log */
ProcessSpec Sam3ServerProcessSpec(
	const Sam3ServerSettings* settings,
	const char* logDir,
	Sam3ServerSpecText* text
);

/* a connect to the socket, then a close, under SUPERVISOR_READY_PROBE_CALL_NS: true
 * when the connect completes. The server binds only after the load and the warm pass,
 * so a completed connect means ready; the kernel completes it in the listen backlog,
 * also during a pass. No socket file and a refused connect are false. ctx is the
 * Sam3ServerSpecText */
bool Sam3ServerConnectProbe(void* ctx);

/* ============================ 2. the messages ============================== */

/* OPEN 1: kSam3MaxMasks, the masks a reply carries.
 * kSam3MaxConcepts: the synonym table's widest entry is 7 concepts. kSam3MaxBoxes is
 * config SAM3_MAX_BOXES_PER_QUERY; kSam3QueueCapacity is config VISION_MAX_ACTIVE_TASKS,
 * one request outstanding per pool thread (RVW3); a test holds them equal */
enum {
	kSam3MaxConcepts = 8,
	kSam3ConceptBytes = 128,
	kSam3MaxBoxes = 128,
	kSam3MaxMasks = 3,
	kSam3QueueCapacity = 8
};

typedef uint32_t Sam3RequestId;
typedef uint8_t  Sam3Count;
typedef uint8_t  Sam3PriorityByte;   /* holds a Sam3Priority */
typedef uint8_t  Sam3StatusByte;     /* holds a Sam3Status   */

/* a command (a gate, a verify, a count) runs before any refresh of a live highlight;
 * within one priority, in arrival order */
typedef enum {
	SAM3_PRIORITY_COMMAND,
	SAM3_PRIORITY_REFRESH
} Sam3Priority;

/* one English concept, UTF-8, NUL-padded; the client cuts a longer one at its last
 * word boundary within kSam3ConceptBytes - 1 bytes. That bounds the message; SAM3's own
 * limit is 32 tokens, and the server's tokenizer cuts there */
typedef struct {
	char m_text[kSam3ConceptBytes];
} Sam3Concept;

/* the request, byte for byte, little-endian; one request per connection. The frame is
 * named by its sequence number; the job holds that slot until the reply (RVW3) */
typedef struct {
	uint8_t          m_pad0;
	Sam3PriorityByte m_priority;
	Sam3Count        m_conceptCount;
	Sam3Count        m_maxMasks;
	Sam3RequestId    m_requestId;
	uint32_t         m_frameSequence;
	float            m_scoreFloor;
	Sam3Concept      m_concepts[kSam3MaxConcepts];
} Sam3Request;

/*
 * @SAM3_STATUS_FRAME_GONE:
 *     no slot holds m_frameSequence: the writer reused it after the job released it
 * @SAM3_STATUS_INVALID_REQUEST:
 *     a priority out of range; a count past its limit; a concept without its NUL
 */
typedef enum {
	SAM3_STATUS_OK,
	SAM3_STATUS_FRAME_GONE,
	SAM3_STATUS_INVALID_REQUEST
} Sam3Status;

/* corners in pixels, clamped to the frame; m_concept indexes the request's concepts.
 * The boxes come sorted by score, duplicates merged (TR17): one object found under two
 * concepts is one box; mask k belongs to box k */
typedef struct {
	uint16_t  m_x1;
	uint16_t  m_y1;
	uint16_t  m_x2;
	uint16_t  m_y2;
	float     m_score;
	Sam3Count m_concept;
	uint8_t   m_pad[3];
} Sam3Box;

/* the reply, one fixed layout: this header; kSam3MaxBoxes Sam3Box, the first
 * m_boxCount valid, the rest zero; m_maskCount masks of m_maskSize bytes each, one byte
 * per pixel, 0 or nonzero, from byte 2056; then the server closes the connection. An OK
 * reply is 2056 + m_maskCount x width x height bytes; any other status is the 8-byte
 * header alone; a count short of its status's length is SAM3_CLOSED. m_maskSize is the
 * frame block's size, never a config value */
typedef struct {
	Sam3StatusByte m_status;
	Sam3Count      m_boxCount;
	Sam3Count      m_maskCount;
	uint8_t        m_pad;
	FrameSize      m_maskSize;
} Sam3ReplyHeader;

static_assert(sizeof(Sam3Request) == 1040, "a request is 1040 bytes");
static_assert(sizeof(Sam3Box) == 16, "a box is 16 bytes");
static_assert(sizeof(Sam3ReplyHeader) == 8, "a reply header is 8 bytes");

/* ============================ 3. the client ================================ */

/* how one request ended; every value but SAM3_OK is a false return
 * @SAM3_REFUSED:
 *     no server listens: the model loads, the process relaunches, or it is down
 * @SAM3_CLOSED:
 *     the connection closed or was reset before the whole reply (0 bytes, a short
 *     count, ECONNRESET, EPIPE): the server stopped, or died of a GPU out-of-memory
 * @SAM3_TIMEOUT:
 *     a system call waited the caller's timeout: the connect on a full backlog, the
 *     send, or the one read of the reply; the client closed the socket
 * @SAM3_FRAME_GONE:
 *     the server found no slot with the sequence: the caller did not hold it
 * @SAM3_INVALID_REQUEST:
 *     the server refused the request's fields
 * @SAM3_INVALID_REPLY:
 *     a count past its limit; masks larger than the caller's buffer
 */
typedef enum {
	SAM3_OK,
	SAM3_REFUSED,
	SAM3_CLOSED,
	SAM3_TIMEOUT,
	SAM3_FRAME_GONE,
	SAM3_INVALID_REQUEST,
	SAM3_INVALID_REPLY
} Sam3Result;

/* the caller's memory for the masks, given before the call, a new one per request:
 * mask k at k times width times height */
typedef struct {
	uint8_t* m_bytes;
	uint64_t m_capacityBytes;
} Sam3MaskBuffer;

/* the caller's, filled by every request; m_masks is given by the caller;
 * m_requestId is the client's own number for this request, kept from the send */
typedef struct {
	Sam3Result     m_result;
	Sam3RequestId  m_requestId;
	Sam3Count      m_boxCount;
	Sam3Box        m_boxes[kSam3MaxBoxes];
	Sam3Count      m_maskCount;
	FrameSize      m_maskSize;
	Sam3MaskBuffer m_masks;
} Sam3Reply;

/* the app owns it; no socket lives past a request; the client never reads a status
 * row: the reply is the truth
 * @m_nextRequestId: the join key of SPAN_SAM3_REQUEST and SPAN_SAM3_PASS; one add per
 *                   request, from any pool thread */
typedef struct {
	char                  m_socketPath[kSam3ServerSocketPathBytes];
	_Atomic Sam3RequestId m_nextRequestId;
} Sam3Client;

Sam3Client* Sam3ClientCreate(const char* socketPath);
void        Sam3ClientDestroy(Sam3Client* c);   /* after every pool thread is joined */

/* any thread; the client sets m_requestId on its own copy of the request, and bounds
 * its concepts; one connection per request. The socket stays blocking with SO_SNDTIMEO
 * and SO_RCVTIMEO of timeoutNs, so each system call waits up to timeoutNs (Python: never
 * settimeout). The whole reply is one read: recvmsg into the header, the boxes and
 * m_masks with MSG_WAITALL, ended by the server's close; one GIL release. It records
 * nothing: the caller times the call (PHN1) and records SPAN_SAM3_REQUEST with
 * m_requestId. FRAME_GONE, INVALID_REQUEST and INVALID_REPLY are our bugs: the caller
 * dies (RVW4) */
bool Sam3ClientDetect(
	Sam3Client* c,
	const Sam3Request* request,
	uint64_t timeoutNs,
	Sam3Reply* reply
);

/* ============================ 4. the record ================================ */

/* SPAN_SAM3_PASS, in the server's own process (record-sam3-<pid>.jsonl): req; wait, ms
 * from the request's read to the pass's start; boxes. The keys of the former
 * record_sam3.h, the former perf_record_sam3.h */
void RecordSam3Pass(
	MonotonicNs start,
	MonotonicNs end,
	Sam3RequestId req,
	float waitMs,
	uint32_t boxes
);

#endif
