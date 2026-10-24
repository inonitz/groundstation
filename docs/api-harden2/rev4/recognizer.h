/*
 * recognizer.h -- harden2 API rev4 DRAFT (2026-10-02). Module recognizer/.
 * One sentence in, one decision out, then the decision carried out. Every step is declared
 * here, in the order it runs, so the header alone tells what happens to a sentence (HDR3).
 *
 *   Recognize(text) = RecognizerRoute (decide; sends NOTHING) + RecognizerAct (carry it out).
 *   The app calls the two in a row (log.h shows the lines). The benchmark calls only Route:
 *   that is the one reason the two are separate.
 */
#ifndef __HARDEN2_API_RECOGNIZER_H__
#define __HARDEN2_API_RECOGNIZER_H__
#include "runtime.h"
#include "flight.h"
#include "perception.h"
#include "gemma.h"
#include "log.h"                          /* TurnDecision, TurnResponse, TurnKind            */

/*
 * @flight:
 *     missions and the critical commands go here
 * @vision:
 *     vision requests go here (NULL in a benchmark)
 * @gemma:
 *     the ONE plan request
 */
typedef struct Recognizer {
	FlightController* flight;
	Vision*           vision;
	Gemma*            gemma;
} Recognizer;

/* @warmUp: send one plan request now, so Gemma has the planner's long prompt in its cache
 * before the first command (measured: the first plan 549 ms warmed, 1546 ms not).
 * false: a benchmark. */
Recognizer* RecognizerCreate(
	FlightController* flight,
	Vision* vision,
	Gemma* gemma,
	bool warmUp
);
void RecognizerClose(Recognizer* r);

/* ======== Route: decide. Steps 1-6; the first that answers wins. ======== */
void RecognizerRoute(Recognizer* r, const char* text, TurnDecision* out);
/* 1. The trigger commands: no model, at once. The sentence WITHOUT its filler words
 *     ("the drone", "already", "now", "please") must EQUAL one command of the table. A
 *     stop word plus anything else is not an emergency: "stop for 10 seconds" goes on
 *     to step 2. */
typedef enum {
	TRIGGER_NONE,
	TRIGGER_EMERGENCY,
	TRIGGER_MANUAL,
	TRIGGER_AUTO,
	TRIGGER_CLEAR
} Trigger;

/*
 * @command:
 *     the whole command, without filler words: "עצור", "stop", "המשך", "resume"
 * @trigger:
 *     what it does: "עצור" -> TRIGGER_EMERGENCY
 */
typedef struct {
	const char* command;
	Trigger     trigger;
} TriggerEntry;

extern const TriggerEntry kTriggerTable[];
Trigger MatchTrigger(const char* text);
/* 2. The fixed commands: no model. A sentence that fully matches one pattern becomes its
 *     mission. Examples (Hebrew sentence -> mission):
 *         "עלה 5 מטרים"       -> fly up 5 m
 *         "עצור ל-10 שניות"   -> wait 10 s
 *         "קצת קדימה"         -> fly forward 1 m ("a bit" is exactly 1 m) */
bool MatchFixedCommand(const char* text, char* missionJson, size_t cap);
/* 3. A pure "do not ..." with no order in it is refused before the model sees it. */
bool IsOnlyNegation(const char* text);
/* 4. Make the Hebrew easier for the model: number words become digits, known slips are
 *     fixed. */
void RewriteHebrew(const char* text, char* he2, size_t cap);
/* 5. THE one Gemma request: he2 -> {"kind", "target_en", "mission"}. false = Gemma
 *     failed. */
bool AskPlan(Recognizer* r, const char* he2, char* planJson, size_t cap);
/* 6. Check a planned mission before it may fly: every number the user said must be in
 *     the mission; a mission equal to one of the prompt's examples, from a sentence
 *     without that example's numbers, is a copy and is refused. */
bool NumbersMatch(const char* he2, const char* missionJson);
bool IsCopiedExample(const char* he2, const char* missionJson);

/* ================= Act: carry the decision out ================= */
/* emergency -> FlightHalt; manual / auto -> FlightSetManual; a mission -> FlightFly;
 * clear -> VisionClear(0); highlight / count / describe -> a vision job; a reject ->
 * nothing is sent. It fills the response; the app words and speaks it. The recognizer
 * never speaks. */
void RecognizerAct(Recognizer* r, const TurnDecision* d, TurnResponse* out);
#endif
