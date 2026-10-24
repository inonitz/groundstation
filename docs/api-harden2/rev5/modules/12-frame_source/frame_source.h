/* frame_source.h -- the one writer of the frame buffer: a webcam, the drone's stream
 * or a video file; one kind per run, its size fixed before the buffer exists.
 * Rulings: FR1, FB2, FB3, FB5, RVW5, Q3 a, RUN9, RUN16, REV8, RCD1 (the ledger).
 * The mechanism: frame_source_internal.h */
#ifndef __HARDEN2_FRAME_SOURCE_H__
#define __HARDEN2_FRAME_SOURCE_H__

#include <stdbool.h>
#include <stdint.h>

#include "monotonic_clock.h"
#include "recorder.h"
#include "runtime.h"

/* framebuffer.h's handle and descriptor; its FrameSize goes at the recorder's fold */
typedef struct Framebuffer Framebuffer;
typedef int32_t FileDescriptorType;

/* ============================ 1. the kinds ================================= */

typedef enum {
	FRAME_SOURCE_WEBCAM,
	FRAME_SOURCE_DRONE,
	FRAME_SOURCE_FILE
} FrameSourceKind;

typedef uint32_t FrameSourceCount;

/* config values */
enum {
	kDroneFrameWidth = 1920,
	kDroneFrameHeight = 1080,
	kFrameSourceArgvMax = 8,
	kGstreamerRxEnvMax = 2,
	kFrameBridgeEnvMax = 3,
	kFrameSourceNumberBytes = 16,
	kFrameSourcePathBytes = 4096,
	kFrameSourceEnvBytes = 128
};

#define FRAME_SOURCE_STALL_NS              UINT64_C(6000000000)
#define FRAME_SOURCE_RESTART_EVERY_NS      UINT64_C(15000000000)
#define FRAME_SOURCE_POLL_EVERY_NS         UINT64_C(1000000000)
#define FRAME_SOURCE_PROBE_RETRY_NS        UINT64_C(1000000000)
#define FRAME_SOURCE_FAILED_READ_PAUSE_NS  UINT64_C(100000000)
#define GSTREAMER_RX_READY_TIMEOUT_NS      UINT64_C(10000000000)
#define FRAME_BRIDGE_READY_TIMEOUT_NS      UINT64_C(10000000000)

#define GSTREAMER_RX_NAME  "gstreamer"
#define FRAME_BRIDGE_NAME  "frame_bridge"
#define DRONE_FRAME_TOPIC  "camera/stream"

/* config's VIDEO picks the kind; the webcam asks for MJPG at m_webcamRequest */
typedef struct {
	FrameSourceKind m_kind;
	uint32_t        m_webcamDevice;
	FrameSize       m_webcamRequest;
	const char*     m_filePath;
	const char*     m_phoneIpv4;
} FrameSourceSettings;

FrameSourceSettings FrameSourceSettingsFromConfig(void);

/* ============================ 2. the size, before the buffer =============== */

/* before RecorderCreate and FramebufferCreate. The webcam: open, read one frame,
 * release; no frame: once more after PROBE_RETRY (a camera a stopped run just
 * released). The drone: 1920x1080, a given. The file: its first frame. False: no
 * frame; the app dies at start */
bool FrameSourceProbeSize(const FrameSourceSettings* s, FrameSize* out);

/* ============================ 3. the drone's two processes ================= */

/* the strings each spec points to; the app holds them until SupervisorDestroy */
typedef struct {
	const char* m_argv[kFrameSourceArgvMax];
	const char* m_env[kGstreamerRxEnvMax];
	char        m_libraryPathEnv[kFrameSourcePathBytes];
	char        m_logPath[kFrameSourcePathBytes];
} GstreamerRxSpecText;

