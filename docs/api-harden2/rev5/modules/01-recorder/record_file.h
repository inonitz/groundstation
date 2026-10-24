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
