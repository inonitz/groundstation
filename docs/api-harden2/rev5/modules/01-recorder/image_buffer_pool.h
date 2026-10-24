/* image_buffer_pool.h -- an object pool with a free list, plus a producer-consumer work
 * queue: a fixed set of N image buffers in one pixel block, allocated once. The free
 * list holds the buffers nobody uses; the work queue holds the filled ones, oldest
 * first. A producer takes a buffer from the free list, fills it, and enqueues it. The
 * consumer peeks the oldest, processes it, appends its line, dequeues it and returns it
 * to the free list. A buffer in neither queue belongs to the one thread that holds it.
 * V4L2 calls the same shape a buffer queue. Here: the vision job threads fill, the
 * writer encodes the PNG (recorder.md section 2.4) */
#ifndef __HARDEN2_IMAGE_BUFFER_POOL_H__
#define __HARDEN2_IMAGE_BUFFER_POOL_H__

#include <stdbool.h>
#include <stdint.h>

#include "fixed_text.h"
#include "frame_types.h"
#include "index_queue.h"
#include "monotonic_clock.h"
#include "record_frame.h"

/* kMasksPerPass: the perception's mask limit; config/ in Python (RCD7) */
enum {
	kFramePoolBuffers = 8,
	kMasksPerPass = 3,
	kMaskPoolBuffers = kFramePoolBuffers * kMasksPerPass
};

typedef uint32_t BufferCount;

/* the writer's one write of the PNG file to the disk; kept on the image, so a frame
 * line retried after a failed append knows its ok value and skips the encode */
typedef enum {
	PNG_WRITE_PENDING,
	PNG_WRITTEN,
	PNG_WRITE_FAILED,
	PNG_NAME_CLASH
} PngOnDiskStatus;

DEFINE_FIXED_TEXT(FolderName, kRecordFolderBytes);   /* one or two names under the session folder */
DEFINE_FIXED_TEXT(FileName, kRecordNameBytes);       /* the PNG's name without its extension */

/* one frame or one mask. m_pixels points into the pool's pixel block (the frame size
 * times 3 for BGR24, times 1 for GRAY8). m_frameCaptureTimestamp: when the frame source
 * wrote the frame, from the caller; a mask carries its frame's. m_frameCopiedInTimestamp:
 * when the pixels were copied in from the shared slot; the stall question reads it */
typedef struct {
	uint8_t*        m_pixels;
	MonotonicNs     m_frameCaptureTimestamp;
	MonotonicNs     m_frameCopiedInTimestamp;
	FolderName      m_folderName;
	FileName        m_fileName;
	PngOnDiskStatus m_status;                 /* PNG_WRITE_PENDING until the writer's one write */
} ImageBuffer;

/* m_pixelBlock: one allocation of m_count images; m_buffers: one array of m_count
 * structs. The two index queues sit each under its own lock (RCD50): a take and a
 * return use the free list's, an enqueue and a dequeue the work queue's */
typedef struct {
	uint8_t*     m_pixelBlock;
	ImageBuffer* m_buffers;
	BufferCount  m_count;
	IndexQueue   m_freeList;
	IndexQueue   m_workQueue;   /* oldest first */
} ImageBufferPool;

/* false: the allocation failed; Create then returns false and the app dies at start */
bool ImageBufferPoolCreate(ImageBufferPool* pool, BufferCount count, uint32_t bytesPerImage);
void ImageBufferPoolDestroy(ImageBufferPool* pool);

/* the producer's side */
ImageBuffer* ImageBufferPoolTakeFree(ImageBufferPool* pool);   /* NULL: every buffer is in use */
/* stamps m_frameCopiedInTimestamp, puts the buffer on the work queue */
void ImageBufferPoolEnqueueFilled(ImageBufferPool* pool, ImageBuffer* image);

/* the consumer's side: the oldest filled image stays at the front until its frame line
 * is in the file; peek, encode once, append, then dequeue and return (section 2.4) */
ImageBuffer* ImageBufferPoolPeekFilled(ImageBufferPool* pool);   /* NULL: the work queue is empty */
void ImageBufferPoolDequeueFilled(ImageBufferPool* pool);         /* the front, after its frame line */
/* back on the free list; m_status back to PNG_WRITE_PENDING */
void ImageBufferPoolReturnFree(ImageBufferPool* pool, ImageBuffer* image);

/* the stall question, for RecorderReadHealth: the copy time of the oldest image on the
 * work queue, or 0 when it is empty; the front index and the image's time are two reads,
 * a racy pair that delays a stall report by one frame at most (section 2.8) */
MonotonicNs ImageBufferPoolOldestCopiedInTimestamp(ImageBufferPool* pool);

#endif
