/* record_span.h -- contract 1 of the recorder: a span, a duration of our own code */
#ifndef __HARDEN2_RECORD_SPAN_H__
#define __HARDEN2_RECORD_SPAN_H__

#include "record_field.h"
#include "recorder.h"

/* SPAN_QUEUE_MESSAGE: one message of the app's main queue from its stamp to its handling.
 * SPAN_OBJECT_COUNT: the count job's three frames. SPAN_E2E: the push-to-talk release
 * to the first drawn box or the spoken answer */
typedef enum {
	SPAN_STARTUP,
	SPAN_FRAME,
	SPAN_QUEUE_MESSAGE,
	SPAN_ASR,
	SPAN_TURN,
	SPAN_LLAMA_REQUEST,
	SPAN_SAM3_REQUEST,
	SPAN_SAM3_PASS,
	SPAN_DJI_REQUEST,
	SPAN_EMERGENCY,
	SPAN_HIGHLIGHT_GATE,
	SPAN_OBJECT_COUNT,
	SPAN_DESCRIBE,
	SPAN_SAY,
	SPAN_E2E,
	SPAN_STAGE_COUNT
} SpanStage;

/* between two MonotonicNow() reads, with its typed fields; built on the calling thread
 * and pushed into the thread's own queue, no lock while the queue has room, no text; a
 * text that does not fit is cut and marked, never refused (recorder.md section 2.1) */
RecordResult RecordSpan(
	SpanStage stage,
	MonotonicNs start,
	MonotonicNs end,
	const RecordField* fields,
	FieldCount count
);

#endif
