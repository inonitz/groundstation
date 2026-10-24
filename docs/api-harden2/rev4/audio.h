/*
 * audio.h -- harden2 API rev4 DRAFT (2026-10-02; the owner's "ideal", HDR2/HDR3). Module
 * audio/.
 *
 * SPEECH IN: every source ends as TEXT on ONE ROS2 topic; the app has ONE subscriber.
 *
 *   the laptop mic --> our ASR server (C++, whisper; a supervised process) --+
 *                                                                           |
 *   the phone mic --> Google's model on the phone --(WiFi)--> PhoneBridge --+
 *                                                                           |
 *                                                 the ROS2 topic "transcript"
 *                                                                           |
 *                           SpeechIn, the ONE subscriber: onHeard(text, source)
 * SPEECH OUT: say(text) -> every voice in the list speaks it.
 */
#ifndef __HARDEN2_API_AUDIO_H__
#define __HARDEN2_API_AUDIO_H__
#include "runtime.h"
#include "dji_app.h"

/* ---------------- speech in ---------------- */
/* the only two sources */
typedef enum {
	SPEECH_MIC,
	SPEECH_PHONE
} SpeechSource;

/* one topic message */
typedef struct {
	SpeechSource source;
	const char*  text;
} Transcript;

typedef void (*HeardFn)(const Transcript* heard);

/*
 * @transcripts:
 *     the ONE topic both sources publish on
 * @onHeard:
 *     the app's handler of a transcript
 */
typedef struct SpeechIn {
	RosSubscription* transcripts;
	HeardFn          onHeard;
} SpeechIn;

SpeechIn*   SpeechInCreate(HeardFn onHeard);
void        SpeechInClose(SpeechIn* in);
ProcessSpec AsrServerProcess(const char* logDir);   /* the mic's ASR server */
/* The phone side. The phone app POSTs {"text": ...} to the laptop (it also sends the
 * same text over TCP; the bridge listens only to the POST, so no duplicate arrives).
 * The bridge publishes each text on the transcript topic as SPEECH_PHONE. That is all
 * it does. */
/*
 * @port:
 *     config.PHONE_ASR_PORT
 * @listener:
 *     the HTTP listener
 * @publisher:
 *     the ROS2 publisher on the transcript topic
 * @status:
 *     the "phone speech" row: UP while it listens
 */
typedef struct PhoneBridge {
	uint16_t  port;
	OsThread* listener;
	void*     publisher;
	Status*   status;
} PhoneBridge;

PhoneBridge* PhoneBridgeCreate(uint16_t port);
void         PhoneBridgeClose(PhoneBridge* b);

/* ---------------- speech out ---------------- */
typedef enum {
	VOICE_PHONE,
	VOICE_LAPTOP
} VoiceKind;

/* VOICE_PHONE: the phone speaks */
/*
 * @dji:
 *     POST /tts {text}: Android's own text-to-speech
 */
typedef struct {
	DjiApp* dji;
} PhoneVoice;

/* VOICE_LAPTOP: the laptop speaks, offline */
/*
 * @phonemizer:
 *     phonikud: Hebrew text -> phonemes
 * @synthesizer:
 *     piper: phonemes -> audio samples
 * @player:
 *     plays the samples on the laptop's speaker
 */
typedef struct {
	void* phonemizer;
	void* synthesizer;
	void* player;
} LaptopVoice;

typedef struct Voice {
	VoiceKind kind;
	union { PhoneVoice phone; LaptopVoice laptop; } as;
} Voice;

void VoiceSpeak(Voice* v, const char* text);   /* returns when the sentence was spoken */
void VoiceStop(Voice* v);   /* cut the sentence that is playing */
/*
 * @voices:
 *     config.TTS_OUTPUTS; 0 = silent
 * @wake:
 *     the worker sleeps on it
 * @running:
 *     ATOMIC: false ends the worker
 * @pending:
 *     ONE waiting sentence: a newer one replaces it
 */
typedef struct SpeechOut {
	Voice*       voices;
	uint32_t     nVoices;
	OsThread*    worker;
	OsCondition* wake;
	bool         running;
	const char*  pending;
} SpeechOut;

SpeechOut* SpeechOutCreate(const VoiceKind* kinds, uint32_t n, DjiApp* dji);
/* Never blocks: store the sentence as `pending`, wake the worker. The worker then, for
 *     each
 * voice: VoiceStop (cut the old sentence), VoiceSpeak (say the new one). */
void SpeechOutSay(SpeechOut* out, const char* text);
void SpeechOutClose(SpeechOut* out);
#endif
