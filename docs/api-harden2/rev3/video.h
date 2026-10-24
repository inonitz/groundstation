/*
 * video.h -- harden2 API v2.3 (2026-09-24). Module video/: ONE interface over ONE source,
 * picked by config.VIDEO (owner ruling 2026-09-23). Video opens the source, retries it,
 * owns its "video" status row, hands out the latest frame and, for DJI video, restarts
 * gstreamer when the frames stop.
 */
#ifndef __HARDEN2_API_VIDEO_H__
#define __HARDEN2_API_VIDEO_H__
#include "runtime.h"

/* ---- the objects of this module, with their data members ---- */
typedef struct Video Video;
typedef struct RosStream RosStream;
struct RosStream {                        /* python: video.ros_stream.RosStream (VIDEO=dji)  */
	void*            frame;               /* the latest image from the ROS2 topic            */
	uint64_t         frames;              /* how many arrived                                */
	OsLock*          lock;
	RosSubscription* sub;
};
struct Video {                            /* python: video.video.Video                       */
	const char* source;                   /* "0", an rtsp URL, a file path, a ROS topic      */
	int         kind;                     /* a VideoSourceKind                               */
	bool        live;                     /* a live source never "ends"                      */
	Process*    gstreamer;                /* VIDEO=dji only, else NULL                       */
	void*       latest;                   /* the newest frame, for VideoSnapshot             */
	OsLock*     lock;
	uint64_t    seenFrames;               /* the stall guard counts from here                */
	double      lastFrame;                /* when the last frame came (monotonic s)          */
	double      lastRestart;              /* when gstreamer was last restarted               */
	Status*     status;                   /* the "video" row                                 */
	void*       capture;                  /* cv2.VideoCapture, or the RosStream              */
};

typedef enum {
	SRC_ROS,       /* the phone's video: gstreamer -> ROS2 camera/stream (VIDEO=dji)     */
	SRC_WEBCAM,    /* a camera index                                                     */
	SRC_GSTREAMER, /* a pipeline string                                                  */
	SRC_STREAM,    /* an rtsp/http URL                                                   */
	SRC_FILE       /* a video file (tests)                                               */
} VideoSourceKind;
VideoSourceKind VideoSourceKindOf(const char* source);   /* the ONE classifier          */

typedef struct {
	const uint8_t* bgr;
	uint32_t       width, height;
} VideoFrame;

typedef struct Video Video;
/* @gstreamer: the gstreamer Process handle (SRC_ROS only), else NULL. Never open within
 * config.OPEN_TIMEOUT -> FAILED and die (the source is required). */
Video* VideoCreate(const char* source, Process* gstreamer);
bool   VideoRead(Video* v, VideoFrame* out);      /* the display loop; runs the stall guard */
bool   VideoSnapshot(Video* v, VideoFrame* copy); /* a private copy, for vision tasks       */
bool   VideoIsLive(const Video* v);               /* a live source never "ends". [rev3: the
                                                     header's own words] every camera and stream
                                                     is live; only SRC_FILE ends             */
void   VideoClose(Video* v);
uint32_t VideoStatus(Video* v, StatusRow* rows, uint32_t cap);   /* its "video" row       */
SupProcess GstreamerProcess(const char* logDir, const char* phoneIp);   /* WAITS, never dies */

/* The camera tool (video/cam_list.py, a script): every camera and what it delivers
 * (`run.sh status`), or with --selected only WEBCAM_DEV (`run.sh preflight`, owner P1 a); a
 * camera that gives no frame is read once more after CAMERA_CHECK_RETRY_SECONDS (O3 a). */

#endif /* __HARDEN2_API_VIDEO_H__ */
