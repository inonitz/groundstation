/* runtime.h -- the floor of the app: Die, the supervisor, ROS 2, the preflight.
 * The public contract. The mechanism, in code: runtime_internal.h (the house split:
 * a thin public header, the internals beside it). */
#ifndef __HARDEN2_RUNTIME_H__
#define __HARDEN2_RUNTIME_H__

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "monotonic_clock.h"
#include "recorder.h"

/* ================================ 1. Die =================================== */
/* Die(reason) never returns: the sequence below, in this order, then _exit(1) */

/* one signature for every action of the sequence; past deadlineNs it is left behind */
typedef void (*DieActionFn)(void* ctx, const char* reason, MonotonicNs deadlineNs);

#define DIE_HANDOVER_CAP_NS  UINT64_C(1000000000)    /* 1 s: the emergency budget      */
#define DIE_NOTIFY_CAP_NS    UINT64_C(500000000)     /* 0.5 s                          */
#define DIE_FLUSH_CAP_NS     UINT64_C(5000000000)    /* 5 s: perf and telemetry, both  */
#define DIE_CHILDREN_CAP_NS  UINT64_C(10000000000)   /* 10 s: the children, together  */

/* the four steps, named (the owner, RUN3); the contexts stay the caller's */
/* the phone client: halt, stop, stop */
void DieSetHandover(DieActionFn fn, void* ctx);
void DieSetNotify(DieActionFn fn, void* ctx);   /* the app: one POST /tts */
void DieAddFlush(DieActionFn fn, void* ctx);   /* perf, telemetry: their flush */
void DieSetChildrenStop(DieActionFn fn, void* ctx);   /* SupervisorCreate sets it */

/* 1 handover (1 s)  2 notify (0.5 s)  3 flushes (5 s)  4 children (10 s)  5 _exit(1) */
void Die(const char* reason);

/* a start-up fault: nothing registered yet, so the sequence is the banner and _exit */
void DieInstallUncaughtErrorHooks(void);   /* threading, main thread, unraisable */

/* ============================ 2. the supervisor ============================= */

typedef enum {
	PROCESS_STARTING,
	PROCESS_UP,
	PROCESS_RECOVERING,
	PROCESS_WAITING_FOR_USER,
	PROCESS_FAILED,
	PROCESS_DOWN
} ProcessState;

/* the row the main thread reads each frame: ONE atomic load of an immutable pair. The
 * pair is replaced, never changed; the old pair is reclaimed only after the main thread
 * has drawn a frame since the swap (a grace period; in Python the collector does it) */
typedef struct {
	ProcessState m_state;
	const char*  m_detail;
} RowValue;

typedef struct {
	const RowValue* _Atomic m_row;
} StatusRow;

typedef bool (*ReadyProbeFn)(void* ctx);   /* an HTTP /health or a port; under 200 ms */

/* how a process is stopped (PROC2: its own way): the stop signal, then a retry signal
 * after a delay when the first did not end it (0 = none), then the kill after the
 * grace, logged. llama-server: SIGINT, SIGINT after 2 s, 10 s. The others: SIGINT, 0,
 * 10 s */
typedef struct {
	int32_t  m_stopSignal;
	int32_t  m_retrySignal;
	uint64_t m_retryDelayNs;
	uint64_t m_graceNs;
} ProcessStopPolicy;

/*
 * @BUDGET_SPENT_WAIT_FOR_USER:
 *     a phone-side part: WAITING, relaunched every 5 s
 */
typedef enum {
	BUDGET_SPENT_DIE,
	BUDGET_SPENT_WAIT_FOR_USER
} BudgetSpentPolicy;

/* a module's description of its process, from a pure function of config and the log
 * folder; the supervisor COPIES it whole (the strings too) at Create, since a relaunch
 * 40 minutes later must not depend on the caller's memory. m_passFds: descriptors the
 * child inherits (the framebuffer's memfd for the SAM3 server, FB2); every other
 * descriptor stays closed in the child */
