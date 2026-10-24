/* perf_record_sam3.h -- the perf stage the SAM3 server owns, in its own process with
 * its own tracer: sam3_pass. Moves into the SAM3 server's header at its review. */
#ifndef __HARDEN2_PERF_RECORD_SAM3_H__
#define __HARDEN2_PERF_RECORD_SAM3_H__

#include "perf.h"

/* "sam3_pass": req, wait (ms, the queue wait before the pass), boxes */
void PerfSam3Pass(
	PerfTracer* p,
	PerfTimestamp start,
	PerfTimestamp end,
	uint32_t req,
	float waitMs,
	uint32_t boxes
);

#endif
