/*
 * log.h -- harden2 API v2.3 (2026-09-24). Module log/ (the session record; log/trace.py deleted 2026-09-24).
 * Records one session: every spoken request, what the app decided, what it sent, what it saw.
 * It cannot fail in a way a restart would fix, so it has NO status row and NO recovery:
 * LogOpen() checks the folder at start (create + write), and a failure there dies.
 */
#ifndef __HARDEN2_API_LOG_H__
#define __HARDEN2_API_LOG_H__
#include "system.h"
#include "video.h"                        /* VideoFrame                                      */
#include "perception.h"                   /* Box                                             */

bool        LogOpen(const char* sessionDir);
void        LogClose(void);                   /* every record is written when made  */   /* create + write-test; false -> the app dies */
const char* LogDir(void);                      /* where every proc-<name>.log also goes      */
const char* LogLatestSession(void);   /* the newest session folder (the review tools); none -> die */

/* One turn = one thing the user said. Two slots, because the vision thread and the Gemma
 * thread work on the same turn at the same time and must never close each other's record. */
typedef uint32_t TurnId;
typedef enum { SLOT_VISION, SLOT_DESCRIBE } LogSlot;
TurnId LogBeginTurn(const char* heard, const char* source);   /* a mic turn claims its clip */
void   LogSet(TurnId t, const char* key, const char* jsonValue);   /* kind, mission, action */
void   LogCommit(TurnId t);                                  /* write the turn record       */
void   LogBeginRequest(TurnId t, LogSlot s, const char* kind, const char* target);
void   LogSavePass(TurnId t, LogSlot s, const VideoFrame* f, const Box* boxes, uint32_t n,
	uint32_t ms);                        /* one detect pass: the frame + what was found      */
void   LogEndRequest(TurnId t, LogSlot s, const char* verdictJson);

#endif /* __HARDEN2_API_LOG_H__ */
