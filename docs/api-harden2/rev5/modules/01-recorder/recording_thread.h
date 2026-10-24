/* recording_thread.h -- the PRODUCER side of the recorder: a thread registers at its
 * start and owns one entry of the producers table, with its own queue and its own
 * statistics; all entries are made at Create (recorder.md section 2.1) */
#ifndef __HARDEN2_RECORDING_THREAD_H__
#define __HARDEN2_RECORDING_THREAD_H__

#include <stdbool.h>
#include <stdint.h>

#include "common_names.h"
#include "monotonic_clock.h"
#include "record_event.h"
#include "record_field.h"
#include "record_span.h"
#include "recorder.h"
#include "recorder_statistics.h"
#include "spsc_record_queue.h"

/* kRecordingThreadsMax: the design's count (PRF5; config/ in Python); the 17th
 * registration dies (RVW4). kRecordQueueRecords: a power of two, over six minutes at 40
 * spans a second (RCD35). kRecordQueueWatermark: past it the push wakes the writer (2.3) */
enum {
	kRecordingThreadsMax = 16,
	kRecordQueueRecords = 16384,
	kRecordQueueWatermark = kRecordQueueRecords >> 1
};

/* what a producer puts into its queue for the writer: THREAD_NAME once, at registration
 * (the file's thread line); DROP_LINE when a hole closes: the file's drop line, built by the thread */
typedef enum {
	QUEUED_SPAN = 1,
	QUEUED_EVENT = 2,
	QUEUED_THREAD_NAME = 3,
	QUEUED_DROP_LINE = 4
} QueuedKind;

/* the record form of the thread's name, queued once at registration into the empty queue */
typedef struct {
	ThreadName m_threadName;
} ThreadNameRecord;

/* one run of drops, as the writer gets it: only the four dropped counters are non-zero.
 * m_firstDropTimestamp is "from" in the drop line, where the hole starts; m_latestDropTimestamp
 * is "to", where it ends so far, and 0 while no run of drops is open */
typedef struct {
	RecordingThreadStatistics m_dropped;
	MonotonicNs               m_firstDropTimestamp;
	MonotonicNs               m_latestDropTimestamp;
} DropLine;

typedef struct OsLock OsLock;   /* the runtime's mutex (runtime_internal.h) */

/* one PRODUCER: a registered thread's entry in the producers table; the thread's name
 * travels as its first queued record, so the entry needs nothing from registration but
 * the thread-local pointer. The counters are the thread's own. m_pendingDropLine is the open run of drops;
 * it goes into the queue before the next record that succeeds, as perf's PERF_RECORD_LOST
 * does; m_dropLineLock guards it alone, since the writer takes a drop line still pending at the
 * last pass (sections 2.1 and 2.7) */
typedef struct {
	ThreadIdx                 m_threadIndex;    /* "t" in every line of this thread */
	SpscRecordQueue           m_recordsToWriter;
	SpscProducer              m_producerEnd;    /* filled at Create; the thread pushes through it */
	RecordingThreadStatistics m_statistics;
	DropLine                m_pendingDropLine;
	OsLock*                   m_dropLineLock;
} RecordingThread;

/* the thread-local pointer at this thread's entry: filled by RecorderRegisterThread,
 * cleared by RecorderUnregisterThread; NULL means NOT_REGISTERED */
extern _Thread_local RecordingThread* tls_producerOfThisThread;

/* the units a drop adds to the statistics and to the pending drop line */
extern const RecordingThreadStatistics kOneSpanDropped;
extern const RecordingThreadStatistics kOneEventDropped;
extern const RecordingThreadStatistics kOneFrameDropped;
extern const RecordingThreadStatistics kOneMaskDropped;

/* the push, on the calling thread: the record built, pushed, then the watermark check;
 * no lock while the queue has room; a drop takes the drop line lock. A hole in the
 * records that ends needs two free slots: the drop line, then the record. In Python the
 * record is a tuple appended to the thread's deque (section 2.1) */
bool RecordingThreadPushSpan(
	RecordingThread* p,
	SpanStage stage,
	MonotonicNs start,
	MonotonicNs end,
	const RecordField* fields,
	FieldCount count
);
bool RecordingThreadPushEvent(
	RecordingThread* p,
	RecordTopic topic,
	MonotonicNs at,
	const RecordField* fields,
	FieldCount count
);
/* on a drop: add the unit to the statistics; under the drop line lock, add it to the pending
 * drop line, open the drop line if none is open, stamp it */
void RecordingThreadCountDroppedRecord(RecordingThread* p, const RecordingThreadStatistics* unit);
/* on the first success after a hole in the records: under the drop line lock, copy the pending
 * drop line out and close it; the caller queues it when a slot is free, else the hole stays
 * open. The writer calls it once, for a run still open at the last pass (2.7) */
void RecordingThreadTakePendingDropLine(RecordingThread* p, DropLine* out);
/* once per crossing of the watermark; the set is skipped when OsEventIsSet says the
 * flag is already set (is-set 23 ns, set 332 ns; section 2.3) */
void RecordingThreadWakeWriterIfHalfFull(RecordingThread* p, RecordCount queuedBefore);

#endif
