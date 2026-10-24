/* telemetry_record_dispatch.h -- the records the app's dispatch owns and writes through
 * the telemetry sink: a turn (two lines) and an event. Moves into the dispatch module's
 * header at its review; the keys below are the contract the replayer reads (TEL3). */
#ifndef __HARDEN2_TELEMETRY_RECORD_DISPATCH_H__
#define __HARDEN2_TELEMETRY_RECORD_DISPATCH_H__

#include "telemetry.h"

/* every text is UTF-8, copied by the sink during the call, never cut; a value outside
 * a table below is written as given (the replayer shows it; a test catches it; TEL2) */
extern const char* const kTurnKinds[];    /* emergency, manual, auto, clear, mission,
 * highlight, count, describe, reject, planner_failed, empty */
extern const char* const kEventKinds[];   /* key, stop_sent, stop_reply, manual_on,
 * manual_off, mission_cancelled, sentence_dropped, mission_refused, status_change,
 * telemetry_health, end, die */

/* one turn, the app's own object; EVERY turn writes both lines, at once for a kind
 * that ends at its decision; the lines are joined by seq
 * @m_seq:            the turn's number; the join key "turn" of perf
 * @m_startedAt:      the transcript's receipt
 * @m_endedAt:        the platform reply, the first box or the spoken reply
 * @m_input:          "mic" or "phone"
 * @m_audioClip:      "asr_clips/<name>", the clip new at this transcript, or ""
 * @m_kind:           one of kTurnKinds
 * @m_platformStatus: the phone app's HTTP status; 0 = no request; 409 = manual mode
 * @m_refused:        "waiting" when refused while the phone's row was WAITING, else ""
 * @m_visionJob:      the job this turn started, or 0 */
typedef struct {
	uint32_t      m_seq;
	PerfTimestamp m_startedAt;
	PerfTimestamp m_endedAt;
	const char*   m_input;
	const char*   m_heard;
	const char*   m_audioClip;
	const char*   m_he2;
	const char*   m_kind;
	const char*   m_missionJson;
	const char*   m_target;
	const char*   m_rejectReason;
	uint32_t      m_platformStatus;
	const char*   m_refused;
	uint32_t      m_visionJob;
	const char*   m_spoken;
} TurnData;

/* topic "turn", phase "decided", at = m_startedAt: seq, phase, started, input, heard,
 * audio_clip, he2, kind, mission, target, reject, job. Every text value is JSON-escaped
 * by the helper (json.dumps); the mission is embedded as a JSON object, not a string */
void TelemetryTurnDecided(TelemetryLogger* t, const TurnData* turn);

/* topic "turn", phase "ended", at = m_endedAt: seq, phase, ended, status, refused,
 * spoken */
void TelemetryTurnEnded(TelemetryLogger* t, const TurnData* turn);

/* an event of the run, main thread only
 * @m_kind:   one of kEventKinds
 * @m_turn:   the turn concerned, or 0
 * @m_job:    the job concerned, or 0
 * @m_detail: the key name, the HTTP status, the row and its state, the reason */
typedef struct {
	PerfTimestamp m_at;
	const char*   m_kind;
	uint32_t      m_turn;
	uint32_t      m_job;
	const char*   m_detail;
} EventData;

/* topic "event": kind, turn, job, detail */
void TelemetryEvent(TelemetryLogger* t, const EventData* event);

#endif
