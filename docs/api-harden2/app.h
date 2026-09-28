/*
 * app.h -- harden2 API v2.4 (2026-09-26). Module app/: builds the services, gives each module
 * the services it needs, runs the screen, then closes modules and services in reverse order
 * (owner ruling 2026-09-23). Anything that fails while starting dies with the reason.
 *
 *   FIRST:               SysCheckDependencies() (system.h), before any module is imported.
 *   SERVICES, in order:  SessionLog -> Perf (log.h) -> Supervisor (+ the processes the
 *                        settings need: Gemma and the keyboard hook always; the ASR server
 *                        when "ros" is an ASR source; the mock when CONTROL=mock; gstreamer
 *                        when VIDEO=dji) -> Gemma client -> DjiApp -> Sam3 loader
 *   MODULES, in order:   SpeechOut -> Video -> Control -> Vision -> Recognizer -> Turns ->
 *                        SpeechIn -> the StatusBoard (from its sources: every Process,
 *                        DjiApp, Sam3, Video, SpeechIn) -> Ui -> Keys (it needs UiRequestQuit)
 *   SHUTDOWN:            the modules in reverse, the ROS2 context, the services in reverse,
 *                        Perf, then the SessionLog.
 */
#ifndef __HARDEN2_API_APP_H__
#define __HARDEN2_API_APP_H__
#include "system.h"
#include "audio.h"
#include "video.h"
#include "recognizer.h"   /* control.h, perception.h */
#include "log.h"

/* ---- keys (app/keys.py): the keyboard hook's ROS2 topic -> one callback per key PRESS,
 * and one per key RELEASE. Keys knows nothing about the drone. */
typedef void (*KeyFn)(int32_t evdevCode);
typedef struct Keys Keys;
Keys*      KeysCreate(KeyFn onKey, KeyFn onRelease);   /* onRelease may be NULL          */
void       KeysClose(Keys* k);
SupProcess KeysProcess(const char* logDir);        /* always started: the global keys    */
/* Only function keys act, from any window (owner 2026-09-23): F4 toggles manual and says
 * the result, F1 quits (@quitApp: UiRequestQuit), F2 clears the highlight (@clear:
 * VisionClear). Every letter does nothing: letters are typed in other windows. */
void       AppOnGlobalKey(int32_t evdevCode, Control* control, void (*say)(const char*),
                          void (*quitApp)(void), void (*clear)(void));
/* The push-to-talk (F5) RELEASE marks the start of the ASR timing (PerfMark). */
void       AppOnKeyRelease(int32_t evdevCode, Perf* perf);

/* ---- turns (app/turns.py): one transcript -> the log turn -> Recognize() -> show and say
 * the Routed result. VisionSinks: the vision callbacks -> chat, speech and the log. */
void AppOnHeard(const char* text, const char* source);
typedef struct Turns Turns;
Turns* TurnsCreate(Recognizer* r, void (*say)(const char*), SessionLog* log, Perf* perf);

/* ---- the screen (app/ui.py): the ONLY code that draws. Camera full width on top; below it
 * the status pane (orange WAITING, green UP, red otherwise) and the scrolling chat.
 * Drawing helpers: app/draw.py (fonts, wrapping, a box), app/chat_rows.py (chat -> rows),
 * app/chat_pane.py (render_chat), app/status_pane.py (render_status). */
typedef struct Ui Ui;
/* @manualOn: the manual-mode banner; a callback, the screen never holds control. */
/* @perf: one "frame" record per second (fps; read / draw / show mean and worst ms). */
Ui*  UiCreate(Video* video, StatusBoard* board, const char* sessionDir, bool (*manualOn)(void),
	Perf* perf);
void UiRun(Ui* ui, void (*onClear)(void));        /* returns on quit                      */
void UiRequestQuit(Ui* ui);   /* any thread: UiRun returns at its next frame (the F1 key)  */
void UiClose(Ui* ui);

/* ---- the scripted run (app/feed.py): a SEPARATE program, not part of the app. It waits
 * for Gemma, then publishes each sentence of a script on ASR_TOPIC, as if spoken, so every
 * measured run gets the same input. Script lines: a sentence, "wait N", or a "#" comment.
 * It dies unless CONTROL=mock (the sentences become commands). run.sh starts it with
 * SCRIPT=<file> (SCRIPT=default = app/perf_script.txt). */
int FeedMain(const char* scriptPath);

#endif /* __HARDEN2_API_APP_H__ */
