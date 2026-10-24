/*
 * scripted_run.h -- harden2 API rev4 DRAFT (2026-10-02; moved out of app.h, owner
 * HDR1).
 * test/scripted_e2e_run.py: a TEST TOOL, a separate program. The app never calls it.
 *
 * What it is for: a measured run needs the same spoken input every time. This program
 *     waits for Gemma, then publishes each sentence of a script on the ASR topic,
 *     exactly as the ASR server publishes a transcript. The app cannot tell the
 *     difference, so the test drives the REAL app through its real input path, with no
 *     mock inside the app.
 * Who uses it: `SCRIPT=<file> run.sh up ...` (a scripted run; it dies unless
 *     CONTROL=mock, because the sentences become commands), and the whole-app test
 *     (test/test_app.py). Why a separate program and not a mode of the app: owner
 *     ruling 2.1 / Q4 (2026-09-26): the second main left app/ and became
 *     test/scripted_e2e_run.py.
 *  */
#ifndef __HARDEN2_API_SCRIPTED_RUN_H__
#define __HARDEN2_API_SCRIPTED_RUN_H__
#include "runtime.h"

/* one line of a script file */
/*
 * @what:
 *     "say" (a sentence) or "wait" (seconds)
 */
typedef struct {
	const char* what;
	const char* value;
} ScriptStep;

/* "#" = a comment */
uint32_t ScriptParse(const char* text, ScriptStep* out, uint32_t cap);
/* THIRD-PARTY: an rclpy publisher on ASR_TOPIC (String) */
typedef struct RosPublisher RosPublisher;
RosPublisher* ScriptSpeechPublisher(void* node);
/* as the ASR server does */
void ScriptPublishTranscript(RosPublisher* pub, const char* text);
int  ScriptMain(const char* scriptPath);   /* wait for Gemma, then play the script */

#endif /* __HARDEN2_API_SCRIPTED_RUN_H__ */
