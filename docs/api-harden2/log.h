/*
 * log.h -- harden2 API v2.4 (2026-09-26). Module log/ (the session record; log/trace.py deleted 2026-09-24).
 * Records one session: every spoken request, what the app decided, what it sent, what it saw.
 * It cannot fail in a way a restart would fix, so it has NO status row and NO recovery:
 * LogOpen() checks the folder at start (create + write), and a failure there dies.
 * Files: log/session.py (the record), log/disk.py (atomic writes, the folder check),
 * log/perf.py (the timings), and the read-only tools below.
 */
#ifndef __HARDEN2_API_LOG_H__
#define __HARDEN2_API_LOG_H__
#include "system.h"
#include "video.h"                        /* VideoFrame                                      */
#include "perception.h"                   /* Box                                             */

bool        LogOpen(const char* sessionDir);   /* create + write-test; false -> the app dies */
void        LogClose(void);                   /* every record is written when made          */
const char* LogDir(void);                      /* where every proc-<name>.log also goes      */
/* log/session_files.py: the newest session folder (the review tools); none -> die */
const char* LogLatestSession(void);

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

/* ---- the timings (log/perf.py): one JSON line per event in <session>/perf.jsonl, on every
 * run. Stages: asr (F5 release -> transcript, mic only), turn, gemma, sam3 (wait + forward),
 * highlight_gate, count, describe, say, frame (per second: fps; read / draw / show mean AND worst; the
 * longest gap between two frames), gpu (per second). */
typedef struct Perf Perf;
Perf* PerfOpen(const char* sessionDir);   /* NULL folder = record nothing (the tests)      */
void  PerfRecord(Perf* p, const char* stage, float ms, const char* fieldsJson);
void  PerfMark(Perf* p, const char* name);                 /* remember "now" under a name  */
bool  PerfTakeSince(Perf* p, const char* name, float* ms); /* ms since the mark; forgets it */
void  PerfStartGpuSampler(Perf* p);                        /* a "gpu" record every second  */
void  PerfClose(Perf* p);

/* ---- read-only tools over a recorded session (each defaults to the newest session) ----
 *   log/show.py          replay a session: the transcripts, decisions and frames
 *   log/score.py         judge a session against a live-test list -> REPORT.md
 *   log/perf_report.py   p50 / p95 / max per stage from perf.jsonl (`run.sh perf`)     */
const char* LogTraceFile(const char* sessionDir);   /* trace.jsonl, or an older layout    */

#endif /* __HARDEN2_API_LOG_H__ */
