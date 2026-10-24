/* record_event.h -- contract 2 of the recorder: an event, a fact with fields at one
 * instant */
#ifndef __HARDEN2_RECORD_EVENT_H__
#define __HARDEN2_RECORD_EVENT_H__

#include "record_field.h"
#include "recorder.h"

typedef const char* RecordTopic;   /* a string literal: "turn", "pass", "key"; never freed */

/* a turn, a pass, a key press, a status change; the same path and rules as a span
 * (recorder.md section 2.1) */
RecordResult RecordEvent(
	RecordTopic topic,
	MonotonicNs at,
	const RecordField* fields,
	FieldCount count
);

#endif
