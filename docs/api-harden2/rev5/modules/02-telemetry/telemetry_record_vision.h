/* telemetry_record_vision.h -- the records the vision jobs own and write through the
 * telemetry sink: a pass with its frame and masks, and a job (two lines). Moves into
 * the vision jobs' header at its review; the keys are the replayer's contract (TEL3). */
#ifndef __HARDEN2_TELEMETRY_RECORD_VISION_H__
#define __HARDEN2_TELEMETRY_RECORD_VISION_H__

#include "telemetry.h"

extern const char* const kPassSteps[];    /* gate, verify, refresh, count_frame,
 * describe */
extern const char* const kJobKinds[];     /* highlight, count, describe */
extern const char* const kJobStates[];    /* started, absent, lost, cleared, done,
 * failed, refused */

/* a box in the frame's pixels, corners, as the replayer draws it; the job converts
 * the SAM3 module's box into this */
typedef struct {
	float       m_x1;
	float       m_y1;
	float       m_x2;
	float       m_y2;
	float       m_score;
	const char* m_label;
} TelemetryBox;

/* one SAM3 or Gemma pass; the job thread calls VisionPass while it holds its frame
 * slot and posts its VisionResult after the call returns; the sink copies the frame
 * and the masks during the call, so the slot is released at once (RVW3)
 * @m_job:        with m_jobKind names the channel "perception/<job:04d>-<kind>"
 * @m_index:      the pass's number in the job, from the job thread; the frames' seq
 * @m_req:        the request number; the join key "req" of perf
 * @m_step:       one of kPassSteps
 * @m_capturedAt: the frame source's PerfNow() when it published the slot
 * @m_bgr:        the pixels, BGR24; m_width and m_height are the slot's and must equal
 *                TelemetryCreate's, or the sink returns INVALID_ARG (it cannot see the
 *                buffer's size from a pointer)
 * @m_masks:      one GRAY8 mask per kept box, 0 or nonzero, at the frame's size; at
 *                most the perception's mask limit */
typedef struct {
	uint32_t              m_job;
	const char*           m_jobKind;
	uint32_t              m_index;
	uint32_t              m_req;
	const char*           m_step;
	PerfTimestamp         m_startedAt;
	PerfTimestamp         m_endedAt;
	uint32_t              m_frame;
	PerfTimestamp         m_capturedAt;
	const uint8_t*        m_bgr;
	uint32_t              m_width;
	uint32_t              m_height;
	uint32_t              m_strideBytes;
	const char*           m_phraseSent;
	const TelemetryBox*   m_boxes;
	uint32_t              m_nBoxes;
	const uint8_t* const* m_masks;
	uint32_t              m_nMasks;
	const char*           m_answer;
} VisionPassData;

/* the frame to <channel>/<index:06d>.png and each mask to
 * <channel>/<index:06d>_mask_<k>.png FIRST, then the topic "pass" line: job, index, req,
 * step, started, ended, frame, captured, phrase, boxes (a list of [x1, y1, x2, y2,
 * score, label]), answer, png (the frame's file name, "" when the pool dropped it),
 * masks (one name per mask, "" when dropped). A reader skips a line whose files are
 * missing */
void TelemetryVisionPass(TelemetryLogger* t, const VisionPassData* pass);

/* a job, written by the main thread at its start (state "started") and at its end,
 * joined by id
 * @m_kind:   one of kJobKinds
 * @m_state:  one of kJobStates
 * @m_passes: how many passes the job made; 0 at the start */
typedef struct {
	uint32_t      m_id;
	uint32_t      m_turn;
	const char*   m_kind;
	const char*   m_phrase;
	PerfTimestamp m_requestedAt;
	PerfTimestamp m_endedAt;
	const char*   m_state;
	const char*   m_why;
	uint32_t      m_passes;
	const char*   m_answer;
	const char*   m_spoken;
} VisionJobData;

/* topic "job": id, turn, kind, phrase, requested, ended, state, why, passes, answer,
 * spoken, channel ("perception/<job:04d>-<kind>") */
void TelemetryJobStarted(TelemetryLogger* t, const VisionJobData* job);
void TelemetryJobEnded(TelemetryLogger* t, const VisionJobData* job);

#endif
