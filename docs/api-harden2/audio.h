/*
 * audio.h -- harden2 API v2.3 (2026-09-24). Module audio/: speech in and speech out.
 * Owner rulings 2026-09-23: each is ONE interface over a LIST of backends from config;
 * all listed backends run at once (a remote source never takes the ground-control mic
 * away). A new backend is one class plus one line in the registry.
 */
#ifndef __HARDEN2_API_AUDIO_H__
#define __HARDEN2_API_AUDIO_H__
#include "system.h"
#include "dji_app.h"

/* ---- speech in: config.ASR_SOURCES, e.g. {"ros", "phone"} ----
 *   ros   (asr_ros.RosAsr)   the laptop mic, through our ASR server (a supervised process,
 *                            started only when "ros" is listed) -> ROS2 topic ASR_TOPIC.
 *   phone (asr_phone.PhoneAsr) the phone app sends each transcript to the laptop (REST and
 *                            TCP, deduplicated; untrusted input never kills the app).
 * Every source feeds the same callback. An unknown source name dies at start. */
typedef void (*HeardFn)(const char* text, const char* source);   /* "ros" | "phone" */
typedef struct SpeechIn SpeechIn;
SpeechIn* SpeechInCreate(const char** sources, uint32_t n, HeardFn onHeard);
void      SpeechInClose(SpeechIn* in);
/* its sources' rows: "phone speech" (the ros source's health is its server's row) */
uint32_t  SpeechInStatus(SpeechIn* in, StatusRow* rows, uint32_t cap);
SupProcess AsrRosProcess(const char* logDir);    /* the ASR server: a laptop part       */

/* ---- speech out: config.TTS_OUTPUTS, e.g. {"phone"} or {"phone", "laptop"}; {} = silent ----
 *   phone  (tts_phone.PhoneTts)  POST /tts through dji_app; its health IS the "dji app" row.
 *   laptop (tts_laptop.LaptopTts) offline phonikud; a playback error dies at once (9a-1).
 * Latest answer wins: Say() overwrites a one-slot mailbox and cuts what is playing. */
typedef struct SpeechOut SpeechOut;
SpeechOut* SpeechOutCreate(const char** outputs, uint32_t n, DjiApp* dji);
void       SpeechOutSay(SpeechOut* out, const char* text);   /* never blocks            */
void       SpeechOutClose(SpeechOut* out);

#endif /* __HARDEN2_API_AUDIO_H__ */
