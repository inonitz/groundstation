/* record_frame.h -- contract 3 of the recorder: a frame or a mask, as a lossless PNG at
 * compression level 1 (TEL16) */
#ifndef __HARDEN2_RECORD_FRAME_H__
#define __HARDEN2_RECORD_FRAME_H__

#include "frame_types.h"
#include "record_field.h"
#include "recorder.h"

/* buffer sizes: a folder name of at most 63 characters, one or two names joined by one
 * "/"; a file name of at most 31 characters, no "/", no extension */
enum {
	kRecordFolderBytes = 64,
	kRecordNameBytes = 32
};

/* the checks run before the take, so the fill cannot fail; INVALID_ARG: the size, the
 * format, the stride, the folder or the name. Then: a free buffer taken, the pixels
 * copied, the buffer enqueued, the writer woken; the PNG is the writer's (section 2.4) */
RecordResult RecordFrame(
	const char* folder,
	const char* name,
	MonotonicNs at,
	const FrameView* frame
);

#endif
