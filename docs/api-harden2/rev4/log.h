/*
 * log.h -- harden2 API rev4 DRAFT (2026-10-02). Module log/: the record of one session.
 * SessionLog OWNS two lists: the TURNS (one per thing the user said) and the VISION
 *     JOBS (one per count, highlight or describe). A job is not part of a turn: a
 *     highlight keeps running long after the turn that asked for it (owner HDR3). The
 *     timings are in perf.h.
 *  */
#ifndef __HARDEN2_API_LOG_H__
#define __HARDEN2_API_LOG_H__
#include "runtime.h"
#include "audio.h"                        /* SpeechSource                                    */
#include "sam3.h"                         /* Box, FrameSeq                                   */

typedef uint32_t TaskId;                  /* a vision job's number; 0 = none                 */
typedef enum {
	TURN_EMERGENCY,
	TURN_MANUAL,
	TURN_AUTO,
	TURN_CLEAR,
	TURN_MISSION,
	TURN_HIGHLIGHT,
	TURN_COUNT,
	TURN_DESCRIBE,
	TURN_REJECT,
	TURN_GEMMA_FAILED,
	TURN_EMPTY
} TurnKind;

typedef enum {
	REJECT_NONE,
	REJECT_NEGATED,
	REJECT_NUMBERS_CHANGED,
	REJECT_SHOT_ECHO,
	REJECT_NOT_A_COMMAND
} RejectReason;

/* 1. the raw input */
/*
 * @seq:
 *     the turn's number in this session: 0, 1, 2, ...
 * @heard:
 *     the transcript
 * @audioClip:
 *     "asr_clips/utt_0007.wav", or NULL (phone)
 */
typedef struct {
	uint32_t     seq;
	double       epoch;
	SpeechSource source;
	const char*  heard;
	const char*  audioClip;
} TurnInput;

/* 2. what the recognizer decided */
/*
 * @he2:
 *     the Hebrew Gemma read; "" when no model ran
 * @missionJson:
 *     TURN_MISSION
 * @target:
 *     TURN_HIGHLIGHT / TURN_COUNT: the English target
 * @reject:
 *     TURN_REJECT
 */
typedef struct {
	TurnKind     kind;
	const char*  he2;
	const char*  missionJson;
	const char*  target;
	RejectReason reject;
	uint32_t     recognizeMs;
	uint32_t     planMs;
} TurnDecision;

/* 3. what the user got back */
/*
 * @flightStatus:
 *     the phone app's answer to the mission, or 0
 * @visionJob:
 *     the job this turn started, or 0
 * @spoken:
 *     what was said back
 */
typedef struct {
	int32_t      flightStatus;
	TaskId       visionJob;
	const char*  spoken;
	uint32_t     e2eMs;
} TurnResponse;

typedef struct {
	TurnInput    input;
	TurnDecision decision;
	TurnResponse response;
} Turn;

/* one vision job, from its start to its end */
/*
 * @turnSeq:
 *     the turn that asked for it
 * @kind:
 *     TURN_COUNT | TURN_HIGHLIGHT | TURN_DESCRIBE
 * @passesDir:
 *     "perception/0007_highlight_chair/": each SAM3 pass saved as its frame + its boxes
 * @resultJson:
 *     count: n; highlight: present, best; describe: text
 */
typedef struct {
	TaskId      task;
	uint32_t    turnSeq;
	TurnKind    kind;
	const char* phrase;
	const char* passesDir;
	uint32_t    nPasses;
	const char* resultJson;
} VisionJob;

/*
 * @dir:
 *     the session folder
 * @turns:
 *     EVERY turn of the session, in order
 * @jobs:
 *     every vision job
 * @clipsTaken:
 *     The ASR server saves each mic utterance as "asr_clips/audio_<n>_<time>.wav" before
 *     it publishes the transcript. A mic turn takes the newest clip no turn has taken
 *     yet and renames it "utt_<seq>.wav". This count is how many clips were taken so
 *     far.
 * @lock:
 *     two threads can begin turns at the same moment
 */
typedef struct SessionLog {
	const char* dir;
	Turn*       turns;
	uint32_t    nTurns;
	VisionJob*  jobs;
	uint32_t    nJobs;
	uint32_t    clipsTaken;
	OsLock*     lock;
} SessionLog;

/* create + write-test; failure -> SysDie */
SessionLog* LogOpen(const char* sessionDir);
void        LogClose(SessionLog* log);
Turn*       LogBeginTurn(SessionLog* log, const char* heard, SpeechSource source);
void        LogCommitTurn(SessionLog* log, Turn* t);   /* + one line of trace.jsonl */
VisionJob*  LogBeginJob(
	SessionLog* log,
	const Turn* asker,
	TaskId task,
	TurnKind kind,
	const char* phrase
);
/* the frame is read from the ring by its number */
void LogSavePass(
	SessionLog* log,
	VisionJob* job,
	FrameSeq frame,
	const Box* boxes,
	uint32_t n,
	uint32_t ms
);
void LogEndJob(SessionLog* log, VisionJob* job, const char* resultJson);
/* A whole turn, as the app runs it: Turn* t = LogBeginTurn(log, heard->text,
 * heard->source); RecognizerRoute(rec, t->input.heard, &t->decision); // decide
 * RecognizerAct(rec, &t->decision, &t->response); // fly, or start a vision job
 * LogCommitTurn(log, t); // the turn is in log->turns
 *  */
#endif
