# The recorder: the eighteen headers, verbatim, for review (draft 31, 2026-10-24; the design: recorder.md section 2)

## 00-util/fixed_text.h
```c
/* fixed_text.h -- a text of a fixed size as a named type, so a field carries its meaning:
 * DEFINE_FIXED_TEXT(PathText, 256) makes typedef struct { char m_text[256]; } PathText */
#ifndef __HARDEN2_UTIL_FIXED_TEXT_H__
#define __HARDEN2_UTIL_FIXED_TEXT_H__

#define DEFINE_FIXED_TEXT(Name, bytes) \
	typedef struct {                   \
		char m_text[bytes];            \
	} Name

#endif
```

## 00-util/common_names.h
```c
/* common_names.h -- the fixed-size names more than one module writes: a path, a
 * process, a thread */
#ifndef __HARDEN2_UTIL_COMMON_NAMES_H__
#define __HARDEN2_UTIL_COMMON_NAMES_H__

#include <stdint.h>

#include "fixed_text.h"

DEFINE_FIXED_TEXT(PathText, 256);
DEFINE_FIXED_TEXT(ProcessName, 32);
DEFINE_FIXED_TEXT(ThreadName, 32);

typedef uint32_t RecordCount;   /* records, in a queue or in a counter */
typedef uint32_t ThreadIdx;     /* an index into the producers table; "t" in the file */
typedef uint32_t ThreadCount;   /* a count of producers */

#endif
```

## 00-util/monotonic_clock.h
```c
/* monotonic_clock.h -- the one time source of every record and every deadline:
 * CLOCK_MONOTONIC in nanoseconds; it never jumps and never goes back; every process on
 * the machine reads the same one. In Python: time.monotonic_ns() */
#ifndef __HARDEN2_UTIL_MONOTONIC_CLOCK_H__
#define __HARDEN2_UTIL_MONOTONIC_CLOCK_H__

#include <stdint.h>

typedef uint64_t MonotonicNs;
typedef uint64_t DurationNs;

MonotonicNs MonotonicNow(void);

#endif
```

## 00-util/frame_types.h
```c
/* frame_types.h -- a frame's size, its pixel format, and a view of its pixels. Shared by
 * the recorder, the frame buffer and the frame source: one home. */
#ifndef __HARDEN2_FRAME_TYPES_H__
#define __HARDEN2_FRAME_TYPES_H__

#include <stdint.h>

/* the source's size, fixed per run */
typedef struct {
	uint16_t m_width;
	uint16_t m_height;
} FrameSize;

typedef enum {
	PIXEL_BGR24,
	PIXEL_GRAY8
} PixelFormat;

/* a frame or a mask as its holder sees it; the pixels stay the holder's */
typedef struct {
	PixelFormat    m_format;
	FrameSize      m_size;
	uint32_t       m_strideBytes;
	const uint8_t* m_pixels;
} FrameView;

#endif
```

## 00-util/statistics.h
```c
/* statistics.h -- program statistics: a struct of named RecordCount counters, one per
 * field, walked as an array for the arithmetic. One actor writes its own statistics;
 * where another thread reads them, they sit under a lock and are copied whole */
#ifndef __HARDEN2_UTIL_STATISTICS_H__
#define __HARDEN2_UTIL_STATISTICS_H__

#include <stdbool.h>
#include <stddef.h>

#include "common_names.h"

/* the number of counters of a statistics struct: every field is a RecordCount */
#define STATISTICS_COUNTERS(Type)  (sizeof(Type) / sizeof(RecordCount))

void StatisticsAdd(RecordCount* dst, const RecordCount* src, size_t counters);        /* dst += src */
void StatisticsSubtract(RecordCount* dst, const RecordCount* src, size_t counters);   /* dst -= src */
bool StatisticsAny(const RecordCount* s, size_t counters);   /* true when any counter is non-zero */

#endif
```

