/* perf_record_screen.h -- the perf stages the screen owns: frame, gpu. Moves into the
 * screen's header at its review; the payload keys are the report's contract (TEL4). */
#ifndef __HARDEN2_PERF_RECORD_SCREEN_H__
#define __HARDEN2_PERF_RECORD_SCREEN_H__

#include "perf.h"

/* "frame": read, draw, show (ms); the span is the previous frame's end to this end */
void PerfFrame(
	PerfTracer* p,
	PerfTimestamp previousEnd,
	PerfTimestamp readStart,
	PerfTimestamp drawStart,
	PerfTimestamp showStart,
	PerfTimestamp end
);

/* "gpu": mem (MiB), load (percent); a sample, start == end, once a second */
void PerfGpu(PerfTracer* p, PerfTimestamp at, uint32_t memMiB, uint32_t loadPct);

#endif
