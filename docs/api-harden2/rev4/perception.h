/*
 * perception.h -- harden2 API rev4 DRAFT (2026-10-02). Module perception2/: the vision
 * system. A vision JOB is one count, one highlight or one describe. Each job runs on
 * its own thread, at most kVisionMaxJobs alive. Several highlights live at once; a new
 * one stops none (the plan, ruling TN2). The screen does not keep boxes of its own: it
 * reads them from the jobs here.
 *  */
#ifndef __HARDEN2_API_PERCEPTION_H__
#define __HARDEN2_API_PERCEPTION_H__
#include "runtime.h"
#include "sam3.h"
#include "gemma.h"
#include "log.h"

enum {
	kVisionMaxJobs = 8
};

/* SAM3 is still loading */
typedef enum {
	JOB_CHECKING,
	JOB_TRACKING,
	JOB_ABSENT,
	JOB_LOST,
	JOB_CLEARED,
	JOB_DONE,
	JOB_NOT_READY
} JobState;

/* ONE vision job; the jobs pane shows these */
/*
 * @kind:
 *     TURN_COUNT | TURN_HIGHLIGHT | TURN_DESCRIBE
 * @phrase:
 *     what the user asked for, in English
 * @latest:
 *     highlight: the boxes and masks drawn now, with the number of the frame they were
 *     found on
 * @count:
 *     count: the answer
 * @answer:
 *     describe: Gemma's answer
 * @why:
 *     JOB_ABSENT: which check failed
 * @stop:
 *     ATOMIC: set by VisionClear; the thread ends
 * @record:
 *     its record in the session log
 */
typedef struct {
	TaskId      task;
	TurnKind    kind;
	const char* phrase;
	JobState    state;
	Detection   latest;
	uint32_t    count;
	const char* answer;
	const char* why;
	bool        stop;
	OsThread*   thread;
	VisionJob*  record;
} Job;

/* the app: chat line, speech; called on every */
typedef void (*JobChangedFn)(const Job* job);
                                                /* state change and on a count /
                                                 * describe answer */
/*
 * @jobs:
 *     the live jobs; a free place has task 0
 * @sam3Turn:
 *     SAM3 does one pass at a time: a user's request goes before a highlight's refresh
 */
typedef struct Vision {
	Sam3*        sam3;
	Gemma*       gemma;
	FrameRing*   frames;
	SessionLog*  log;
	Job          jobs[kVisionMaxJobs];
	uint32_t     nextTask;
	OsLock*      jobsLock;
	OsCondition* sam3Turn;
	JobChangedFn onJobChanged;
} Vision;

Vision* VisionCreate(
	Sam3* sam3,
	Gemma* gemma,
	FrameRing* frames,
	SessionLog* log,
	JobChangedFn onJobChanged
);
void VisionClose(Vision* v);
/* Start a job. 0 = refused: kVisionMaxJobs are alive. A refused request starts NOTHING. */
TaskId VisionCount(Vision* v, const Turn* asker, const char* phrase);
TaskId VisionHighlight(Vision* v, const Turn* asker, const char* phrase);
TaskId VisionDescribe(Vision* v, const Turn* asker, const char* question);
void VisionClear(Vision* v, TaskId task);   /* 0 = every highlight; else that one job */
/* a copy of the live jobs: the screen */
uint32_t VisionJobs(Vision* v, Job* out, uint32_t cap);

/* ---- what a job's thread does, step by step (nothing here is hidden) ----
 * COUNT: CountPass on kCountFrames frames, a short gap apart; the answer is the median;
 *     then the job becomes a highlight of what it counted.
 * HIGHLIGHT: HighlightGate on the newest frame. Not there -> JOB_ABSENT, end. There ->
 *     the gate's own boxes are drawn at once; then every period: HighlightPass on the
 *     newest frame, until `stop` (JOB_CLEARED) or no hit for the give-up time
 *     (JOB_LOST).
 * DESCRIBE: one Gemma request with the newest frame and the question; no SAM3. */
/* 1. ask SAM3 for every candidate at a low score; 2. keep the boxes that score near the
 *     best one; 3. keep each kept box's mask, drop a mask that covers almost the whole
 *     frame. */
void HighlightPass(Vision* v, FrameSeq frame, const char* phrase, Detection* out);
/* Is it in view? SAM3 must find it with a score of 0.5 or more. For a target with a
 * relation ("the bag held by the child") VerifyRelation must hold too. `why` names the
 * failed check. */
bool HighlightGate(
	Vision* v,
	FrameSeq frame,
	const char* phrase,
	Detection* found,
	const char** why
);
uint32_t CountPass(Vision* v, FrameSeq frame, const char* phrase);
/* The target split for the relation check: "bag held by child with green shirt" ->
 * main "bag", relation REL_TOUCH, related "child with green shirt", colour "green". */
typedef enum {
	REL_NONE,
	REL_TOUCH,
	REL_ON,
	REL_UNDER,
	REL_ABOVE,
	REL_IN,
	REL_NEAR
} Relation;

typedef struct {
	const char* mainObject;
	Relation    relation;
	const char* relatedObject;
	const char* color;
} Target;

Target SplitTarget(const char* phrase);
/* box geometry + the colour of the related box */
bool VerifyRelation(
	Vision* v,
	FrameSeq frame,
	const Target* t,
	const Detection* mainFound,
	const char** why
);
#endif
