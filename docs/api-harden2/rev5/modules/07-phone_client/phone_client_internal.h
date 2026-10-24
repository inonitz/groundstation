/* phone_client_internal.h -- what is behind the opaque PhoneClient: its state and the
 * steps of one send and of the probe, in call order. */
#ifndef __HARDEN2_PHONE_CLIENT_INTERNAL_H__
#define __HARDEN2_PHONE_CLIENT_INTERNAL_H__

#include <stdatomic.h>
#include <stdbool.h>

#include "phone_client.h"
#include "runtime_internal.h"

/* @m_host:              PhoneClientCreate copies the host here
 * @m_row:               written by the probe thread only, one store per change
 * @m_motionClosed:      Die's latch: set by the hand-over; our code never clears it
 * @m_motionRequestsLeft: counted just before a motion request's bytes leave
 * @m_dieSentence:       the notify's /tts body, built at Create from config
 * @m_stopFd:            an eventfd: Destroy writes it; the probe waits on it */
struct PhoneClient {
	char             m_host[16];
	uint16_t         m_port;
	StatusRow        m_row;
	atomic_flag      m_motionClosed;
	_Atomic uint64_t m_motionRequestsLeft;
	char             m_dieSentence[512];
	int32_t          m_stopFd;
	OsThread*        m_probeThread;
};

/* PhoneSend, in call order; each socket call gets the time left before the deadline */

/* 1. connect: a new attempt every PHONE_CONNECT_ATTEMPT_NS, the first to connect
 * wins; -1 when none connected by the deadline */
#define PHONE_CONNECT_ATTEMPT_NS  UINT64_C(250000000)
int32_t PhoneConnect(const PhoneClient* c, MonotonicNs deadlineNs);

/* 2. in PhoneSend itself: a motion route checks m_motionClosed, then counts
 * m_motionRequestsLeft */

/* 3. the request and its reply, Connection: close; a motion request waits for the reply
 * in PHONE_MOTION_SLICE_NS steps and resets once m_motionClosed is set */
#define PHONE_MOTION_SLICE_NS  UINT64_C(20000000)
PhoneResult PhoneRequest(
	int32_t fd,
	PhoneRoute route,
	const char* bodyJson,
	MonotonicNs deadlineNs,
	atomic_flag* motionClosed
);

/* the probe thread: step 1 and one GET /status/ every PHONE_PROBE_PERIOD_NS; the row
 * from the reply, stored only on a change; it waits on m_stopFd between probes */
void PhoneProbeThread(PhoneClient* c);

#endif