## 00-util/index_queue.h
```c
/* index_queue.h -- a bounded first-in first-out queue of indexes of a pool's items, safe
 * for any number of threads on either side: one lock, held for a few loads and stores.
 * In Python: a collections.deque under one threading.Lock (recorder.md section 2.4) */
#ifndef __HARDEN2_UTIL_INDEX_QUEUE_H__
#define __HARDEN2_UTIL_INDEX_QUEUE_H__

#include <stdbool.h>
#include <stdint.h>

typedef uint32_t ItemIndex;
typedef uint32_t ItemCount;

#define INDEX_NONE  UINT32_C(0xFFFFFFFF)

typedef struct OsLock OsLock;   /* the runtime's mutex (runtime_internal.h) */

/* the payload of an index is the user's own array; an index that is in no queue belongs
 * to the one thread that popped it. m_indexes: m_capacity entries, a ring under the lock */
typedef struct {
	OsLock*    m_lock;
	ItemIndex* m_indexes;
	ItemCount  m_capacity;
	ItemCount  m_head;
	ItemCount  m_count;
} IndexQueue;

/* false: the allocation failed */
bool IndexQueueCreate(IndexQueue* q, ItemCount capacity);
void IndexQueueDestroy(IndexQueue* q);

bool      IndexQueuePush(IndexQueue* q, ItemIndex index);   /* false: full */
ItemIndex IndexQueuePop(IndexQueue* q);   /* the oldest, removed; INDEX_NONE: empty */
/* the oldest, not removed; INDEX_NONE: empty. Push, Pop and Front each take the lock
 * inside; a caller that reads the item a Front names reads it a moment later, unlocked */
ItemIndex IndexQueueFront(IndexQueue* q);

#endif
```

## 00-util/spsc_record_queue.h
```c
/* spsc_record_queue.h -- a bounded queue of records with ONE producer and ONE consumer;
 * full means the new record is dropped and counted. Python: a deque of tuples, bounded
 * by a count (150 ns a push). C: a ring of record slots and a byte area (section 2.1) */
#ifndef __HARDEN2_UTIL_SPSC_RECORD_QUEUE_H__
#define __HARDEN2_UTIL_SPSC_RECORD_QUEUE_H__

#include <stdalign.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "common_names.h"

typedef uint16_t RecordBytes;   /* one record's length */
typedef uint8_t  RecordKind;    /* the user's kinds */

/* ============================ 1. the contract ============================== */

typedef struct SpscRecordQueue SpscRecordQueue;

/* the two endpoints are distinct types, so a holder can only produce or only consume */
typedef struct {
	SpscRecordQueue* m_queue;
} SpscProducer;

typedef struct {
	SpscRecordQueue* m_queue;
} SpscConsumer;

/* false: the allocation failed; on true the two endpoints are filled, each for exactly
 * one thread. The queue holds at most maxRecords records of at most maxRecordBytes each */
bool SpscRecordQueueCreate(
	SpscRecordQueue* q,
	RecordCount maxRecords,
	RecordBytes maxRecordBytes,
	SpscProducer* producer,
	SpscConsumer* consumer
);
void SpscRecordQueueDestroy(SpscRecordQueue* q);

/* false: full; the record is dropped and counted by the caller */
bool SpscProducerPush(
	SpscProducer* p,
	RecordKind kind,
	const void* record,
	RecordBytes bytes
);
/* pushed and not yet popped */
RecordCount SpscProducerRecordsQueued(const SpscProducer* p);

/* the oldest record, without removing it: false when empty; the pointer stays valid
 * until Pop, which removes that one record */
bool SpscConsumerFront(
	SpscConsumer* c,
	RecordKind* kind,
	const void** record,
	RecordBytes* bytes
);
void SpscConsumerPop(SpscConsumer* c);

/* ============================ 2. the C storage ============================= */

typedef uint32_t RingPosition;   /* grows forever; the slot is the position masked by the count */
typedef uint32_t ByteOffset;

enum {
	kCacheLineBytes = 64,
	kRingBytesPerRecordExpected = 64
};

/* one slot per record: where its bytes are and what it is; the bytes live in the byte
 * area, written before the slot is published. m_reserved: zero */
typedef struct {
	ByteOffset  m_at;
	RecordBytes m_bytes;
	RecordKind  m_kind;
	uint8_t     m_reserved;
} RecordSlot;

/* two rings that move together, the slots and the byte area; a record that does not fit
 * before the end goes at 0. m_head is the producer's and m_tail the consumer's, each on
 * its own cache line; release stores, acquire loads. m_slotCount: a power of two */
struct SpscRecordQueue {
	RecordCount m_slotCount;
	RecordBytes m_maxRecordBytes;
	RecordSlot* m_slots;
	uint8_t*    m_bytes;
	ByteOffset  m_byteCapacity;
	alignas(kCacheLineBytes) _Atomic RingPosition m_head;
	alignas(kCacheLineBytes) _Atomic RingPosition m_tail;
};

#endif
```

