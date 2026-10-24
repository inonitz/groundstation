/*
 * recognizer.h -- harden2 API v2.4 (2026-09-28). Module recognizer/: the router for speech. It parses
 * EVERY sentence in two chained steps (owner 2026-09-26: "One should make the decision, one should
 * do the acting"): RecognizerRoute() decides and sends nothing; RecognizerAct() carries the decision
 * out. Recognize() = Route + Act, the app's one call. The recognizer benchmark calls Route.
 * What Route decides, in order:
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
#include "runtime.h"
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
typedef enum {
	DECIDED_EMERGENCY, DECIDED_MANUAL, DECIDED_AUTO, DECIDED_CLEAR, DECIDED_MISSION,
	DECIDED_HIGHLIGHT, DECIDED_COUNT, DECIDED_DESCRIBE, DECIDED_REJECT,
	DECIDED_GEMMA_FAILED, DECIDED_EMPTY
} DecisionKind;
typedef struct {                          /* what Route decided; nothing is sent yet         */
	DecisionKind kind;
	const char*  text;                    /* the sentence as said                            */
	const char*  he2;                     /* the Hebrew Gemma read ("" when no model ran)    */
	const char*  missionJson;             /* MISSION; also a guarded REJECT (what it refused) */
	const char*  tag;                     /* MISSION: "bypass" (no model) or "planned"       */
	char         target[64];              /* HIGHLIGHT / COUNT; DESCRIBE: Gemma's target_en  */
	RejectReason reject;                  /* REJECT                                          */
	uint32_t     recognizeMs, planMs;
} Decision;
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
void        RecognizerRoute(Recognizer* r, const char* text, Decision* out); /* sends nothing */
void        RecognizerAct(Recognizer* r, const Decision* d, Routed* out);  /* control, vision */
void        Recognize(Recognizer* r, const char* text, Routed* out);       /* Route + Act     */
/* The ONE Gemma call (the benches measure it): Hebrew -> {kind, target_en, mission} JSON.
 * false = no plan (the request failed, or the reply is not a plan). */
bool        RecognizerPlan(Recognizer* r, const char* he2, char* planJson, size_t cap);

/* The start-up warm-up (owner L1): one plan request for config.PLAN_WARM_UP_SENTENCE, so the
 * planner's long prompt is in Gemma's cache before the first command. Nothing is sent. */
void RecognizerWarmUp(Gemma* gemma);

#endif /* __HARDEN2_API_RECOGNIZER_H__ */
