/*
 * video.h -- harden2 API rev4 DRAFT (2026-10-02; reworked, owner HDR3). Module video/.
 * ONE video source feeds the frame ring (frames.h). There are three kinds of source,
 * chosen ONCE
 * from config.VIDEO. Each kind is its own small struct; none is a patched version of another.
 *
 *   VIDEO=dji     the drone's camera:
 *                 phone app --(H.264 over TCP)--> our gstreamer program
 *                 (a native ROS2 node, a supervised process)
 *                 --(the ROS2 topic camera/stream)--> RosSource
 *   VIDEO=webcam  a camera on the laptop: CameraSource reads it directly
 *   a file path   a recorded video, for tests: FileSource; the ONLY kind that can end
 */
#ifndef __HARDEN2_API_VIDEO_H__
#define __HARDEN2_API_VIDEO_H__
#include "runtime.h"
#include "frames.h"

typedef enum {
	VIDEO_DRONE,
	VIDEO_WEBCAM,
	VIDEO_FILE
} VideoKind;

/* VIDEO_DRONE */
/*
 * @images:
 *     camera/stream: each image goes into the ring
 * @lastFrameAt:
 *     for the stall check
 * @restartStream:
 *     The stream can stall while the process still runs. Then Video asks for a restart
 *     through this callback (the app gives ProcessRestart on the gstreamer process).
 *     Video does NOT hold or own the process: the supervisor does.
 */
typedef struct {
	RosSubscription* images;
	double           lastFrameAt;
	void (*restartStream)(const char* reason);
} RosSource;

/* VIDEO_WEBCAM */
typedef struct {
	int32_t   device;
	void*     capture;
	OsThread* reader;
} CameraSource;

typedef struct {
	const char* path;
	void*       capture;
	OsThread*   reader;
	bool        ended;
} FileSource;

/*
 * @ring:
 *     where every frame is written
 * @status:
 *     the "video" row: UP while frames arrive
 */
typedef struct Video {
	VideoKind  kind;
	union { RosSource drone; CameraSource webcam; FileSource file; } source;
	FrameRing* ring;
	Status*    status;
} Video;

/* restartStream: VIDEO_DRONE only */
Video* VideoCreate(
	VideoKind kind,
	const char* source,
	FrameRing* ring,
	void (*restartStream)(const char* reason)
);
void VideoClose(Video* v);
FrameSeq VideoNewest(const Video* v);   /* the newest frame's number; 0 = no frame yet */
bool VideoEnded(const Video* v);   /* true ONLY for a file at its end. A camera or the */
                                          /* drone stream never ends: no frames = the
                                           *     row is */
                                          /* not UP and the screen shows "waiting for
                                           * video" */
/* VIDEO_DRONE */
ProcessSpec GstreamerProcess(const char* logDir, const char* phoneIp);
#endif