typedef struct {
	const char* m_argv[kFrameSourceArgvMax];
	const char* m_env[kFrameBridgeEnvMax];
	int32_t     m_passFds[1];
	char        m_framesFdNumber[kFrameSourceNumberBytes];
	char        m_pythonPathEnv[kFrameSourcePathBytes];
	char        m_mallocTunablesEnv[kFrameSourceEnvBytes];
	char        m_logPath[kFrameSourcePathBytes];
} FrameBridgeSpecText;

/* pure (RUN9). The owner's receiver, unchanged: llm_to_action_gstreamer_rx --dji <phone>
 * from the native bin folder; env: LD_LIBRARY_PATH with that folder first, an addition
 * (RUN16); the probe GstreamerRxReadyProbe; SIGINT, no retry, 10 s;
 * BUDGET_SPENT_WAIT_FOR_USER; <logDir>/proc-gstreamer.log. No video server at its
 * launch, or an end of stream, leaves it alive without frames: it never reconnects; the
 * stall guard's planned restart does */
ProcessSpec GstreamerRxProcessSpec(
	const char* logDir,
	const char* phoneIpv4,
	GstreamerRxSpecText* text
);

/* OPEN 3. true: camera/stream has a publisher: the node is up; frames may not flow */
bool GstreamerRxReadyProbe(void* ctx);

/* OPEN 1, OPEN 2. pure. Our process: python3 video/frame_bridge.py --frames-fd <n>, the
 * block's descriptor passed read-write; env, additions: PYTHONPATH=<harden2 root> and
 * config's GLIBC_TUNABLES (two static malloc thresholds); the probe
 * FrameBridgeReadyProbe; SIGINT, no
 * retry, 10 s; BUDGET_SPENT_DIE; <logDir>/proc-frame_bridge.log. It subscribes to
 * camera/stream (depth 10) and is the buffer's one writer for the run; the take holds
 * its own GIL, not the app's */
ProcessSpec FrameBridgeProcessSpec(
	const char* logDir,
	FileDescriptorType framesFd,
	FrameBridgeSpecText* text
);

/* OPEN 3. true: camera/stream has a subscriber */
bool FrameBridgeReadyProbe(void* ctx);

/* ============================ 4. the source ================================ */

typedef struct CaptureSource CaptureSource;
typedef struct DroneSource   DroneSource;

/* the app holds it by value; the kind sets one pointer, the other is NULL; both NULL:
 * Create failed, the app dies at start */
typedef struct {
	FrameSourceKind m_kind;
	CaptureSource*  m_capture;
	DroneSource*    m_drone;
} FrameSourceHandle;

/* opens the device with the probe's settings; starts the frame source thread, the
 * buffer's one writer; it reads each frame straight into a claimed slot. OPEN 4 */
FrameSourceHandle WebcamSourceCreate(
	const FrameSourceSettings* s,
	FrameSize size,
	Framebuffer* frames
);

/* the same thread; the file looped and paced at its own frame rate; for tests */
FrameSourceHandle FileSourceCreate(
	const FrameSourceSettings* s,
	FrameSize size,
	Framebuffer* frames
);

/* OPEN 1. no thread in the app: the bridge writes the buffer */
FrameSourceHandle DroneSourceCreate(
	Supervisor* supervisor,
	ProcessHandle receiver,
	Framebuffer* frames
);

/* the stop, then the join; a join waits at most one read, and up to OpenCV's 10 s select
 * timeout on a dead camera. Before SupervisorDestroy and FramebufferDestroy */
void FrameSourceDestroy(FrameSourceHandle h);

/* ============================ 5. the stall guard and the row =============== */

/* the main thread, every POLL_EVERY: the buffer's latest sequence, from its health. A
 * new one: UP. None for STALL_NS: RECOVERING; the drone's receiver gets a planned
 * restart, again every RESTART_EVERY while it lasts. A changed row records one "video"
 * event. OPEN 5: the buffer's held-slot scan runs beside it */
void FrameSourcePoll(FrameSourceHandle h, MonotonicNs now);

/* the "video" row: STARTING until the first frame, UP, RECOVERING; read each frame */
const StatusRow* FrameSourceRow(FrameSourceHandle h);

#endif
