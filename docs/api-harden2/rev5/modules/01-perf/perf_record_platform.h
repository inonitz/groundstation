/* perf_record_platform.h -- the perf stages the phone-app client owns: dji_request and
 * emergency. Moves into the client's header at its review (TEL4). */
#ifndef __HARDEN2_PERF_RECORD_PLATFORM_H__
#define __HARDEN2_PERF_RECORD_PLATFORM_H__

#include "perf.h"

/* "dji_request": path, status; the request to the reply, in the app */
void PerfDjiRequest(
	PerfTracer* p,
	PerfTimestamp start,
	PerfTimestamp end,
	const char* path,
	uint32_t status
);

/* "emergency": turn, status; the stop transcript's receipt to the POST reply */
void PerfEmergency(
	PerfTracer* p,
	PerfTimestamp start,
	PerfTimestamp end,
	uint32_t turn,
	uint32_t status
);

#endif
