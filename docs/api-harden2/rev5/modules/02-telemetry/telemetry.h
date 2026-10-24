/* telemetry.h -- the record of a run, for replay. A generic sink: it knows no turn, no
 * pass, no job (TEL3); each module that owns a record defines its record and its
 * helper in its own header and calls the two record functions below. Opaque: a ring
 * of events per recording thread (the perf shape), a frame pool, a mask pool, one
 * writer thread, the file handles; NO app state. It never kills the app after
 * start-up (TEL2): a failed write, a stall, a low disk, a full pool or a full ring
 * degrade, drop and count. Rulings: TEL2 to TEL17, NAM3, RVW3, V1. Below it: perf.h. */
#ifndef __HARDEN2_TELEMETRY_H__
#define __HARDEN2_TELEMETRY_H__

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "perf.h"

/* Lifetime: one logger per process, the app's; created by the main thread right
 * after perf, destroyed right before perf. Every module gets the pointer in its
 * constructor. */

/* what a record call returns; never an exception, never a wait
 * @TELEMETRY_OK:          copied; the writer will write it
 * @TELEMETRY_DROPPED:     the ring or a pool was full: counted, nothing written
 * @TELEMETRY_INVALID_ARG: a size or format not Create's, an event past EventBytes, a
 *                         thread past MaxThreads: our bug; counted as dropped; never
 *                         trips degraded
 * @TELEMETRY_DEGRADED:    the disk failed or is under the reserve: nothing is written
 *                         now; the record still enters the ring */
typedef enum {
	TELEMETRY_OK,
	TELEMETRY_DROPPED,
	TELEMETRY_INVALID_ARG,
	TELEMETRY_DEGRADED
} TelemetryResult;

/* @TELEMETRY_BGR24: a frame, three bytes per pixel, into the frame pool
 * @TELEMETRY_GRAY8: a mask, one byte per pixel, 0 or nonzero, into the mask pool */
typedef enum {
	TELEMETRY_BGR24,
	TELEMETRY_GRAY8
} TelemetryPixelFormat;

/* six counters, one per cause; each has one writer and one reader, so each is an
 * atomic store (SK4); the main thread reads them every frame (TelemetryReadHealth)
 * @m_droppedEvents: a ring was full; incremented by the recording thread
 * @m_droppedFrames: a pool was full, or a wrong size or format; by the recording thread
 * @m_failedWrites:  the disk refused a write (EIO, ENOSPC); by the writer; degrades
 * @m_stalled:       computed at read from four atomic values the sink keeps (records
 *                   queued, records written, the last finished write, the time work
 *                   last became pending): work pending and nothing finished for
 *                   TELEMETRY_STALL_NS since the later of the two times; so the first
 *                   record after a quiet stretch is never a stall
 * @m_degraded:      the writer is paused (a failed write, or free space under the
 *                   reserve); events still enter the rings and the newest survive;
 *                   writing resumes when the free space rises above the reserve
 * @m_freeGiB:       the last free-space reading, by the writer, for the chat line */
typedef struct {
	uint64_t m_droppedEvents;
	uint64_t m_droppedFrames;
	uint64_t m_failedWrites;
	bool     m_stalled;
	bool     m_degraded;
	uint32_t m_freeGiB;
} TelemetryHealth;

/* config values, read once at Create (config/ is the one source):
 * MaxThreads: rings allocated at Create, one per recording thread; the design has 10
 *     (the main thread, the emergency thread, 8 job threads); 16 is the budget; an 11th
 *     or later thread past the budget is our own bug: its events are dropped and
 * counted (TEL2: telemetry never dies), the counter shows the bug
 * RingEvents: per ring, events in flight; full = drop and count
 * EventBytes: one ring record; an event's keys longer than this are our own bug:
 *     INVALID_ARG, dropped and counted, never cut (a turn line with a 2 KB mission and
 *     512 bytes of Hebrew fits); 16 rings of 256 records of 4 KiB = 16 MiB
 * PoolFrames: BGR24 frames in flight; full = drop the frame and count; the caller's
 *     frame slot is released at once, never held for the logger (RVW3)
 * PoolMasks: GRAY8 masks in flight: PoolFrames times the perception's mask limit (the
 *     same config entry, 3 today) WriterPollMs, WriterIdlePollMs: the writer sleeps 10
 *     ms between looks while work flows, and 50 ms once every ring and pool has been
 *     empty for 500 ms; no producer ever notifies it, so the recording path takes no
 *     lock (the backoff saves wake-ups on battery) the free-space rule (TEL17): bytes =
 *     width * height * 3 * TELEMETRY_FRAME_RATIO ExpectedPassesPerMinute * minutes;
 *     Create fails under bytes(FlightMinutes); the writer pauses under
 *     bytes(ReserveMinutes) and resumes above it; at 1080p: 2.8 MB a pass, 3.4 GB for a
 *     40-minute flight, 0.4 GB for 5 minutes; no number for one machine; the product
 *     passes 2^31 at 1080p, so it is computed in uint64_t (Python: an int)
 * ExpectedPassesPerMinute: the vision rate a flight sustains, 30 (the busiest recorded
 *     session; the median is 15; the ceiling of 180 is never sustained)
 * FlightMinutes: the flight length the start check covers, 40
 * ReserveMinutes: the pause reserve, 5
 * FreeCheckEvery: the writer's free-space check, in records the 64-bit and the float
 *     values are macros: an enum member is an int, and a static const in a header is a
 *     copy per translation unit */
