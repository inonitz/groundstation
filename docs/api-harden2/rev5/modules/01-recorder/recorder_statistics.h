/* recorder_statistics.h -- what each actor of the recorder counts, since Create; every
 * struct is a statistics struct (00-util/statistics.h): RecordCount fields only, so the
 * arithmetic walks it as an array. The health is their aggregate (recorder.md 2.5) */
#ifndef __HARDEN2_RECORDER_STATISTICS_H__
#define __HARDEN2_RECORDER_STATISTICS_H__

#include "statistics.h"

/* one recording thread: what it queued, and what was dropped, by kind. All eight are the
 * thread's own: relaxed atomic increments by the thread, relaxed loads by the writer, no lock */
typedef struct {
	RecordCount m_spansQueued;
	RecordCount m_eventsQueued;
	RecordCount m_framesQueued;
	RecordCount m_masksQueued;
	RecordCount m_spansDropped;
	RecordCount m_eventsDropped;
	RecordCount m_framesDropped;
	RecordCount m_masksDropped;
} RecordingThreadStatistics;

/* the one writer: the file and the PNGs */
typedef struct {
	RecordCount m_linesWritten;
	RecordCount m_bytesWritten;
	RecordCount m_failedAppends;    /* appends to the record file that failed */
	RecordCount m_linesCut;         /* C only: lines longer than the line buffer */
	RecordCount m_pngsWritten;
	RecordCount m_pngFailures;
	RecordCount m_pngNameClashes;
	RecordCount m_flushes;
	RecordCount m_recordsCutOffAtDeadline;   /* the last pass: records still queued at the drain deadline */
	RecordCount m_imagesCutOffAtDeadline;    /* the same, for filled images */
} RecordWriterStatistics;

#endif
