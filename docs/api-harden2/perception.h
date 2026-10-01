/*
 * perception.h -- harden2 API v2.4 (2026-09-26). Module perception2/: see, count, highlight, describe.
 *
 * Threads (owner design 2026-09-23): a dispatcher sleeps on a condition variable. Each task
 * gets its own thread, at most config.VISION_MAX_TASKS alive. SAM3 is ONE model on ONE GPU, so each
 * forward pass takes the SAM3 priority lock: a user command outranks a highlight refresh.
 * A task waits (sleeps) OUTSIDE the lock, so a waiting task never blocks another.
 */
#ifndef __HARDEN2_API_PERCEPTION_H__
#define __HARDEN2_API_PERCEPTION_H__
#include "runtime.h"
#include "video.h"
#include "sam3.h"                         /* Sam3, Box, Mask, DetectStatus    */

/* ---- the SAM3 priority lock ---- */
typedef enum { PRIO_COMMAND = 0, PRIO_REFRESH = 1 } VisionPriority;
void SamLock(VisionPriority p);           /* highest priority first, FIFO within a priority  */
void SamUnlock(void);

/* ---- the vision service: built from the services it needs, callbacks to the app ---- */
typedef struct Gemma Gemma;
typedef struct Perf Perf;
typedef struct Vision Vision;
typedef bool (*SnapshotFn)(VideoFrame* copy);   /* the video module's latest frame   */
typedef uint32_t TaskId;
typedef enum { TASK_OK, TASK_FULL, TASK_NOT_READY } TaskStatus;

/* Highlight: GATE (is it there?) -> TRACKING (the gate's own boxes are the first update, no
 * second pass before the first box (owner L2); then re-detect every period, counted from the
 * START of the last detect) -> LOST after giveUpS without a hit, or CLEARED by the user.
 * Related-noun phrases ("the man next to the car") are split and verified: the related noun,
 * the relation and the colour must hold, or the highlight is ABSENT. */
typedef enum { HL_TRACKING, HL_ABSENT, HL_LOST, HL_CLEARED, HL_NOT_READY } HighlightState;
typedef struct {
	TaskId         task;
	HighlightState state;
	const char*    phrase;
	const char*    concepts;              /* the phrase SAM3 got                              */
	const Box*     boxes;  uint32_t n;
	const Mask*    masks;                 /* one per box, or NULL when masks are off          */
	const char*    reason;                /* ABSENT: which part failed ("no car found"; with
	                                         GATE=vlm "Gemma does not see it", owner O4)     */
	float          best;                  /* the best score the gate saw                      */
	bool           first;                 /* the first TRACKING update after the gate         */
} HighlightUpdate;

/* The app's callbacks (Sinks), given ONCE at create; every task reports through them.
 * onStart runs on the SUBMITTING thread, before the task runs, so the app can open the
 * task's log record in the right turn. */
typedef struct {
	void (*onStart)(TaskId t, const char* kind, const char* phrase);
	/* count: countFrames frames, countGap apart; the median of the per-frame counts.
	 * Every frame failing = TASK_NOT_READY, never 0. */
	void (*onCount)(TaskId t, TaskStatus s, uint32_t n, const char* phrase,
		const uint32_t* perFrame, uint32_t frames);
	void (*onHighlight)(const HighlightUpdate* u);
	/* describe: Gemma answers with the image; a long text for the chat, a short one spoken */
	void (*onDescribe)(TaskId t, bool ok, const char* longText, const char* spoken,
		const VideoFrame* f);
	void (*onPass)(TaskId t, const VideoFrame* f, const Box* raw, uint32_t n, uint32_t ms);
} VisionSinks;

/* @useMasks: the masks switch (the t key). @maxTasks: config.VISION_MAX_TASKS. */
Vision*    VisionCreate(Sam3* sam3, Gemma* gemma, SnapshotFn snapshot, const VisionSinks* sinks,
	bool (*useMasks)(void), uint32_t maxTasks, Perf* perf);
void       VisionClose(Vision* v);
/* Each: TASK_OK and the new task, or TASK_FULL (too many tasks alive: refused, not queued). */
TaskStatus VisionCount(Vision* v, const char* phrase, TaskId* out);   /* fire and forget  */
TaskStatus VisionHighlight(Vision* v, const char* phrase, TaskId* out);  /* replaces the live one */
TaskStatus VisionDescribe(Vision* v, const char* question, TaskId* out);
void       VisionClear(Vision* v);   /* every live highlight reports HL_CLEARED            */
uint32_t   VisionAlive(Vision* v);   /* tasks alive now                                   */

/* ---- text helper (pure): the phrase SAM3 gets from what the user said ---- */
const char* VisionConcepts(const char* phrase);   /* strip "the", positions, relations     */

#endif /* __HARDEN2_API_PERCEPTION_H__ */
