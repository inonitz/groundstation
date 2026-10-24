/*
 * video.h -- harden2 API v2.3 (2026-09-24). Module video/: ONE interface over ONE source,
 * picked by config.VIDEO (owner ruling 2026-09-23). Video opens the source, retries it,
 * owns its "video" status row, hands out the latest frame and, for DJI video, restarts
 * gstreamer when the frames stop.
 */
#ifndef __HARDEN2_API_VIDEO_H__
#define __HARDEN2_API_VIDEO_H__
#include "system.h"

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
bool   VideoIsLive(const Video* v);               /* a live source never "ends"             */
void   VideoClose(Video* v);
uint32_t VideoStatus(Video* v, StatusRow* rows, uint32_t cap);   /* its "video" row       */
SupProcess GstreamerProcess(const char* logDir, const char* phoneIp);   /* WAITS, never dies */

#endif /* __HARDEN2_API_VIDEO_H__ */
