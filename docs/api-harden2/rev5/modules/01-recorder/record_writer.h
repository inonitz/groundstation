/* record_writer.h -- the one CONSUMER of the recorder and the one producer of its file:
 * one thread per process; it drains every queue and both pools and writes every line;
 * it never calls a record contract (recorder.md sections 2.2, 2.3 and 2.7) */
#ifndef __HARDEN2_RECORD_WRITER_H__
#define __HARDEN2_RECORD_WRITER_H__

#include <stdatomic.h>
#include <stdbool.h>

#include "common_names.h"
#include "fixed_text.h"
#include "monotonic_clock.h"
#include "record_field.h"
#include "recorder.h"
#include "recorder_statistics.h"
#include "recording_thread.h"
#include "spsc_record_queue.h"

struct Recorder;

/* the runtime's thread, and its wake flag: a condition variable with a remembered notify
 * (runtime_internal.h; threading.Thread and threading.Event in Python; section 2.3) */
typedef struct OsThread OsThread;
typedef struct OsEvent OsEvent;

typedef int      FileDescriptor;
typedef uint64_t ByteCount;

/* kWriterLineBytes: the one line buffer of a C build, twice the record bound; a line
 * that does not fit is written cut and counted in m_linesCut; Python has no buffer
 * (section 2.2). The values are the design's; the Python build reads them from config/ */
enum {
	kWriterLineBytes = 16384,
	kWriterExpectedVisionPassesPerMinute = 30,
	kWriterFlightMinutes = 40,
	kWriterReserveMinutes = 5
};

#define WRITER_WAKE_EVERY_NS             UINT64_C(5000000000)   /* the timer                    */
#define WRITER_FLUSH_TO_DISK_EVERY_NS    UINT64_C(5000000000)   /* the free space, the time reference, the health line, the flush */
#define WRITER_STALL_NS                  UINT64_C(5000000000)   /* frames only                  */
#define WRITER_PNG_BYTES_PER_RAW_BYTE    0.45f

DEFINE_FIXED_TEXT(LineText, kWriterLineBytes);
DEFINE_FIXED_TEXT(DieReasonText, 256);

_Static_assert(kWriterLineBytes >= 2 * kRecordMaxRecordBytes, "the line buffer is twice the record bound");

/* ============================ the record file ============================== */

/* created once per process by RecorderCreate with RECORD_FILE_OPEN_FLAGS; appended by
 * the writer alone; a failed append leaves the record at the front and ends the pass;
 * a short append is truncated back to the line's start (section 2.2) */
typedef struct {
	FileDescriptor m_fileDescriptor;
	PathText       m_filePath;   /* <sessionDir>/record-<process>-<pid>.jsonl */
} RecordFile;

bool RecordFileCreate(RecordFile* f, const char* sessionDir, const ProcessName* process);
/* the time reference, then the info line; frame is NULL in a process without pools */
bool RecordFileWriteHeader(RecordFile* f, const char* infoJson, const FrameSize* frame);
/* false: failed, truncated back to the line's start */
bool RecordFileAppendLine(RecordFile* f, const LineText* line, ByteCount length);
void RecordFileFlushToDisk(RecordFile* f);   /* fsync: the kernel's cache to the disk */
void RecordFileClose(RecordFile* f);

/* ============================ the writer =================================== */

/* the one CONSUMER: its thread and two flags; the stop request, stored under the state
 * lock before STOPPING (2.6): m_drainDeadline is the time until which the writer may still
 * write what is queued; what remains then is counted as dropped and the writer stops
 * (Destroy: now plus its timeout; Die: its 5 s flush cap); m_dieReason is Die's text or
 * empty; its consumer ends of the producers' queues; its own statistics; the 5 s timer */
typedef struct {
	OsThread*              m_thread;
	OsEvent*               m_wakeFlag;
	OsEvent*               m_stoppedFlag;
	_Atomic MonotonicNs    m_drainDeadline;
	DieReasonText          m_dieReason;
	SpscConsumer           m_queuesFromProducers[kRecordingThreadsMax];
	RecordWriterStatistics m_statistics;
	MonotonicNs            m_lastFlushTimestamp;
	LineText*              m_line;   /* the one line buffer, made at Create */
} RecordWriter;

/* one record to one JSON line with the keys of record_file.h, by its QueuedKind: the only
 * place a record becomes text. NaN and infinity become null; invalid UTF-8 is replaced.
 * false: the line did not fit the buffer; written as it is, counted */
bool RecordWriterFormatRecord(
	ThreadCount thread,
	RecordKind kind,
	const void* record,
	RecordBytes bytes,
	LineText* line,
	ByteCount* length
);

/* has the writer stopped taking filled images: the oldest has waited on a work queue for
 * more than WRITER_STALL_NS (oldestCopiedIn from ImageBufferPoolOldestCopiedInTimestamp);
 * false when oldestCopiedIn is 0 (section 2.8) */
bool RecordWriterIsStalled(MonotonicNs oldestCopiedIn, MonotonicNs now);

/* the writer thread's whole loop, one function: the pass of seven steps (section 2.2),
 * always back to step 1 (2.3); on STOPPING the last pass drains to empty or to the
 * deadline, then the die line, the sums, the health line, the flush, STOPPED (2.7) */
void RecordWriterRun(struct Recorder* r);

#endif
