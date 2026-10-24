/* recorder.h -- the one record service of a process: its lifetime and its health.
 * Ambient: created once per process, no handle. The contracts: record_span.h,
 * record_event.h, record_frame.h. The design: recorder.md section 2 (2.9 the lifetime) */
#ifndef __HARDEN2_RECORDER_H__
#define __HARDEN2_RECORDER_H__

#include <stdbool.h>
#include <stdint.h>

#include "common_names.h"
#include "frame_types.h"
#include "monotonic_clock.h"
#include "recorder_statistics.h"

/* ============================ 1. the lifetime ============================== */

/* the app's buffer pools, sized by the source's frame */
typedef struct {
	FrameSize m_size;
} RecorderFrameConfig;

#define RECORDER_NO_FRAMES ((const RecorderFrameConfig*)0)   /* a process that records no frames */

/* the bounds Create checks explicitly, in both builds; maximum lengths, not buffer sizes;
 * from config/ in the Python build (section 2.9) */
enum {
	kRecorderSessionDirMax = 192,    /* characters; plus the file name fits PathText, 256 */
	kRecorderProcessNameMax = 31,    /* characters; fits ProcessName, 32 */
	kRecorderInfoJsonMax = 8192      /* bytes */
};

/* once per process, at the app's start; allocates everything; writes the two header
 * lines; makes <sessionDir>/asr_clips/. false: a second call, a bound exceeded, the
 * folder unwritable, the file exists, an allocation failed, or under the reserve (2.9) */
bool RecorderCreate(
	const char* sessionDir,
	const char* processName,
	const char* infoJson,
	const RecorderFrameConfig* frames
);

/* the stop request, the wait for "stopped" up to the timeout, then the join: true.
 * false: the timeout passed; nothing is stored and the daemon thread ends with the
 * process (sections 2.6 and 2.9) */
bool RecorderDestroy(DurationNs timeout);

/* Die step 3; fits DieActionFn(ctx, reason, deadlineNs); ctx is NULL and unused. The
 * stop request under the state lock, then the wait for "stopped" until the deadline;
 * never joins; returns at once on the writer's own thread (section 2.6) */
void RecorderFlushInDie(void* unusedCtx, const char* reason, MonotonicNs deadlineNs);

/* every thread that records registers at its start and unregisters at its end; the
 * registration takes the next entry of the producers table by one atomic fetch-and-add,
 * fills the thread-local pointer and queues the thread's name as its first record; the
 * 17th registration ever dies, and so does a second registration of one thread (2.1).
 * false: the recorder is not created. A record call from an unregistered thread
 * returns NOT_REGISTERED and counts nowhere */
bool RecorderRegisterThread(const char* threadName);
void RecorderUnregisterThread(void);

/* ============================ 2. the health ================================ */

/* the status row's data: the aggregate of the actors' statistics (recorder_statistics.h).
 * The writer stores it at the end of each pass and the main thread reads it once per
 * frame, field by field with relaxed atomics, no lock: each field is whole, the set may
 * be one pass stale. mb_writerStalled is computed at read (sections 2.5 and 2.8) */
typedef struct {
	RecordingThreadStatistics m_producersTotal;   /* the sum over the producers table */
	RecordWriterStatistics    m_consumer;
	bool                      mb_lastAppendFailed;
	bool                      mb_freeSpaceUnderReserve;   /* under 5 minutes of frames: frames are refused */
	float                     m_freeSpaceGiB;
	bool                      mb_writerStalled;   /* no filled image taken for WRITER_STALL_NS */
} RecorderHealth;

void RecorderReadHealth(RecorderHealth* out);

#endif