enum {
	kTelemetryMaxThreads = 16,
	kTelemetryRingEvents = 256,
	kTelemetryEventBytes = 4096,
	kTelemetryPoolFrames = 8,
	kTelemetryPoolMasks = 24,
	kTelemetryWriterPollMs = 10,
	kTelemetryWriterIdlePollMs = 50,
	kTelemetryWriterIdleAfterMs = 500,
	kTelemetryExpectedPassesPerMinute = 30,
	kTelemetryFlightMinutes = 40,
	kTelemetryReserveMinutes = 5,
	kTelemetryFreeCheckEvery = 100
};

#define TELEMETRY_STALL_NS        UINT64_C(5000000000)
#define TELEMETRY_FSYNC_EVERY_NS  UINT64_C(5000000000)
/* PNG level 1 bytes per raw byte, the worst measured (TEL16) */
#define TELEMETRY_FRAME_RATIO     0.45f

/* THE FILES of <session>/, the generic layer:
 * meta.json: session, host, started (ISO text), clock {monotonic, realtime, boottime:
 *   a PerfClockLine read by telemetry itself}, frame {width, height}, and the
 *   "info" JSON the creator passes (the models; the sink does not read it)
 * trace.jsonl: one JSON object per event line: {"k": <topic>, "at": <PerfTimestamp>,
 *   ...the caller's keys...}, in write order; the handle stays open; flushed and
 *   fsynced once every TELEMETRY_FSYNC_EVERY_NS and at the end; a reader skips a torn
 *   last line. The endings: a "health" line at Destroy; none when killed.
 * <channel>/<name>.png: a frame or a mask, lossless PNG level 1, at the source's
 *   resolution (TEL16); the helper names it (a pass: "000012"; its masks:
 *   "000012_mask_0" ...); written directly and never fsynced: the kernel writes it
 *   back; a torn file after a power cut is skipped by the reader.
 * The topics, channels and keys are the owning modules' contract (telemetry.md,
 * "The records and their homes"). */

typedef struct TelemetryLogger TelemetryLogger;

extern TelemetryLogger* const TELEMETRY_NONE;   /* records nothing; starts no thread */

/* NULL when sessionDir cannot be created or written, or the free space is under
 * bytes(FlightMinutes): the app's start-up dies on NULL (2026-09-23; TEL2 is about
 * flight). Makes <session>/ and asr_clips/ (the ASR node writes there); writes
 * meta.json with infoJson; allocates the rings and both pools (sized by the frame)
 * at once. The frame size is the source's, probed or given before the frame buffer and
 * the logger are made (the webcam probed; the drone 1920x1080; a file probed) */
TelemetryLogger* TelemetryCreate(
	const char* sessionDir,
	uint32_t frameWidth,
	uint32_t frameHeight,
	const char* infoJson
);

/* the "health" line, the stop sentinel, a join with timeoutNs; past it: returns
 * anyway with health.m_stalled (never dies) */
void TelemetryDestroy(TelemetryLogger* t, uint64_t timeoutNs);

/* inside die(), after the hand-over and the notify: the "die" event with the reason,
 * then as Destroy with timeoutNs; on the writer's own thread: one direct append */
void TelemetryFlushInDie(TelemetryLogger* t, const char* reason, uint64_t timeoutNs);

/* read by the main thread each frame like a status row; a change becomes a chat
 * line; nothing here ever dies */
void TelemetryReadHealth(const TelemetryLogger* t, TelemetryHealth* out);

/* an event: the JSON keys without braces, UTF-8, copied into the calling thread's
 * ring during the call; never blocks; from any thread */
TelemetryResult TelemetryRecordEvent(
	TelemetryLogger* t,
	const char* topic,
	PerfTimestamp at,
	const char* keysJson
);

/* a frame (BGR24, the frame pool) or a mask (GRAY8, the mask pool), both written as
 * PNG level 1 by the writer under <channel>/<name>.png: the pixels are copied into the
 * pool during the call, then the caller may release its slot; a full pool drops and
 * counts; a size or format not Create's is INVALID_ARG; never blocks; from any thread */
TelemetryResult TelemetryRecordFrame(
	TelemetryLogger* t,
	const char* channel,
	const char* name,
	PerfTimestamp at,
	TelemetryPixelFormat format,
	uint32_t width,
	uint32_t height,
	uint32_t strideBytes,
	const uint8_t* pixels
);

#endif
