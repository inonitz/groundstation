/*
 * perf.h -- harden2 API rev4 DRAFT (2026-10-02; split from log.h, owner HDR2).
 * log/perf.py: the timings of a run. Every event goes into a memory buffer; a writer
 * thread appends the buffer to <session>/perf.jsonl every 5 s; SysDie writes it first,
 * so a crash keeps its timings. `run.sh perf` (log/perf_report.py) computes the
 * statistics afterwards.
 *  */
#ifndef __HARDEN2_API_PERF_H__
#define __HARDEN2_API_PERF_H__
#include "runtime.h"

typedef struct {
	const char* stage;
	float       ms;
	double      at;
	const char* fieldsJson;
} PerfEvent;

typedef struct {
	const char* name;
	double      at;
	const char* fieldsJson;
} PerfMark;

/*
 * @path:
 *     <session>/perf.jsonl; NULL = record nothing
 * @buffer:
 *     events not yet written
 * @marks:
 *     remembered start times ("ptt_release", "e2e")
 * @writer:
 *     writes the buffer every PERF_FLUSH_SECONDS
 * @gpuSampler:
 *     a "gpu" event every PERF_GPU_SAMPLE_SECONDS
 * @running:
 *     ATOMIC
 */
typedef struct Perf {
	const char* path;
	PerfEvent*  buffer;
	uint32_t    nBuffered;
	PerfMark*   marks;
	uint32_t    nMarks;
	OsLock*     lock;
	OsThread*   writer;
	OsThread*   gpuSampler;
	bool        running;
} Perf;

Perf* PerfOpen(const char* sessionDir);
void  PerfRecord(Perf* p, const char* stage, float ms, const char* fieldsJson);
void  PerfMarkNow(Perf* p, const char* name, float agoMs, const char* fieldsJson);
/* ms since the mark */
void PerfEnd(Perf* p, const char* mark, const char* stage, const char* fieldsJson);
void PerfClose(Perf* p);
#endif
