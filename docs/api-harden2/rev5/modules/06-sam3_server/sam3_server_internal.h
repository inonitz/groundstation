/* sam3_server_internal.h -- the server process behind sam3_server.h: its state, its
 * one thread's loop in order, the pass as steps, the TOCTOU list. */
#ifndef __HARDEN2_SAM3_SERVER_INTERNAL_H__
#define __HARDEN2_SAM3_SERVER_INTERNAL_H__

#include "sam3_server.h"

/* the frame buffer's read-only view (framebuffer.h; that header joins this one at the
 * fold, when its FrameSize goes, RCD2) */
typedef struct FramebufferView FramebufferView;

/* torch: the nf4 model, its processor, and the kept RGB buffer at the frame size */
typedef struct Sam3Model Sam3Model;

typedef int32_t  SocketDescriptor;
typedef uint64_t ArrivalNumber;
typedef uint32_t PendingCount;

/* every connect the backlog can hold: the pool's requests and the probe's */
enum {
	kSam3UnreadCapacity = kSam3QueueCapacity + 1
};

/* ============================ 1. the queue ================================= */

/* one request read, waiting for the GPU
 * @m_readAt: MonotonicNow() when the request was read; the span's wait starts here */
typedef struct {
	Sam3Request       m_request;
	SocketDescriptor  m_connection;
	MonotonicNs m_readAt;
	ArrivalNumber     m_arrival;
} Sam3Pending;

/* a binary heap ordered by (priority, arrival). Full: the loop reads no more requests
 * (Python: a list; the clients bound it, no check) */
typedef struct {
	Sam3Pending   m_entries[kSam3QueueCapacity];
	PendingCount  m_count;
	ArrivalNumber m_nextArrival;
} Sam3PendingQueue;

/* the connections accepted whose request has not arrived yet; each waits in the poll.
 * Full: the loop accepts no more; a later connect waits in the backlog inside its own
 * client's SO_SNDTIMEO */
typedef struct {
	SocketDescriptor m_connections[kSam3UnreadCapacity];
	PendingCount     m_count;
} Sam3UnreadSet;

/* the server's state; one thread, the process's main thread, owns all of it. The
 * recorder's writer is the recorder's own thread
 * @mb_stopping: set by the SIGINT handler; the signal's byte on m_wakePipe wakes the
 *              poll (Python: signal.set_wakeup_fd) */
typedef struct {
	FramebufferView* m_frames;
	FrameSize        m_frameSize;
	Sam3Model*       m_model;
	SocketDescriptor m_listen;
	int32_t          m_wakePipe[2];
	Sam3UnreadSet    m_unread;
	Sam3PendingQueue m_pending;
	_Atomic bool     mb_stopping;
} Sam3Server;

/* ============================ 2. the process =============================== */

/* python3 -m sam3.server --session D --socket P --frames-fd N --weights W, with
 * PYTHONPATH the project folder. In order: the crash hooks of runtime
 * (DieInstallUncaughtErrorHooks: an exception on any thread, a GPU out-of-memory among
 * them, runs Die, which here holds only the record's flush, then _exit(1)); the SIGINT
 * handler and the wake pipe; RecorderCreate(D, "sam3", "{}", RECORDER_NO_FRAMES), false: Die;
 * DieAddFlush(RecorderFlushInDie); FramebufferOpen(N), NULL: Die; the model's load from
 * W; the warm pass; mb_stopping set: exit 0; unlink P, bind, listen with
 * kSam3QueueCapacity; the loop until mb_stopping; close every connection still unread or
 * queued (their clients see SAM3_CLOSED); RecorderDestroy; FramebufferClose; exit 0 */
int Sam3ServerMain(int argc, const char* const* argv);

/* one pass on a black frame at the block's size, SAM3_WARM_UP_PHRASE, no masks: the
 * first pass of a fresh model takes 1330 ms against 383 ms warm (measured) */
void Sam3ServerWarmPass(Sam3Server* s);

/* the loop, every step on the one thread, until mb_stopping:
 * 1. poll on m_wakePipe[0], m_listen (while the unread set is not full) and every
 *    unread connection; the timeout 0 when the queue holds a request, none when empty;
 * 2. each readable unread connection: Sam3ServerReadRequest;
 * 3. m_listen readable: accept ONE connection into the unread set, then back to step 1
 *    with the timeout 0, so its bytes are read before the next pop;
 * 4. only in a round that accepted none, and the queue holds a request:
 *    Sam3ServerRunOne.
 * No call blocks on a client but the reply's send; the poll said readable before each
 * accept, so the blocking listen socket never waits */
void Sam3ServerLoop(Sam3Server* s);

