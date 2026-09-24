/*
 * dji_app.h -- harden2 API v2.3 (2026-09-24). Module dji_app/: the ONE client for the DJI
 * phone app, or the mock that stands in for it: drone commands, /tts, and the transmit
 * switch. Its own status row "dji app": UP while the app answers; no answer -> WAITING
 * (orange: the user must fix the phone app) and a probe (GET /status/, read-only) every
 * config.WAITING_RETRY_SECONDS turns it UP again. The app never dies because of the phone.
 *
 * Results: the standard library's HTTP status (Python http.HTTPStatus), or NONE when the
 * app did not answer at all. 409 CONFLICT = the transmit switch blocked the request.
 * SAFETY: a real phone is HUMAN-ONLY; a non-loopback host without allowReal dies.
 */
#ifndef __HARDEN2_API_DJI_APP_H__
#define __HARDEN2_API_DJI_APP_H__
#include "system.h"

typedef int32_t HttpStatus;          /* 200 OK, 409 CONFLICT, ...; see HTTP_NONE           */
enum { HTTP_NONE = 0 };              /* no answer at all (Python: None)                    */

typedef struct DjiApp DjiApp;
DjiApp* DjiAppCreate(const char* host, uint16_t port, bool allowReal, float timeoutS);
void    DjiAppClose(DjiApp* d);      /* stops the probe                                    */
uint32_t DjiAppStatus(DjiApp* d, StatusRow* rows, uint32_t cap);   /* its "dji app" row */

/* The transmit switch: control is its ONLY user (F4 and the spoken manual/auto end there). */
void DjiAppSetTransmit(DjiApp* d, bool enabled);
bool DjiAppTransmitting(const DjiApp* d);

/* Motion requests: 409 CONFLICT while the switch is off (nothing leaves the laptop). */
HttpStatus DjiAppTakeoff(DjiApp* d);                           /* POST /c/takeoff          */
HttpStatus DjiAppLand(DjiApp* d);                              /* POST /c/land             */
HttpStatus DjiAppFlyMission(DjiApp* d, const char* actionsJson);   /* POST /c/fly [...]    */
HttpStatus DjiAppHalt(DjiApp* d);          /* a delay:0 mission pre-empts; keeps sticks    */
/* Never blocked. */
HttpStatus DjiAppStop(DjiApp* d);          /* POST /c/stop: stop(emergency), the RC flies  */
HttpStatus DjiAppSpeak(DjiApp* d, const char* text);           /* POST /tts                */

SupProcess DjiMockProcess(const char* logDir);   /* CONTROL=mock only; WAITS, never dies  */

#endif /* __HARDEN2_API_DJI_APP_H__ */
