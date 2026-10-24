/* frame_source_internal.h -- the state behind the handle, the stall rule as a pure
 * function, the steps of the capture thread, of Poll and of the bridge, the TOCTOU
 * list */
#ifndef __HARDEN2_FRAME_SOURCE_INTERNAL_H__
#define __HARDEN2_FRAME_SOURCE_INTERNAL_H__

#include <stdatomic.h>

#include "frame_source.h"

typedef struct OsThread      OsThread;
typedef struct CaptureDevice CaptureDevice;   /* cv2.VideoCapture */

/* ============================ 1. the stall guard =========================== */

/* the main thread's alone: Poll is its only caller
 * @m_lastNewFrameAt: Create's time until the first frame
 * @m_lastRestartAt:  0 until the first planned restart */
typedef struct {
	uint32_t          m_lastSequence;
	MonotonicNs m_lastNewFrameAt;
	MonotonicNs m_lastRestartAt;
	FrameSourceCount  m_plannedRestarts;
} StallGuard;

/*
 * @STALL_MARK:
 *     the row RECOVERING; no restart
 * @STALL_RESTART:
 *     the row RECOVERING and the receiver's planned restart
 */
typedef enum {
	STALL_NONE,
	STALL_NEW_FRAME,
	STALL_MARK,
	STALL_RESTART
} StallAction;

/* pure, tested by a table: another sequence than the last: NEW_FRAME; under STALL_NS
 * since the last new frame: NONE; no restart allowed (the webcam, the file): MARK; no
 * restart yet, or RESTART_EVERY since the last: RESTART; else MARK. Every compare is
 * now minus an earlier MonotonicNow() stamp */
StallAction FrameSourceDecideStall(
	const StallGuard* g,
	uint32_t latestSequence,
	bool canRestart,
	MonotonicNs now
);

/* ============================ 2. the state ================================= */

/* the webcam or the file. The thread writes the slots and adds to the two counters
 * (relaxed); Poll loads them; m_guard and m_row are the main thread's
 * @mb_isFile:         at a failed read, rewind instead of the pause; pace each frame
 * @m_frameIntervalNs: the file's pacing, 1 s over its frame rate; 0 for the webcam */
struct CaptureSource {
	bool                     mb_isFile;
	CaptureDevice*           m_device;
	Framebuffer*             m_frames;
	FrameSize                m_size;
	DurationNs         m_frameIntervalNs;
	OsThread*                m_thread;
	_Atomic bool             mb_stop;
	_Atomic FrameSourceCount m_failedReads;
	_Atomic FrameSourceCount m_rejectedFrames;
	StallGuard               m_guard;
	StatusRow                m_row;
};

/* the drone: every field the main thread's */
struct DroneSource {
	Supervisor*   m_supervisor;
	ProcessHandle m_receiver;
	Framebuffer*  m_frames;
	StallGuard    m_guard;
	StatusRow     m_row;
};

/* the bridge process's one state; its executor thread is the only writer
 * @m_frames:   OPEN 2, FramebufferOpenWriter(fd) on the inherited descriptor
 * @m_size:     the block's own
 * @m_rejected: logged once, at the exit */
typedef struct {
	Framebuffer*     m_frames;
	FrameSize        m_size;
	FrameSourceCount m_rejected;
	RosSubscription* m_subscription;
} FrameBridge;

/* ============================ 3. the steps, in order ======================= */

/* CaptureThread, until mb_stop:
 *   1. no claim open: claim = FramebufferBeginWrite (Die when no slot is free, FR1)
 *   2. ok, image = read(m_device, the claim's pixels)
 *   3. not ok: failed reads + 1; the file at its end: rewind, else pause
 *      FAILED_READ_PAUSE; back to 2, the claim kept
 *   4. image is not the claim's pixels (another size: OpenCV made its own array and
 *      left the slot untouched): rejected + 1; back to 2, the claim kept
 *   5. at = MonotonicNow(); FramebufferEndWrite(claim, at); no claim open
 *   6. the file: sleep to its next frame time
 *   At the stop: return; a claim still open is left to the buffer's end.
 * Poll, on the main thread:
 *   1. FramebufferReadHealth: its latest sequence, read from the block
 *   2. NEW_FRAME: the guard's sequence and time; the row UP
 *   3. MARK: the row RECOVERING
 *   4. RESTART: SupervisorRestartOnPurpose(receiver, "no frame for 6 s"); the guard's
 *      restart time and count; the row RECOVERING
 *   5. a changed row: RecordVideoRow
 * FrameBridgeMain, the bridge process:
 *   1. SIGINT sets the stop event
 *   2. FramebufferOpenWriter(fd); NULL: exit 1
 *   3. RosContextInit; RosSubscriptionCreate on camera/stream
 *   4. wait for the stop
 *   5. RosSubscriptionDestroy; RosContextShutdown; FramebufferCloseWriter
 *   6. one log line with the frames written and rejected; exit 0
 * FrameBridgeOnImage, on the bridge's executor thread:
 *   1. height, width, "bgr8", step width * 3 and the data length against m_size; a
 *      mismatch: rejected + 1; return before any claim
 *   2. at = MonotonicNow(); claim = BeginWrite; copy_pixels; EndWrite(claim, at) */

/* one "video" event per row change, the keys: state, detail, failed_reads, rejected,
 * restarts; the main thread */
void RecordVideoRow(
	MonotonicNs at,
	const RowValue* row,
	FrameSourceCount failedReads,
	FrameSourceCount rejectedFrames,
	FrameSourceCount plannedRestarts
);

/* TOCTOU (gate item 11). A claim, then a failed read: the claim stays open and the next
 * good read fills the same slot; nothing publishes a slot before a good read. A claim,
 * then a frame of another size: OpenCV writes its own array, the slot is untouched, the
 * claim stays open. The probe's size, then Create's reopen: another size at the reopen
 * is rejected frame by frame, counted, and named in the row. A frame, then the drone
 * bridge's claim: every check runs before the claim. The stall check, then the restart:
 * a frame that lands between costs one needless restart, 1 to 3 s of video. Destroy
 * while the thread holds a claim: the stop flag, the join, then the buffer's Destroy;
 * the open claim dies with the buffer. Poll and Destroy: both on the main thread. The
 * bridge killed between BeginWrite and EndWrite: its slot stays WRITING for the run;
 * named, not closed (FORCED, gate item 12) */

#endif
