/*
 * runtime.h -- harden2 API rev4 DRAFT (2026-10-02). Module runtime/: dying, the
 * supervisor of our processes, and the ROS2 context. (The status rows: status.h. The
 * preflight's dependency list is a tool, not part of the running app: preflight.h, to
 * be written.)
 * House rule: nothing in our code throws. A fatal error calls SysDie(); everything else
 *     returns a status.
 *  */
#ifndef __HARDEN2_API_RUNTIME_H__
#define __HARDEN2_API_RUNTIME_H__
#include "status.h"

/* ---------------- dying (runtime/fatal.py) ---------------- */
typedef void (*SysCleanupFn)(void);
/* run when the app dies; first = before all */
void SysOnDie(SysCleanupFn fn, bool first);
void SysDie(const char* reason);   /* print the reason, run the cleanups, exit */
void SysInstallCrashHooks(void);   /* an uncaught error on ANY thread -> SysDie */

/* ---------------- the supervisor (runtime/supervisor.py) ---------------- ONE
 * Supervisor for the whole app. It owns EVERY process the app launches (llama-server,
 * the keyboard hook, the ASR server, the mock phone app, gstreamer, SAM3). For each
 * process, one watcher thread sleeps until the process exits. On an exit nobody asked
 * for: RECOVERING, start it again. After kSupRestartBudget failed restarts: a required
 * process -> FAILED and SysDie; a process that depends on the phone -> WAITING and a
 * slow retry. */
enum {
	kSupRestartBudget = 3
};

typedef bool (*ReadyFn)(void);   /* "is it serving?" (a port answers, /health is ok) */
/* HOW to start one process (python: ProcessSpec) */
/*
 * @name:
 *     also the name of its status row
 * @env:
 *     NULL = inherit
 * @ready:
 *     NULL = ready once launched
 * @logPath:
 *     <session>/proc-<name>.log
 */
typedef struct ProcessSpec {
	const char*  name;
	const char** argv;
	const char** env;
	ReadyFn      ready;
	float        readyTimeoutS;
	const char*  logPath;
	bool         required;
} ProcessSpec;

/* ONE running process (python: Process) */
/*
 * @pid:
 *     the OS process now running under this name
 * @restarts:
 *     failed restarts so far
 * @plannedRestart:
 *     a restart we asked for: not counted as a failure
 * @up:
 *     set while it is ready
 * @status:
 *     its ONE row
 * @watcher:
 *     sleeps until the process exits
 */
typedef struct Process {
	const char* name;
	int32_t     pid;
	uint32_t    restarts;
	bool        plannedRestart;
	OsEvent*    up;
	Status*     status;
	OsThread*   watcher;
} Process;

/*
 * @processes:
 *     every process the app started
 * @stopping:
 *     ATOMIC: SupStopAll began; exits are expected
 */
typedef struct Supervisor {
	Process** processes;
	uint32_t  nProcesses;
	bool      stopping;
} Supervisor;

Supervisor* SupCreate(void);
Process* SupStart(Supervisor* s, const ProcessSpec* spec);   /* launch + watch */
bool ProcessWaitUp(Process* p, float timeoutS);
bool ProcessRestart(Process* p, const char* reason);   /* a planned restart */
void SupStopAll(Supervisor* s);   /* at shutdown and on SysDie; every row -> DOWN */

/* ---------------- ROS2 (runtime/ros.py) ---------------- The ROS2 library needs ONE
 * init per program before any node, and ONE shutdown at the end.
 * Both calls are explicit: the app calls RosInit first and RosShutdown last. */
void RosInit(void);
void RosShutdown(void);
typedef void (*RosMessageFn)(const void* msg);
/* one topic, on its own node and its own thread */
/*
 * @spin:
 *     runs the executor: calls onMessage per message
 */
typedef struct RosSubscription {
	void*     node;
	void*     executor;
	OsThread* spin;
} RosSubscription;

RosSubscription* RosSubscribe(
	const char* node,
	const char* topic,
	RosMessageFn onMessage
);
void RosSubscriptionClose(RosSubscription* s);
#endif
