/* framebuffer_internal.h -- the state behind the two handles, the writer's choice of a
 * slot as a pure function, the steps of every call in order, the TOCTOU list. */
#ifndef __HARDEN2_FRAMEBUFFER_INTERNAL_H__
#define __HARDEN2_FRAMEBUFFER_INTERNAL_H__

#include "framebuffer.h"

/* the one mapping, with the header's offsets resolved once (FB7: kept) */
typedef struct {
	FramebufferHeader* m_header;
	FrameSlotHeader*   m_slots;
	uint8_t*           m_pixels;
	uint64_t           m_total;
} FramebufferMap;

/* the atomic views of the implementation language (Python: the package's view
 * contexts, entered at Create, exited at Destroy) */
typedef struct FramebufferViews FramebufferViews;

/* m_writerThread and mb_writeOpen are the writer thread's own. The three shared values
 * are relaxed atomics: m_slotsHeld (writer stores, main thread loads), m_retries and
 * m_misses (readers add, main thread loads); a lost add on a diagnostic is harmless.
 * The next sequence is the latest slot's sequence plus 1 (FB7: no copies) */
struct Framebuffer {
	FramebufferMap     m_map;
	FileDescriptorType m_fd;
	FramebufferViews*  m_views;
	uint64_t           m_writerThread;
	bool               mb_writeOpen;
	_Atomic uint32_t   m_slotsHeld;
	_Atomic uint64_t   m_retries;
	_Atomic uint64_t   m_misses;
};

/* this thread's holds, 0 or 1 (Python: threading.local) */
extern _Thread_local uint32_t gFramebufferHoldsOnThread;

struct FramebufferView {
	FramebufferMap     m_map;
	FileDescriptorType m_fd;
	FramebufferViews*  m_views;
};

uint64_t FramebufferBytes(FrameSize size, uint32_t slots);

/* the oldest slot (the lowest sequence; 0 is the oldest) with a count of 0, skipping
 * latestIndex; -1 when none. slotsHeld gets the count of slots with readers. A lost
 * compare-and-swap after it calls it again: the loser's slot now has a count of 1 */
int32_t FramebufferPickOldestFree(
	const FrameSlotHeader* slots,
	uint32_t slotCount,
	uint32_t latestIndex,
	uint32_t* slotsHeld
);

/* Create: memfd_create; ftruncate; reserve the pages (ENOSPC: NULL); map read-write,
 * populated; the header; the views, recast to keep the GIL and checked (a miss: NULL);
 * every sequence and count 0; m_latestIndex = NO_FRAME.
 * Destroy: exit the views; drop the pixel views; unmap (a pixel array kept past its
 * Release: logged); close the descriptor.
 * BeginWrite: m_writerThread 0: store this thread; another thread: Die; mb_writeOpen
 * set: Die; set it; Pick; -1: Die; compare-and-swap the count 0 -> WRITING; a loss:
 * Pick again; store m_sequence = 0; return the slot's pixels.
 * EndWrite: sequence = the latest slot's sequence + 1 (1 when NO_FRAME); store
 * m_capturedAt; store m_sequence; subtract WRITING; store m_latestIndex; clear
 * mb_writeOpen.
 * AcquireLatest: the thread's hold is 1: Die; at most AcquireTries times: load
 * m_latestIndex; NO_FRAME: false; previous = add 1 to the count; WRITING in previous:
 * subtract 1, add 1 to m_retries, again; else load m_sequence and m_capturedAt, the
 * thread's hold = 1, true. After the last try: add 1 to m_misses, false.
 * Release: previous = subtract 1; previous 0 or WRITING alone: Die; the thread's hold
 * = 0.
 * Open: reopen the descriptor read-only (/proc/self/fd); fstat (a size under
 * HeaderBytes: NULL); map read-only, populated; the header against the size (NULL on a
 * mismatch); the views as in Create.
 * Find: sequence 0: false; the slot whose m_sequence matches: true; none: false. */

/* TOCTOU (gate item 11). The writer's "count is 0, then write": the compare-and-swap is
 * the check and the claim in one instruction; a reader that added 1 first makes it fail.
 * The reader's "latest, then add 1": the add returns WRITING when the writer got there
 * first; the writer never takes the latest slot, so this needs a reader asleep until the
 * slot is reused (1 frame with 9 holders, 11 with none). A reader asleep longer holds a
 * complete, newer frame and reports the sequence it reads after the hold. The server's
 * "Find, then read": the job's hold covers every reply it accepts; a slot under write
 * carries sequence 0, so Find never matches it; a reply after the job's timeout is
 * dropped by its request id (module 6). Create, then Open: the server is launched after
 * Create returned; no name exists for an earlier open. Release twice: the subtract's
 * previous value catches 0 and WRITING alone; a second release while another reader
 * holds is not seen, so the with-block is the only release path. A second hold on one
 * thread: the thread-local count. A second writer: the stored thread; a write left
 * open: the flag. Destroy while the writer runs: the writer's join first (module 12). */

#endif
