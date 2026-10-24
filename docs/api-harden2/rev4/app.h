/*
 * app.h -- harden2 API rev4 DRAFT (2026-10-02). Module app/: the program. It starts
 * every part, runs the screen until quit, then stops every part in reverse order.
 *  */
#ifndef __HARDEN2_API_APP_H__
#define __HARDEN2_API_APP_H__
#include "runtime.h"
#include "perf.h"
#include "frames.h"
#include "video.h"
#include "audio.h"
#include "keys.h"
#include "flight.h"
#include "recognizer.h"   /* perception.h, gemma.h, sam3.h, log.h */

typedef struct {
	const char* role;
	const char* text;
	const char* style;
} ChatLine;

/* app/ui.py: the ONLY code that draws */
/*
 * @video:
 *     the newest frame's number
 * @frames:
 *     the pixels
 * @vision:
 *     VisionJobs: the boxes and masks to draw, and the rows of the jobs pane. The screen
 *     keeps no copy.
 * @board:
 *     the status pane
 * @flight:
 *     FlightIsManual: the MANUAL banner (a read only)
 * @chat:
 *     the chat pane's newest lines
 * @chatScroll:
 *     rows scrolled up; 0 = follow the newest
 * @showMasks:
 *     the t key
 * @quit:
 *     ATOMIC: set by F1 from the key thread
 * @chatLock:
 *     the turn thread adds lines, the screen reads
 */
typedef struct Screen {
	const Video*            video;
	const FrameRing*        frames;
	Vision*                 vision;
	const StatusBoard*      board;
	const FlightController* flight;
	ChatLine                chat[60];
	uint32_t                nChat;
	uint32_t                chatScroll;
	bool                    showMasks;
	bool                    quit;
	OsLock*                 chatLock;
} Screen;

/* The window:   +------------------------------------------------------------------+
 *               | the camera frame; on it every live highlight's boxes and masks,  |
 *               | the HUD (fps, the video kind, the phone-app address), and a      |
 *               | MANUAL banner while manual mode is on                            |
 *               +----------------+---------------------------+---------------------+
 *               | the status     | the chat: what was heard, | the active jobs:    |
 *               | pane: one row  | what was decided, the     | one row per vision  |
 *               | per part       | answer; scrolls           | job; a click        |
 *               |                |                           | focuses or deletes  |
 *               +----------------+---------------------------+---------------------+
 * Window keys (only while the window has the focus): q / Esc quit | c clear every highlight |
 * t masks on/off | [ ] or the wheel scroll the chat | x clear the chat. */
void ScreenRun(Screen* s);   /* one pass: newest frame -> draw the jobs' boxes and */
                                          /* masks -> compose the panes -> show -> one
                                           * key; */
                                          /* no frame yet: "waiting for video". Ends on
                                           *     quit. */
void ScreenAddChat(Screen* s, const char* role, const char* text, const char* style);

/*
 * @log:
 *     -- built first, in this order; stopped last, in reverse --
 * @gemma:
 *     starts the llama-server
 * @sam3:
 *     starts the SAM3 process
 * @dji:
 *     the phone app, or the mock
 * @keyboardHook:
 *     the native global-keys program
 * @asrServer:
 *     the mic's ASR server
 * @gstreamer:
 *     VIDEO_DRONE only, else NULL
 * @mockPhone:
 *     CONTROL=mock only, else NULL
 * @video:
 *     -- then these, each given only what it needs --
 */
typedef struct App {
	SessionLog*       log;
	Perf*             perf;
	Supervisor*       supervisor;
	FrameRing*        frames;
	Gemma*            gemma;
	Sam3*             sam3;
	DjiApp*           dji;
	Process*          keyboardHook;
	Process*          asrServer;
	Process*          gstreamer;
	Process*          mockPhone;
	Video*            video;
	SpeechOut*        speechOut;
	FlightController* flight;
	Vision*           vision;
	Recognizer*       recognizer;
	PhoneBridge*      phoneBridge;
	SpeechIn*         speechIn;
	Keys*             keys;
	StatusBoard*      board;
	Screen            screen;
} App;

/* anything that fails while starting -> SysDie */
App* AppStart(const char* videoSource);
void AppRun(App* a);   /* ScreenRun, until quit */
void AppStop(App* a);   /* the lower block in reverse, then the upper block */

/* ---- what the app DOES when something arrives (the callbacks it gives the parts) ---- */
/* A transcript (given to SpeechIn). One turn, start to end:
 *     Turn* t = LogBeginTurn(a->log, heard->text, heard->source);
 *     ScreenAddChat: the user's line
 *     RecognizerRoute(a->recognizer, t->input.heard, &t->decision);
 *     RecognizerAct(a->recognizer, &t->decision, &t->response);
 *     word the result (a flight status, a refusal's reason) -> ScreenAddChat + SpeechOutSay
 *     LogCommitTurn(a->log, t);                                                          */
void AppOnHeard(App* a, const Transcript* heard);
/* A vision job changed (given to Vision): a count's number, a describe's answer, "no
 * chair in
 * view", "lost": one chat line and, where it is an answer, one spoken sentence. */
void AppOnJobChanged(App* a, const Job* job);
/* A global key was pressed (given to Keys; keys.h only DELIVERS keys, it knows no
 * drone): F4 -> FlightSetManual(!FlightIsManual) and say the result; F1 -> screen.quit;
 * F2 -> VisionClear(0). Any other key: nothing. */
void AppOnKeyPress(App* a, int32_t evdevCode);
/* A global key was released: F5 (push-to-talk) -> PerfMarkNow("ptt_release"): the ASR
 *     and the command-to-action timings start there. */
void AppOnKeyRelease(App* a, int32_t evdevCode);
#endif
