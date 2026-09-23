/*
 * draft-harden2-app-api.h -- DRAFT, owner request 2026-09-23. Not built, not ruled.
 *
 * One interface per system of the harden2 app. Every call returns a status; nothing throws.
 * A fatal error calls AppDie() (fatal.py die()). The Python app mirrors these names 1:1:
 * one module per section below, and nothing reaches past a section's functions.
 */
#ifndef __HARDEN2_APP_API_DRAFT_H__
#define __HARDEN2_APP_API_DRAFT_H__
#include <stdint.h>
#include <stdbool.h>

/* ---------------------------------------------------------------- fatal (fatal.py) */
typedef void (*CleanupFn)(void);
void AppOnDie(CleanupFn fn);                  /* run on die, in reverse order, each guarded       */
void AppDie(const char* reason);              /* print reason, run cleanups, exit. Never returns. */

/* ---------------------------------------------------------------- status board (system/status.py) */
typedef enum { STATE_STARTING, STATE_UP, STATE_RECOVERING, STATE_FAILED, STATE_DOWN } SystemState;
typedef struct {
	const char* system;                       /* "gemma", "sam3", "drone link", ...               */
	SystemState state;
	char        detail[128];
} StatusRow;
void     StatusReport(const char* system, SystemState state, const char* detail);
uint32_t StatusSnapshot(StatusRow* rows, uint32_t maxRows);   /* returns the row count        */

/* ---------------------------------------------------------------- supervisor (system/supervisor.py)
 * ONE recovery mechanism for every system: a local process (gemma, asr, gstreamer, mock) AND a
 * remote service (phone TTS, drone link). A service is three callbacks. The supervisor checks it,
 * restarts it up to kSupervisorMaxRestarts times, then reports FAILED and dies -- unless the service
 * is marked mayFail (the drone link: flag red, never die). */
typedef bool (*ServiceStartFn)(void);         /* launch the process / open the connection         */
typedef bool (*ServiceCheckFn)(void);         /* is it answering right now?                       */
typedef void (*ServiceStopFn)(void);
typedef struct {
	const char*    name;
	ServiceStartFn start;
	ServiceCheckFn check;
	ServiceStopFn  stop;
	float          readyTimeoutS;
	bool           mayFail;                   /* true = report FAILED and keep running            */
} ServiceSpec;
enum { kSupervisorMaxRestarts = 3 };
bool SupervisorAdd(const ServiceSpec* spec);  /* start it, wait ready; false = not ready in time  */
void SupervisorReportFault(const char* name, const char* reason);   /* a user says "it failed"   */
void SupervisorStopAll(void);

/* ---------------------------------------------------------------- drone link (control/, renamed from dji_wire)
 * Sends every command from the laptop to the phone app. It owns the ONE transmit switch.
 * Transmit OFF = every motion command returns LINK_BLOCKED. Stop is always sent. */
typedef enum {
	LINK_SENT,                                /* 2xx from the phone                               */
	LINK_BLOCKED,                             /* transmit switch is OFF; nothing left the laptop  */
	LINK_UNREACHABLE,                         /* no answer from the phone                         */
	LINK_REJECTED                             /* the phone answered non-2xx                       */
} LinkStatus;
typedef enum { CMD_TAKEOFF, CMD_LAND, CMD_FLY_MISSION, CMD_HALT, CMD_GIMBAL } CommandKind;
typedef struct {
	CommandKind kind;
	const char* missionJson;                  /* CMD_FLY_MISSION only: the Action array           */
	float       value;                        /* CMD_GIMBAL: pitch in degrees                     */
} Command;
bool        DroneLinkOpen(const char* host, uint16_t port, bool allowReal);  /* real = HUMAN-ONLY */
void        DroneLinkSetTransmit(bool enabled);    /* called from ONE place: the app's M key      */
bool        DroneLinkIsTransmitting(void);
LinkStatus  DroneLinkSend(const Command* cmd);
LinkStatus  DroneLinkStop(void);                   /* never blocked                               */
const char* DroneLinkStatusText(LinkStatus s);     /* the ONE wording for chat and log            */

/* ---------------------------------------------------------------- vision (perception2/)
 * A dispatcher thread sleeps on a condition variable. Each task gets its own thread, at most
 * kVisionMaxTasks alive. Every thread takes the SAM3 lock only for one forward pass. */
enum { kVisionMaxTasks = 8 };
typedef uint32_t VisionTaskId;
typedef enum { VISION_OK, VISION_FULL, VISION_NOT_READY } VisionStatus;
typedef struct { float x0, y0, x1, y1, conf; } Box;
typedef void (*HighlightFn)(VisionTaskId id, const Box* boxes, uint32_t n);  /* n == 0: lost    */
typedef void (*CountFn)(VisionTaskId id, VisionStatus s, uint32_t count);
VisionStatus VisionHighlight(const char* target, HighlightFn onUpdate, VisionTaskId* outId);
VisionStatus VisionCount(const char* target, CountFn onDone, VisionTaskId* outId);
void         VisionClear(VisionTaskId id);         /* 0 = clear all                               */

/* ---------------------------------------------------------------- gemma (gemma/) */
bool GemmaRequest(const char* messagesJson, const char* grammar, uint32_t maxTokens,
	float timeoutS, char* reply, uint32_t replyCap);  /* true = reply filled                      */

/* ---------------------------------------------------------------- speech (audio/) */
typedef void (*HeardFn)(const char* text, const char* source);   /* "mic" or "phone"             */
bool SpeechListen(HeardFn onHeard);               /* ASR from the mic and the phone               */
bool SpeechSay(const char* text);                 /* latest text wins; false = TTS not UP         */

/* ---------------------------------------------------------------- ui (overlay.py + the display loop)
 * The ONLY way to change what is on screen. Nothing else draws. */
typedef enum { CHAT_USER, CHAT_MODEL, CHAT_SYSTEM } ChatRole;
typedef enum { INPUT_NONE, INPUT_KEY, INPUT_WHEEL, INPUT_QUIT } InputKind;
typedef struct { InputKind kind; int32_t key; int32_t wheel; } InputEvent;
void UiSetFrame(const uint8_t* bgr, uint32_t width, uint32_t height);
void UiSetHighlight(VisionTaskId id, const Box* boxes, uint32_t n);
void UiChatAppend(ChatRole role, const char* text);
void UiChatScroll(int32_t lines);
bool UiPollInput(InputEvent* out);                /* false = no event                             */
void UiRender(void);                              /* camera on top; status | chat below           */

/* ---------------------------------------------------------------- session log (session_log.py) */
typedef uint32_t RequestId;
RequestId SessionBeginRequest(const char* heard, const char* source);
bool      SessionEndRequest(RequestId id, const char* resultJson);   /* false = write failed     */

#endif /* __HARDEN2_APP_API_DRAFT_H__ */
