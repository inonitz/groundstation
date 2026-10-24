/* runtime_internal.h -- what crosses a boundary inside runtime, and what gets a pure
 * test: Die's sequence and its step 4; the supervisor's state and its policy; the
 * subscription's state. The loops live in the source files. */
#ifndef __HARDEN2_RUNTIME_INTERNAL_H__
#define __HARDEN2_RUNTIME_INTERNAL_H__

#include "runtime.h"

/* ============================== 1. Die ===================================== */

enum {
	kDieMaxFlushes = 4
};

/* ONE instance, file-static in the Die source, zero at load, filled by the setters at
 * start, read once in Die; no other file touches it
 * @m_dying: the first Die wins; a later Die parks until the exit */
typedef struct {
	DieActionFn  m_handover;
	void*        m_handoverCtx;
	DieActionFn  m_notify;
	void*        m_notifyCtx;
	DieActionFn  m_flushes[kDieMaxFlushes];
	void*        m_flushCtx[kDieMaxFlushes];
	uint32_t     m_nFlushes;
	DieActionFn  m_childrenStop;
	void*        m_childrenCtx;
	_Atomic bool m_dying;
} DieSequence;

/* Die's step 4, on the Die thread, registered by SupervisorCreate as m_childrenStop:
 * m_launchLock (with a timeout), m_stopping, each child's stop signal through its pidfd
 * where no stop was sent, the retry signal after its delay where the policy has one,
 * one deadline on every pidfd (never a reap), the kill of the late ones, logged.
 * TOCTOU (the owner, 2026-10-17): the check, the fork and the pid store are one critical
 * section; the flag store and the list read are the same one; no reap or close once the
 * flag is set; every signal through the pidfd, never a pid; the lock timeout is the one
 * kept window, covered by the parent-death signal */
void SupervisorStopEveryChildForDie(Supervisor* s, MonotonicNs deadlineNs);

/* ============================ 2. the supervisor ============================= */

/* the one timer of a table entry: what is due next, and when */
/*
 * @DEADLINE_RELAUNCH:
 *     after a crash delay, or the waiting retry
 */
typedef enum {
	DEADLINE_NONE,
	DEADLINE_PROBE,
	DEADLINE_GRACE,
	DEADLINE_RELAUNCH
} DeadlineKind;

/* one table entry per process; every timestamp is MonotonicNow()
 * @m_spec:          the supervisor's own copy, strings included
 * @m_pidfd:         readable when the child exits; the thread polls it
 * @m_stopSentNs:    0 until the stop signal was sent; an exit after it is DOWN
 * @m_deadlineNs:    the one timer; m_deadline says what it means */
typedef struct {
	ProcessSpec   m_spec;
	int32_t       m_pid;
	int32_t       m_pidfd;
	uint32_t      m_restarts;
	MonotonicNs m_launchedNs;
	MonotonicNs m_upNs;
	MonotonicNs m_stopSentNs;
	DeadlineKind  m_deadline;
	MonotonicNs m_deadlineNs;
	const char*   m_plannedRestartReason;
	bool          mb_killed;
	StatusRow     m_row;
} SupervisedProcess;

/* the primitives of the implementation language, opaque here */
typedef struct OsThread OsThread;

/* carried from the recorder review (RCD7, RCD11, RCD27): a condition variable with a
 * remembered notify (a threading.Event): set keeps the notify when nobody waits; clear
 * drops it; is-set reads it without a lock; wait returns on a notify or on its timeout,
 * on the monotonic clock */
typedef struct OsEvent OsEvent;
void OsEventSet(OsEvent* e);
void OsEventClear(OsEvent* e);
bool OsEventIsSet(const OsEvent* e);
/* the mutex behind every lock of the design (a threading.Lock in Python) */
typedef struct OsLock OsLock;
void OsLockAcquire(OsLock* l);
void OsLockRelease(OsLock* l);
bool OsEventWait(OsEvent* e, DurationNs timeout);   /* false: the timeout passed */
typedef struct OsQueue  OsQueue;
typedef struct OsLock   OsLock;

/* the state; the thread owns the table; the loop is in the source file: one poll on
 * every pidfd and the command pipe with a timeout at the earliest m_deadlineNs; a
 * readable pidfd: reap that child under m_launchLock, then the policy; a command: a
 * planned restart or the quit; then every passed deadline, by its kind
 * @m_stopping:  set under m_launchLock by the quit and by Die's step 4; no fork after
 *               it; a reap after it is left to Die */
struct Supervisor {
	SupervisedProcess m_processes[kSupervisorMaxProcesses];
	uint32_t          m_nProcesses;
	_Atomic bool      m_stopping;
	OsThread*         m_thread;
	OsQueue*          m_commandQueue;
	int32_t           m_commandPipe[2];
	OsLock*           m_launchLock;
};

/* @AFTER_EXIT_DOWN:                 a stop was sent or the quit ran: no relaunch
 * @AFTER_EXIT_RELAUNCH_PLANNED:     a restart on purpose: relaunch now; not counted
 * @AFTER_EXIT_RELAUNCH_AFTER_DELAY: a crash within the budget: after 1.5, 3, 4.5 s
 * @AFTER_EXIT_WAIT_FOR_USER:        the budget spent; a phone-side part
 * @AFTER_EXIT_DIE:                  the budget spent; a laptop part */
typedef enum {
	AFTER_EXIT_DOWN,
	AFTER_EXIT_RELAUNCH_PLANNED,
	AFTER_EXIT_RELAUNCH_AFTER_DELAY,
	AFTER_EXIT_WAIT_FOR_USER,
	AFTER_EXIT_DIE
} AfterExitDecision;

/* the restart policy, a pure function of the entry, tested by a table without a
 * process: up for SUPERVISOR_STABLE_NS resets the count first; then the five cases */
AfterExitDecision SupervisorDecideAfterExit(
	const SupervisedProcess* p,
	MonotonicNs now
);

/* every child: its own session (a terminal Ctrl+C never reaches it); the parent-death
 * signal set by this prefix on argv; stopped through its pidfd */
extern const char* const kSupervisorArgvPrefix[];   /* setpriv --pdeathsig TERM -- */

/* ============================== 3. ROS 2 =================================== */

/* the state behind RosSubscription: the node, its one subscription, the executor
 * that spins them, the thread that runs the executor */
/*
 * @m_node:
 *     rclpy.Node
 * @m_subscription:
 *     rclpy.Subscription
 * @m_executor:
 *     rclpy SingleThreadedExecutor
 */
struct RosSubscription {
	const char*             m_nodeName;
	const char*             m_topic;
	const char*             m_messageType;
	RosSubscriptionCallback m_callback;
	void*                   m_callbackCtx;
	void*                   m_node;
	void*                   m_subscription;
	void*                   m_executor;
	OsThread*               m_executorThread;
};

#endif
