/*
 * control.h -- harden2 API v2.3 (2026-09-24). Module control/: the way we interact with the
 * drone, and ONLY that. It parses nothing. It is the only module that sends flight requests
 * and the only user of the transmit switch. Callers: the recognizer (critical commands,
 * missions) and the app's F4 handler.
 */
#ifndef __HARDEN2_API_CONTROL_H__
#define __HARDEN2_API_CONTROL_H__
#include "system.h"
#include "dji_app.h"

typedef struct SessionLog SessionLog;
typedef struct Control Control;
Control*   ControlCreate(DjiApp* dji, SessionLog* log);   /* log: every mission recorded */
void       ControlClose(Control* c);

bool       ControlManualOn(const Control* c);
HttpStatus ControlManual(Control* c);    /* transmit OFF first, then /c/stop: the RC flies */
void       ControlAuto(Control* c);      /* transmit ON                                    */
HttpStatus ControlToggleManual(Control* c, const char** action);   /* the F4 key          */
HttpStatus ControlEmergencyHalt(Control* c);   /* auto: halt; manual: /c/stop (never take
                                                  stick control back from the RC)          */
HttpStatus ControlFly(Control* c, const char* actionsJson);   /* 409 in manual mode        */

/* The ONE wording of a result, for the chat, the speech output and the log. */
const char* ControlOutcomeText(const char* action, HttpStatus status);

#endif /* __HARDEN2_API_CONTROL_H__ */
