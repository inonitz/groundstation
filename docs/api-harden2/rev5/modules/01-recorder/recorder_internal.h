/* recorder_internal.h -- the mechanism behind the recorder, as its actors. Each actor
 * has its own header and its own prefix, so a reader sees who does what:
 *   recording_thread.h      the PRODUCERS: a registered thread's entry in the producers
 *                           table, with its queue and its statistics
 *   image_buffer_pool.h     an object pool with a free list and a work queue: the job
 *                           threads fill image buffers, the writer empties them
 *   record_writer.h         the one CONSUMER: it drains the queues and the pools, and
 *                           it is the one producer of the file
 *   recorder_statistics.h   what each actor counts; the health is the aggregate
 *   record_file.h           the file's names and keys (public, beside the contracts)
 * This header holds the one instance that ties them together and its lifetime state.
 * The design, mechanism by mechanism: recorder.md section 2 */
#ifndef __HARDEN2_RECORDER_INTERNAL_H__
#define __HARDEN2_RECORDER_INTERNAL_H__

#include <stdatomic.h>

#include "common_names.h"
#include "image_buffer_pool.h"
#include "record_writer.h"
#include "recorder.h"
#include "recording_thread.h"

/* the zero value is NOT_CREATED. Create stores RUNNING once per process; the stop
 * request stores STOPPING under m_stateLock, after the reason and the deadline, only
 * from RUNNING; the writer alone stores STOPPED, after its last pass (section 2.6) */
typedef enum {
	RECORDER_NOT_CREATED,
	RECORDER_RUNNING,
	RECORDER_STOPPING,
	RECORDER_STOPPED
} RecorderState;

/* the one instance, file-static in recorder.c; everything inside it is allocated at
 * Create (section 2.9). The threads first: the producers and their consumer.
 * m_nextProducerIndex: the entry allocator, one atomic_fetch_add per registration; past
 * kRecordingThreadsMax it dies (RVW4); the writer walks all entries. The two pools are
 * NULL in a process created with RECORDER_NO_FRAMES. m_health: the writer stores and the
 * main thread loads, field by field, relaxed atomics, no lock (2.5, 2.8) */
struct Recorder {
	RecordingThread       m_producers[kRecordingThreadsMax];
	_Atomic ThreadCount   m_nextProducerIndex;
	RecordWriter          m_consumer;
	FrameSize             m_expectedFrameSize;
	ImageBufferPool*      m_framePool;    /* BGR24, kFramePoolBuffers */
	ImageBufferPool*      m_maskPool;     /* GRAY8, kMaskPoolBuffers */
	RecordFile            m_outputFile;
	RecorderHealth        m_health;
	_Atomic RecorderState m_state;
	OsLock*               m_stateLock;    /* the stop request alone: the one lock of the lifetime */
	ProcessName           m_processName;
	PathText              m_sessionDir;
};

/* the reserve at Create and at the free-space check: W x H x 3 x the PNG ratio x the
 * passes per minute x the minutes */
ByteCount RecorderReserveBytes(FrameSize size, uint32_t minutes);   /* kWriterExpectedVisionPassesPerMinute */

#endif