## 01-recorder/recorder_statistics.h
```c
/* recorder_statistics.h -- what each actor of the recorder counts, since Create; every
 * struct is a statistics struct (00-util/statistics.h): RecordCount fields only, so the
 * arithmetic walks it as an array. The health is their aggregate (recorder.md 2.5) */
#ifndef __HARDEN2_RECORDER_STATISTICS_H__
#define __HARDEN2_RECORDER_STATISTICS_H__

#include "statistics.h"

/* one recording thread: what it queued, and what was dropped, by kind. All eight are the
 * thread's own: relaxed atomic increments by the thread, relaxed loads by the writer, no lock */
typedef struct {
	RecordCount m_spansQueued;
	RecordCount m_eventsQueued;
	RecordCount m_framesQueued;
	RecordCount m_masksQueued;
	RecordCount m_spansDropped;
	RecordCount m_eventsDropped;
	RecordCount m_framesDropped;
	RecordCount m_masksDropped;
} RecordingThreadStatistics;

/* the one writer: the file and the PNGs */
typedef struct {
	RecordCount m_linesWritten;
	RecordCount m_bytesWritten;
	RecordCount m_failedAppends;    /* appends to the record file that failed */
	RecordCount m_linesCut;         /* C only: lines longer than the line buffer */
	RecordCount m_pngsWritten;
	RecordCount m_pngFailures;
	RecordCount m_pngNameClashes;
	RecordCount m_flushes;
	RecordCount m_recordsCutOffAtDeadline;   /* the last pass: records still queued at the drain deadline */
	RecordCount m_imagesCutOffAtDeadline;    /* the same, for filled images */
} RecordWriterStatistics;

#endif
```

## 01-recorder/recorder.h
```c
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
```

