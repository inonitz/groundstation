/*
 * sam3.h -- harden2 API rev4 DRAFT (2026-10-02). Module sam3/: the SAM3 SERVICE,
 * PROPOSED as its own PROCESS (owner HDR3). The weights are loaded exactly as saved on
 * disk: NOTHING converts or quantizes weights at run time (owner HDR3; the offline tool
 * sam3/save_nf4.py made the nf4 files).
 *
 * The process: loads the model, runs one warm-up pass, opens the frame ring, then
 *     answers requests. A request names a FRAME NUMBER and a phrase. The answer holds
 *     that frame's boxes
 * and masks together: a mask never exists apart from its frame and its box.
 *  */
#ifndef __HARDEN2_API_SAM3_H__
#define __HARDEN2_API_SAM3_H__
#include "runtime.h"
#include "frames.h"

/* which saved weights; fixed at start */
typedef enum {
	SAM3_NF4,
	SAM3_BF16
} Sam3Weights;

typedef struct {
	float x0;
	float y0;
	float x1;
	float y1;
	float score;
} Box;

/* 1 byte per pixel */
typedef struct {
	uint32_t width;
	uint32_t height;
	uint8_t* bits;
} Mask;

/* "found nothing" is OK, n = 0 */
typedef enum {
	DETECT_OK,
	DETECT_NOT_READY
} DetectStatus;

/* the answer to ONE request */
/*
 * @frame:
 *     the frame these boxes and masks belong to
 * @boxes:
 *     best score first; nested boxes already merged
 * @masks:
 *     masks[i] is the mask of boxes[i]
 * @ms:
 *     how long the pass took
 */
typedef struct {
	DetectStatus status;
	FrameSeq     frame;
	uint32_t     n;
	Box          boxes[128];
	Mask         masks[128];
	uint32_t     ms;
} Detection;

/* the app's handle to the service */
/*
 * @process:
 *     the SAM3 process (the supervisor owns it)
 * @port:
 *     requests and answers, on 127.0.0.1
 * @status:
 *     the "sam3" row: UP after load + warm-up
 */
typedef struct Sam3 {
	Process*    process;
	FrameRing*  ring;
	uint16_t    port;
	Status*     status;
} Sam3;

ProcessSpec Sam3Process(const char* logDir, Sam3Weights weights);
Sam3*       Sam3Connect(Process* process, FrameRing* ring);
/* One pass on one frame. It pins the frame for the pass. Out of GPU memory -> the
 * process dies; the supervisor restarts it; the app lives on (a gain over SAM3 inside
 * the app). */
void Sam3Detect(
	Sam3* s,
	FrameSeq frame,
	const char* phrase,
	float minScore,
	Detection* out
);
#endif
