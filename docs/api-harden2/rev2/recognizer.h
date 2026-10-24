/*
 * recognizer.h -- harden2 API v2.3 (2026-09-24). Module recognizer/: the router for speech. It parses
 * EVERY sentence and routes the result:
 *
 *   1. Fast path (no Gemma): emergency, manual, auto -> control at once. The turn ends.
 *   2. Deterministic missions (the bypass rules, no Gemma) -> ControlFly().
 *   3. Negation guard ("do not fly up") -> reject.
 *   4. Hebrew normalization, then ONE Gemma call -> mission / count / highlight / describe.
 *   5. Guards on a plan: every spoken number is in the mission; not a prompt-example echo.
 *   6. Route: a mission -> ControlFly(); a vision request -> perception, TYPED (no English
 *      text that perception parses again); a reject or a Gemma failure -> the result.
 *
 * It never speaks and never draws: the app turns the result into chat, speech and log.
 */
#ifndef __HARDEN2_API_RECOGNIZER_H__
#define __HARDEN2_API_RECOGNIZER_H__
#include "system.h"
#include "control.h"
#include "perception.h"

typedef enum {
	ROUTED_CRITICAL,                      /* fast path: control acted                        */
	ROUTED_FLIGHT,                        /* a mission went to control                       */
	ROUTED_VISION,                        /* a request went to perception                    */
	ROUTED_REJECT,                        /* not understood, negated, or failed a guard      */
	ROUTED_GEMMA_FAILED                   /* Gemma did not answer: NOT the user's fault      */
} RouteKind;
typedef enum {
	REJECT_NONE, REJECT_NEGATED, REJECT_NUMBERS_CHANGED, REJECT_SHOT_ECHO, REJECT_NOT_A_COMMAND
} RejectReason;
typedef enum { VISION_COUNT, VISION_HIGHLIGHT, VISION_CLEAR, VISION_DESCRIBE } VisionKind;
typedef struct {
	RouteKind    kind;
	HttpStatus   control;                 /* ROUTED_CRITICAL / ROUTED_FLIGHT: what happened  */
	const char*  actionsJson;             /* ROUTED_FLIGHT: the mission, for chat and log  */
	VisionKind   vision;                  /* ROUTED_VISION                                   */
	char         target[64];              /* ROUTED_VISION: English noun phrase for SAM3     */
	TaskId       task;                    /* ROUTED_VISION: the perception task started      */
	RejectReason reject;
	bool         fromFastPath;            /* no Gemma call was made                          */
	uint32_t     recognizeMs, planMs;
} Routed;

typedef struct Gemma Gemma;
typedef struct Vision Vision;
typedef struct Recognizer Recognizer;
Recognizer* RecognizerCreate(Control* control, Vision* vision, Gemma* gemma, SessionLog* log);
void        RecognizerClose(Recognizer* r);
void        Recognize(Recognizer* r, const char* text, Routed* out);   /* kind covers all */
/* The ONE Gemma call (the benches measure it): Hebrew -> {kind, target_en, mission} JSON.
 * false = no plan (the request failed, or the reply is not a plan). */
bool        RecognizerPlan(Recognizer* r, const char* he2, char* planJson, size_t cap);

#endif /* __HARDEN2_API_RECOGNIZER_H__ */