## 01-recorder/record_field.h
```c
/* record_field.h -- a typed field of a span or an event: a name, a type and a value. The
 * name is a string literal that lives for the whole process; the writer prints it. No
 * table, no id (recorder.md section 2.1) */
#ifndef __HARDEN2_RECORD_FIELD_H__
#define __HARDEN2_RECORD_FIELD_H__

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef const char* FieldName;   /* a string literal; never freed */
typedef uint8_t  FieldCount;
typedef uint16_t TextLength;

/* kRecordMaxRecordBytes: the whole record, 8 KiB (RCD36); the largest record measured
 * is 5849 bytes. kRecordMaxFields: the caller's fields plus the recorder's one, "cut" */
enum {
	kRecordMaxCallerFields = 31,
	kRecordMaxFields = kRecordMaxCallerFields + 1,
	kRecordMaxRecordBytes = 8192
};

/* the recorder's own field, added only when a text was cut: the bytes lost (RCD37) */
#define FIELD_NAME_CUT  "cut"

_Static_assert(kRecordMaxFields <= 255, "FieldCount is a byte");
_Static_assert(kRecordMaxRecordBytes <= 65535, "RecordBytes is 16 bits");

typedef enum {
	FIELD_INT,
	FIELD_FLOAT,
	FIELD_BOOL,
	FIELD_TEXT
} FieldType;

/* m_bytes: the caller's, during the call only; copied into the record */
typedef struct {
	const char* m_bytes;
	TextLength  m_length;
} TextValue;

typedef union {
	int64_t   m_int;
	double    m_float;
	bool      m_bool;
	TextValue m_text;
} FieldValue;

typedef struct {
	FieldName  m_name;
	FieldType  m_type;
	FieldValue m_value;
} RecordField;

/* what every record call returns. DROPPED: a full queue or pool, STOPPING or STOPPED, a
 * frame under the reserve; INVALID_ARG: too many fields, a wrong frame size, format or
 * name. DROPPED and INVALID_ARG are counted; the other three results are not */
typedef enum {
	RECORD_OK,
	RECORD_DROPPED,
	RECORD_INVALID_ARG,
	RECORD_NO_FRAME_POOLS,
	RECORD_NOT_CREATED,
	RECORD_NOT_REGISTERED   /* the calling thread never registered; counted nowhere */
} RecordResult;

/* the field makers, for a C helper that reads as a sentence: a status out, a destination
 * in, the destination unchanged on false; the helper then stops before any record call.
 * In Python a maker returns the field or None. The hot path passes tuples (section 2.1) */
bool FieldInt(RecordField* out, FieldName name, int64_t value);
bool FieldFloat(RecordField* out, FieldName name, double value);
bool FieldBool(RecordField* out, FieldName name, bool value);
bool FieldText(RecordField* out, FieldName name, const char* bytes, TextLength length);

#endif
```

## 01-recorder/record_span.h
```c
/* record_span.h -- contract 1 of the recorder: a span, a duration of our own code */
#ifndef __HARDEN2_RECORD_SPAN_H__
#define __HARDEN2_RECORD_SPAN_H__

#include "record_field.h"
#include "recorder.h"

/* SPAN_QUEUE_MESSAGE: one message of the app's main queue from its stamp to its handling.
 * SPAN_OBJECT_COUNT: the count job's three frames. SPAN_E2E: the push-to-talk release
 * to the first drawn box or the spoken answer */
typedef enum {
	SPAN_STARTUP,
	SPAN_FRAME,
	SPAN_QUEUE_MESSAGE,
	SPAN_ASR,
	SPAN_TURN,
	SPAN_LLAMA_REQUEST,
	SPAN_SAM3_REQUEST,
	SPAN_SAM3_PASS,
	SPAN_DJI_REQUEST,
	SPAN_EMERGENCY,
	SPAN_HIGHLIGHT_GATE,
	SPAN_OBJECT_COUNT,
	SPAN_DESCRIBE,
	SPAN_SAY,
	SPAN_E2E,
	SPAN_STAGE_COUNT
} SpanStage;

/* between two MonotonicNow() reads, with its typed fields; built on the calling thread
 * and pushed into the thread's own queue, no lock while the queue has room, no text; a
 * text that does not fit is cut and marked, never refused (recorder.md section 2.1) */
RecordResult RecordSpan(
	SpanStage stage,
	MonotonicNs start,
	MonotonicNs end,
	const RecordField* fields,
	FieldCount count
);

#endif
```

## 01-recorder/record_event.h
```c
/* record_event.h -- contract 2 of the recorder: an event, a fact with fields at one
 * instant */
#ifndef __HARDEN2_RECORD_EVENT_H__
#define __HARDEN2_RECORD_EVENT_H__

#include "record_field.h"
#include "recorder.h"

typedef const char* RecordTopic;   /* a string literal: "turn", "pass", "key"; never freed */

/* a turn, a pass, a key press, a status change; the same path and rules as a span
 * (recorder.md section 2.1) */
RecordResult RecordEvent(
	RecordTopic topic,
	MonotonicNs at,
	const RecordField* fields,
	FieldCount count
);

#endif
```

