/*
 * audio.h -- harden2 API rev3 DRAFT (2026-10-02; from v2.4). Module audio/: speech in and speech out.
 * Owner rulings 2026-09-23: each is ONE interface over a LIST of backends from config;
 * all listed backends run at once (a remote source never takes the ground-control mic
 * away). A new backend is one class plus one line in the registry.
 */
#ifndef __HARDEN2_API_AUDIO_H__
#define __HARDEN2_API_AUDIO_H__
#include "runtime.h"
#include "dji_app.h"

/* ---- the objects of this module, with their data members ---- */
typedef struct Perf Perf;
typedef void (*HeardFn)(const char* text, const char* source);   /* "ros" | "phone" */
typedef struct RosAsr {                   /* python: audio.asr_ros.RosAsr: the laptop mic    */
	HeardFn          onHeard;
	RosSubscription* sub;                 /* the ASR server's transcript topic               */
} RosAsr;
typedef struct PhoneAsr {                 /* python: audio.asr_phone.PhoneAsr: the phone     */
	HeardFn     onHeard;
	const char* host;                     /* the address the laptop listens on               */
	uint16_t    port;                     /* config.PHONE_ASR_PORT: REST and TCP, one port   */
	float       dedupWindow;              /* the phone sends each transcript twice: seconds  */
	                                      /* within which the same text counts once          */
	const char* lastText;   double lastTime;   /* the last transcript and when it came      */
	void*       loop;                     /* the asyncio loop of the listener thread         */
	void*       server;
	Status*     status;                   /* the "phone speech" row                          */
	OsQueue*    inbox;                    /* transcripts wait here for the deliverer thread  */
	OsThread*   deliverer;                /* calls onHeard, one transcript at a time         */
	OsEvent*    listening;
	OsThread*   thread;                   /* runs the socket server                          */
} PhoneAsr;
typedef struct SpeechIn {                 /* python: audio.speech_in.SpeechIn                */
	void**   sources;                     /* one RosAsr or PhoneAsr per name in ASR_SOURCES  */
	uint32_t nSources;
} SpeechIn;
typedef struct PhoneTts {                 /* python: audio.tts_phone.PhoneTts                */
	DjiApp* dji;                          /* POST /tts through the phone app                 */
} PhoneTts;
typedef struct LaptopTts {                /* python: audio.tts_laptop.LaptopTts              */
	void* g2p;                            /* phonikud: Hebrew text -> phonemes               */
	void* voice;                          /* piper: phonemes -> audio, played on the laptop  */
} LaptopTts;
typedef struct SpeechOut {                /* python: audio.speech_out.SpeechOut              */
	void**       outputs;                 /* one PhoneTts or LaptopTts per name in TTS_OUTPUTS */
	const char** names;   uint32_t nOutputs;
	Perf*        perf;                    /* a "say" record per sentence and output          */
	const char*  pending;                 /* the ONE waiting sentence: the newest wins       */
	OsLock*      lock;
	OsEvent*     wake;                    /* wakes the worker when a sentence arrives        */
	bool         running;
	OsThread*    worker;                  /* speaks; a new sentence cuts the one playing     */
} SpeechOut;

/* ---- speech in: config.ASR_SOURCES, e.g. {"ros", "phone"} ----
 *   ros   (asr_ros.RosAsr)   the laptop mic, through our ASR server (a supervised process,
 *                            started only when "ros" is listed) -> ROS2 topic ASR_TOPIC.
 *   phone (asr_phone.PhoneAsr) the phone app sends each transcript to the laptop (REST and
 *                            TCP, deduplicated; untrusted input never kills the app).
 * Every source feeds the same callback. An unknown source name dies at start. */
SpeechIn* SpeechInCreate(const char** sources, uint32_t n, HeardFn onHeard);
void      SpeechInClose(SpeechIn* in);
/* its sources' rows: "phone speech" (the ros source's health is its server's row) */
uint32_t  SpeechInStatus(SpeechIn* in, StatusRow* rows, uint32_t cap);
SupProcess AsrRosProcess(const char* logDir);    /* the ASR server: a laptop part       */

/* ---- speech out: config.TTS_OUTPUTS, e.g. {"phone"} or {"phone", "laptop"}; {} = silent ----
 *   phone  (tts_phone.PhoneTts)  POST /tts through dji_app; its health IS the "dji app" row.
 *   laptop (tts_laptop.LaptopTts) offline phonikud; a playback error dies at once (9a-1).
 *                            Its packages and model files: the preflight (runtime.h). Its module
 *                            (phonikud, 0.4 s) is imported at start only when selected (D13).
 * Latest answer wins: Say() overwrites a one-slot mailbox and cuts what is playing. */
typedef struct SpeechOut SpeechOut;
typedef struct Perf Perf;
/* @perf: a "say" record per sentence and output */
SpeechOut* SpeechOutCreate(const char** outputs, uint32_t n, DjiApp* dji, Perf* perf);
void       SpeechOutSay(SpeechOut* out, const char* text);   /* never blocks            */
void       SpeechOutClose(SpeechOut* out);

#endif /* __HARDEN2_API_AUDIO_H__ */
