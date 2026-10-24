/* perf_record_vision.h -- the perf stages the vision jobs own: sam3_request (the app
 * side), vision_gate, count, describe. The sam3_pass stage belongs to the SAM3 server
 * (perf_record_sam3.h). Moves into the vision jobs' header at its review (TEL4). */
#ifndef __HARDEN2_PERF_RECORD_VISION_H__
#define __HARDEN2_PERF_RECORD_VISION_H__

#include "perf.h"

/* "sam3_request": req, prio, ok; the request to the reply, in the app */
void PerfSam3Request(
	PerfTracer* p,
	PerfTimestamp start,
	PerfTimestamp end,
	uint32_t req,
	uint32_t prio,
	bool ok
);

/* "vision_gate", "count", "describe": job, result */
void PerfJobStep(
	PerfTracer* p,
	PerfStage stage,
	PerfTimestamp start,
	PerfTimestamp end,
	uint32_t job,
	const char* result
);

#endif
