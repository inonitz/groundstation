/* framebuffer.h -- the shared-memory ring of frames every reader takes the latest from.
 * One writer (the frame source thread), readers in the app (the draw, the vision jobs),
 * and the SAM3 server, which inherits the block's descriptor at launch and reads it.
 * Rulings: SK4, SK5, FR1, RVW3, RVW4, FB1 to FB8 (docs/spec-harden2-cleanup.md). */
#ifndef __HARDEN2_FRAMEBUFFER_H__
#define __HARDEN2_FRAMEBUFFER_H__

#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>

#include "frame_types.h"
#include "monotonic_clock.h"
#include "recorder.h"

/* config values, read once at Create. Slots = MaxHolders + 3: the holders, the slot
 * under write, the latest slot (never taken by the writer), one spare */
enum {
	kFramebufferMaxHolders = 9,
	kFramebufferSlots = kFramebufferMaxHolders + 3,
	kFramebufferAcquireTries = 8,
	kFramebufferHeaderBytes = 4096,
	kFramebufferSlotHeadersAt = 128,
	kFramebufferSlotHeaderBytes = 64,
	kFramebufferSlotAlignBytes = 64,
	kFramebufferBytesPerPixel = 3
};

/* bit 31 of a slot's count dword: the writer is filling the slot */
#define FRAMEBUFFER_WRITING  UINT32_C(0x80000000)

#define FRAMEBUFFER_NO_FRAME  UINT32_C(0xFFFFFFFF)

typedef int32_t FileDescriptorType;

/* the block, byte for byte: this header at 0; the slot headers at SlotHeadersAt; the
 * pixels of slot i at m_pixelsAt + i * m_slotBytes, packed BGR24. Only m_latestIndex
 * changes after Create */
typedef struct {
	FrameSize        m_size;
	uint32_t         m_slotCount;
	uint32_t         m_slotBytes;
	uint32_t         m_pixelsAt;
	uint8_t          m_pad0[48];
	_Atomic uint32_t m_latestIndex;
	uint8_t          m_pad1[60];
} FramebufferHeader;

/* m_sequence is 0 while the slot is empty or being filled, so a Find never matches a
 * slot under write */
typedef struct {
	_Atomic uint32_t m_sequence;
	_Atomic uint32_t m_count;
	MonotonicNs    m_capturedAt;
	uint8_t          m_pad0[48];
} FrameSlotHeader;

/* valid from Acquire (or Find) to Release; the writer cannot touch a held slot */
typedef struct {
	uint32_t       m_index;
	uint32_t       m_sequence;
	MonotonicNs  m_capturedAt;
	const uint8_t* m_pixels;
} ReadOnlyFrameReference;

/* valid from BeginWrite to EndWrite; the sequence is given at EndWrite */
typedef struct {
	uint32_t m_index;
	uint8_t* m_pixels;
} ReadWriteFrameReference;

typedef struct {
	uint32_t m_latestSequence;
	uint32_t m_slotsHeld;
	uint64_t m_retries;
	uint64_t m_misses;
} FramebufferHealthStatus;

/* ============================ 1. the app's buffer ============================ */

typedef struct Framebuffer Framebuffer;

/* A nameless memory file (memfd): only a child that inherits the descriptor can map it;
 * the kernel frees it with the last mapping. The pages are reserved and the mapping
 * populated here, so no write or page fault fails mid-run. NULL: the pages cannot be
 * reserved; the atomics package is not the pinned version or yields the GIL. Created
 * before the supervisor (the SAM3 server's spec passes the descriptor); destroyed after
 * it, after the writer thread and the pool joined */
Framebuffer* FramebufferCreate(FrameSize size);
void         FramebufferDestroy(Framebuffer* f);

FrameSize FramebufferDimensions(const Framebuffer* f);

/* for the SAM3 server's spec: passed at launch, its number on the command line */
FileDescriptorType FramebufferDescriptor(const Framebuffer* f);

/* ============================== 2. the writer ============================== */

/* one thread only, for the buffer's life. Die: no free slot (FR1, a bug); a write still
 * open; a call from another thread */
ReadWriteFrameReference FramebufferBeginWrite(Framebuffer* f);

/* publishes: readers that load the latest after this get this frame */
void FramebufferEndWrite(
	Framebuffer* f,
	ReadWriteFrameReference w,
	MonotonicNs capturedAt
);

/* ============================== 3. a reader ================================ */

/* never blocks. ONE hold per thread at a time: a second Acquire on a holding thread is
 * a bug and dies. False: no frame yet, or AcquireTries misses in a row (counted) */
bool FramebufferAcquireLatest(Framebuffer* f, ReadOnlyFrameReference* out);

/* a release without a hold is a bug and dies */
void FramebufferRelease(Framebuffer* f, ReadOnlyFrameReference ref);

void FramebufferReadHealth(const Framebuffer* f, FramebufferHealthStatus* out);

/* ======================= 4. the other process: a view ======================= */

/* the SAM3 server's read-only mapping; the descriptor is reopened read-only, so the
 * kernel refuses a writable mapping: the server cannot touch a count (RVW3) */
typedef struct FramebufferView FramebufferView;

/* once at the server's start. NULL: not our descriptor, or the atomics package check
 * fails; the server exits and the supervisor relaunches it */
FramebufferView* FramebufferOpen(FileDescriptorType fd);
void             FramebufferClose(FramebufferView* v);

FrameSize FramebufferViewSize(const FramebufferView* v);

/* false: stale, the job released and the writer reused the slot (or sequence 0); the
 * pixels are stable while the job holds the slot, which covers every reply it accepts */
bool FramebufferFind(
	const FramebufferView* v,
	uint32_t sequence,
	ReadOnlyFrameReference* out
);

#endif
