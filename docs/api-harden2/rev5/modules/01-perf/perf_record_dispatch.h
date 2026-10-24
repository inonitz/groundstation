/* perf_record_dispatch.h -- the perf stages the app's dispatch owns: startup, message,
 * turn, e2e. Moves into the dispatch module's header at its review (TEL4). */
#ifndef __HARDEN2_PERF_RECORD_DISPATCH_H__
#define __HARDEN2_PERF_RECORD_DISPATCH_H__

#include "perf.h"

/* "startup": row, restart; the launch to the row's first UP */
void PerfStartup(
	PerfTracer* p,
	PerfTimestamp launched,
	PerfTimestamp up,
	const char* row,
	uint32_t restart
);

/* "message": kind, key (the turn, the request or the key sequence number); the
 * enqueue to the drain; a wait on a full queue is inside the span */
void PerfMessage(
	PerfTracer* p,
	PerfTimestamp enqueued,
	PerfTimestamp drained,
	const char* kind,
	uint32_t key
);

/* "turn": kind, turn; the transcript to the decision */
void PerfTurn(
	PerfTracer* p,
	PerfTimestamp start,
	PerfTimestamp end,
	const char* kind,
	uint32_t turn
);

/* "e2e": turn, from (ptt, phone, transcript), to (command, box) */
void PerfE2e(
	PerfTracer* p,
	PerfTimestamp start,
	PerfTimestamp end,
	uint32_t turn,
	const char* from,
	const char* to
);

#endif