typedef struct {
	const char*        m_name;
	const char* const* m_argv;
	const char* const* m_env;
	ReadyProbeFn       m_readyProbe;
	void*              m_readyProbeCtx;
	uint64_t           m_readyTimeoutNs;
	ProcessStopPolicy  m_stop;
	BudgetSpentPolicy  m_onBudgetSpent;
	const char*        m_logPath;
	const int32_t*     m_passFds;
	uint32_t           m_nPassFds;
} ProcessSpec;

/* what the module holds, by value */
typedef struct {
	uint32_t         m_index;
	const StatusRow* m_row;
} ProcessHandle;

typedef struct Supervisor Supervisor;   /* OS resources only, no app state: opaque */

enum {
	kSupervisorMaxProcesses = 8,
	kSupervisorMaxRestarts = 3
};

/* up SUPERVISOR_STABLE_NS: the restart count goes back to 0; the relaunch delay is
 * 1.5 s, then 3 s, then 4.5 s: the delay times the restart count (2026-10-17) */
#define SUPERVISOR_STABLE_NS            UINT64_C(60000000000)
#define SUPERVISOR_RELAUNCH_DELAY_NS    UINT64_C(1500000000)
#define SUPERVISOR_WAITING_RETRY_NS     UINT64_C(5000000000)
#define SUPERVISOR_READY_PROBE_NS       UINT64_C(500000000)
#define SUPERVISOR_READY_PROBE_CALL_NS  UINT64_C(200000000)
#define SUPERVISOR_DEFAULT_GRACE_NS     UINT64_C(10000000000)

/* the supervisor OWNS the processes: it is created with every spec the settings need
 * (a module gives its spec through a pure function; the app collects them), launches
 * them all, watches, relaunches, and stops them all at Destroy; a module never
 * launches or stops its own process */
Supervisor* SupervisorCreate(const ProcessSpec* specs, uint32_t nSpecs);
void SupervisorDestroy(Supervisor* s);   /* every child its stop, one deadline, join */

/* the handle of a process by its spec name, for a row or a planned restart */
ProcessHandle SupervisorProcess(const Supervisor* s, const char* name);

/* blocks until the row is UP (true), FAILED or WAITING (false); the app, at start */
bool SupervisorWaitUntilReady(Supervisor* s, ProcessHandle p);

/* the one request a module may make: a planned restart (the video stall guard);
 * the process's own stop, then the relaunch; not counted against the budget */
void SupervisorRestartOnPurpose(Supervisor* s, ProcessHandle p, const char* reason);

/* ============================== 3. ROS 2 =================================== */

void RosContextInit(void);   /* rclpy.init, once per process; the Ctrl+C handler off */
/* rclpy.shutdown, after the last subscriber is destroyed */
void RosContextShutdown(void);

/* the callback of a subscription; it runs on the subscriber's executor thread (below),
 * never on the main thread; it stamps the message with MonotonicNow() and hands it on; it
 * holds no app state */
typedef void (*RosSubscriptionCallback)(void* ctx, const void* message);

/* one ROS 2 node with ONE subscription, spun by its own single-threaded executor on
 * its own thread: a producer thread of the app (the keys, the mic, the drone frames) */
typedef struct RosSubscription RosSubscription;

RosSubscription* RosSubscriptionCreate(
	const char* nodeName,
	const char* topic,
	const char* messageType,
	RosSubscriptionCallback callback,
	void* ctx
);
/* executor shutdown, join, destroy the node, free the subscription; ctx stays the
 * caller's */
void RosSubscriptionDestroy(RosSubscription* sub);

/* ============================ 4. the preflight ============================== */

/* run once at start, before any package import: the packages, the native programs,
 * the model files, one libggml version, the CPUs the process may use; a miss dies
 * with the command that fixes it */
void PreflightOrDie(void);

#endif
