/*
 * system.h -- harden2 API v2.3 (2026-09-24). Module system/: fatal errors, the status rows
 * and the board, the supervisor, the ROS2 context, and the start-up dependency check.
 *
 * House rule: nothing in our code throws. A fatal error calls SysDie(). Everything else
 * returns a status. A third-party call that can throw is wrapped ONCE, in util.h.
 */
#ifndef __HARDEN2_API_SYSTEM_H__
#define __HARDEN2_API_SYSTEM_H__
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "util.h"

/* ---------------------------------------------------------------- fatal (fatal.py) */
typedef void (*SysCleanupFn)(void);
void SysOnDie(SysCleanupFn fn);           /* run on die, newest first, each one guarded     */
void SysDie(const char* reason);          /* one at a time; a 2nd caller waits. No return. */
void SysInstallCrashHooks(void);          /* uncaught error, any thread or loop -> SysDie */

/* ---------------------------------------------------------------- status board (status.py) */
typedef enum {
	STATE_STARTING,                       /* launched, not ready yet                         */
	STATE_UP,                             /* green                                           */
	STATE_RECOVERING,                     /* died, being restarted                           */
	STATE_WAITING,                        /* external, down: waiting for the USER to fix it  */
	STATE_FAILED,                         /* not recoverable: the app is about to die        */
	STATE_DOWN                            /* stopped on purpose                              */
} SysState;
typedef struct StatusRow {
	char     name[32];                    /* "gemma", "sam3", "asr", "keys", "dji app", ...  */
	SysState state;
	char     detail[128];                 /* the reason, shown on the status pane            */
	uint64_t sinceUs;                     /* when this state began                           */
} SysStatusRow;
typedef SysStatusRow StatusRow;

/* Each part that has a row OWNS it (owner ruling 2026-09-24): only the part sets it, and
 * the part reports it through its own XxxStatus() call. The board owns nothing. */
typedef struct Status Status;             /* one row: set by its owner, read by anyone      */
Status*  StatusCreate(const char* name);  /* starts STARTING                                */
void     StatusSet(Status* s, SysState state, const char* detail);   /* logs a change    */
void     SysFail(Status* s, const char* detail, const char* reason);  /* FAILED + die     */

/* A source: any part with rows. It writes its rows and returns how many (0 = none). */
typedef uint32_t (*StatusSourceFn)(void* part, StatusRow* rows, uint32_t cap);
typedef struct { void* part; StatusSourceFn status; } StatusSource;
typedef struct StatusBoard StatusBoard;   /* the app builds it once, from its sources       */
StatusBoard* StatusBoardCreate(const StatusSource* sources, uint32_t n);
uint32_t     StatusBoardSnapshot(StatusBoard* b, StatusRow* rows, uint32_t cap);  /* order */

/* ---------------------------------------------------------------- supervisor (supervisor.py)
 * Owns every process the app launches. One watcher thread per process blocks on its exit
 * (no polling). On an unplanned exit: RECOVERING, relaunch; after kSupRestartBudget failed
 * restarts: FAILED + SysDie, or WAITING when the process is not required. A planned restart
 * (e.g. the video stall guard) is not counted. */
enum { kSupRestartBudget = 3 };
typedef bool (*SupReadyFn)(void);         /* is the process serving? (port open, /health)    */
typedef struct {
	const char*  name;
	const char** argv;                    /* NULL-terminated                                 */
	const char** env;                     /* NULL = inherit; native_env() for ROS binaries   */
	SupReadyFn   ready;                   /* NULL = ready once launched                      */
	float        readyTimeoutS;
	const char*  logPath;                 /* <session>/proc-<name>.log                       */
	bool         required;                /* true: past the budget -> FAILED + SysDie (laptop
	                                         parts). false: WAITING + a slow retry (it depends
	                                         on the phone app: the mock, gstreamer)          */
} SupProcess;                             /* a module describes it; the app starts it */
typedef struct Process Process;           /* the handle SupStart returns                    */
Process* SupStart(const SupProcess* spec);  /* launch + supervise on its own thread         */
bool     ProcessRestart(Process* p, const char* reason);   /* planned: not counted          */
bool     ProcessWaitUp(Process* p, float timeoutS);        /* a bench waits for ready       */
uint32_t ProcessStatus(Process* p, StatusRow* rows, uint32_t cap);   /* its own ONE row   */
void     SupStopAll(void);                /* registered with SysOnDie; every row -> DOWN     */

/* ---------------------------------------------------------------- dependency check
 * ONE place, run first in main. Replaces the scattered find_spec guards. Every missing
 * library, binary, model file or device dies here, with the list of what is missing. */
void SysCheckDependencies(void);

/* ---------------------------------------------------------------- the ROS2 context (ros.py)
 * ONE for the app: started before the first node, stopped after the last. rclpy's own
 * Ctrl+C handler is off, so a node stops with no exception: executor shutdown, join, destroy. */
void RosStart(void);
void RosStop(void);
/* One topic on its own node and executor thread: the keys, speech in and ROS video use it. */
typedef void (*RosMessageFn)(const void* msg);
typedef struct RosSubscription RosSubscription;
RosSubscription* RosSubscribe(const char* node, const char* topic, RosMessageFn onMessage);
void             RosSubscriptionClose(RosSubscription* s);   /* executor, thread, node */

#endif /* __HARDEN2_API_SYSTEM_H__ */
