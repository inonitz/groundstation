/*
 * perception.h -- harden2 API v2.3 (2026-09-24). Module perception2/: see, count, highlight, describe.
 *
 * Threads (owner design 2026-09-23): a dispatcher sleeps on a condition variable. Each task
 * gets its own thread, at most kVisionMaxTasks alive. SAM3 is ONE model on ONE GPU, so each
 * forward pass takes the SAM3 priority lock: a user command outranks a highlight refresh.
 * A task waits (sleeps) OUTSIDE the lock, so a waiting task never blocks another.
 */
#ifndef __HARDEN2_API_PERCEPTION_H__
#define __HARDEN2_API_PERCEPTION_H__
#include "system.h"
#include "video.h"

/* ---- the vision backend (SAM3 today; SAM3.1 / EOVSAM later drop in here) ---- */
typedef enum { DETECT_OK, DETECT_NOT_READY } DetectStatus;   /* "no hits" is DETECT_OK, n=0 */
typedef struct { float x0, y0, x1, y1, conf; char label[32]; } Box;
typedef struct { uint32_t width, height; uint8_t* bits; } Mask;   /* 1 byte per pixel        */
typedef struct {
	const char* name;                     /* config SCENE_SEG: "sam3"; unknown name -> die    */
	const char* modelDir;
	const char* precision;                /* "nf4", fixed at load                             */
} BackendConfig;
typedef struct Sam3 Sam3;               /* the backend loader: a SERVICE             */
Sam3*        Sam3Load(const BackendConfig* cfg);   /* async; fail -> die             */
uint32_t     Sam3Status(Sam3* s, StatusRow* rows, uint32_t cap);   /* its "sam3" row */
DetectStatus VisionDetect(const VideoFrame* f, const char* phrase, float floor, uint32_t topk,
	Box* hits, uint32_t cap, uint32_t* n);   /* nested boxes of one object already merged     */
bool         VisionMaskFor(const VideoFrame* f, const Box* box, Mask* out);  /* last detect */
/* GPU out of memory in a forward -> die (owner: no retry for now). */

/* ---- the SAM3 priority lock ---- */
typedef enum { PRIO_COMMAND = 0, PRIO_REFRESH = 1 } VisionPriority;
void SamLock(VisionPriority p);           /* highest priority first, FIFO within a priority  */
void SamUnlock(void);

/* ---- the vision service: built from the services it needs, callbacks to the app ---- */
typedef struct Gemma Gemma;
typedef struct Vision Vision;
typedef bool (*SnapshotFn)(VideoFrame* copy);   /* the video module's latest frame   */
/* ---- tasks ---- */
enum { kVisionMaxTasks = 8 };             /* a constant; tune to the hardware later           */
typedef uint32_t TaskId;
typedef enum { TASK_OK, TASK_FULL, TASK_NOT_READY } TaskStatus;

/* Count: fire and forget. countFrames frames, countGap apart; median of the per-frame counts
 * (contained boxes merged, tiny boxes dropped). Every frame failing = NOT_READY, never 0. */
typedef void (*CountDoneFn)(TaskId id, TaskStatus s, uint32_t count, const char* phrase);
TaskStatus VisionCount(const char* phrase, CountDoneFn done, TaskId* out);

/* Highlight: GATING (is it there?) -> TRACKING (re-detect every refreshPeriodS, counted from
 * the START of the last detect) -> LOST after giveUpS without a hit, or CLEARED by the user.
 * Related-noun phrases ("the man next to the car") are split and verified: the related noun,
 * the relation and the colour must hold, or the highlight is refused. */
typedef enum { HL_GATING, HL_TRACKING, HL_ABSENT, HL_LOST, HL_CLEARED } HighlightState;
typedef struct {
	TaskId         id;
	HighlightState state;
	const char*    phrase;
	const char*    reason;                /* ABSENT: which part failed ("no car found")       */
	const Box*     boxes;  uint32_t n;
	const Mask*    masks;                 /* one per box, or NULL when masks are off          */
} HighlightUpdate;
typedef void (*HighlightFn)(const HighlightUpdate* u);
TaskStatus VisionHighlight(const char* phrase, HighlightFn onUpdate, TaskId* out);
void       VisionClear(TaskId id);   /* 0 = clear all: the only form built (one
                                        highlight at a time)                    */

/* Describe: a free question about the frame, answered by Gemma with the image (gemma.h). */
typedef void (*DescribeDoneFn)(TaskId id, bool ok, const char* answer);
TaskStatus VisionDescribe(const char* question, DescribeDoneFn done, TaskId* out);

/* ---- text helpers (pure): the phrase SAM3 gets from what the user said ---- */
const char* VisionConcepts(const char* phrase);   /* strip "the", positions, relations     */
bool        VisionParseCount(const char* text, char* phrase, size_t cap);
bool        VisionParseHighlight(const char* text, char* phrase, size_t cap);  /* "" = clear */

#endif /* __HARDEN2_API_PERCEPTION_H__ */
