"""audio/ -- speech in and speech out, each ONE interface over a list of backends (owner
ruling 2026-09-23). speech_in.SpeechIn runs config.ASR_SOURCES (asr_ros: the laptop mic
through our ASR server; asr_phone: the phone app's speech). speech_out.SpeechOut drives
config.TTS_OUTPUTS (tts_phone: the phone app's /tts; tts_laptop: offline phonikud)."""
