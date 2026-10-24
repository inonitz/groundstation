/* perf.h -- the timing record of a run. One tracer per process, a ring per thread.
 * Rulings: C.1, R7, PRF1, PRF2, RVW4 to RVW7 (docs/spec-harden2-cleanup.md). */
#ifndef __HARDEN2_PERF_H__
#define __HARDEN2_PERF_H__

#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>

/* raw nanoseconds of CLOCK_MONOTONIC; the one clock of every process of the app */
typedef uint64_t PerfTimestamp;

typedef enum {
	PERF_STARTUP,
	PERF_ASR,
	PERF_TURN,
	PERF_MESSAGE,
	PERF_LLAMA_REQUEST,
	PERF_SAM3_REQUEST,
	PERF_SAM3_PASS,
	PERF_DJI_REQUEST,
	PERF_EMERGENCY,
	PERF_VISION_GATE,
	PERF_COUNT,
	PERF_DESCRIBE,
	PERF_SAY,
	PERF_E2E,
	PERF_FRAME,
	PERF_GPU,
	PERF_STAGE_COUNT
} PerfStage;

typedef enum {
	PERF_SPAN,
	PERF_SAMPLE
} PerfStageKind;

/* the report skips a PERF_SAMPLE stage in the percentile table.
 * PERF_GPU: the memory and load once a second, by the main thread */
extern const PerfStageKind kPerfStageKind[PERF_STAGE_COUNT];

/* kPerfMaxThreads is the design's count of recording threads (16 in the app, 2 in
 * the SAM3 server), a config constant beside PERF_FLUSH_SECONDS; never the core
 * count. A thread beyond it is our own bug and dies (RVW4). */
enum {
	kPerfRecordBytes = 128,
	kPerfPayloadBytes = 104,
	kPerfRingRecords = 4096,
	kPerfMaxThreads = 32
};

/* The file <session>/perf-<process>-<pid>.jsonl: one JSON object per line.
 * The four line kinds, with their JSON key names. The first key, k, names the
 * kind: clock, thread, drop, rec. */

/* the three clocks are read back to back
 * @m_process:   "app" or "sam3"
 * @m_pid:       the process id
 * @m_monotonic: CLOCK_MONOTONIC, the clock of every timestamp
 * @m_realtime:  CLOCK_REALTIME; the report converts a timestamp with the pair
 * @m_boottime:  CLOCK_BOOTTIME; an offset unlike another file's means a suspend */
typedef struct {
	const char*   m_process;
	uint32_t      m_pid;
	PerfTimestamp m_monotonic;
	uint64_t      m_realtime;
	PerfTimestamp m_boottime;
} PerfClockLine;

/* @m_threads: [index, native id, name] per ring new since the last drain */
typedef struct {
	uint32_t      m_pid;
	const char*   m_threads;
} PerfThreadLine;

/* @m_thread:  the ring's index
 * @m_dropped: records refused since the last drain, since the ring was full */
typedef struct {
	uint32_t      m_thread;
	uint32_t      m_dropped;
} PerfDropLine;

/* @m_stage:   the PerfStage name without PERF_, lower case: "frame"
 * @m_thread:  the ring's index; the merge key is (pid, thread)
 * @m_start:   PerfNow() before the step
 * @m_end:     PerfNow() after the step; equal to start for a PERF_SAMPLE
 * @m_p:       the payload, nested: the stage's keys, ASCII, at most
 *             kPerfPayloadBytes; a longer payload is replaced by {"cut":N} */
typedef struct {
	const char*   m_stage;
	uint32_t      m_thread;
	PerfTimestamp m_start;
	PerfTimestamp m_end;
	const char*   m_p;
} PerfRecordLine;

/* the C build's in-memory record of a ring, kPerfRecordBytes; not the file's layout */
typedef struct {
	uint8_t       m_stage;
	uint8_t       m_thread;
	uint8_t       m_pad[6];
	PerfTimestamp m_start;
	PerfTimestamp m_end;
	char          m_payload[kPerfPayloadBytes];
} PerfEvent;

/* opaque: the rings, the file, the writer thread; NO app state */
typedef struct PerfTracer PerfTracer;

extern PerfTracer* const PERF_NONE;   /* records nothing; starts no thread */

/* Lifetime: one tracer per PROCESS, created once by the process's first step
 * (the app's main thread; the SAM3 server's main), held by that owner, destroyed by
 * the owner last. No module holds it (the owner, 2026-10-18, PRF7); how a caller
 * reaches it is OPEN (PRF7). A thread's ring is made
 * inside its first PerfRecord, owned by the tracer, freed in PerfDestroy.
 * Memory: kPerfMaxThreads rings of kPerfRingRecords * kPerfRecordBytes, one
 * contiguous block per ring (512 KiB), allocated at the thread's first record. */
PerfTracer*   PerfCreate(const char* sessionDir, const char* processName);
void          PerfDestroy(PerfTracer* p);
PerfTimestamp PerfNow(void);
void          PerfRecord(
	PerfTracer* p,
	PerfStage stage,
	PerfTimestamp start,
	PerfTimestamp end,
	const char* payloadJson
);
void PerfFlush(PerfTracer* p);   /* in die(): step 3, under the records cap */

#endif