## 01-recorder/record_frame.h
```c
/* record_frame.h -- contract 3 of the recorder: a frame or a mask, as a lossless PNG at
 * compression level 1 (TEL16) */
#ifndef __HARDEN2_RECORD_FRAME_H__
#define __HARDEN2_RECORD_FRAME_H__

#include "frame_types.h"
#include "record_field.h"
#include "recorder.h"

/* buffer sizes: a folder name of at most 63 characters, one or two names joined by one
 * "/"; a file name of at most 31 characters, no "/", no extension */
enum {
	kRecordFolderBytes = 64,
	kRecordNameBytes = 32
};

/* the checks run before the take, so the fill cannot fail; INVALID_ARG: the size, the
 * format, the stride, the folder or the name. Then: a free buffer taken, the pixels
 * copied, the buffer enqueued, the writer woken; the PNG is the writer's (section 2.4) */
RecordResult RecordFrame(
	const char* folder,
	const char* name,
	MonotonicNs at,
	const FrameView* frame
);

#endif
```

## 01-recorder/record_file.h
```c
/* record_file.h -- the file the recorder writes and the readers read: every name in it
 * has its one home here. One JSON object per line; every time in CLOCK_MONOTONIC
 * nanoseconds unless the key says otherwise. The contract lines: recorder.md section 5 */
#ifndef __HARDEN2_RECORD_FILE_H__
#define __HARDEN2_RECORD_FILE_H__

#include <fcntl.h>

#include "record_field.h"
#include "record_span.h"

#define RECORD_FILE_NAME_FORMAT   "record-%s-%d.jsonl"   /* the process name, the pid */
#define RECORD_FILE_OPEN_FLAGS    (O_WRONLY | O_CREAT | O_EXCL | O_APPEND | O_CLOEXEC)
#define RECORD_FRAME_PATH_FORMAT  "%s/%s/%s.png"         /* the session dir, the folder, the name; the writer makes the folder */
#define RECORD_PNG_OPEN_FLAGS     (O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC)

/* the order in a file is the writer's pass order (section 2.2) and, at the end, the last
 * pass order (section 2.7): a thread's name line and its drop lines sit in its stream, at
 * their place; a failed append never disturbs the order; a reader skips and counts a line
 * it cannot parse */
typedef enum {
	LINE_TIME_REFERENCE,
	LINE_INFO,
	LINE_THREAD,
	LINE_SPAN,
	LINE_EVENT,
	LINE_FRAME,
	LINE_DROP,
	LINE_HEALTH,
	LINE_FAULT,
	LINE_DIE,
	LINE_KIND_COUNT
} LineKind;

/* the value of "k" per LineKind, in enum order */
#define LINE_KIND_NAMES \
	{ "time", "info", "thread", "span", "event", "frame", "drop", "health", "fault", "die" }

/* the value of "s" per SpanStage, in enum order */
#define SPAN_STAGE_NAMES \
	{ "startup", "frame", "queue_message", "asr", "turn", "llama_request", "sam3_request", \
	  "sam3_pass", "dji_request", "emergency", "highlight_gate", "object_count", "describe", \
	  "say", "e2e" }

/* every line */
#define LINE_KEY_KIND          "k"

/* time reference: one monotonic reading next to the wall clock and the boot clock, read
 * back to back; written at Create and again before every health line */
#define TIME_KEY_PROCESS       "process"
#define TIME_KEY_PID           "pid"
#define TIME_KEY_MONOTONIC_NS  "monotonic_ns"
#define TIME_KEY_WALL_US       "wall_us"
#define TIME_KEY_BOOT_NS       "boot_ns"

/* info: the caller's info object under "info", and the frame size when the process has
 * pools, once */
#define INFO_KEY_FRAME         "frame"
#define INFO_KEY_FRAME_WIDTH   "w"
#define INFO_KEY_FRAME_HEIGHT  "h"
#define INFO_KEY_CALLER        "info"

/* thread: the index every later line names, and the thread's name; queued by the
 * registering thread as its first record, so it precedes its records */
#define THREAD_KEY_INDEX       "t"
#define THREAD_KEY_NAME        "name"

/* span: the thread, the stage name, start and end, the fields as an object */
#define SPAN_KEY_THREAD        "t"
#define SPAN_KEY_STAGE         "s"
#define SPAN_KEY_START         "a"
#define SPAN_KEY_END           "b"
#define SPAN_KEY_FIELDS        "p"

/* event: the thread, the topic name, the time, the fields as an object, like a span */
#define EVENT_KEY_THREAD       "t"
#define EVENT_KEY_TOPIC        "topic"
#define EVENT_KEY_AT           "at"
#define EVENT_KEY_FIELDS       "p"

/* frame: written after the PNG attempt, ok true when it landed and false when the write
 * failed or the name clashed; the event that asked for it names the PNG as a request */
#define FRAME_KEY_FOLDER       "folder"
#define FRAME_KEY_NAME         "name"
#define FRAME_KEY_AT           "at"
#define FRAME_KEY_OK           "ok"

/* fault: at the end of a pass in which a fault counter or a flag changed (TEL2, T1): the
 * time, the cause (a key name of the health), and the new value; the fault counters are
 * the dropped counts, failed_appends, lines_cut, png_failures, png_name_clashes, the two
 * cut-off counts */
#define FAULT_KEY_AT           "at"
#define FAULT_KEY_WHAT         "what"
#define FAULT_KEY_COUNT        "count"

/* drop: one burst of drops of one thread, written from the drop drop line the thread queued
 * when the burst ended (section 2.1): the counts by kind, the first and the latest drop */
#define DROP_KEY_THREAD        "t"
#define DROP_KEY_SPANS         "spans"
#define DROP_KEY_EVENTS        "events"
#define DROP_KEY_FRAMES        "frames"
#define DROP_KEY_MASKS         "masks"
#define DROP_KEY_FROM          "from"
#define DROP_KEY_TO            "to"

/* health: the RecorderHealth aggregate, one object per statistics struct, the counters
 * by name in field order (recorder_statistics.h), then the flags and the free space */
#define HEALTH_KEY_PRODUCERS_TOTAL  "producers_total"
#define HEALTH_KEY_CONSUMER         "consumer"
#define RECORDING_THREAD_STATISTICS_KEYS \
	{ "spans_queued", "events_queued", "frames_queued", "masks_queued", "spans_dropped", \
	  "events_dropped", "frames_dropped", "masks_dropped" }
#define RECORD_WRITER_STATISTICS_KEYS \
	{ "lines_written", "bytes_written", "failed_appends", "lines_cut", "pngs_written", \
	  "png_failures", "png_name_clashes", "flushes", "records_cut_off_at_deadline", \
	  "images_cut_off_at_deadline" }
#define HEALTH_KEY_LAST_APPEND_FAILED       "last_append_failed"
#define HEALTH_KEY_FREE_SPACE_UNDER_RESERVE "free_space_under_reserve"
#define HEALTH_KEY_FREE_SPACE_GIB           "free_space_gib"
#define HEALTH_KEY_WRITER_STALLED           "writer_stalled"

/* die: the reason, once, on the last pass of a Die */
#define DIE_KEY_AT             "at"
#define DIE_KEY_REASON         "reason"

#endif
```

