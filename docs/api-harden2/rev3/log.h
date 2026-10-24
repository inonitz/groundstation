/*
 * log.h -- harden2 API rev3 DRAFT (2026-10-02; from v2.4, see RULINGS.md and GAPS.md). Module log/ (the session record; log/trace.py deleted 2026-09-24).
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

/* ---- the objects of this module, with their data members ---- */
typedef struct SessionLog SessionLog;
typedef struct Perf Perf;
/* ONE turn = one thing the user said and what the system did with it (python: the dict
 * SessionLog.begin() opens and commit() writes as one line of trace.jsonl). The file IS the
 * list of turns; no list is kept in memory. */
typedef struct Turn {
	/* -- the request -- */
	uint32_t    seq;                      /* the turn's number in this session               */
	const char* ts;                       /* wall time, text                                 */
	double      epoch;
	const char* source;                   /* "mic" | "phone"                                 */
	const char* audioClip;                /* the mic clip of this turn, or NULL              */
	const char* heardHe;                  /* the transcript                                  */
	/* -- what the recognizer decided -- */
	const char* he2;                      /* the Hebrew Gemma read                           */
	const char* flagsJson;                /* the parser's and the guards' notes              */
	const char* kind;                     /* mission | highlight | count | describe | ...    */
	const char* targetEn;                 /* the English target of a vision request          */
	const char* missionJson;              /* the mission, exactly as sent                    */
	/* -- the response -- */
	const char* visionQuery;
	const char* perceptionDir;            /* the folder of this turn's vision passes         */
	const char* verdictJson;              /* a vision request's result                       */
	const char* spoken;                   /* what was said back                              */
	const char* action;                   /* the log tag of what was done                    */
	const char* rejectReason;
	const char* timingsJson;              /* recognizer_ms, plan_ms, e2e_ms                  */
} Turn;
struct SessionLog {                       /* python: log.session.SessionLog                  */
	const char* dir;                      /* the session folder                              */
	const char* clipsDir;                 /* <dir>/asr_clips                                 */
	const char* percDir;                  /* <dir>/perception                                */
	const char* tracePath;                /* <dir>/trace.jsonl: one Turn per line            */
	OsLock*     lock;
	void*       tl;                       /* per thread: the Turn it has open                */
	int32_t     seq;                      /* the last turn number given out                  */
	void*       claimed;                  /* the audio clips already taken by a turn         */
	void*       reqs;                     /* slot -> the open vision request                 */
};
struct Perf {                             /* python: log.perf.Perf                           */
	const char* path;                     /* <session>/perf.jsonl, or NULL (records nothing) */
	OsLock*     lock;
	OsLock*     writeLock;
	void*       rows;                     /* the events not yet written                      */
	void*       marks;                    /* name -> a remembered time and its fields        */
	OsEvent*    stop;
	OsThread**  threads;                  /* the writer, the GPU sampler, the startup watch  */
	void*       gpu;                      /* the pynvml handle                               */
};

bool        LogOpen(const char* sessionDir);   /* create + write-test; false -> the app dies */
void        LogClose(void);                   /* every record is written when made          */
const char* LogDir(void);                      /* where every proc-<name>.log also goes      */
/* log/session_files.py: the newest session folder (the review tools); none -> die */
const char* LogLatestSession(void);

/* One turn = one thing the user said. Two slots, because the vision thread and the Gemma
 * thread work on the same turn at the same time and must never close each other's record. */
typedef uint32_t TurnId;
/* [rev3: follows TN2] one slot per vision TASK: several tasks run at once and each keeps its
 * own record. v2.4 had two slots (vision, describe); the code already uses the task id. */
typedef uint32_t LogSlot;                 /* the vision task's id                           */
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
