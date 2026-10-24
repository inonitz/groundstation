/* phone_client.h -- the one client of the phone app, or of our mock of it. */
#ifndef __HARDEN2_PHONE_CLIENT_H__
#define __HARDEN2_PHONE_CLIENT_H__

#include <stdint.h>

#include "monotonic_clock.h"
#include "recorder.h"
#include "runtime.h"

/* opaque; it sends to the host it is given and does not know whether that is the phone
 * or the mock: the app picks the host from config's CONTROL. It only dials out */
typedef struct PhoneClient PhoneClient;

/* dies at start when ipv4 is not a dotted IPv4 literal, or when the probe thread cannot
 * start */
PhoneClient* PhoneClientCreate(const char* ipv4, uint16_t port);

/* after every sender is joined and Die's two actions are cleared */
void PhoneClientDestroy(PhoneClient* c);

/*
 * @PHONE_ROUTE_STOP:
 *     the aircraft brakes and the sticks go to the RC; the groundstation never cuts the
 *     motors (the owner, 2026-10-18)
 */
typedef enum {
	PHONE_ROUTE_FLY,
	PHONE_ROUTE_TAKEOFF,
	PHONE_ROUTE_LAND,
	PHONE_ROUTE_STOP,
	PHONE_ROUTE_TTS
} PhoneRoute;

/*
 * @PHONE_OK:
 *     a 2xx reply whose body says "ok": true
 * @PHONE_REFUSED:
 *     any other reply: the phone answers its errors 200 "ok": false
 * @PHONE_NOT_SENT:
 *     no request byte left: no connect by the deadline or a wrong route and body
 * @PHONE_NO_REPLY:
 *     the request left and no reply came by the deadline: it MAY have run
 */
typedef enum {
	PHONE_OK,
	PHONE_REFUSED,
	PHONE_NOT_SENT,
	PHONE_NO_REPLY
} PhoneOutcome;

/* @m_httpStatus: 0 unless a reply came */
typedef struct {
	PhoneOutcome m_outcome;
	uint32_t     m_httpStatus;
} PhoneResult;

/* one request on a new connection of the calling thread, bounded by deadlineNs on the
 * MonotonicNow clock. FLY and TTS need a JSON body; the other routes take NULL; a wrong pair
 * is PHONE_NOT_SENT. It decides nothing, retries nothing, records nothing */
PhoneResult PhoneSend(
	PhoneClient* c,
	PhoneRoute route,
	const char* bodyJson,
	MonotonicNs deadlineNs
);

/* FLY with this body: the phone ends its running mission and brakes */
extern const char* const kPhoneHaltMission;

/* the "phone" row: UP or WAITING_FOR_USER; GET /status/ every 2 s */
const StatusRow* PhoneClientRow(const PhoneClient* c);

#define PHONE_PROBE_PERIOD_NS  UINT64_C(2000000000)

/* Die's two actions (DieActionFn); ctx is the client */

/* the owner, 2026-10-18 (option a): no motion after it starts; the halt once any
 * motion request left this run; /c/stop; /c/stop again 400 ms before the deadline */
void PhoneHandoverForDie(void* client, const char* reason, MonotonicNs deadlineNs);

/* one POST /tts of config's die sentence */
void PhoneNotifyForDie(void* client, const char* reason, MonotonicNs deadlineNs);

#endif
