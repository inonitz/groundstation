/*
 * app.h -- harden2 API rev3 DRAFT (2026-10-02; from v2.4; see RULINGS.md and GAPS.md).
 * Module app/: builds the services, gives each module the services it needs, runs the
 * screen, then closes the modules and the services in reverse order (owner ruling
 * 2026-09-23). Anything that fails while starting dies with the reason.
 *
 *   START    1. AppServicesCreate (below): every service, in its order.
 *            2. the modules, in this order: SpeechOut -> Video -> Control -> Vision ->
 *               Recognizer -> TurnHandler -> SpeechIn -> StatusBoard -> Ui -> Keys.
 *   RUN      UiRun: the screen loop, until quit.
 *   SHUTDOWN the modules in reverse, the ROS2 context, then AppServicesClose.
 * No dependency check here (owner Q5 a): `run.sh preflight` is its one place.
 * Everything loads at start, nothing during the run (owner 3.3).
 */
#ifndef __HARDEN2_API_APP_H__
#define __HARDEN2_API_APP_H__
#include "runtime.h"
#include "audio.h"
#include "video.h"
#include "recognizer.h"   /* control.h, perception.h */
#include "log.h"
#include "keys.h"

/* ================= the services (app/main.py class Services) =================
 * Built by ONE call (owner D15), in the order of the members. Closed in reverse. */
typedef struct AppServices {
	SessionLog* log;                      /* 1. the session folder; unwritable -> die        */
	Perf*       perf;                     /* 2. perf.jsonl in that folder                    */
	Supervisor* supervisor;               /* 3. keeps every process alive                    */
	Gemma*      gemma;                    /* 4. the client; the server is warmed through it  */
	Process**   processes;                /* 5. gemma, keys; asr (ASR source "ros"); the     */
	uint32_t    nProcesses;               /*    mock (CONTROL=mock); gstreamer (VIDEO=dji)   */
	Process*    gstreamer;                /*    the gstreamer handle, or NULL                */
	DjiApp*     dji;                      /* 6. the phone app (or the mock)                  */
	Sam3*       sam3;                     /* 7. loads SAM3 on its own thread, warms it up    */
} AppServices;
AppServices* AppServicesCreate(const char* source, float importsMs);   /* dies on a failure */
void         AppServicesClose(AppServices* s);

/* ================= the global keys (app/main.py; the Keys object: keys.h) ================= */
/* F4 toggles manual mode and says the result; F1 quits (@quitApp = UiRequestQuit); F2 clears
 * the highlights (@clear = VisionClear with task 0). Any other key: nothing. */
void AppOnGlobalKey(int32_t evdevCode, Control* control, void (*say)(const char*),
	void (*quitApp)(void), void (*clear)(void));
/* The F5 RELEASE marks the start of the ASR and e2e timings (PerfMark "ptt_release"). */
void AppOnKeyRelease(int32_t evdevCode, Perf* perf);

/* ================= one spoken turn (app/turns.py) =================
 * The turn's DATA is ONE struct: log.h's Turn (the request and the response). SessionLog
 * builds it and writes it as one line of trace.jsonl. The object below holds no turn data:
 * it is the HANDLER that runs when a transcript arrives (python class: Turns). */
typedef struct TurnHandler {              /* python: app.turns.Turns                         */
	Recognizer* recognizer;               /* decides and acts                                */
	void      (*say)(const char*);        /* one chat line + the same text spoken            */
	SessionLog* session;                  /* opens and commits the Turn                      */
	Perf*       perf;
} TurnHandler;
TurnHandler* TurnHandlerCreate(Recognizer* r, void (*say)(const char*), SessionLog* log, Perf* perf);
/* What one transcript does, in order (python: Turns.__call__):
 *   1. perf: "asr" (mic only), start "e2e".      2. chat: the user's line.
 *   3. SessionLog begins a Turn.                 4. Recognize(text) -> Routed.
 *   5. show and say the result.                  6. SessionLog commits the Turn. */
void AppOnHeard(TurnHandler* t, const char* text, const char* source);   /* "mic" | "phone" */

/* The app's side of the vision callbacks (python: app.turns.VisionSinks): the ONE place that
 * turns a vision result into chat lines, speech and log records. */
