/*
 * perception.h -- harden2 API rev3 DRAFT (2026-10-02; from v2.4, see RULINGS.md and GAPS.md). Module perception2/: see, count, highlight, describe.
 *
 * Threads (owner design 2026-09-23): a dispatcher sleeps on a condition variable. Each task
 * gets its own thread, at most config.VISION_MAX_TASKS alive. SAM3 is ONE model on ONE GPU, so each
 * forward pass takes the SAM3 priority lock: a user command outranks a highlight refresh.
 * A task waits (sleeps) OUTSIDE the lock, so a waiting task never blocks another.
 * [rev3: TN2] Several highlights live at once: each is its own task, with its own boxes, until
 * its give-up or a clear. A new highlight stops no other task.
 */
#ifndef __HARDEN2_API_PERCEPTION_H__
#define __HARDEN2_API_PERCEPTION_H__
#include "runtime.h"
#include "video.h"
#include "sam3.h"                         /* Sam3, Box, Mask, DetectStatus    */

/* ---- the objects of this module, with their data members ---- */
typedef struct Gemma Gemma;
typedef struct Perf Perf;
typedef struct Vision Vision;
typedef struct Dispatcher Dispatcher;
typedef struct PriorityLock PriorityLock;
typedef struct PerceptionEngine PerceptionEngine;
struct PriorityLock {                     /* python: perception2.sam3_lock.PriorityLock      */
	OsCondition* cond;
	void*        waiting;                 /* the waiters, by (priority, arrival)             */
	bool         held;
	uint64_t     arrival;                 /* a counter: FIFO within one priority             */
};
struct Dispatcher {                       /* python: perception2.dispatcher.Dispatcher       */
	uint32_t     maxTasks;                /* mk_maxTasks: tasks alive at once (8)            */
	const char*  name;
	OsCondition* cond;                    /* the dispatcher thread sleeps on it              */
	void*        pending;                 /* tasks admitted, not yet started                 */
	uint32_t     active;                  /* tasks alive now                                 */
	bool         stop;                    /* mb_stop                                         */
	OsThread*    thread;
};
struct PerceptionEngine {                 /* python: perception2.engine.PerceptionEngine     */
	void*    detect;                      /* (frame, phrase, floor) -> (status, boxes)       */
	void*    maskForBox;                  /* (frame, box) -> mask                            */
	void*    vlmAsk;                      /* (frame, question) -> Gemma's answer             */
	float    floor;                       /* the detector's low query threshold              */
	float    drawConf;                    /* the least score a drawn box may have            */
	float    rel;                         /* keep boxes within this share of the best score  */
	uint32_t maskK;                       /* mask at most this many boxes per frame          */
};
/* a vision target split for the verify step (python: perception2.verify.Target, Related) */
typedef struct { const char* noun; const char* color; } Related;   /* "child with green shirt", "green" */
typedef struct {
	const char* head;                     /* what SAM3 searches and draws: "backpack"        */
	Related     related;                  /* the related object, or empty                    */
	const char* relation;                 /* touch | on | under | above | in | near | none   */
} Target;
typedef struct { const char* verdict; const char* reason; } Verified;   /* draw | absent | failed */

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
 * task's log record in the right turn. [rev3] Only an ADMITTED task starts: a request refused
 * as TASK_FULL calls nothing. */
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
struct Vision {                           /* python: perception2.vision.Vision               */
	Perf*             perf;
	SnapshotFn        snapshot;           /* the video module's latest frame                 */
	VisionSinks       sinks;              /* the app's callbacks                             */
	bool            (*useMasks)(void);    /* the masks switch (the t key)                    */
	PriorityLock*     sam3;               /* EVERY SAM3 pass takes it                        */
	Dispatcher*       dispatch;           /* admits and starts the task threads              */
	TaskId            ids;                /* the next task id                                */
	void*             tl;                 /* per task thread: its task id and priority       */
	OsLock*           hlLock;
	void*             highlights;         /* task -> its stop OsEvent (the live highlights)  */
	PerceptionEngine* engine;
};

/* @useMasks: the masks switch (the t key). @maxTasks: config.VISION_MAX_TASKS. */
Vision*    VisionCreate(Sam3* sam3, Gemma* gemma, SnapshotFn snapshot, const VisionSinks* sinks,
	bool (*useMasks)(void), uint32_t maxTasks, Perf* perf);
void       VisionClose(Vision* v);
/* Each: TASK_OK and the new task, or TASK_FULL (too many tasks alive: refused, not queued). */
TaskStatus VisionCount(Vision* v, const char* phrase, TaskId* out);   /* fire and forget  */
TaskStatus VisionHighlight(Vision* v, const char* phrase, TaskId* out);  /* [rev3: TN2] a new task
                                                 beside the live ones; it replaces none */
TaskStatus VisionDescribe(Vision* v, const char* question, TaskId* out);
/* [rev3: TN2, T3C; the id is v2.3's] task 0 = every live highlight, the one form the app calls
 * today; a task id = that one highlight (the jobs pane, T3C (2)). Each reports HL_CLEARED. A
 * highlight still in its gate is cleared too. */
void       VisionClear(Vision* v, TaskId task);
/* [rev3: T3C (2)] the live jobs, for the jobs pane */
typedef struct { TaskId task; const char* kind; const char* phrase; HighlightState state; } VisionJob;
uint32_t   VisionJobs(Vision* v, VisionJob* out, uint32_t cap);
uint32_t   VisionAlive(Vision* v);   /* tasks alive now                                   */

/* ---- text helper (pure): the phrase SAM3 gets from what the user said ---- */
const char* VisionConcepts(const char* phrase);   /* strip "the", positions, relations     */

#endif /* __HARDEN2_API_PERCEPTION_H__ */