/* the bytes have arrived (the poll said so): one read of sizeof(Sam3Request) that does
 * not wait; 0 bytes (the probe's connect, a client that gave up) or a short read: close;
 * Sam3CheckRequest; invalid: reply INVALID_REQUEST, close; else push with m_readAt and
 * the next arrival. A queue already full leaves the connection in the unread set */
void Sam3ServerReadRequest(Sam3Server* s, SocketDescriptor connection);

/* pop the best; FramebufferFind(m_frames, m_frameSequence) false: reply FRAME_GONE,
 * close; else MonotonicNow, Sam3ModelDetect, MonotonicNow, the reply with
 * SAM3_SERVER_SEND_TIMEOUT_NS, close, RecordSam3Pass. A failed send (the client gave
 * up: EPIPE, ECONNRESET, the timeout) closes and goes on */
void Sam3ServerRunOne(Sam3Server* s);

/* ============================ 3. the pass ================================== */

/* the pass, in order: the slot's pixels converted BGR to RGB into the model's kept
 * buffer (cv2.cvtColor; the slot is read once, in place); the image encoded once; per
 * concept the tokenizer with truncation at 32 tokens (the processor's own call does not
 * truncate, and 33 tokens raise), the text encoder and the detector; the scores (the
 * logit times the presence score) over m_scoreFloor kept, the boxes scaled to the frame
 * and clamped to it; every concept's boxes in one list, sorted by score;
 * Sam3MergeNested; the first kSam3MaxBoxes; the mask count is the smaller of m_maxMasks
 * and the box count; when it is above 0, the low-resolution masks of those first boxes
 * are upsampled to the frame and thresholded on the GPU, then copied out. The other
 * masks never leave the GPU at full size */
void Sam3ModelDetect(
	Sam3Model* m,
	const uint8_t* bgrPixels,
	const Sam3Request* request,
	Sam3ReplyHeader* header,
	Sam3Box* boxes,
	uint8_t* masks
);

/* TR17, pure, on the CPU: a box is dropped when a kept box with a higher score overlaps
 * it by IoU over 0.5, of any concept of the request; or holds over 0.7 of it, of the
 * same concept only. A synonym's duplicate is near-identical, so IoU finds it; a part
 * inside its whole (a drawer in a dresser) is a second object. Sorted input; returns
 * the kept count */
uint32_t Sam3MergeNested(Sam3Box* boxes, uint32_t count);

/* pure: SAM3_STATUS_OK, or SAM3_STATUS_INVALID_REQUEST */
Sam3Status Sam3CheckRequest(const Sam3Request* request);

/* pure: the heap by (priority, arrival); Push on a full queue is our bug and dies */
void        Sam3PendingPush(Sam3PendingQueue* q, const Sam3Pending* entry);
Sam3Pending Sam3PendingPop(Sam3PendingQueue* q);

/* TOCTOU (gate item 11), each window and what closes it.
 * W1, "the row says UP, then the request": the client never reads a row; a connect to
 * a dead server fails at once (ECONNREFUSED 15 us, ENOENT 73 us).
 * W2, "Find, then read the pixels": the job holds the slot until the reply or its
 * timeout, so the writer cannot claim it. Kept window: the job's timeout fires inside
 * the pass's 0.2 ms copy of the slot; the writer may reuse it; the pass reads a torn
 * frame; its reply goes to a closed socket, so nobody accepts it.
 * W3, "the reply after the job gave up": one connection per request binds a reply to
 * its request; the client closed it, so the send fails and is dropped.
 * W4, "the stale socket file, then the bind": the old process has exited before the
 * supervisor relaunches (pidfd); the new one unlinks, then binds. Kept window: another
 * process of this user creates the path in between; the session folder is this run's.
 * W5, "the probe's connect, then a pass": the socket is bound only after the warm pass;
 * the kernel completes the connect in the backlog, so a pass never delays the probe.
 * W6, "SIGINT during the load": the flag is read after the load; the process exits 0
 * before the bind.
 * W7, "a pop, then SIGINT": the flag is read after each pass; the pass in flight is
 * answered.
 * W8, "the flag is clear, then the poll": a SIGINT between the two writes its byte to
 * the wake pipe, so the poll returns at once.
 * W9, "the accept, then the request's bytes": the read waits for the poll, never on the
 * client; a client that never sends holds one unread entry until its own timeout closes
 * it.
 * W10, "the accept, then the pop": a round that accepted pops nothing; the next round
 * reads the new request first, so a command that arrived during a pass runs before a
 * refresh read earlier. Kept window: a client whose bytes come after that zero-timeout
 * poll (it waits for its GIL) waits one pass. */

#endif
