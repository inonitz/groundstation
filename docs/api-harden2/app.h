/*
 * app.h -- harden2 API v2.3 (2026-09-24). Module app/: builds the services, gives each module
 * the services it needs, runs the screen, then closes modules and services in reverse order
 * (owner ruling 2026-09-23). Anything that fails while starting dies with the reason.
 *
 *   SERVICES, in order:  SessionLog -> Supervisor (+ the processes the settings need:
 *                        Gemma and the keyboard hook always; the ASR server when "ros" is an
 *                        ASR source; the mock when CONTROL=mock; gstreamer when VIDEO=dji)
 *                        -> Gemma client -> DjiApp -> Sam3 loader
 *   MODULES, in order:   SpeechOut -> Video -> Control -> Vision -> Recognizer -> Turns ->
 *                        SpeechIn -> Keys -> the StatusBoard (from its sources: every
 *                        Process, DjiApp, Sam3, Video, SpeechIn) -> Ui
 *   SHUTDOWN:            the modules in reverse, the ROS2 context, the services in reverse.
 */
#ifndef __HARDEN2_API_APP_H__
#define __HARDEN2_API_APP_H__
#include "system.h"
#include "audio.h"
#include "video.h"
#include "recognizer.h"   /* control.h, perception.h */
#include "log.h"

/* ---- keys (app/keys.py): the keyboard hook's ROS2 topic -> one callback per key PRESS.
 * Keys knows nothing about the drone. The app's handler acts on the kill key only (F4):
 * ControlToggleManual() and say the result. Letters never act (typed in other windows). */
typedef void (*KeyFn)(int32_t evdevCode);
typedef struct Keys Keys;
Keys*      KeysCreate(KeyFn onKey);
void       KeysClose(Keys* k);
SupProcess KeysProcess(const char* logDir);        /* always started: F4 needs it        */
void       AppOnGlobalKey(int32_t evdevCode, Control* control);

/* ---- turns (app/turns.py): one transcript -> the log turn -> Recognize() -> show and say
 * the Routed result. VisionSinks: the vision callbacks -> chat, speech and the log. */
void AppOnHeard(const char* text, const char* source);

/* ---- the screen (app/ui.py): the ONLY code that draws. Camera full width on top; below it
 * the status pane (orange WAITING, green UP, red otherwise) and the scrolling chat. */
typedef struct Ui Ui;
/* @manualOn: the manual-mode banner; a callback, the screen never holds control. */
Ui*  UiCreate(Video* video, StatusBoard* board, const char* sessionDir, bool (*manualOn)(void));
void UiRun(Ui* ui, void (*onClear)(void));        /* returns on quit                      */
void UiClose(Ui* ui);

#endif /* __HARDEN2_API_APP_H__ */
