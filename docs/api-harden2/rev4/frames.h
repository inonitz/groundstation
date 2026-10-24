/*
 * frames.h -- harden2 API rev4 DRAFT (2026-10-02). The frame ring: ONE place in shared
 * memory where every video frame lives. PROPOSED with SAM3 as its own process (owner:
 * "RIGHT NOW").
 *
 * Why: SAM3 in its own process must see the frames without a copy per request. Measured
 *     (bench/sam3-assessment, 2026-09-28): a frame through shared memory 0.1 ms; a
 *     request to a SAM3 process costs 0.4 ms more than in-process; a detect itself
 *     takes about 410 ms.
 *
 * How it is used:
 * - The video source writes each NEW frame straight into the next free slot (the camera
 *     reads into the slot's pixels; a ROS image is copied in once). That is the only
 *     copy of the frame.
 * - Everyone else gets a FRAME NUMBER (seq), never pixels: the screen draws slot[seq];
 *     a vision request to SAM3 carries only (seq, phrase); the reply carries (seq,
 *     boxes, masks).
 * - A reader PINS the slot it works on; the writer never overwrites a pinned slot. So
 *     the frame of a 410 ms detect is still there when its boxes come back, and the log
 *     can save "this frame with these boxes" from the same slot. Then the reader unpins
 *     it.
 *  */
#ifndef __HARDEN2_API_FRAMES_H__
#define __HARDEN2_API_FRAMES_H__
#include "util.h"

/* 32 x 1280x720x3 bytes = about 88 MB */
enum {
	kFrameRingSlots = 32
};

typedef uint64_t FrameSeq;                /* the frame's number since the app started        */
/*
 * @capturedAt:
 *     monotonic seconds
 * @pins:
 *     ATOMIC: readers working on this slot
 * @bgr:
 *     width x height x 3, in the shared memory
 */
typedef struct {
	FrameSeq  seq;
	double    capturedAt;
	uint32_t  width;
	uint32_t  height;
	uint32_t  pins;
	uint8_t*  bgr;
} FrameSlot;

/*
 * @shmName:
 *     the shared-memory block every process opens
 * @newest:
 *     ATOMIC: the last frame written
 */
typedef struct FrameRing {
	const char* shmName;
	FrameSlot   slots[kFrameRingSlots];
	FrameSeq    newest;
} FrameRing;

/* the app */
FrameRing* FrameRingCreate(const char* shmName, uint32_t width, uint32_t height);
FrameRing* FrameRingOpen(const char* shmName);   /* another process (SAM3) */
/* the oldest unpinned slot, for the source */
FrameSlot* FrameRingBeginWrite(FrameRing* r);
void       FrameRingEndWrite(FrameRing* r, FrameSlot* s);   /* it becomes `newest` */
/* NULL: already overwritten */
const FrameSlot* FrameRingPin(FrameRing* r, FrameSeq seq);
void             FrameRingUnpin(FrameRing* r, const FrameSlot* s);
#endif