## 01-recorder/recording_thread.h
```c
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
```

## 01-recorder/image_buffer_pool.h
```c
/* image_buffer_pool.h -- an object pool with a free list, plus a producer-consumer work
 * queue: a fixed set of N image buffers in one pixel block, allocated once. The free
 * list holds the buffers nobody uses; the work queue holds the filled ones, oldest
 * first. A producer takes a buffer from the free list, fills it, and enqueues it. The
 * consumer peeks the oldest, processes it, appends its line, dequeues it and returns it
 * to the free list. A buffer in neither queue belongs to the one thread that holds it.
 * V4L2 calls the same shape a buffer queue. Here: the vision job threads fill, the
 * writer encodes the PNG (recorder.md section 2.4) */
#ifndef __HARDEN2_IMAGE_BUFFER_POOL_H__
#define __HARDEN2_IMAGE_BUFFER_POOL_H__

#include <stdbool.h>
#include <stdint.h>

#include "fixed_text.h"
#include "frame_types.h"
#include "index_queue.h"
#include "monotonic_clock.h"
#include "record_frame.h"

/* kMasksPerPass: the perception's mask limit; config/ in Python (RCD7) */
enum {
	kFramePoolBuffers = 8,
	kMasksPerPass = 3,
	kMaskPoolBuffers = kFramePoolBuffers * kMasksPerPass
};

typedef uint32_t BufferCount;

/* the writer's one write of the PNG file to the disk; kept on the image, so a frame
 * line retried after a failed append knows its ok value and skips the encode */
typedef enum {
	PNG_WRITE_PENDING,
	PNG_WRITTEN,
	PNG_WRITE_FAILED,
	PNG_NAME_CLASH
} PngOnDiskStatus;

DEFINE_FIXED_TEXT(FolderName, kRecordFolderBytes);   /* one or two names under the session folder */
DEFINE_FIXED_TEXT(FileName, kRecordNameBytes);       /* the PNG's name without its extension */

/* one frame or one mask. m_pixels points into the pool's pixel block (the frame size
 * times 3 for BGR24, times 1 for GRAY8). m_frameCaptureTimestamp: when the frame source
 * wrote the frame, from the caller; a mask carries its frame's. m_frameCopiedInTimestamp:
 * when the pixels were copied in from the shared slot; the stall question reads it */
typedef struct {
	uint8_t*        m_pixels;
	MonotonicNs     m_frameCaptureTimestamp;
	MonotonicNs     m_frameCopiedInTimestamp;
	FolderName      m_folderName;
	FileName        m_fileName;
	PngOnDiskStatus m_status;                 /* PNG_WRITE_PENDING until the writer's one write */
} ImageBuffer;

/* m_pixelBlock: one allocation of m_count images; m_buffers: one array of m_count
 * structs. The two index queues sit each under its own lock (RCD50): a take and a
 * return use the free list's, an enqueue and a dequeue the work queue's */
typedef struct {
	uint8_t*     m_pixelBlock;
	ImageBuffer* m_buffers;
	BufferCount  m_count;
	IndexQueue   m_freeList;
	IndexQueue   m_workQueue;   /* oldest first */
} ImageBufferPool;

/* false: the allocation failed; Create then returns false and the app dies at start */
bool ImageBufferPoolCreate(ImageBufferPool* pool, BufferCount count, uint32_t bytesPerImage);
void ImageBufferPoolDestroy(ImageBufferPool* pool);

/* the producer's side */
ImageBuffer* ImageBufferPoolTakeFree(ImageBufferPool* pool);   /* NULL: every buffer is in use */
/* stamps m_frameCopiedInTimestamp, puts the buffer on the work queue */
void ImageBufferPoolEnqueueFilled(ImageBufferPool* pool, ImageBuffer* image);

/* the consumer's side: the oldest filled image stays at the front until its frame line
 * is in the file; peek, encode once, append, then dequeue and return (section 2.4) */
ImageBuffer* ImageBufferPoolPeekFilled(ImageBufferPool* pool);   /* NULL: the work queue is empty */
void ImageBufferPoolDequeueFilled(ImageBufferPool* pool);         /* the front, after its frame line */
/* back on the free list; m_status back to PNG_WRITE_PENDING */
void ImageBufferPoolReturnFree(ImageBufferPool* pool, ImageBuffer* image);

/* the stall question, for RecorderReadHealth: the copy time of the oldest image on the
 * work queue, or 0 when it is empty; the front index and the image's time are two reads,
 * a racy pair that delays a stall report by one frame at most (section 2.8) */
MonotonicNs ImageBufferPoolOldestCopiedInTimestamp(ImageBufferPool* pool);

#endif
```

## 01-recorder/record_writer.h
```c
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
```

## 01-recorder/recorder_internal.h
```c
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
```
