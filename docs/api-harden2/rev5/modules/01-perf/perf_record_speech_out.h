/* perf_record_speech_out.h -- the perf stage speech out owns: say, one sentence on
 * one voice. Moves into the speech-out header at its review (TEL4). */
#ifndef __HARDEN2_PERF_RECORD_SPEECH_OUT_H__
#define __HARDEN2_PERF_RECORD_SPEECH_OUT_H__

#include "perf.h"

/* "say": output (phone, laptop) */
void PerfSay(PerfTracer* p, PerfTimestamp start, PerfTimestamp end, const char* output);

#endif