typedef struct AppVisionSinks {
	SessionLog* session;
	void      (*speak)(const char*);      /* speech only                                     */
	void*       kinds;                    /* task -> "count" | "highlight" | "describe"      */
} AppVisionSinks;

/* ================= the screen's shared state (app/state.py class Shared; one instance S) ====
 * Written by the turn handler and the vision callbacks, read by the screen. Every read and
 * write holds `lock`. */
typedef struct { const char* role; const char* text; const char* kind; } ChatLine;
typedef struct ScreenState {
	OsLock*     lock;
	const Box*  hlDets;   uint32_t nDets; /* the boxes drawn now. [rev3: TN2] becomes one    */
	const Mask* hlMasks;                  /* entry per live highlight task                   */
	bool        hlFirstBox;               /* a highlight's first boxes wait to be drawn      */
	const char* target;                   /* the phrase SAM3 got, shown on the HUD           */
	bool        thinking;                 /* show "thinking..." in the chat (see GAPS.md G3) */
	bool        useSam;                   /* the masks switch (the t key)                    */
	ChatLine    chat[60];                 /* the newest 60 chat lines                        */
	uint32_t    chatScroll;               /* rows scrolled up from the newest (0 = follow)   */
} ScreenState;

/* ================= the screen (app/ui.py): the ONLY code that draws =================
 * ONE window (cv2), composed every frame:
 *
 *      +---------------------------------------------------------------+
 *      |  the camera frame, full width                                 |
 *      |  on it: each highlight's boxes and masks; the HUD (fps, the   |
 *      |  video source, the phone-app target "mock 127.0.0.1:8079" or  |
 *      |  "REAL ..."); a MANUAL banner while manual mode is on         |
 *      +----------------------+----------------------------------------+
 *      |  the status pane     |  the chat pane                         |
 *      |  one row per part:   |  the session folder, then the turns:   |
 *      |  green UP, orange    |  what was heard, the kind, the mission |
 *      |  WAITING, red else,  |  steps, the answer; "thinking..." on   |
 *      |  with its detail     |  the live turn; scrolls                |
 *      +----------------------+----------------------------------------+
 *      [rev3: T3C (2)] plus a pane of the active vision jobs: one row per job; a click
 *      focuses a job or deletes it (VisionClear(task)).
 *
 * Window keys (they act only while this window has the focus; values in config):
 *      q or Esc quit | c clear the highlights | t masks on/off | [ ] or the mouse wheel
 *      scroll the chat | x clear the chat.   The kill key is NOT here: it is global (keys.h).
 * One pass of the loop (python: Ui.run):
 *      1. VideoRead. No frame: draw "waiting for video" with both panes, and go on.
 *      2. copy the highlight state out of ScreenState (under its lock).
 *      3. draw the masks, the boxes and the HUD on the frame.
 *      4. compose the frame with the status pane (StatusBoardSnapshot) and the chat pane.
 *      5. show it; read one window key; record one "frame" perf event.
 *      6. if this frame showed a highlight's first boxes: end the "e2e" timing. */
typedef struct Ui {                       /* python: app.ui.Ui                               */
	Perf*        perf;
	Video*       video;                   /* the frames                                      */
	StatusBoard* board;                   /* the status pane's rows                          */
	const char*  sessionDir;              /* shown in the chat pane's header                 */
	bool       (*manualOn)(void);         /* the MANUAL banner; the screen never holds control */
	const char*  srcLabel;                /* HUD: the video source, short                    */
	const char*  djiText;                 /* HUD: "mock host:port" or "REAL host:port"       */
	OsEvent*     quit;                    /* set by UiRequestQuit, from any thread           */
} Ui;
Ui*  UiCreate(Video* video, StatusBoard* board, const char* sessionDir, bool (*manualOn)(void),
	Perf* perf);
void UiRun(Ui* ui, void (*onClear)(void));    /* returns on quit                              */
void UiRequestQuit(Ui* ui);               /* any thread: UiRun returns at its next frame (F1) */
void UiClose(Ui* ui);

#endif /* __HARDEN2_API_APP_H__ */
