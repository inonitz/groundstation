/* frame_types.h -- a frame's size, its pixel format, and a view of its pixels. Shared by
 * the recorder, the frame buffer and the frame source: one home. */
#ifndef __HARDEN2_FRAME_TYPES_H__
#define __HARDEN2_FRAME_TYPES_H__

#include <stdint.h>

/* the source's size, fixed per run */
typedef struct {
	uint16_t m_width;
	uint16_t m_height;
} FrameSize;

typedef enum {
	PIXEL_BGR24,
	PIXEL_GRAY8
} PixelFormat;

/* a frame or a mask as its holder sees it; the pixels stay the holder's */
typedef struct {
	PixelFormat    m_format;
	FrameSize      m_size;
	uint32_t       m_strideBytes;
	const uint8_t* m_pixels;
} FrameView;

#endif
