/*
 * dji_app.h -- harden2 API v2.3 (2026-09-24). Module dji_app/: the ONE client for the
 * DJI phone app, or the mock that stands in for it: drone commands, /tts, and the
 * transmit switch. Its own status row "dji app": UP while the app answers; no answer ->
 * WAITING (orange: the user must fix the phone app) and a probe (GET /status/,
 * read-only) every config.PHONE_APP_CHECK_SECONDS (2 s; owner U6 a) turns it UP again.
 * The app never dies because of the phone.
 *
 * Results: the standard library's HTTP status (Python http.HTTPStatus), or NONE when
 *     the app did not answer at all. 409 CONFLICT = the transmit switch blocked the
 *     request.
 * SAFETY: a real phone is HUMAN-ONLY; a non-loopback host without allowReal dies.
 *  */
#ifndef __HARDEN2_API_DJI_APP_H__
#define __HARDEN2_API_DJI_APP_H__
#include "runtime.h"

/* ---- the object of this module, with its data members ---- */
typedef struct Perf Perf;
typedef struct DjiApp DjiApp;
/* python: dji_app.client.DjiApp */
/*
 * @host:
 *     127.0.0.1 (the mock) or the phone's IP
 * @timeout:
 *     seconds, per HTTP request
 * @probe:
 *     The phone is outside the laptop: nothing tells us when it comes back. ONLY while
 *     it does not answer, this thread asks GET /status/ (read-only) every 2 s, and turns
 *     the row UP when an answer comes. While the phone answers, no thread runs (probe ==
 *     NULL).
 * @closed:
 *     set at shutdown: ends the probe
 * @status:
 *     the "dji app" row: UP, or WAITING (orange)
 */
struct DjiApp {
	const char* host;
	uint16_t    port;
	float       timeout;
	OsThread*   probe;
	OsEvent*    closed;
	Status*     status;
};

typedef int32_t HttpStatus;          /* 200 OK, 409 CONFLICT, ...; see HTTP_NONE           */
/* no answer at all (Python: None) */
enum {
	HTTP_NONE = 0
};

typedef struct DjiApp DjiApp;
/* @perf: a command that gets any reply ends the "e2e" timing (PerfEnd "e2e", end=command) */
DjiApp* DjiAppCreate(
	const char* host,
	uint16_t port,
	bool allowReal,
	float timeoutS,
	Perf* perf
);
void DjiAppClose(DjiApp* d);   /* stops the probe */
/* its "dji app" row */
uint32_t DjiAppStatus(DjiApp* d, StatusRow* rows, uint32_t cap);

/* [rev4] No transmit switch here: manual mode lives in the flight controller
 * (flight.h), which simply does not call the motion requests below while manual is on. */

/* Motion requests: 409 CONFLICT while the switch is off (nothing leaves the laptop). */
HttpStatus DjiAppTakeoff(DjiApp* d);   /* POST /c/takeoff */
HttpStatus DjiAppLand(DjiApp* d);   /* POST /c/land */
/* POST /c/fly [...] */
HttpStatus DjiAppFlyMission(DjiApp* d, const char* actionsJson);
HttpStatus DjiAppHalt(DjiApp* d);   /* a delay:0 mission pre-empts; keeps sticks */
/* Never blocked. */
HttpStatus DjiAppStop(DjiApp* d);   /* POST /c/stop: stop(emergency), the RC flies */
HttpStatus DjiAppSpeak(DjiApp* d, const char* text);   /* POST /tts */

/* CONTROL=mock only; WAITS, never dies */
ProcessSpec DjiMockProcess(const char* logDir);

#endif /* __HARDEN2_API_DJI_APP_H__ */
