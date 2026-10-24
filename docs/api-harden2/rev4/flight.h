/*
 * flight.h -- harden2 API rev4 DRAFT (2026-10-02; was control.h, owner HDR2/HDR3).
 * Module
 * control/: the flight controller on the software side. It is the ONLY code that sends
 *     a flight request, and the only owner of manual mode. It parses nothing. It talks
 *     to the DJI phone app through dji_app.h; a second platform would bring its own
 *     client beside dji_app (ruling 2026-09-23: "No new DroneLink": no generic drone
 *     layer until a second platform exists).
 *  */
#ifndef __HARDEN2_API_FLIGHT_H__
#define __HARDEN2_API_FLIGHT_H__
#include "runtime.h"
#include "dji_app.h"
typedef struct SessionLog SessionLog;

/*
 * @log:
 *     every mission sent is written into its turn
 * @manual:
 *     ATOMIC. true: the pilot's RC flies; our missions are refused. No lock anywhere in
 *     this struct.
 */
typedef struct FlightController {
	DjiApp*     dji;
	SessionLog* log;
	bool        manual;
} FlightController;

FlightController* FlightCreate(DjiApp* dji, SessionLog* log);
void              FlightClose(FlightController* f);
/* manual = true: FIRST the flag (so no mission can leave after this line), THEN POST
 *     /c/stop: the aircraft stops and the RC has the sticks.
 * manual = false: the flag only; missions are allowed again. The F4 key and the spoken
 *     "manual" / "auto" all end here. */
HttpStatus FlightSetManual(FlightController* f, bool manual);
bool       FlightIsManual(const FlightController* f);
/* The emergency stop. It ALWAYS stops the aircraft, in both modes: auto: a zero-length
 * mission replaces the running one (we keep the sticks); manual: /c/stop (the RC keeps
 * the sticks). */
HttpStatus FlightHalt(FlightController* f);
/* Send one mission. Manual mode: nothing is sent and the answer is 409 CONFLICT. */
HttpStatus FlightFly(FlightController* f, const char* missionJson);
#endif
