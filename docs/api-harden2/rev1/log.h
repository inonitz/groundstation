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
#include "runtime.h"
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

/* ---- the timings (log/perf.py), on every run. Every event, every frame included, goes into a
 * memory buffer; a writer thread appends it to <session>/perf.jsonl every PERF_FLUSH_SECONDS (5);
 * SysDie writes it before any other cleanup. Stages: startup (per status row: launch -> first UP;
 * "imports", "every row"), asr (F5 release -> transcript, mic only), turn, gemma, sam3 (wait +
 * forward), highlight_gate, count, describe, say, e2e (command -> action, ROADMAP < 1 s: start
 * ptt | phone | transcript, end command | box), frame (EVERY frame: ms = the gap since the
 * previous frame; read / draw / show), gpu (pynvml, every PERF_GPU_SAMPLE_SECONDS). */
typedef struct Perf Perf;
Perf* PerfOpen(const char* sessionDir);   /* NULL folder = record nothing, no thread (tests) */
void  PerfRecord(Perf* p, const char* stage, float ms, const char* fieldsJson); /* buffered  */
/* remember "now" (or agoMs before now) under a name, with fields PerfEnd adds to its record */
void  PerfMark(Perf* p, const char* name, float agoMs, const char* fieldsJson);
bool  PerfTakeSince(Perf* p, const char* name, float* ms); /* ms since the mark; forgets it */
void  PerfMoveMark(Perf* p, const char* name, const char* newName);   /* keep it under newName */
/* record `stage`: ms since the mark `name`, its fields + these; forget it (none: no record) */
void  PerfEnd(Perf* p, const char* name, const char* stage, const char* fieldsJson);
void  PerfFlush(Perf* p);                   /* write the buffer now (the writer, SysDie)    */
void  PerfStartGpuSampler(Perf* p);         /* a "gpu" record every PERF_GPU_SAMPLE_SECONDS */
/* a "startup" record per board row when it is first UP, ms since `launched`              */
void  PerfWatchStartup(Perf* p, StatusBoard* board, double launched);  /* board: its snapshot */
void  PerfClose(Perf* p);                   /* stop the threads, then flush                 */

/* ---- read-only tools over a recorded session (each defaults to the newest session) ----
 *   log/show.py          replay a session: the transcripts, decisions and frames
 *   log/perf_report.py   n, min, P25-P99, max per stage; the 20 slowest frames (`run.sh perf`) */
const char* LogTraceFile(const char* sessionDir);   /* trace.jsonl, or an older layout    */

#endif /* __HARDEN2_API_LOG_H__ */
