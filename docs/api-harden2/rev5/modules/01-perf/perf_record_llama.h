/* perf_record_llama.h -- the perf stage the llama module owns: llama_request, the
 * request to the reply in the app (RVW5). Moves into the llama module's header. */
#ifndef __HARDEN2_PERF_RECORD_LLAMA_H__
#define __HARDEN2_PERF_RECORD_LLAMA_H__

#include "perf.h"

/* the server's own timings when its reply has them: cached, prompt and predicted
 * tokens; prompt and predicted ms */
typedef struct {
	uint32_t m_cachedTokens;
	uint32_t m_promptTokens;
	uint32_t m_predictedTokens;
	float    m_promptMs;
	float    m_predictedMs;
} LlamaTimings;

/* "llama_request": req, label (plan, vision), ok, cn, pn, gn, pm, gm */
void PerfLlamaRequest(
	PerfTracer* p,
	PerfTimestamp start,
	PerfTimestamp end,
	uint32_t req,
	const char* label,
	bool ok,
	const LlamaTimings* timings
);

#endif
